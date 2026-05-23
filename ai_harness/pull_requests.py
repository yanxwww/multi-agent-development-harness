from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PullRequestError(Exception):
    pass


def render_pr_command(
    target: Path,
    run_id: str,
    base: str = "main",
    draft: bool = False,
    executable: str = "gh",
) -> Path:
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    gate_path = run_dir / "pr_gate.json"
    body_path = run_dir / "pr-body.md"
    if not run_path.exists():
        raise PullRequestError(f"run metadata is missing for {run_id}")
    if not gate_path.exists():
        raise PullRequestError(f"PR gate is missing for {run_id}")

    run = json.loads(run_path.read_text())
    gate = json.loads(gate_path.read_text())
    if run.get("mode") != "writer":
        raise PullRequestError("PR command can only be rendered for writer runs")
    if gate.get("status") != "passed":
        raise PullRequestError(f"PR gate is {gate.get('status', 'missing')}")
    if not body_path.exists():
        raise PullRequestError(f"PR body is missing for {run_id}")
    push_execution = _load_optional_json(run_dir / "push_execution.json")
    if push_execution.get("status") != "succeeded":
        raise PullRequestError(f"push execution is {push_execution.get('status', 'missing')}")

    head = run.get("branch")
    if not isinstance(head, str) or not head:
        raise PullRequestError(f"run branch is missing for {run_id}")

    command = _expected_pr_command(run_id=run_id, run=run, base=base, draft=draft, executable=executable)
    command["created_at"] = _now()
    output_path = run_dir / "pr_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    _append_trace(run_dir, {"event": "pr_command_rendered", "run_id": run_id, "base": base, "head": head})
    return output_path


def run_pr_command(target: Path, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise PullRequestError("timeout must be greater than 0")

    run_dir = target / ".ai" / "runs" / run_id
    command_path = run_dir / "pr_command.json"
    if not command_path.exists():
        raise PullRequestError(f"PR command is missing for {run_id}")

    command = json.loads(command_path.read_text())
    run_path = run_dir / "run.json"
    if run_path.exists():
        run = json.loads(run_path.read_text())
        if run.get("mode") == "writer":
            push_execution = _load_optional_json(run_dir / "push_execution.json")
            if push_execution.get("status") != "succeeded":
                raise PullRequestError(f"push execution is {push_execution.get('status', 'missing')}")
            expected = _expected_pr_command(
                run_id=run_id,
                run=run,
                base=_string_field(command, "base", "main"),
                draft=bool(command.get("draft", False)),
                executable=_string_field(command, "executable", "gh"),
            )
            _validate_command_fields(
                command,
                expected,
                ["run_id", "agent_id", "executable", "base", "head", "title", "body_file", "draft", "argv", "display"],
                "PR command does not match rendered PR policy",
            )
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise PullRequestError("PR command argv must be a non-empty string list")

    stdout_path = run_dir / "pr_stdout.log"
    stderr_path = run_dir / "pr_stderr.log"
    started_at = _now()
    _append_trace(run_dir, {"event": "pr_command_started", "run_id": run_id})
    attempt = _run_attempt(argv, target, timeout_seconds)
    stdout_path.write_text(attempt["stdout"])
    stderr_path.write_text(attempt["stderr"])
    finished_at = _now()
    status = "succeeded" if attempt["exit_code"] == 0 and not attempt["timed_out"] else "failed"
    execution = {
        "run_id": run_id,
        "status": status,
        "argv": argv,
        "timeout_seconds": timeout_seconds,
        "exit_code": attempt["exit_code"],
        "timed_out": attempt["timed_out"],
        "duration_seconds": attempt["duration_seconds"],
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_log": "pr_stdout.log",
        "stderr_log": "pr_stderr.log",
    }
    (run_dir / "pr_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    _append_trace(
        run_dir,
        {
            "event": "pr_command_finished",
            "run_id": run_id,
            "status": status,
            "exit_code": attempt["exit_code"],
            "timed_out": attempt["timed_out"],
        },
    )
    return execution


def _expected_pr_command(
    run_id: str,
    run: dict[str, Any],
    base: str,
    draft: bool,
    executable: str,
) -> dict[str, Any]:
    head = run.get("branch")
    if not isinstance(head, str) or not head:
        raise PullRequestError(f"run branch is missing for {run_id}")
    title = f"[AI:{run.get('agent_id')}] {run.get('task_summary', run_id)}"
    body_file = f".ai/runs/{run_id}/pr-body.md"
    argv = [
        executable,
        "pr",
        "create",
        "--base",
        base,
        "--head",
        head,
        "--title",
        title,
        "--body-file",
        body_file,
    ]
    if draft:
        argv.append("--draft")
    return {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "executable": executable,
        "base": base,
        "head": head,
        "title": title,
        "body_file": body_file,
        "draft": draft,
        "argv": argv,
        "display": shlex.join(argv),
    }


def _validate_command_fields(
    command: dict[str, Any],
    expected: dict[str, Any],
    keys: list[str],
    error: str,
) -> None:
    for key in keys:
        if command.get(key) != expected.get(key):
            raise PullRequestError(f"{error}: {key}")


def _string_field(command: dict[str, Any], key: str, default: str) -> str:
    value = command.get(key, default)
    if not isinstance(value, str) or not value:
        raise PullRequestError(f"PR command {key} must be a non-empty string")
    return value


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _run_attempt(argv: list[str], cwd: Path, timeout_seconds: float) -> dict[str, Any]:
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


def _append_trace(run_dir: Path, event: dict[str, Any]) -> None:
    event["ts"] = _now()
    with (run_dir / "trace.jsonl").open("a") as trace:
        trace.write(json.dumps(event) + "\n")


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
