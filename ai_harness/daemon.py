from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation import run_automation
from .runs import validate_run_id
from .validation import validate_scaffold


class DaemonError(Exception):
    pass


def run_automation_daemon(
    target: Path,
    event_file: Path,
    run_id: str,
    execute: bool = False,
    timeout_seconds: float = 900.0,
    retries: int = 0,
    validation_mode: str = "run",
    create_worktree: bool = True,
    base_ref: str = "HEAD",
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise DaemonError("timeout must be greater than 0")
    validate_run_id(run_id)
    validate_scaffold(target)
    if not event_file.exists():
        raise DaemonError(f"event file does not exist: {event_file}")

    event = json.loads(event_file.read_text())
    event_dir = target / ".ai" / "events" / run_id
    if event_dir.exists():
        raise DaemonError(f"event run already exists: {run_id}")
    event_dir.mkdir(parents=True)
    (event_dir / "event.json").write_text(json.dumps(event, indent=2) + "\n")

    issue = _issue_from_event(event)
    task = _scheduler_task_from_event(event, issue)
    task_path = event_dir / "scheduler_task.json"
    task_path.write_text(json.dumps(task, indent=2) + "\n")

    summary: dict[str, Any] = {
        "run_id": run_id,
        "status": "planned",
        "executed": False,
        "issue": issue["id"],
        "event": issue["event"],
        "scheduler_task": str(task_path.relative_to(target)),
        "created_at": _now(),
    }
    if execute:
        automation = run_automation(
            target=target,
            issue=issue["id"],
            plan_path=None,
            scheduler_task_path=task_path,
            run_id=run_id,
            timeout_seconds=timeout_seconds,
            retries=retries,
            validation_mode=validation_mode,
            create_worktree=create_worktree,
            base_ref=base_ref,
        )
        summary.update(
            {
                "status": automation["status"],
                "executed": True,
                "automation_run": f".ai/runs/{run_id}/automation_run.json",
            }
        )
    (event_dir / "automation_daemon.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _issue_from_event(event: dict[str, Any]) -> dict[str, str]:
    if isinstance(event.get("issue"), dict):
        issue = event["issue"]
        return {
            "id": str(issue.get("number", "unknown")),
            "title": str(issue.get("title", "")),
            "body": str(issue.get("body", "")),
            "event": "issue",
        }
    if isinstance(event.get("pull_request"), dict):
        pull_request = event["pull_request"]
        return {
            "id": f"pr-{pull_request.get('number', 'unknown')}",
            "title": str(pull_request.get("title", "")),
            "body": str(pull_request.get("body", "")),
            "event": "pull_request",
        }
    return {
        "id": "event-unknown",
        "title": str(event.get("action", "GitHub event")),
        "body": json.dumps(event, indent=2),
        "event": "unknown",
    }


def _scheduler_task_from_event(event: dict[str, Any], issue: dict[str, str]) -> dict[str, Any]:
    repository = event.get("repository", {}) if isinstance(event.get("repository"), dict) else {}
    title = issue["title"] or issue["id"]
    body = issue["body"]
    return {
        "summary": f"Plan automation for {issue['event']} {issue['id']}: {title}",
        "issue": issue["id"],
        "event": issue["event"],
        "repository": repository.get("full_name", ""),
        "event_action": event.get("action", ""),
        "source_title": title,
        "source_body": body,
        "acceptance": [
            "Return a runtime-blind SchedulePlan JSON object.",
            "Dispatch only agent identities from .ai/agent-catalog.yml.",
            "Do not include connector, runtime, model, credential, or shell command fields.",
        ],
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
