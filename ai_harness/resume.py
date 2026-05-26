from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ResumeCommandError(Exception):
    pass


def render_resume_command(
    target: Path,
    run_id: str,
    executable: str | None = None,
    output_schema: str = ".ai/schemas/agent_result.schema.json",
) -> Path:
    run_dir, run = _load_run(target, run_id)
    decision = _load_resume_decision(run_dir, run_id)
    connector_execution = _load_connector_execution(run_dir, run_id)
    runtime_session = _runtime_session(connector_execution, run_id)
    prompt_path = _write_resume_prompt(target, run_dir, run_id, decision)

    command = _expected_resume_command(
        target=target,
        run_id=run_id,
        run=run,
        decision=decision,
        runtime_session=runtime_session,
        executable=executable,
        output_schema=output_schema,
        prompt_path=prompt_path,
    )
    command["created_at"] = _now()
    output_path = run_dir / "resume_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    _append_trace(
        run_dir,
        {
            "event": "resume_command_rendered",
            "run_id": run_id,
            "runtime_session_kind": command["runtime_session_kind"],
        },
    )
    return output_path


def run_resume_command(target: Path, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ResumeCommandError("timeout must be greater than 0")

    run_dir, run = _load_run(target, run_id)
    command_path = run_dir / "resume_command.json"
    if not command_path.exists():
        raise ResumeCommandError(f"resume command is missing for {run_id}")
    command = json.loads(command_path.read_text())
    decision = _load_resume_decision(run_dir, run_id)
    connector_execution = _load_connector_execution(run_dir, run_id)
    runtime_session = _runtime_session(connector_execution, run_id)
    prompt_path = _resolve_target_relative_path(target, _string_field(command, "prompt_file"))
    _validate_prompt_hash(prompt_path, _string_field(command, "prompt_sha256"))

    expected = _expected_resume_command(
        target=target,
        run_id=run_id,
        run=run,
        decision=decision,
        runtime_session=runtime_session,
        executable=_string_field(command, "executable"),
        output_schema=_string_field(command, "output_schema"),
        prompt_path=prompt_path,
    )
    _validate_command_fields(
        command,
        expected,
        [
            "run_id",
            "agent_id",
            "connector",
            "profile",
            "executable",
            "workspace",
            "output_schema",
            "runtime_session_kind",
            "runtime_session_id",
            "resume_mode",
            "decision_file",
            "prompt_file",
            "prompt_sha256",
            "argv",
            "display",
        ],
        "resume command does not match rendered resume policy",
    )
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ResumeCommandError("resume command argv must be a non-empty string list")
    workspace = _string_field(command, "workspace")
    cwd = target / workspace
    if not cwd.exists() or not cwd.is_dir():
        raise ResumeCommandError(f"resume command workspace does not exist: {workspace}")

    stdout_path = run_dir / "resume_stdout.log"
    stderr_path = run_dir / "resume_stderr.log"
    events_path = run_dir / "resume_events.jsonl"
    events_path.write_text("")
    started_at = _now()
    _append_trace(run_dir, {"event": "resume_command_started", "run_id": run_id})
    attempt = _run_attempt(argv, cwd, timeout_seconds, prompt_path.read_text())
    stdout_path.write_text(attempt["stdout"])
    stderr_path.write_text(attempt["stderr"])
    _capture_json_events(attempt["stdout"], events_path)
    runtime_observation, last_agent_message = _extract_runtime_observations(attempt["stdout"])
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
        "finished_at": _now(),
        "stdout_log": "resume_stdout.log",
        "stderr_log": "resume_stderr.log",
        "events_log": "resume_events.jsonl",
    }
    if runtime_observation:
        execution["runtime_session"] = runtime_observation
    if last_agent_message:
        execution["last_agent_message"] = last_agent_message
    (run_dir / "resume_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    _append_trace(
        run_dir,
        {
            "event": "resume_command_finished",
            "run_id": run_id,
            "status": status,
            "exit_code": attempt["exit_code"],
            "timed_out": attempt["timed_out"],
        },
    )
    return execution


def _expected_resume_command(
    target: Path,
    run_id: str,
    run: dict[str, Any],
    decision: dict[str, Any],
    runtime_session: dict[str, Any],
    executable: str | None,
    output_schema: str,
    prompt_path: Path,
) -> dict[str, Any]:
    connector = str(run.get("connector", ""))
    profile = str(run.get("connector_profile", ""))
    workspace = str(run.get("worktree") or ".")
    session_kind = str(runtime_session.get("kind", ""))
    session_id = str(runtime_session.get("id", ""))
    executable = executable or _default_executable(connector)
    prompt_file = str(prompt_path.relative_to(target))

    if connector == "codex-cli" and session_kind == "codex_thread":
        argv = [executable, "exec", "resume", session_id, "--json", "-"]
    elif connector == "claude-code-cli" and session_kind == "claude_session":
        schema_path = target / output_schema
        argv = [
            executable,
            "--bare",
            "-p",
            "--resume",
            session_id,
            "--append-system-prompt-file",
            "AGENTS.md",
            "--output-format",
            "json",
            "--json-schema",
            schema_path.read_text(),
        ]
    else:
        raise ResumeCommandError(f"unsupported resume connector/session pair: {connector}/{session_kind}")

    return {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "connector": connector,
        "profile": profile,
        "executable": executable,
        "workspace": workspace,
        "output_schema": output_schema,
        "runtime_session_kind": session_kind,
        "runtime_session_id": session_id,
        "resume_mode": runtime_session.get("resume_mode", "cli_resume"),
        "decision_file": f".ai/runs/{run_id}/runtime_state_decision.json",
        "decision_reason": decision.get("reason", ""),
        "prompt_file": prompt_file,
        "prompt_sha256": _sha256(prompt_path),
        "argv": argv,
        "display": shlex.join(argv),
    }


