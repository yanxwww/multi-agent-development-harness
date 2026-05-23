from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connectors import render_connector_command
from .dispatch import dispatch_plan
from .executor import run_connector_command
from .gates import run_pr_gate, run_validation_gate


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

    for entry in dispatch_log:
        child_run_id = entry["run_id"]
        child: dict[str, Any] = {
            "run_id": child_run_id,
            "agent_id": entry["agent_id"],
            "task_id": entry["task_id"],
        }
        try:
            command_path = render_connector_command(target, child_run_id)
            execution = run_connector_command(target, child_run_id, timeout_seconds=timeout_seconds, retries=retries)
            validation = run_validation_gate(
                target,
                child_run_id,
                timeout_seconds=timeout_seconds,
                mode=validation_mode,
            )
            pr_gate = run_pr_gate(target, child_run_id)
            child.update(
                {
                    "connector_command": str(command_path.relative_to(target)),
                    "connector_status": execution["status"],
                    "validation_status": validation["status"],
                    "pr_gate_status": pr_gate["status"],
                    "status": _child_status(execution["status"], validation["status"], pr_gate["status"]),
                }
            )
        except Exception as exc:
            child.update({"status": "failed", "error": str(exc)})
        if child["status"] != "succeeded":
            status = "failed"
        children.append(child)

    summary = {
        "run_id": run_id,
        "status": status,
        "children": children,
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "validation_mode": validation_mode,
        "created_at": _now(),
    }
    (schedule_dir / "dispatch_run.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


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

