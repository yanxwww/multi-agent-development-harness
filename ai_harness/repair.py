from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .followups import render_repair_schedule_plan
from .orchestrator import dispatch_run


class RepairError(Exception):
    pass


def run_auto_repair(
    target: Path,
    source_run_id: str,
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
    repair_run_id: str | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise RepairError("timeout must be greater than 0")
    source_run_dir = target / ".ai" / "runs" / source_run_id
    source_run_path = source_run_dir / "run.json"
    if not source_run_path.exists():
        raise RepairError(f"source run metadata is missing for {source_run_id}")
    source_run = json.loads(source_run_path.read_text())

    followup = render_repair_schedule_plan(target=target, source_run_id=source_run_id)
    plan_path = source_run_dir / "repair_schedule_plan.json"
    plan = json.loads(plan_path.read_text())
    repair_run_id = repair_run_id or f"{source_run_id}-repair-dispatch"
    summary: dict[str, Any] = {
        "source_run_id": source_run_id,
        "repair_run_id": repair_run_id,
        "repair_schedule_status": followup["status"],
        "status": "not_required",
        "dispatch_status": None,
        "created_at": _now(),
    }
    if not plan.get("run_plan"):
        _write_summary(source_run_dir, summary)
        return summary

    dispatch_summary = dispatch_run(
        target=target,
        issue=str(source_run.get("issue_id", "")),
        plan_path=plan_path,
        run_id=repair_run_id,
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
    summary.update(
        {
            "status": dispatch_summary["status"],
            "dispatch_status": dispatch_summary["status"],
            "dispatch_run": f".ai/runs/{repair_run_id}/dispatch_run.json",
            "children": dispatch_summary["children"],
        }
    )
    _write_summary(source_run_dir, summary)
    return summary


def _write_summary(source_run_dir: Path, summary: dict[str, Any]) -> None:
    (source_run_dir / "auto_repair_run.json").write_text(json.dumps(summary, indent=2) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
