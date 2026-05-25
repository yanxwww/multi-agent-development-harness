from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connectors import render_connector_command
from .dispatch import dispatch_plan
from .executor import run_connector_command
from .gates import run_pr_gate, run_validation_gate
from .git_publish import (
    render_commit_command,
    render_push_command,
    run_commit_command,
    run_diff_gate,
    run_push_command,
)
from .pull_requests import render_pr_command
from .skill_sync import sync_run_skills


class OrchestratorError(Exception):
    pass


def dispatch_run(
    target: Path,
    issue: str,
    plan_path: Path,
    run_id: str,
    timeout_seconds: float,
    retries: int = 0,
    validation_mode: str = "run",
    create_worktree: bool = True,
    base_ref: str = "HEAD",
    prepare_pr_command: bool = False,
    pr_base: str = "main",
    draft_pr: bool = False,
    commit_and_push: bool = False,
    push_remote: str = "origin",
) -> dict[str, Any]:
    schedule_dir = dispatch_plan(
        target=target,
        issue=issue,
        plan_path=plan_path,
        run_id=run_id,
        create_worktree=create_worktree,
        base_ref=base_ref,
    )
    dispatch_log = _load_dispatch_log(schedule_dir / "dispatch_log.jsonl")
    children: list[dict[str, Any]] = []
    status = "succeeded"
    task_status: dict[str, str] = {}
    pending = list(dispatch_log)

    while pending:
        progressed = False
        for entry in list(pending):
            task_id = entry["task_id"]
            dependencies = entry.get("depends_on", [])
            if any(task_status.get(dependency) in {"failed", "blocked"} for dependency in dependencies):
                child = {
                    "run_id": entry["run_id"],
                    "agent_id": entry["agent_id"],
                    "task_id": task_id,
                    "depends_on": dependencies,
                    "status": "blocked",
                    "error": "dependency did not succeed",
                }
                children.append(child)
                task_status[task_id] = "blocked"
                status = "failed"
                pending.remove(entry)
                progressed = True
                continue
            if any(dependency not in task_status for dependency in dependencies):
                continue

            child = _execute_child(
                target=target,
                entry=entry,
                timeout_seconds=timeout_seconds,
                retries=retries,
                validation_mode=validation_mode,
                prepare_pr_command=prepare_pr_command,
                pr_base=pr_base,
                draft_pr=draft_pr,
                commit_and_push=commit_and_push,
                push_remote=push_remote,
            )
            children.append(child)
            task_status[task_id] = child["status"]
            if child["status"] != "succeeded":
                status = "failed"
            pending.remove(entry)
            progressed = True
        if not progressed:
            for entry in pending:
                child = {
                    "run_id": entry["run_id"],
                    "agent_id": entry["agent_id"],
                    "task_id": entry["task_id"],
                    "depends_on": entry.get("depends_on", []),
                    "status": "blocked",
                    "error": "dependencies could not be resolved",
                }
                children.append(child)
                task_status[entry["task_id"]] = "blocked"
                status = "failed"
            pending.clear()

    summary = {
        "run_id": run_id,
        "status": status,
        "children": children,
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "validation_mode": validation_mode,
        "prepare_pr_command": prepare_pr_command,
        "pr_base": pr_base,
        "draft_pr": draft_pr,
        "commit_and_push": commit_and_push,
        "push_remote": push_remote,
        "created_at": _now(),
    }
    (schedule_dir / "dispatch_run.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _execute_child(
    target: Path,
    entry: dict[str, Any],
    timeout_seconds: float,
    retries: int,
    validation_mode: str,
    prepare_pr_command: bool,
    pr_base: str,
    draft_pr: bool,
    commit_and_push: bool,
    push_remote: str,
) -> dict[str, Any]:
    child_run_id = entry["run_id"]
    child: dict[str, Any] = {
        "run_id": child_run_id,
        "agent_id": entry["agent_id"],
        "task_id": entry["task_id"],
        "depends_on": entry.get("depends_on", []),
    }
    try:
        skill_sync = sync_run_skills(target, child_run_id)
        command_path = render_connector_command(target, child_run_id)
        execution = run_connector_command(target, child_run_id, timeout_seconds=timeout_seconds, retries=retries)
        validation = run_validation_gate(
            target,
            child_run_id,
            timeout_seconds=timeout_seconds,
            mode=validation_mode,
        )
        pr_gate = run_pr_gate(target, child_run_id)
        diff_gate = None
        commit_execution = None
        push_execution = None
        commit_sha = ""
        if commit_and_push and pr_gate["status"] == "passed":
            diff_gate = run_diff_gate(target, child_run_id)
            if diff_gate["status"] != "passed":
                raise OrchestratorError(f"diff gate is {diff_gate['status']}")
            render_commit_command(target, child_run_id)
            commit_execution = run_commit_command(target, child_run_id, timeout_seconds=timeout_seconds)
            if commit_execution["status"] != "succeeded":
                raise OrchestratorError(f"commit command is {commit_execution['status']}")
            commit_sha = commit_execution.get("commit_sha", "")
            render_push_command(target, child_run_id, remote=push_remote)
            push_execution = run_push_command(target, child_run_id, timeout_seconds=timeout_seconds)
            if push_execution["status"] != "succeeded":
                raise OrchestratorError(f"push command is {push_execution['status']}")
        pr_command_path = None
        if prepare_pr_command and pr_gate["status"] == "passed":
            pr_command_path = render_pr_command(
                target=target,
                run_id=child_run_id,
                base=pr_base,
                draft=draft_pr,
            )
        child.update(
            {
                "connector_command": str(command_path.relative_to(target)),
                "skill_sync": str((target / ".ai" / "runs" / child_run_id / "skill_sync.json").relative_to(target)),
                "skill_count": len(skill_sync["skills"]),
                "connector_status": execution["status"],
                "validation_status": validation["status"],
                "pr_gate_status": pr_gate["status"],
                "diff_gate_status": diff_gate["status"] if diff_gate else None,
                "commit_status": commit_execution["status"] if commit_execution else None,
                "commit_sha": commit_sha,
                "push_status": push_execution["status"] if push_execution else None,
                "pr_command": str(pr_command_path.relative_to(target)) if pr_command_path else None,
                "status": _child_status(execution["status"], validation["status"], pr_gate["status"]),
            }
        )
    except Exception as exc:
        child.update({"status": "failed", "error": str(exc)})
    return child


def _load_dispatch_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise OrchestratorError(f"dispatch log is missing: {path}")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _child_status(connector_status: str, validation_status: str, pr_gate_status: str) -> str:
    if connector_status != "succeeded":
        return "failed"
    if validation_status not in {"passed", "skipped"}:
        return "failed"
    if pr_gate_status not in {"passed", "not_required"}:
        return "failed"
    return "succeeded"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
