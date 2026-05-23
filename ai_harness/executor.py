from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connectors import ConnectorError, has_connector_command_policy, validate_connector_command_artifact


class ExecutionError(Exception):
    pass


def run_connector_command(
    target: Path,
    run_id: str,
    timeout_seconds: float,
    retries: int = 0,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ExecutionError("timeout must be greater than 0")
    if retries < 0:
        raise ExecutionError("retries must be 0 or greater")

    run_dir = target / ".ai" / "runs" / run_id
    command_path = run_dir / "connector_command.json"
    if not command_path.exists():
        raise ExecutionError(f"connector command is missing for {run_id}")

    command = json.loads(command_path.read_text())
    if has_connector_command_policy(target, run_id):
        try:
            validate_connector_command_artifact(target, run_id, command)
        except ConnectorError as exc:
            raise ExecutionError(str(exc)) from exc
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ExecutionError("connector command argv must be a non-empty string list")
    workspace = command.get("workspace", ".")
    if not isinstance(workspace, str) or not workspace:
        raise ExecutionError("connector command workspace must be a non-empty string")
    cwd = target / workspace
    if not cwd.exists() or not cwd.is_dir():
        raise ExecutionError(f"connector workspace does not exist: {workspace}")

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    events_path = run_dir / "connector_events.jsonl"
    trace_path = run_dir / "trace.jsonl"
    for path in [stdout_path, stderr_path, events_path]:
        path.write_text("")

    attempts: list[dict[str, Any]] = []
    max_attempts = retries + 1
    final_exit_code: int | None = None
    status = "failed"
    started_at = _now()

    for attempt_number in range(1, max_attempts + 1):
        _append_jsonl(
            trace_path,
            {
                "ts": _now(),
                "event": "connector_attempt_started",
                "run_id": run_id,
                "attempt": attempt_number,
            },
        )
        attempt = _run_attempt(argv, timeout_seconds, cwd)
        attempt["attempt"] = attempt_number
        attempts.append(attempt)
        final_exit_code = attempt["exit_code"]

        attempt_stdout_path = run_dir / f"stdout.attempt-{attempt_number}.log"
        attempt_stderr_path = run_dir / f"stderr.attempt-{attempt_number}.log"
        attempt_stdout_path.write_text(attempt["stdout"])
        attempt_stderr_path.write_text(attempt["stderr"])
        with stdout_path.open("a") as stdout_log:
            stdout_log.write(attempt["stdout"])
        with stderr_path.open("a") as stderr_log:
            stderr_log.write(attempt["stderr"])
        _capture_json_events(attempt["stdout"], events_path, attempt_number)

        _append_jsonl(
            trace_path,
            {
                "ts": _now(),
                "event": "connector_attempt_finished",
                "run_id": run_id,
                "attempt": attempt_number,
                "exit_code": attempt["exit_code"],
                "timed_out": attempt["timed_out"],
                "duration_seconds": attempt["duration_seconds"],
            },
        )
        if attempt["exit_code"] == 0 and not attempt["timed_out"]:
            status = "succeeded"
            break

    finished_at = _now()
    execution = {
        "run_id": run_id,
        "status": status,
        "connector": command.get("connector"),
        "profile": command.get("profile"),
        "argv": argv,
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "attempts": attempts,
        "final_exit_code": final_exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
        "events_log": "connector_events.jsonl",
    }
    (run_dir / "connector_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    _append_jsonl(
        trace_path,
        {
            "ts": finished_at,
            "event": "connector_run_finished",
            "run_id": run_id,
            "status": status,
            "final_exit_code": final_exit_code,
            "attempts": len(attempts),
        },
    )
    return execution


def _run_attempt(argv: list[str], timeout_seconds: float, cwd: Path) -> dict[str, Any]:
    start = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            cwd=str(cwd),
        )
        end = datetime.now(timezone.utc)
        return {
            "exit_code": completed.returncode,
            "timed_out": False,
            "duration_seconds": _duration_seconds(start, end),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        end = datetime.now(timezone.utc)
        return {
            "exit_code": None,
            "timed_out": True,
            "duration_seconds": _duration_seconds(start, end),
            "stdout": _decode_timeout_output(exc.stdout),
            "stderr": _decode_timeout_output(exc.stderr),
        }


def _capture_json_events(stdout: str, events_path: Path, attempt_number: int) -> None:
    with events_path.open("a") as events:
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                event.setdefault("attempt", attempt_number)
                events.write(json.dumps(event) + "\n")


def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(event) + "\n")


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _duration_seconds(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds(), 6)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
