from __future__ import annotations

import json
import os
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation import run_automation
from .local_daemon_policy import load_trigger_policy
from .runs import validate_run_id
from .validation import validate_scaffold


class LocalDaemonError(Exception):
    pass


GITHUB_JSON_FIELDS = "number,title,body,labels,comments,updatedAt,url"


def run_github_sync_poll(
    target: Path,
    run_id: str,
    executable: str = "gh",
    execute: bool = False,
    status_sync: bool = False,
    status_timeout_seconds: float = 30.0,
    timeout_seconds: float = 900.0,
    retries: int = 0,
    validation_mode: str = "run",
    create_worktree: bool = True,
    base_ref: str = "HEAD",
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise LocalDaemonError("timeout must be greater than 0")
    validate_run_id(run_id)
    validate_scaffold(target)

    root = _local_daemon_root(target)
    with _poll_lease(root, run_id):
        state = _load_state(root)
        processed = set(state.get("processed_event_ids", []))
        items = _load_github_items(target=target, executable=executable)
        trigger_policy = load_trigger_policy(target)
        candidates = _trigger_events(items, trigger_policy)

        created_events: list[dict[str, Any]] = []
        skipped_events: list[dict[str, Any]] = []
        for event in candidates:
            event_id = event["event_id"]
            event_dir = root / "events" / event_id
            if event_id in processed or event_dir.exists():
                skipped_events.append({"event_id": event_id, "reason": "already processed"})
                processed.add(event_id)
                continue
            event_dir.mkdir(parents=True)
            (event_dir / "event.json").write_text(json.dumps(event, indent=2) + "\n")
            task = _scheduler_task(event)
            task_path = event_dir / "scheduler_task.json"
            task_path.write_text(json.dumps(task, indent=2) + "\n")
            created = {
                "event_id": event_id,
                "source": event["source"],
                "trigger": event["trigger"],
                "action": event["action"],
                "scheduler_task": str(task_path.relative_to(target)),
                "executed": False,
                "status": "planned",
            }
            if execute and event["action"] in {"run", "plan", "repair", "review"}:
                automation_run_id = f"run-local-{_safe_id(event_id)}"
                automation = run_automation(
                    target=target,
                    issue=_issue_for_event(event),
                    plan_path=None,
                    scheduler_task_path=task_path,
                    run_id=automation_run_id,
                    timeout_seconds=timeout_seconds,
                    retries=retries,
                    validation_mode=validation_mode,
                    create_worktree=create_worktree,
                    base_ref=base_ref,
                    prepare_pr_command=True,
                    draft_pr=False,
                    commit_and_push=True,
                    run_pr_commands=True,
                    github_checks=True,
                    checks_watch=True,
                    lifecycle=True,
                    auto_review=True,
                    auto_risk_approval=True,
                    auto_repair=True,
                    run_auto_repair_enabled=True,
                    merge=True,
                    delete_branch=True,
                )
                created.update(
                    {
                        "executed": True,
                        "status": automation["status"],
                        "automation_run_id": automation_run_id,
                        "automation_run": f".ai/runs/{automation_run_id}/automation_run.json",
                    }
                )
            status_result = _sync_event_status(
                target=target,
                event=event,
                created=created,
                enabled=status_sync,
                executable=executable,
                timeout_seconds=status_timeout_seconds,
            )
            if status_result is not None:
                created["status_sync"] = status_result
            _write_event_result(event_dir, created)
            created_events.append(created)
            processed.add(event_id)

        state.update(
            {
                "processed_event_ids": sorted(processed),
                "last_poll_run_id": run_id,
                "last_poll_at": _now(),
            }
        )
        _write_state(root, state)
        summary = {
            "run_id": run_id,
            "mode": "poll",
            "status": "planned" if not execute else _combined_status(created_events),
            "execute": execute,
            "created_event_count": len(created_events),
            "skipped_event_count": len(skipped_events),
            "created_events": created_events,
            "skipped_events": skipped_events,
            "created_at": _now(),
        }
        _write_poll_summary(root, run_id, summary)
        return summary


def run_local_daemon(
    target: Path,
    run_id: str,
    executable: str = "gh",
    once: bool = False,
    interval_seconds: float = 60.0,
    execute: bool = False,
    status_sync: bool = False,
    status_timeout_seconds: float = 30.0,
    timeout_seconds: float = 900.0,
    retries: int = 0,
    validation_mode: str = "run",
    create_worktree: bool = True,
    base_ref: str = "HEAD",
) -> dict[str, Any]:
    if interval_seconds <= 0:
        raise LocalDaemonError("interval must be greater than 0")
    if once:
        summary = run_github_sync_poll(
            target=target,
            run_id=run_id,
            executable=executable,
            execute=execute,
            status_sync=status_sync,
            status_timeout_seconds=status_timeout_seconds,
            timeout_seconds=timeout_seconds,
            retries=retries,
            validation_mode=validation_mode,
            create_worktree=create_worktree,
            base_ref=base_ref,
        )
        summary["mode"] = "once"
        _write_poll_summary(_local_daemon_root(target), run_id, summary)
        return summary

    iteration = 0
    last_summary: dict[str, Any] = {}
    while True:
        iteration += 1
        poll_run_id = f"{run_id}-{iteration}"
        last_summary = run_github_sync_poll(
            target=target,
            run_id=poll_run_id,
            executable=executable,
            execute=execute,
            status_sync=status_sync,
            status_timeout_seconds=status_timeout_seconds,
            timeout_seconds=timeout_seconds,
            retries=retries,
            validation_mode=validation_mode,
            create_worktree=create_worktree,
            base_ref=base_ref,
        )
        time.sleep(interval_seconds)
    return last_summary


def sync_github_status(
    target: Path,
    event_id: str,
    status: str,
    message: str,
    executable: str = "gh",
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise LocalDaemonError("timeout must be greater than 0")
    root = _local_daemon_root(target)
    event_dir = root / "events" / event_id
    event_path = event_dir / "event.json"
    if not event_path.exists():
        raise LocalDaemonError(f"local daemon event is missing: {event_id}")
    event = json.loads(event_path.read_text())
    source = event.get("source", {}) if isinstance(event, dict) else {}
    kind = str(source.get("kind", ""))
    number = str(source.get("number", ""))
    if kind not in {"issue", "pr"} or not number:
        raise LocalDaemonError("event source must be an issue or pr with a number")

    body_path = event_dir / "status_comment.md"
    body_path.write_text(_status_comment_body(event=event, status=status, message=message))
    command = _status_command(
        event_id=event_id,
        source_kind=kind,
        number=number,
        executable=executable,
        body_file=str(body_path),
    )
    (event_dir / "status_sync_command.json").write_text(json.dumps(command, indent=2) + "\n")
    result = _run_attempt(command["argv"], target, timeout_seconds)
    (event_dir / "status_sync_stdout.log").write_text(result["stdout"])
    (event_dir / "status_sync_stderr.log").write_text(result["stderr"])
    summary = {
        "event_id": event_id,
        "status": "succeeded" if result["exit_code"] == 0 and not result["timed_out"] else "failed",
        "source": source,
        "argv": command["argv"],
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "stdout_log": "status_sync_stdout.log",
        "stderr_log": "status_sync_stderr.log",
        "created_at": _now(),
    }
    (event_dir / "status_sync.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _load_github_items(target: Path, executable: str) -> list[dict[str, Any]]:
    issues = _run_gh_json(
        [executable, "issue", "list", "--state", "open", "--json", GITHUB_JSON_FIELDS],
        cwd=target,
    )
    prs = _run_gh_json(
        [executable, "pr", "list", "--state", "open", "--json", GITHUB_JSON_FIELDS],
        cwd=target,
    )
    items: list[dict[str, Any]] = []
    for issue in issues:
        if isinstance(issue, dict):
            items.append({"kind": "issue", **issue})
    for pull_request in prs:
        if isinstance(pull_request, dict):
            items.append({"kind": "pr", **pull_request})
    return items


def _run_gh_json(argv: list[str], cwd: Path) -> list[dict[str, Any]]:
    result = _run_attempt(argv, cwd, timeout_seconds=30.0)
    if result["timed_out"] or result["exit_code"] != 0:
        raise LocalDaemonError(result["stderr"].strip() or f"GitHub command failed: {argv}")
    try:
        value = json.loads(result["stdout"] or "[]")
    except json.JSONDecodeError as exc:
        raise LocalDaemonError(f"GitHub command output is not JSON: {exc}") from exc
    if not isinstance(value, list):
        raise LocalDaemonError("GitHub list command must return a JSON array")
    return value


def _trigger_events(items: list[dict[str, Any]], policy: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    label_actions = policy["label_actions"]
    comment_actions = policy["comment_actions"]
    for item in items:
        kind = str(item.get("kind", "issue"))
        number = item.get("number")
        if number is None:
            continue
        source = {
            "kind": kind,
            "number": int(number),
            "title": str(item.get("title", "")),
            "url": str(item.get("url", "")),
            "updated_at": str(item.get("updatedAt", "")),
        }
        labels = item.get("labels", [])
        if isinstance(labels, list):
            for label in labels:
                label_name = label.get("name") if isinstance(label, dict) else label
                if str(label_name) in label_actions:
                    events.append(_event(source=source, trigger=str(label_name), action=label_actions[str(label_name)]))
        comments = item.get("comments", [])
        if isinstance(comments, list):
            for comment in comments:
                body = comment.get("body", "") if isinstance(comment, dict) else ""
                command = _comment_command(str(body), comment_actions)
                if command:
                    events.append(_event(source=source, trigger=command, action=comment_actions[command]))
    return events


def _event(source: dict[str, Any], trigger: str, action: str) -> dict[str, Any]:
    event_id = f"{source['kind']}-{source['number']}-{_trigger_id(trigger)}"
    return {
        "event_id": event_id,
        "source": source,
        "trigger": trigger,
        "action": action,
        "created_at": _now(),
    }


def _comment_command(body: str, comment_actions: dict[str, str]) -> str:
    first_line = body.strip().splitlines()[0].strip() if body.strip() else ""
    return first_line if first_line in comment_actions else ""


def _scheduler_task(event: dict[str, Any]) -> dict[str, Any]:
    source = event["source"]
    source_name = f"{source['kind']} {source['number']}"
    return {
        "summary": f"Plan local automation for {source_name}: {source.get('title', '')}",
        "issue": _issue_for_event(event),
        "event_id": event["event_id"],
        "trigger": event["trigger"],
        "action": event["action"],
        "source_url": source.get("url", ""),
        "acceptance": [
            "Return a runtime-blind SchedulePlan JSON object.",
            "Dispatch only agent identities from .ai/agent-catalog.yml.",
            "Do not include connector, runtime, model, credential, or shell command fields.",
        ],
    }


def _issue_for_event(event: dict[str, Any]) -> str:
    source = event["source"]
    if source.get("kind") == "pr":
        return f"pr-{source.get('number')}"
    return str(source.get("number", "unknown"))


def _status_comment_body(event: dict[str, Any], status: str, message: str) -> str:
    source = event.get("source", {})
    return "\n".join(
        [
            "## AI Harness Local Daemon",
            "",
            f"- Status: {status}",
            f"- Event ID: {event.get('event_id', '')}",
            f"- Trigger: {event.get('trigger', '')}",
            f"- Source: {source.get('kind', '')} #{source.get('number', '')}",
            "",
            message.strip() or "No additional details.",
            "",
        ]
    )


def _status_command(event_id: str, source_kind: str, number: str, executable: str, body_file: str) -> dict[str, Any]:
    subcommand = "pr" if source_kind == "pr" else "issue"
    argv = [executable, subcommand, "comment", number, "--body-file", body_file]
    return {
        "event_id": event_id,
        "executable": executable,
        "source_kind": source_kind,
        "number": number,
        "body_file": body_file,
        "argv": argv,
        "display": " ".join(argv),
    }


def _local_daemon_root(target: Path) -> Path:
    root = target / ".ai" / "local-daemon"
    for directory in ["events", "leases", "polls"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    return root


def _load_state(root: Path) -> dict[str, Any]:
    path = root / "state.json"
    if not path.exists():
        return {"version": 1, "processed_event_ids": []}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise LocalDaemonError("local daemon state must be an object")
    if not isinstance(value.get("processed_event_ids", []), list):
        raise LocalDaemonError("local daemon processed_event_ids must be a list")
    return value


def _write_state(root: Path, state: dict[str, Any]) -> None:
    (root / "state.json").write_text(json.dumps(state, indent=2) + "\n")


def _write_poll_summary(root: Path, run_id: str, summary: dict[str, Any]) -> None:
    (root / "polls" / f"{run_id}.json").write_text(json.dumps(summary, indent=2) + "\n")


def _write_event_result(event_dir: Path, result: dict[str, Any]) -> None:
    payload = {
        "event_id": result["event_id"],
        "source": result["source"],
        "trigger": result["trigger"],
        "action": result["action"],
        "status": result["status"],
        "executed": result["executed"],
        "scheduler_task": result["scheduler_task"],
        "updated_at": _now(),
    }
    for key in ["automation_run_id", "automation_run", "status_sync"]:
        if key in result:
            payload[key] = result[key]
    (event_dir / "event_result.json").write_text(json.dumps(payload, indent=2) + "\n")


def _sync_event_status(
    target: Path,
    event: dict[str, Any],
    created: dict[str, Any],
    enabled: bool,
    executable: str,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    if not enabled:
        return None
    try:
        return sync_github_status(
            target=target,
            event_id=event["event_id"],
            status=created["status"],
            message=_event_status_message(created),
            executable=executable,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return {
            "event_id": event["event_id"],
            "status": "failed",
            "error": str(exc),
            "created_at": _now(),
        }


def _event_status_message(result: dict[str, Any]) -> str:
    if result.get("executed"):
        return "\n".join(
            [
                f"Local automation completed with status `{result.get('status', 'unknown')}`.",
                f"Automation run: `{result.get('automation_run_id', '')}`.",
                "Runtime logs, traces, and connector outputs remain local.",
            ]
        )
    return "\n".join(
        [
            "Local daemon created a scheduler task for this trigger.",
            f"Scheduler task: `{result.get('scheduler_task', '')}`.",
            "Runtime execution remains local.",
        ]
    )


@contextmanager
def _poll_lease(root: Path, run_id: str):
    lease_path = root / "leases" / "poll.lock"
    payload = {"run_id": run_id, "created_at": _now()}
    try:
        fd = os.open(lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise LocalDaemonError(f"local daemon poll lease is already held: {lease_path}") from exc
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
        yield
    finally:
        try:
            lease_path.unlink()
        except FileNotFoundError:
            pass


def _combined_status(events: list[dict[str, Any]]) -> str:
    if not events:
        return "planned"
    return "succeeded" if all(event.get("status") == "succeeded" for event in events) else "failed"


def _run_attempt(argv: list[str], cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        return {
            "exit_code": result.returncode,
            "timed_out": False,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": time.monotonic() - started,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "timed_out": True,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_seconds": time.monotonic() - started,
        }


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "-" for ch in value).strip("-") or "event"


def _trigger_id(trigger: str) -> str:
    return _safe_id(trigger.strip().lstrip("/").replace(":", "-").replace(" ", "-"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