def _load_run(target: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise ResumeCommandError(f"run metadata is missing for {run_id}")
    return run_dir, json.loads(run_path.read_text())


def _load_resume_decision(run_dir: Path, run_id: str) -> dict[str, Any]:
    path = run_dir / "runtime_state_decision.json"
    if not path.exists():
        raise ResumeCommandError(f"runtime state decision is missing for {run_id}")
    decision = json.loads(path.read_text())
    if decision.get("assessor_agent_id") != "scheduler-agent":
        raise ResumeCommandError("runtime state decision must come from scheduler-agent")
    if decision.get("decision") != "resume_runtime_session":
        raise ResumeCommandError(f"runtime state decision is {decision.get('decision', 'missing')}")
    prompt = decision.get("continuation_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ResumeCommandError("runtime state decision must include a continuation_prompt")
    return decision


def _load_connector_execution(run_dir: Path, run_id: str) -> dict[str, Any]:
    path = run_dir / "connector_execution.json"
    if not path.exists():
        raise ResumeCommandError(f"connector execution is missing for {run_id}")
    value = json.loads(path.read_text())
    return value if isinstance(value, dict) else {}


def _runtime_session(connector_execution: dict[str, Any], run_id: str) -> dict[str, Any]:
    runtime_session = connector_execution.get("runtime_session")
    if not isinstance(runtime_session, dict):
        raise ResumeCommandError(f"runtime session is missing for {run_id}")
    if runtime_session.get("resume_mode") != "cli_resume":
        raise ResumeCommandError("runtime session is not resumable through CLI")
    session_id = runtime_session.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ResumeCommandError("runtime session id must be a non-empty string")
    return runtime_session


def _write_resume_prompt(target: Path, run_dir: Path, run_id: str, decision: dict[str, Any]) -> Path:
    prompt = "\n".join(
        [
            "# Resume Runtime Session",
            "",
            f"Run ID: {run_id}",
            f"Decision: {decision.get('decision', '')}",
            f"Reason: {decision.get('reason', '')}",
            "",
            "Continue the prior runtime session from its existing context.",
            "Do not treat next-step advice as completion; finish the assigned work and produce the required structured result.",
            "",
            "## Continuation Prompt",
            "",
            str(decision["continuation_prompt"]).strip(),
            "",
        ]
    )
    prompt_path = run_dir / "resume_prompt.md"
    prompt_path.write_text(prompt)
    return prompt_path


def _default_executable(connector: str) -> str:
    if connector == "codex-cli":
        return "codex"
    if connector == "claude-code-cli":
        return "claude"
    raise ResumeCommandError(f"unsupported resume connector: {connector}")


def _validate_prompt_hash(path: Path, expected: str) -> None:
    if not path.exists() or not path.is_file():
        raise ResumeCommandError(f"resume prompt is missing: {path}")
    if _sha256(path) != expected:
        raise ResumeCommandError("resume prompt file does not match resume command hash")


def _validate_command_fields(command: dict[str, Any], expected: dict[str, Any], keys: list[str], error: str) -> None:
    for key in keys:
        if command.get(key) != expected.get(key):
            raise ResumeCommandError(f"{error}: {key}")


def _string_field(command: dict[str, Any], key: str) -> str:
    value = command.get(key)
    if not isinstance(value, str) or not value:
        raise ResumeCommandError(f"resume command {key} must be a non-empty string")
    return value


def _run_attempt(argv: list[str], cwd: Path, timeout_seconds: float, stdin_text: str) -> dict[str, Any]:
    start = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
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


def _capture_json_events(stdout: str, events_path: Path) -> None:
    with events_path.open("a") as events:
        for event in _json_stdout_events(stdout):
            events.write(json.dumps(event) + "\n")


def _extract_runtime_observations(stdout: str) -> tuple[dict[str, Any] | None, str]:
    runtime_session: dict[str, Any] | None = None
    last_agent_message = ""
    for event in _json_stdout_events(stdout):
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            runtime_session = {
                "kind": "codex_thread",
                "id": event["thread_id"],
                "resume_mode": "cli_resume",
            }
        elif isinstance(event.get("session_id"), str):
            runtime_session = {
                "kind": "claude_session",
                "id": event["session_id"],
                "resume_mode": "cli_resume",
            }
        message = _agent_message_text(event)
        if message:
            last_agent_message = message
    return runtime_session, last_agent_message


def _json_stdout_events(stdout: str) -> list[dict[str, Any]]:
    events = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _agent_message_text(event: dict[str, Any]) -> str:
    item = event.get("item")
    if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
        return item["text"]
    if isinstance(event.get("result"), str):
        return event["result"]
    return ""


def _append_trace(run_dir: Path, event: dict[str, Any]) -> None:
    event["ts"] = _now()
    with (run_dir / "trace.jsonl").open("a") as trace:
        trace.write(json.dumps(event) + "\n")


def _resolve_target_relative_path(target: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ResumeCommandError("resume prompt_file must be relative to target")
    resolved_target = target.resolve()
    resolved_path = (target / path).resolve()
    if resolved_path != resolved_target and resolved_target not in resolved_path.parents:
        raise ResumeCommandError("resume prompt_file must stay inside target")
    return resolved_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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
