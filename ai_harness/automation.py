from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .github import render_github_checks_command, run_github_checks_command
from .integration import render_integration_command, render_integration_plan, run_integration_command
from .lifecycle import run_lifecycle
from .orchestrator import dispatch_run
from .pull_requests import run_pr_command


class AutomationError(Exception):
    pass


def run_automation(
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
    run_pr_commands: bool = False,
    github_checks: bool = False,
    gh_executable: str = "gh",
    checks_watch: bool = False,
    checks_interval: int = 10,
    lifecycle: bool = False,
    skill_run_id: str | None = None,
    integration_run_id: str | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise AutomationError("timeout must be greater than 0")

    dispatch_summary = dispatch_run(
        target=target,
        issue=issue,
        plan_path=plan_path,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        retries=retries,
        validation_mode=validation_mode,
        create_worktree=create_worktree,
        base_ref=base_ref,
        prepare_pr_command=prepare_pr_command,
        pr_base=pr_base,
        draft_pr=draft_pr,
        commit_and_push=commit_and_push,
        push_remote=push_remote,
    )

    status = "succeeded" if dispatch_summary["status"] == "succeeded" else "failed"
    child_phases = []
    for child in dispatch_summary["children"]:
        try:
            child_phase = _run_child_publication_phases(
                target=target,
                child=child,
                timeout_seconds=timeout_seconds,
                run_pr_commands=run_pr_commands,
                github_checks=github_checks,
                gh_executable=gh_executable,
                checks_watch=checks_watch,
                checks_interval=checks_interval,
                lifecycle=lifecycle,
                skill_run_id=skill_run_id,
            )
        except Exception as exc:
            child_phase = {
                "run_id": child.get("run_id"),
                "agent_id": child.get("agent_id"),
                "dispatch_status": child.get("status"),
                "status": "failed",
                "error": str(exc),
            }
        if child_phase["status"] == "failed":
            status = "failed"
        child_phases.append(child_phase)

    integration_phase = None
    if integration_run_id and dispatch_summary["status"] == "succeeded":
        try:
            integration_phase = _run_integration_phase(
                target=target,
                issue=issue,
                schedule_run_id=run_id,
                integration_run_id=integration_run_id,
                base_ref=base_ref,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            integration_phase = {
                "run_id": integration_run_id,
                "status": "failed",
                "error": str(exc),
            }
        if integration_phase["status"] != "succeeded":
            status = "failed"
    elif integration_run_id:
        integration_phase = {
            "run_id": integration_run_id,
            "status": "skipped",
            "reason": "dispatch failed",
        }

    summary = {
        "run_id": run_id,
        "status": status,
        "dispatch_status": dispatch_summary["status"],
        "dispatch_run": "dispatch_run.json",
        "children": child_phases,
        "integration": integration_phase,
        "options": {
            "prepare_pr_command": prepare_pr_command,
            "commit_and_push": commit_and_push,
            "run_pr_commands": run_pr_commands,
            "github_checks": github_checks,
            "lifecycle": lifecycle,
            "integration_run_id": integration_run_id,
        },
        "created_at": _now(),
    }
    schedule_dir = target / ".ai" / "runs" / run_id
    (schedule_dir / "automation_run.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _run_child_publication_phases(
    target: Path,
    child: dict[str, Any],
    timeout_seconds: float,
    run_pr_commands: bool,
    github_checks: bool,
    gh_executable: str,
    checks_watch: bool,
    checks_interval: int,
    lifecycle: bool,
    skill_run_id: str | None,
) -> dict[str, Any]:
    run_id = child["run_id"]
    phase: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": child.get("agent_id"),
        "mode": child.get("mode"),
        "requires_pr": child.get("requires_pr", False),
        "dispatch_status": child.get("status"),
        "status": "succeeded" if child.get("status") == "succeeded" else "failed",
    }
    if phase["status"] == "failed":
        return phase
    if child.get("mode") != "writer" or not child.get("requires_pr", False):
        phase["publication_status"] = "skipped"
        return phase

    if run_pr_commands:
        if not child.get("pr_command"):
            phase.update({"status": "failed", "error": "PR command was requested but not prepared"})
            return phase
        pr_execution = run_pr_command(target=target, run_id=run_id, timeout_seconds=timeout_seconds)
        phase["pr_status"] = pr_execution["status"]
        if pr_execution["status"] != "succeeded":
            phase["status"] = "failed"
            return phase

    if github_checks:
        render_github_checks_command(
            target=target,
            run_id=run_id,
            executable=gh_executable,
            watch=checks_watch,
            interval=checks_interval,
        )
        checks_execution = run_github_checks_command(target=target, run_id=run_id, timeout_seconds=timeout_seconds)
        phase["github_checks_status"] = checks_execution["status"]
        phase["ci_status"] = checks_execution.get("ci_status")
        phase["eval_status"] = checks_execution.get("eval_status")
        if checks_execution["status"] != "succeeded":
            phase["status"] = "failed"
            return phase

    if lifecycle:
        lifecycle_summary = run_lifecycle(target=target, run_id=run_id, skill_run_id=skill_run_id)
        phase["lifecycle_status"] = lifecycle_summary["status"]
        if lifecycle_summary["status"] != "merge_ready":
            phase["status"] = "failed"

    return phase


def _run_integration_phase(
    target: Path,
    issue: str,
    schedule_run_id: str,
    integration_run_id: str,
    base_ref: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    render_integration_plan(
        target=target,
        issue=issue,
        schedule_run_id=schedule_run_id,
        run_id=integration_run_id,
        base_ref=base_ref,
    )
    render_integration_command(target=target, run_id=integration_run_id)
    execution = run_integration_command(target=target, run_id=integration_run_id, timeout_seconds=timeout_seconds)
    return {
        "run_id": integration_run_id,
        "status": execution["status"],
        "commit_sha": execution.get("commit_sha", ""),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
