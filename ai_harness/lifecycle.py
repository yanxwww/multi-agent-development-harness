from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class LifecycleError(Exception):
    pass


RESOLVED_FINDING_STATUSES = {"resolved", "fixed", "rejected-with-reason", "closed"}
RISK_APPROVER_AGENT_ID = "risk-approval-agent"


def run_ci_eval_gate(target: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(target, run_id)
    _load_run(run_dir, run_id)
    ci = _load_optional_json(run_dir / "ci_results.json")
    eval_results = _load_optional_json(run_dir / "eval_results.json")
    reasons: list[str] = []

    _collect_result_reasons("CI", ci, reasons)
    _collect_result_reasons("Eval", eval_results, reasons)

    gate = {
        "run_id": run_id,
        "status": "passed" if not reasons else "blocked",
        "reasons": reasons,
        "ci_status": ci.get("status", "missing"),
        "eval_status": eval_results.get("status", "missing"),
        "created_at": _now(),
    }
    (run_dir / "ci_eval_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "ci_eval_gate_finished", "run_id": run_id, "status": gate["status"]})
    return gate


def run_review_gate(target: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(target, run_id)
    _load_run(run_dir, run_id)
    review = _load_optional_json(run_dir / "review_findings.json")
    findings = review.get("findings") if isinstance(review, dict) else None
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        raise LifecycleError("review findings must be a list")

    unresolved_blocking: list[str] = []
    unresolved_major: list[str] = []
    open_nonblocking: list[str] = []
    normalized: list[dict[str, Any]] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise LifecycleError(f"review finding at index {index} must be an object")
        finding_id = str(finding.get("id") or f"finding-{index + 1}")
        severity = str(finding.get("severity", "note"))
        status = str(finding.get("status", "open"))
        unresolved = status not in RESOLVED_FINDING_STATUSES
        normalized.append({**finding, "id": finding_id, "severity": severity, "status": status})
        if not unresolved:
            continue
        if severity == "blocking":
            unresolved_blocking.append(finding_id)
        elif severity == "major":
            unresolved_major.append(finding_id)
        else:
            open_nonblocking.append(finding_id)

    reasons = []
    if unresolved_blocking:
        reasons.append(f"unresolved blocking findings: {unresolved_blocking}")
    if unresolved_major:
        reasons.append(f"unresolved major findings: {unresolved_major}")
    gate = {
        "run_id": run_id,
        "status": "passed" if not reasons else "blocked",
        "reasons": reasons,
        "unresolved_blocking_findings": unresolved_blocking,
        "unresolved_major_findings": unresolved_major,
        "open_nonblocking_findings": open_nonblocking,
        "findings": normalized,
        "created_at": _now(),
    }
    (run_dir / "review_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "review_gate_finished", "run_id": run_id, "status": gate["status"]})
    return gate


def run_risk_approval_gate(target: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(target, run_id)
    run = _load_writer_run(run_dir, run_id)
    risk_level = str(run.get("risk_level", "medium"))
    approval = _load_optional_json(run_dir / "risk_approval.json")
    reasons: list[str] = []
    approval_status = "missing"
    approver_agent_id = None

    if risk_level != "high":
        gate = {
            "run_id": run_id,
            "status": "not_required",
            "reasons": [],
            "risk_level": risk_level,
            "approval_status": "not_required",
            "approver_agent_id": None,
            "created_at": _now(),
        }
        (run_dir / "risk_approval_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
        _append_trace(run_dir, {"event": "risk_approval_gate_finished", "run_id": run_id, "status": gate["status"]})
        return gate

    if not approval:
        reasons.append("risk approval is missing")
    elif not isinstance(approval, dict):
        reasons.append("risk approval must be an object")
    else:
        approval_status = str(approval.get("status", "missing"))
        approver_agent_id = approval.get("approver_agent_id")
        if approval_status != "approved":
            reasons.append(f"risk approval status is {approval_status}")
        if approver_agent_id != RISK_APPROVER_AGENT_ID:
            reasons.append(f"risk approval approver must be {RISK_APPROVER_AGENT_ID}")
        if approval.get("source_run_id") != run_id:
            reasons.append("risk approval source_run_id does not match run")
        approval_risk_level = str(approval.get("risk_level", "missing"))
        if approval_risk_level != risk_level:
            reasons.append(f"risk approval risk_level is {approval_risk_level}")
        rationale = approval.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            reasons.append("risk approval rationale is missing")

    gate = {
        "run_id": run_id,
        "status": "passed" if not reasons else "blocked",
        "reasons": reasons,
        "risk_level": risk_level,
        "approval_status": approval_status,
        "approver_agent_id": approver_agent_id,
        "created_at": _now(),
    }
    (run_dir / "risk_approval_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "risk_approval_gate_finished", "run_id": run_id, "status": gate["status"]})
    return gate


def acquire_writer_lock(target: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(target, run_id)
    run = _load_writer_run(run_dir, run_id)
    branch = _run_branch(run, run_id)
    lock_path = _branch_lock_path(target, branch)
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        if lock.get("owner_run_id") != run_id:
            raise LifecycleError(f"branch is locked by {lock.get('owner_run_id', 'unknown')}")
    else:
        lock = {
            "branch": branch,
            "owner_run_id": run_id,
            "owner_agent_id": run.get("agent_id"),
            "history": [
                {
                    "event": "acquired",
                    "owner_run_id": run_id,
                    "owner_agent_id": run.get("agent_id"),
                    "reason": "initial writer owner",
                    "ts": _now(),
                }
            ],
            "created_at": _now(),
        }
    lock["updated_at"] = _now()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    _write_run_lock(run_dir, lock)
    _append_trace(run_dir, {"event": "writer_lock_acquired", "run_id": run_id, "branch": branch})
    return lock


def transfer_writer_lock(target: Path, from_run_id: str, to_run_id: str, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise LifecycleError("writer transfer reason is required")
    from_run_dir = _run_dir(target, from_run_id)
    to_run_dir = _run_dir(target, to_run_id)
    from_run = _load_writer_run(from_run_dir, from_run_id)
    to_run = _load_writer_run(to_run_dir, to_run_id)
    from_branch = _run_branch(from_run, from_run_id)
    to_branch = _run_branch(to_run, to_run_id)
    if from_branch != to_branch:
        raise LifecycleError("writer transfer requires both runs to target the same branch")

    lock_path = _branch_lock_path(target, from_branch)
    if not lock_path.exists():
        raise LifecycleError("writer lock is missing")
    lock = json.loads(lock_path.read_text())
    if lock.get("owner_run_id") != from_run_id:
        raise LifecycleError(f"writer lock is owned by {lock.get('owner_run_id', 'unknown')}")

    lock["owner_run_id"] = to_run_id
    lock["owner_agent_id"] = to_run.get("agent_id")
    lock.setdefault("history", []).append(
        {
            "event": "transferred",
            "from_run_id": from_run_id,
            "to_run_id": to_run_id,
            "owner_agent_id": to_run.get("agent_id"),
            "reason": reason,
            "ts": _now(),
        }
    )
    lock["updated_at"] = _now()
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    _write_run_lock(to_run_dir, lock)
    transfer = {
        "from_run_id": from_run_id,
        "to_run_id": to_run_id,
        "branch": from_branch,
        "reason": reason,
        "created_at": _now(),
    }
    (to_run_dir / "writer_transfer.json").write_text(json.dumps(transfer, indent=2) + "\n")
    _append_trace(from_run_dir, {"event": "writer_lock_transferred_from", "run_id": from_run_id, "to_run_id": to_run_id})
    _append_trace(to_run_dir, {"event": "writer_lock_transferred_to", "run_id": to_run_id, "from_run_id": from_run_id})
    return lock


def run_merge_gate(target: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(target, run_id)
    run = _load_writer_run(run_dir, run_id)
    branch = _run_branch(run, run_id)
    reasons: list[str] = []

    _require_artifact_status(run_dir, "pr_gate.json", "PR gate", {"passed"}, reasons)
    _require_artifact_status(run_dir, "push_execution.json", "push execution", {"succeeded"}, reasons)
    _require_artifact_status(run_dir, "ci_eval_gate.json", "CI/Eval gate", {"passed"}, reasons)
    _require_artifact_status(run_dir, "review_gate.json", "review gate", {"passed"}, reasons)

    lock = _load_optional_json(_branch_lock_path(target, branch))
    if not lock:
        reasons.append("writer lock is missing")
    elif lock.get("owner_run_id") != run_id:
        reasons.append(f"writer lock is owned by {lock.get('owner_run_id', 'unknown')}")

    risk_level = str(run.get("risk_level", "medium"))
    if risk_level == "high":
        _require_artifact_status(run_dir, "risk_approval_gate.json", "risk approval gate", {"passed"}, reasons)

    gate = {
        "run_id": run_id,
        "status": "passed" if not reasons else "blocked",
        "merge_ready": not reasons,
        "reasons": reasons,
        "branch": branch,
        "owner_run_id": lock.get("owner_run_id") if lock else None,
        "risk_level": risk_level,
        "risk_approval_required": risk_level == "high",
        "created_at": _now(),
    }
    (run_dir / "merge_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "merge_gate_finished", "run_id": run_id, "status": gate["status"]})
    return gate


def run_lifecycle(target: Path, run_id: str, skill_run_id: str | None = None) -> dict[str, Any]:
    run_dir = _run_dir(target, run_id)
    _load_writer_run(run_dir, run_id)
    skill_run_id = skill_run_id or f"{run_id}-skill-evolution"
    stages: list[dict[str, Any]] = []

    lock = _run_lifecycle_stage(
        stages,
        name="writer_lock",
        artifact="writer_lock.json",
        action=lambda: acquire_writer_lock(target, run_id),
        status_from_result=lambda _: "passed",
    )
    ci_eval = _run_lifecycle_stage(
        stages,
        name="ci_eval_gate",
        artifact="ci_eval_gate.json",
        action=lambda: run_ci_eval_gate(target, run_id),
        status_from_result=lambda result: str(result.get("status", "missing")),
    )
    review = _run_lifecycle_stage(
        stages,
        name="review_gate",
        artifact="review_gate.json",
        action=lambda: run_review_gate(target, run_id),
        status_from_result=lambda result: str(result.get("status", "missing")),
    )
    risk = _run_lifecycle_stage(
        stages,
        name="risk_approval_gate",
        artifact="risk_approval_gate.json",
        action=lambda: run_risk_approval_gate(target, run_id),
        status_from_result=lambda result: str(result.get("status", "missing")),
    )
    merge = _run_lifecycle_stage(
        stages,
        name="merge_gate",
        artifact="merge_gate.json",
        action=lambda: run_merge_gate(target, run_id),
        status_from_result=lambda result: str(result.get("status", "missing")),
    )
    skill = _run_lifecycle_stage(
        stages,
        name="skill_evolution_plan",
        artifact="skill_evolution_plan.json",
        action=lambda: render_skill_evolution_plan(target, source_run_id=run_id, run_id=skill_run_id),
        status_from_result=lambda result: str(result.get("status", "missing")),
    )

    merge_ready = merge.get("status") == "passed"
    failed = any(stage["status"] == "failed" for stage in stages)
    summary = {
        "run_id": run_id,
        "status": "merge_ready" if merge_ready else "failed" if failed else "blocked",
        "merge_ready": merge_ready,
        "stages": stages,
        "writer_lock_status": lock.get("status"),
        "ci_eval_status": ci_eval.get("status"),
        "review_status": review.get("status"),
        "risk_approval_status": risk.get("status"),
        "merge_gate_status": merge.get("status"),
        "skill_evolution_status": skill.get("status"),
        "skill_run_id": skill_run_id,
        "created_at": _now(),
    }
    (run_dir / "lifecycle_run.json").write_text(json.dumps(summary, indent=2) + "\n")
    _append_trace(run_dir, {"event": "lifecycle_run_finished", "run_id": run_id, "status": summary["status"]})
    return summary


def render_skill_evolution_plan(target: Path, source_run_id: str, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir(target, source_run_id)
    _load_run(run_dir, source_run_id)
    review = _load_optional_json(run_dir / "review_findings.json")
    findings = review.get("findings", []) if isinstance(review, dict) else []
    if not isinstance(findings, list):
        raise LifecycleError("review findings must be a list")

    counter = Counter(
        str(finding.get("pattern"))
        for finding in findings
        if isinstance(finding, dict) and finding.get("pattern")
    )
    patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ]
    status = "recommended" if patterns else "not_recommended"
    plan = {
        "source_run_id": source_run_id,
        "run_id": run_id,
        "status": status,
        "patterns": patterns,
        "created_at": _now(),
    }
    schedule_plan = {
        "run_plan": [],
        "blocked": [],
        "risk_notes": [],
    }
    if patterns:
        schedule_plan["run_plan"].append(
            {
                "agent_id": "skill-curator",
                "task_id": "T-skill-evolution",
                "mode": "writer",
                "depends_on": [],
                "expected_output": "skill_update_pr",
                "requires_pr": True,
                "risk_level": "medium",
                "success_criteria": [
                    f"Create skill/eval/rule update for repeated pattern: {patterns[0]['pattern']}",
                    "Include before trace, after eval, rollback, and permission impact notes",
                ],
            }
        )
        schedule_plan["risk_notes"].append("Skill evolution changes must open a dedicated skill update PR.")

    (run_dir / "skill_evolution_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (run_dir / "skill_evolution_schedule_plan.json").write_text(json.dumps(schedule_plan, indent=2) + "\n")
    _append_trace(run_dir, {"event": "skill_evolution_plan_rendered", "run_id": source_run_id, "status": status})
    return plan


def _run_lifecycle_stage(
    stages: list[dict[str, Any]],
    name: str,
    artifact: str,
    action: Callable[[], dict[str, Any]],
    status_from_result: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    stage: dict[str, Any] = {"name": name, "artifact": artifact}
    try:
        result = action()
        stage["status"] = status_from_result(result)
        if isinstance(result, dict) and result.get("reasons"):
            stage["reasons"] = result["reasons"]
    except LifecycleError as exc:
        result = {"status": "blocked", "error": str(exc)}
        stage["status"] = "blocked"
        stage["error"] = str(exc)
    except Exception as exc:
        result = {"status": "failed", "error": str(exc)}
        stage["status"] = "failed"
        stage["error"] = str(exc)
    stages.append(stage)
    return result


def _collect_result_reasons(name: str, artifact: dict[str, Any], reasons: list[str]) -> None:
    if not artifact:
        reasons.append(f"{name} results are missing")
        return
    status = artifact.get("status", "missing")
    if status != "passed":
        reasons.append(f"{name} results status is {status}")
    checks = artifact.get("checks", [])
    if not isinstance(checks, list):
        reasons.append(f"{name} checks must be a list")
        return
    for check in checks:
        if not isinstance(check, dict):
            reasons.append(f"{name} check must be an object")
            continue
        check_status = check.get("status", "missing")
        if check_status not in {"passed", "skipped"}:
            reasons.append(f"{name} check {check.get('name', 'unnamed')} is {check_status}")


def _require_artifact_status(
    run_dir: Path,
    filename: str,
    label: str,
    allowed: set[str],
    reasons: list[str],
) -> None:
    artifact = _load_optional_json(run_dir / filename)
    if not artifact:
        reasons.append(f"{label} is missing")
        return
    status = artifact.get("status", "missing")
    if status not in allowed:
        reasons.append(f"{label} is {status}")


def _run_dir(target: Path, run_id: str) -> Path:
    return target / ".ai" / "runs" / run_id


def _load_run(run_dir: Path, run_id: str) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise LifecycleError(f"run metadata is missing for {run_id}")
    return json.loads(run_path.read_text())


def _load_writer_run(run_dir: Path, run_id: str) -> dict[str, Any]:
    run = _load_run(run_dir, run_id)
    if run.get("mode") != "writer":
        raise LifecycleError("writer lifecycle operation requires a writer run")
    return run


def _run_branch(run: dict[str, Any], run_id: str) -> str:
    branch = run.get("branch")
    if not isinstance(branch, str) or not branch:
        raise LifecycleError(f"run branch is missing for {run_id}")
    return branch


def _branch_lock_path(target: Path, branch: str) -> Path:
    return target / ".ai" / "locks" / "branches" / (_safe_branch_id(branch) + ".json")


def _safe_branch_id(branch: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", branch).strip("_") or "branch"


def _write_run_lock(run_dir: Path, lock: dict[str, Any]) -> None:
    (run_dir / "writer_lock.json").write_text(json.dumps(lock, indent=2) + "\n")


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
