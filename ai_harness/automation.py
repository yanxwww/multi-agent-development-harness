from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .followups import render_repair_schedule_plan, run_review_agent, run_risk_approval_agent
from .github import render_github_checks_command, run_github_checks_command
from .integration import render_integration_command, render_integration_plan, run_integration_command
from .lifecycle import run_lifecycle
from .orchestrator import dispatch_run
from .pull_requests import render_merge_command, run_merge_command, run_pr_command
from .repair import run_auto_repair
from .scheduler import run_scheduler


class AutomationError(Exception):
    pass


def run_automation(
    target: Path,
    issue: str,
    plan_path: Path | None,
    run_id: str,
    timeout_seconds: float,
    scheduler_task_path: Path | None = None,
    scheduler_run_id: str | None = None,
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
    auto_review: bool = False,
    auto_risk_approval: bool = False,
    auto_repair: bool = False,
    run_auto_repair_enabled: bool = False,
    merge: bool = False,
    merge_method: str = "squash",
    delete_branch: bool = False,
    skill_run_id: str | None = None,
    integration_run_id: str | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise AutomationError("timeout must be greater than 0")
    if (plan_path is None) == (scheduler_task_path is None):
        raise AutomationError("provide exactly one of plan_path or scheduler_task_path")

    scheduler_summary = None
    if scheduler_task_path is not None:
        scheduler_run_id = scheduler_run_id or f"{run_id}-scheduler"
        scheduler_summary = run_scheduler(
            target=target,
            issue=issue,
            task_path=scheduler_task_path,
            run_id=scheduler_run_id,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )
        plan_path = target / scheduler_summary["schedule_plan"]
    assert plan_path is not None

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
        gh_executable=gh_executable,
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
                auto_review=auto_review,
                auto_risk_approval=auto_risk_approval,
                auto_repair=auto_repair,
                run_auto_repair_enabled=run_auto_repair_enabled,
                create_worktree=create_worktree,
                base_ref=base_ref,
                prepare_pr_command=prepare_pr_command,
                pr_base=pr_base,
                draft_pr=draft_pr,
                commit_and_push=commit_and_push,
                push_remote=push_remote,
                merge=merge,
                merge_method=merge_method,
                delete_branch=delete_branch,
                retries=retries,
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
        "scheduler_run": scheduler_summary,
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
            "auto_review": auto_review,
            "auto_risk_approval": auto_risk_approval,
            "auto_repair": auto_repair,
            "run_auto_repair": run_auto_repair_enabled,
            "merge": merge,
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
    auto_review: bool,
    auto_risk_approval: bool,
    auto_repair: bool,
    run_auto_repair_enabled: bool,
    create_worktree: bool,
    base_ref: str,
    prepare_pr_command: bool,
    pr_base: str,
    draft_pr: bool,
    commit_and_push: bool,
    push_remote: str,
    merge: bool,
    merge_method: str,
    delete_branch: bool,
    retries: int,
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

    if auto_review:
        review = run_review_agent(
            target=target,
            source_run_id=run_id,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )
        phase["review_agent_status"] = review["status"]
        if review["status"] != "succeeded":
            phase["status"] = "failed"
            return phase

    if auto_risk_approval:
        risk = run_risk_approval_agent(
            target=target,
            source_run_id=run_id,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )
        phase["risk_approval_agent_status"] = risk["status"]
        if risk["status"] not in {"succeeded", "not_required"}:
            phase["status"] = "failed"
            return phase

    if lifecycle:
        lifecycle_summary = run_lifecycle(target=target, run_id=run_id, skill_run_id=skill_run_id)
        phase["lifecycle_status"] = lifecycle_summary["status"]
        if lifecycle_summary["status"] != "merge_ready":
            phase["status"] = "failed"
            if auto_repair:
                repair = render_repair_schedule_plan(target=target, source_run_id=run_id)
                phase["repair_schedule_status"] = repair["status"]
                if run_auto_repair_enabled and repair["status"] == "recommended":
                    repair_run = run_auto_repair(
                        target=target,
                        source_run_id=run_id,
                        timeout_seconds=timeout_seconds,
                        retries=retries,
                        validation_mode="skip",
                        create_worktree=create_worktree,
                        base_ref=base_ref,
                        prepare_pr_command=prepare_pr_command,
                        pr_base=pr_base,
                        draft_pr=draft_pr,
                        gh_executable=gh_executable,
                        commit_and_push=commit_and_push,
                        push_remote=push_remote,
                    )
                    phase["auto_repair_run_status"] = repair_run["status"]
                    phase["auto_repair_run_id"] = repair_run["repair_run_id"]
            return phase

    if merge:
        if not lifecycle:
            phase.update({"status": "failed", "error": "merge requires lifecycle gate execution"})
            return phase
        render_merge_command(
            target=target,
            run_id=run_id,
            method=merge_method,
            delete_branch=delete_branch,
            executable=gh_executable,
        )
        merge_execution = run_merge_command(target=target, run_id=run_id, timeout_seconds=timeout_seconds)
        phase["merge_status"] = merge_execution["status"]
        if merge_execution["status"] != "succeeded":
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
