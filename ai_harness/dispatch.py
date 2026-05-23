from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .runs import create_run, normalize_issue_id
from .validation import load_agent_catalog, load_private_bindings, validate_scaffold


class DispatchError(Exception):
    pass


FORBIDDEN_SCHEDULER_KEYS = {"runtime", "runtime_id", "connector", "connector_profile", "model", "api_key"}
EXPECTED_OUTPUTS = {
    "issue_spec",
    "task_graph",
    "branch_pr",
    "review_findings",
    "test_report",
    "skill_update_pr",
    "schedule_plan",
}
RISK_LEVELS = {"low", "medium", "high"}
MODES = {"read_only", "writer"}


def dispatch_plan(
    target: Path,
    issue: str,
    plan_path: Path,
    run_id: str,
    create_worktree: bool = True,
    base_ref: str = "HEAD",
) -> Path:
    validate_scaffold(target)
    if not plan_path.exists():
        raise DispatchError(f"schedule plan does not exist: {plan_path}")

    plan = json.loads(plan_path.read_text())
    _validate_schedule_plan(plan)
    catalog = load_agent_catalog(target).get("agents", {})
    bindings = load_private_bindings(target).get("bindings", {})
    for item in plan["run_plan"]:
        agent_id = item["agent_id"]
        catalog_entry = catalog.get(agent_id)
        if not catalog_entry:
            raise DispatchError(f"schedule plan references unknown agent_id: {agent_id}")
        if agent_id not in bindings:
            raise DispatchError(f"agent has no private connector binding: {agent_id}")
        _validate_mode_policy(item, catalog_entry)

    schedule_dir = target / ".ai" / "runs" / run_id
    if schedule_dir.exists():
        raise DispatchError(f"schedule run already exists: {run_id}")
    (schedule_dir / "tasks").mkdir(parents=True)
    (schedule_dir / "agent_results").mkdir()
    (schedule_dir / "evidence").mkdir()
    (schedule_dir / "schedule_plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    issue_id = normalize_issue_id(issue)
    log_path = schedule_dir / "dispatch_log.jsonl"
    with log_path.open("w") as log:
        for item in plan["run_plan"]:
            agent_id = item["agent_id"]
            binding = bindings.get(agent_id)

            child_run_id = _child_run_id(run_id, item["task_id"], agent_id)
            task_path = schedule_dir / "tasks" / f"{_safe_id(item['task_id'])}-{agent_id}.json"
            task = {
                "task_id": item["task_id"],
                "summary": f"{item['task_id']}: {item['expected_output']} by {agent_id}",
                "issue": issue_id,
                "acceptance": item.get("success_criteria", []),
                "depends_on": item.get("depends_on", []),
                "risk_level": item.get("risk_level"),
            }
            task_path.write_text(json.dumps(task, indent=2) + "\n")
            child_run = create_run(
                target=target,
                issue=issue,
                agent_id=agent_id,
                task_path=task_path,
                run_id=child_run_id,
                base_ref=base_ref,
                create_worktree=create_worktree and item["mode"] == "writer",
                mode=item["mode"],
            )
            log.write(
                json.dumps(
                    {
                        "event": "dispatch_prepared",
                        "schedule_run_id": run_id,
                        "run_id": child_run["run_id"],
                        "task_id": item["task_id"],
                        "agent_id": agent_id,
                        "mode": item["mode"],
                        "connector": binding["connector"],
                        "connector_profile": binding["profile"],
                        "requires_pr": item["requires_pr"],
                        "risk_level": item["risk_level"],
                    }
                )
                + "\n"
            )
    return schedule_dir


def _validate_schedule_plan(plan: Any) -> None:
    if not isinstance(plan, dict):
        raise DispatchError("schedule plan must be an object")
    for key in ["run_plan", "blocked", "risk_notes"]:
        if key not in plan:
            raise DispatchError(f"schedule plan missing required key: {key}")
    if not isinstance(plan["run_plan"], list):
        raise DispatchError("schedule plan run_plan must be a list")
    if not isinstance(plan["blocked"], list):
        raise DispatchError("schedule plan blocked must be a list")
    if not isinstance(plan["risk_notes"], list):
        raise DispatchError("schedule plan risk_notes must be a list")
    for index, item in enumerate(plan["run_plan"]):
        _validate_plan_item(index, item)


def _validate_plan_item(index: int, item: Any) -> None:
    if not isinstance(item, dict):
        raise DispatchError(f"run_plan[{index}] must be an object")
    leaked = sorted(FORBIDDEN_SCHEDULER_KEYS.intersection(item))
    if leaked:
        raise DispatchError(f"run_plan[{index}] exposes dispatcher-only keys: {leaked}")
    required = ["agent_id", "task_id", "mode", "depends_on", "expected_output", "requires_pr", "risk_level"]
    for key in required:
        if key not in item:
            raise DispatchError(f"run_plan[{index}] missing required key: {key}")
    if item["mode"] not in MODES:
        raise DispatchError(f"run_plan[{index}] has invalid mode: {item['mode']}")
    if item["expected_output"] not in EXPECTED_OUTPUTS:
        raise DispatchError(f"run_plan[{index}] has invalid expected_output: {item['expected_output']}")
    if item["risk_level"] not in RISK_LEVELS:
        raise DispatchError(f"run_plan[{index}] has invalid risk_level: {item['risk_level']}")
    if not isinstance(item["depends_on"], list):
        raise DispatchError(f"run_plan[{index}] depends_on must be a list")
    if not isinstance(item["requires_pr"], bool):
        raise DispatchError(f"run_plan[{index}] requires_pr must be a boolean")


def _validate_mode_policy(item: dict[str, Any], catalog_entry: dict[str, Any]) -> None:
    can_write = bool(catalog_entry.get("can_write_repo"))
    if item["mode"] == "writer" and not can_write:
        raise DispatchError(f"agent cannot be dispatched in writer mode: {item['agent_id']}")
    if item["mode"] == "writer" and not item["requires_pr"]:
        raise DispatchError(f"writer dispatch must require a PR: {item['agent_id']} {item['task_id']}")
    if item["mode"] == "read_only" and item["requires_pr"]:
        raise DispatchError(f"read-only dispatch must not require a PR: {item['agent_id']} {item['task_id']}")


def _child_run_id(schedule_run_id: str, task_id: str, agent_id: str) -> str:
    return f"{schedule_run_id}-{_safe_id(task_id)}-{agent_id}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
