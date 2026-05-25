from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .runs import cleanup_run_workspace, create_run, normalize_issue_id, validate_run_id
from .validation import load_agent_catalog, load_private_bindings, validate_scaffold


class DispatchError(Exception):
    pass


FORBIDDEN_SCHEDULER_KEYS = {"runtime", "runtime_id", "connector", "connector_profile", "model", "api_key"}
PLAN_KEYS = {"run_plan", "blocked", "risk_notes"}
RUN_PLAN_ITEM_KEYS = {
    "agent_id",
    "task_id",
    "mode",
    "depends_on",
    "expected_output",
    "requires_pr",
    "risk_level",
    "success_criteria",
}
BLOCKED_ITEM_KEYS = {"task_id", "reason"}
EXPECTED_OUTPUTS = {
    "issue_spec",
    "task_graph",
    "branch_pr",
    "review_findings",
    "test_report",
    "skill_update_pr",
    "integration_pr",
    "schedule_plan",
    "risk_approval",
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
    validate_run_id(run_id)
    if not plan_path.exists():
        raise DispatchError(f"schedule plan does not exist: {plan_path}")

    plan = json.loads(plan_path.read_text())
    validate_schedule_plan_document(plan)
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

    child_run_ids = [_child_run_id(run_id, item["task_id"], item["agent_id"]) for item in plan["run_plan"]]
    if len(set(child_run_ids)) != len(child_run_ids):
        raise DispatchError("schedule plan produces duplicate child run ids")
    for child_run_id in child_run_ids:
        validate_run_id(child_run_id)
    schedule_dir = target / ".ai" / "runs" / run_id
    if schedule_dir.exists():
        raise DispatchError(f"schedule run already exists: {run_id}")
    for child_run_id in child_run_ids:
        child_run_dir = target / ".ai" / "runs" / child_run_id
        if child_run_dir.exists():
            raise DispatchError(f"child run already exists: {child_run_id}")

    issue_id = normalize_issue_id(issue)
    created_child_run_ids: list[str] = []
    try:
        (schedule_dir / "tasks").mkdir(parents=True)
        (schedule_dir / "agent_results").mkdir()
        (schedule_dir / "evidence").mkdir()
        (schedule_dir / "schedule_plan.json").write_text(json.dumps(plan, indent=2) + "\n")

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
                created_child_run_ids.append(child_run_id)
                log.write(
                    json.dumps(
                        {
                            "event": "dispatch_prepared",
                            "schedule_run_id": run_id,
                            "run_id": child_run["run_id"],
                            "task_id": item["task_id"],
                            "agent_id": agent_id,
                            "mode": item["mode"],
                            "depends_on": item.get("depends_on", []),
                            "connector": binding["connector"],
                            "connector_profile": binding["profile"],
                            "requires_pr": item["requires_pr"],
                            "risk_level": item["risk_level"],
                        }
                    )
                    + "\n"
                )
    except Exception:
        for child_run_id in created_child_run_ids:
            child_run_dir = target / ".ai" / "runs" / child_run_id
            if child_run_dir.exists():
                run_path = child_run_dir / "run.json"
                if run_path.exists():
                    cleanup_run_workspace(target, json.loads(run_path.read_text()))
                shutil.rmtree(child_run_dir)
        if schedule_dir.exists():
            shutil.rmtree(schedule_dir)
        raise
    return schedule_dir


def validate_schedule_plan_document(plan: Any) -> None:
    _validate_schedule_plan(plan)
    _validate_dependency_graph(plan["run_plan"])


def _validate_schedule_plan(plan: Any) -> None:
    if not isinstance(plan, dict):
        raise DispatchError("schedule plan must be an object")
    _reject_forbidden_scheduler_keys(plan)
    extra = sorted(set(plan) - PLAN_KEYS)
    if extra:
        raise DispatchError(f"schedule plan has unknown keys: {extra}")
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
    for index, item in enumerate(plan["blocked"]):
        _validate_blocked_item(index, item)
    for index, note in enumerate(plan["risk_notes"]):
        if not isinstance(note, str):
            raise DispatchError(f"risk_notes[{index}] must be a string")


def _validate_plan_item(index: int, item: Any) -> None:
    if not isinstance(item, dict):
        raise DispatchError(f"run_plan[{index}] must be an object")
    leaked = sorted(FORBIDDEN_SCHEDULER_KEYS.intersection(item))
    if leaked:
        raise DispatchError(f"run_plan[{index}] exposes dispatcher-only keys: {leaked}")
    extra = sorted(set(item) - RUN_PLAN_ITEM_KEYS)
    if extra:
        raise DispatchError(f"run_plan[{index}] has unknown keys: {extra}")
    required = ["agent_id", "task_id", "mode", "depends_on", "expected_output", "requires_pr", "risk_level"]
    for key in required:
        if key not in item:
            raise DispatchError(f"run_plan[{index}] missing required key: {key}")
    for key in ["agent_id", "task_id", "mode", "expected_output", "risk_level"]:
        if not isinstance(item[key], str) or not item[key].strip():
            raise DispatchError(f"run_plan[{index}].{key} must be a non-empty string")
    if item["mode"] not in MODES:
        raise DispatchError(f"run_plan[{index}] has invalid mode: {item['mode']}")
    if item["expected_output"] not in EXPECTED_OUTPUTS:
        raise DispatchError(f"run_plan[{index}] has invalid expected_output: {item['expected_output']}")
    if item["risk_level"] not in RISK_LEVELS:
        raise DispatchError(f"run_plan[{index}] has invalid risk_level: {item['risk_level']}")
    if not isinstance(item["depends_on"], list):
        raise DispatchError(f"run_plan[{index}] depends_on must be a list")
    for dependency_index, dependency in enumerate(item["depends_on"]):
        if not isinstance(dependency, str) or not dependency.strip():
            raise DispatchError(f"run_plan[{index}].depends_on[{dependency_index}] must be a non-empty string")
    if not isinstance(item["requires_pr"], bool):
        raise DispatchError(f"run_plan[{index}] requires_pr must be a boolean")
    if "success_criteria" in item and not isinstance(item["success_criteria"], list):
        raise DispatchError(f"run_plan[{index}] success_criteria must be a list")
    for criteria_index, criteria in enumerate(item.get("success_criteria", [])):
        if not isinstance(criteria, str):
            raise DispatchError(f"run_plan[{index}].success_criteria[{criteria_index}] must be a string")


def _validate_blocked_item(index: int, item: Any) -> None:
    if not isinstance(item, dict):
        raise DispatchError(f"blocked[{index}] must be an object")
    extra = sorted(set(item) - BLOCKED_ITEM_KEYS)
    if extra:
        raise DispatchError(f"blocked[{index}] has unknown keys: {extra}")
    for key in ["task_id", "reason"]:
        if key not in item:
            raise DispatchError(f"blocked[{index}] missing required key: {key}")
        if not isinstance(item[key], str):
            raise DispatchError(f"blocked[{index}].{key} must be a string")


def _reject_forbidden_scheduler_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            next_path = f"{path}.{key}"
            if key in FORBIDDEN_SCHEDULER_KEYS:
                raise DispatchError(f"schedule plan exposes dispatcher-only key: {next_path}")
            _reject_forbidden_scheduler_keys(nested, next_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_forbidden_scheduler_keys(nested, f"{path}[{index}]")


def _validate_mode_policy(item: dict[str, Any], catalog_entry: dict[str, Any]) -> None:
    can_write = bool(catalog_entry.get("can_write_repo"))
    if item["mode"] == "writer" and not can_write:
        raise DispatchError(f"agent cannot be dispatched in writer mode: {item['agent_id']}")
    if item["mode"] == "writer" and not item["requires_pr"]:
        raise DispatchError(f"writer dispatch must require a PR: {item['agent_id']} {item['task_id']}")
    if item["mode"] == "read_only" and item["requires_pr"]:
        raise DispatchError(f"read-only dispatch must not require a PR: {item['agent_id']} {item['task_id']}")


def _validate_dependency_graph(items: list[dict[str, Any]]) -> None:
    task_ids: set[str] = set()
    for index, item in enumerate(items):
        task_id = item["task_id"]
        if task_id in task_ids:
            raise DispatchError(f"duplicate task_id in schedule plan: {task_id}")
        task_ids.add(task_id)

    graph: dict[str, list[str]] = {}
    for item in items:
        task_id = item["task_id"]
        dependencies = item.get("depends_on", [])
        unknown = sorted(set(dependencies) - task_ids)
        if unknown:
            raise DispatchError(f"task {task_id} depends on unknown task ids: {unknown}")
        graph[task_id] = list(dependencies)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise DispatchError(f"schedule plan dependency cycle includes task: {task_id}")
        visiting.add(task_id)
        for dependency in graph[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in graph:
        visit(task_id)


def _child_run_id(schedule_run_id: str, task_id: str, agent_id: str) -> str:
    return f"{schedule_run_id}-{_safe_id(task_id)}-{agent_id}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
