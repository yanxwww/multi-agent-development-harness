from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import extract_json_artifact_from_run
from .connectors import render_connector_command
from .executor import run_connector_command
from .runs import create_run


class FollowupError(Exception):
    pass


def run_review_agent(
    target: Path,
    source_run_id: str,
    timeout_seconds: float,
    retries: int = 0,
    review_run_id: str | None = None,
) -> dict[str, Any]:
    source_run_dir = _source_run_dir(target, source_run_id)
    source_run = _load_source_run(source_run_dir, source_run_id)
    review_run_id = review_run_id or f"{source_run_id}-review"
    task_path = _write_followup_task(
        source_run_dir,
        "review_task.json",
        {
            "summary": f"Review writer run {source_run_id} and return structured findings.",
            "source_run_id": source_run_id,
            "source_agent_id": source_run.get("agent_id"),
            "source_branch": source_run.get("branch"),
            "expected_artifact": "review_findings.json",
        },
    )
    execution = _run_readonly_artifact_agent(
        target=target,
        issue=str(source_run.get("issue_id", "")),
        agent_id="pr-reviewer",
        task_path=task_path,
        run_id=review_run_id,
        output_schema=".ai/schemas/review_findings.schema.json",
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    findings = extract_json_artifact_from_run(
        target=target,
        run_id=review_run_id,
        required_keys={"findings"},
        artifact_name="review findings",
    )
    _write_json(source_run_dir / "review_findings.json", findings)
    review_run_dir = target / ".ai" / "runs" / review_run_id
    _write_json(review_run_dir / "review_findings.json", findings)
    summary = {
        "source_run_id": source_run_id,
        "review_run_id": review_run_id,
        "status": execution["status"],
        "artifact": "review_findings.json",
        "created_at": _now(),
    }
    _write_json(source_run_dir / "review_agent_run.json", summary)
    _append_trace(source_run_dir, {"event": "review_agent_run_finished", "run_id": source_run_id, "review_run_id": review_run_id, "status": execution["status"]})
    return summary


def run_risk_approval_agent(
    target: Path,
    source_run_id: str,
    timeout_seconds: float,
    retries: int = 0,
    approval_run_id: str | None = None,
) -> dict[str, Any]:
    source_run_dir = _source_run_dir(target, source_run_id)
    source_run = _load_source_run(source_run_dir, source_run_id)
    risk_level = str(source_run.get("risk_level", "medium"))
    if risk_level != "high":
        summary = {
            "source_run_id": source_run_id,
            "status": "not_required",
            "risk_level": risk_level,
            "created_at": _now(),
        }
        _write_json(source_run_dir / "risk_approval_agent_run.json", summary)
        return summary

    approval_run_id = approval_run_id or f"{source_run_id}-risk-approval"
    task_path = _write_followup_task(
        source_run_dir,
        "risk_approval_task.json",
        {
            "summary": f"Approve or reject high-risk writer run {source_run_id}.",
            "source_run_id": source_run_id,
            "source_agent_id": source_run.get("agent_id"),
            "source_branch": source_run.get("branch"),
            "risk_level": risk_level,
            "expected_artifact": "risk_approval.json",
        },
    )
    execution = _run_readonly_artifact_agent(
        target=target,
        issue=str(source_run.get("issue_id", "")),
        agent_id="risk-approval-agent",
        task_path=task_path,
        run_id=approval_run_id,
        output_schema=".ai/schemas/risk_approval.schema.json",
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    approval = extract_json_artifact_from_run(
        target=target,
        run_id=approval_run_id,
        required_keys={"status", "approver_agent_id", "source_run_id", "risk_level", "rationale"},
        artifact_name="risk approval",
    )
    _write_json(source_run_dir / "risk_approval.json", approval)
    approval_run_dir = target / ".ai" / "runs" / approval_run_id
    _write_json(approval_run_dir / "risk_approval.json", approval)
    summary = {
        "source_run_id": source_run_id,
        "approval_run_id": approval_run_id,
        "status": execution["status"],
        "artifact": "risk_approval.json",
        "created_at": _now(),
    }
    _write_json(source_run_dir / "risk_approval_agent_run.json", summary)
    _append_trace(source_run_dir, {"event": "risk_approval_agent_run_finished", "run_id": source_run_id, "approval_run_id": approval_run_id, "status": execution["status"]})
    return summary


def render_repair_schedule_plan(target: Path, source_run_id: str) -> dict[str, Any]:
    source_run_dir = _source_run_dir(target, source_run_id)
    source_run = _load_source_run(source_run_dir, source_run_id)
    lifecycle = _load_optional_json(source_run_dir / "lifecycle_run.json")
    reasons = _collect_repair_reasons(source_run_dir, lifecycle)
    plan = {
        "run_plan": [],
        "blocked": [],
        "risk_notes": [],
    }
    status = "not_required"
    if reasons:
        status = "recommended"
        plan["run_plan"].append(
            {
                "agent_id": "ci-repair-agent",
                "task_id": "T-repair",
                "mode": "writer",
                "depends_on": [],
                "expected_output": "branch_pr",
                "requires_pr": True,
                "risk_level": "medium",
                "success_criteria": [
                    f"Repair blocked lifecycle for source run {source_run_id}",
                    "Preserve writer ownership rules or record an owner transfer before touching the source branch",
                    "Return validation, CI, review, and risk gates to passing state",
                ],
            }
        )
        plan["risk_notes"].append("Repair runs must use an isolated worktree and auditable writer ownership.")

    summary = {
        "source_run_id": source_run_id,
        "status": status,
        "source_agent_id": source_run.get("agent_id"),
        "reasons": reasons,
        "schedule_plan": "repair_schedule_plan.json",
        "created_at": _now(),
    }
    _write_json(source_run_dir / "repair_schedule_plan.json", plan)
    _write_json(source_run_dir / "repair_followup.json", summary)
    _append_trace(source_run_dir, {"event": "repair_schedule_plan_rendered", "run_id": source_run_id, "status": status})
    return summary


def _run_readonly_artifact_agent(
    target: Path,
    issue: str,
    agent_id: str,
    task_path: Path,
    run_id: str,
    output_schema: str,
    timeout_seconds: float,
    retries: int,
) -> dict[str, Any]:
    create_run(
        target=target,
        issue=issue,
        agent_id=agent_id,
        task_path=task_path,
        run_id=run_id,
        create_worktree=False,
        mode="read_only",
    )
    render_connector_command(target=target, run_id=run_id, output_schema=output_schema)
    execution = run_connector_command(
        target=target,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    if execution["status"] != "succeeded":
        raise FollowupError(f"{agent_id} connector is {execution['status']}")
    return execution


def _collect_repair_reasons(source_run_dir: Path, lifecycle: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for filename, label in [
        ("ci_eval_gate.json", "CI/Eval gate"),
        ("review_gate.json", "review gate"),
        ("risk_approval_gate.json", "risk approval gate"),
        ("merge_gate.json", "merge gate"),
    ]:
        artifact = _load_optional_json(source_run_dir / filename)
        status = artifact.get("status")
        if status in {"blocked", "failed"}:
            reasons.append(f"{label} is {status}")
            for reason in artifact.get("reasons", []):
                if isinstance(reason, str):
                    reasons.append(reason)
    if lifecycle.get("status") in {"blocked", "failed"} and not reasons:
        reasons.append(f"lifecycle is {lifecycle.get('status')}")
    return reasons


def _source_run_dir(target: Path, source_run_id: str) -> Path:
    run_dir = target / ".ai" / "runs" / source_run_id
    if not run_dir.exists():
        raise FollowupError(f"source run is missing: {source_run_id}")
    return run_dir


def _load_source_run(source_run_dir: Path, source_run_id: str) -> dict[str, Any]:
    run_path = source_run_dir / "run.json"
    if not run_path.exists():
        raise FollowupError(f"source run metadata is missing for {source_run_id}")
    return json.loads(run_path.read_text())


def _write_followup_task(run_dir: Path, filename: str, task: dict[str, Any]) -> Path:
    path = run_dir / filename
    _write_json(path, task)
    return path


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _append_trace(run_dir: Path, event: dict[str, Any]) -> None:
    event["ts"] = _now()
    with (run_dir / "trace.jsonl").open("a") as trace:
        trace.write(json.dumps(event) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
