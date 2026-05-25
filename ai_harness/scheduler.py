from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import extract_json_artifact_from_run
from .connectors import render_connector_command
from .dispatch import validate_schedule_plan_document
from .executor import run_connector_command
from .runs import create_run


class SchedulerError(Exception):
    pass


def run_scheduler(
    target: Path,
    issue: str,
    task_path: Path,
    run_id: str,
    timeout_seconds: float,
    retries: int = 0,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise SchedulerError("timeout must be greater than 0")

    run = create_run(
        target=target,
        issue=issue,
        agent_id="scheduler-agent",
        task_path=task_path,
        run_id=run_id,
        create_worktree=False,
        mode="read_only",
    )
    workspace = prepare_scheduler_workspace(target=target, run_id=run_id)
    run["worktree"] = workspace
    run["scheduler_sanitized_workspace"] = True
    run_dir = target / ".ai" / "runs" / run_id
    (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    _append_trace(run_dir, {"event": "scheduler_workspace_prepared", "run_id": run_id, "workspace": workspace})
    render_connector_command(
        target=target,
        run_id=run_id,
        output_schema=".ai/schemas/schedule_plan.schema.json",
    )
    execution = run_connector_command(
        target=target,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    if execution["status"] != "succeeded":
        raise SchedulerError(f"scheduler connector is {execution['status']}")

    plan = extract_json_artifact_from_run(
        target=target,
        run_id=run_id,
        required_keys={"run_plan", "blocked", "risk_notes"},
        artifact_name="SchedulePlan",
    )
    validate_schedule_plan_document(plan)

    run_dir = target / ".ai" / "runs" / run_id
    schedule_plan_path = run_dir / "schedule_plan.json"
    schedule_plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    summary = {
        "run_id": run_id,
        "agent_id": run["agent_id"],
        "status": "succeeded",
        "schedule_plan": str(schedule_plan_path.relative_to(target)),
        "connector_status": execution["status"],
        "created_at": _now(),
    }
    (run_dir / "scheduler_run.json").write_text(json.dumps(summary, indent=2) + "\n")
    _append_trace(run_dir, {"event": "scheduler_run_finished", "run_id": run_id, "status": "succeeded"})
    return summary


def prepare_scheduler_workspace(target: Path, run_id: str) -> str:
    workspace = target / ".ai" / "scheduler-workspaces" / run_id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    _copy_file_if_exists(target / "AGENTS.md", workspace / "AGENTS.md")
    _copy_tree_if_exists(target / "docs", workspace / "docs")
    _copy_file_if_exists(target / ".ai" / "agent-catalog.yml", workspace / ".ai" / "agent-catalog.yml")
    for directory in ["agents", "rules", "schemas", "skills"]:
        _copy_tree_if_exists(target / ".ai" / directory, workspace / ".ai" / directory)
    return f".ai/scheduler-workspaces/{run_id}"


def _copy_file_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    ignore = shutil.ignore_patterns("private", "runs", "locks", "scheduler-workspaces", "events", "connectors")
    shutil.copytree(source, destination, ignore=ignore)


def _append_trace(run_dir: Path, event: dict[str, Any]) -> None:
    event["ts"] = _now()
    with (run_dir / "trace.jsonl").open("a") as trace:
        trace.write(json.dumps(event) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
