from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GitPublishError(Exception):
    pass


def run_diff_gate(target: Path, run_id: str) -> dict[str, Any]:
    run_dir, run, cwd = _load_writer_workspace(target, run_id)
    status_result = _run_git(["git", "status", "--porcelain=v1"], cwd)
    if status_result["exit_code"] != 0:
        raise GitPublishError(status_result["stderr"].strip() or "git status failed")

    status_lines = [line for line in status_result["stdout"].splitlines() if line.strip()]
    changed_files = [_porcelain_path(line) for line in status_lines]
    diff_patch = _worktree_diff_patch(cwd, status_lines)
    (run_dir / "diff.patch").write_text(diff_patch)

    gate = {
        "run_id": run_id,
        "status": "passed" if changed_files else "clean",
        "worktree": run.get("worktree"),
        "changed_files": changed_files,
        "status_porcelain": status_lines,
        "diff_patch": "diff.patch",
        "created_at": _now(),
    }
    (run_dir / "diff_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "diff_gate_finished", "run_id": run_id, "status": gate["status"]})
    return gate


def render_commit_command(
    target: Path,
    run_id: str,
    message: str | None = None,
    user_name: str = "AI Harness",
    user_email: str = "ai-harness@example.invalid",
) -> Path:
    run_dir, run, _cwd = _load_writer_workspace(target, run_id)
    gate_path = run_dir / "diff_gate.json"
    if not gate_path.exists():
        raise GitPublishError(f"diff gate is missing for {run_id}")
    gate = json.loads(gate_path.read_text())
    if gate.get("status") != "passed":
        raise GitPublishError(f"diff gate is {gate.get('status', 'missing')}")

    message = message or f"[AI:{run.get('agent_id')}] {run.get('task_summary', run_id)}"
    command = _expected_commit_command(
        run_id=run_id,
        run=run,
        message=message,
        user_name=user_name,
        user_email=user_email,
    )
    command["created_at"] = _now()
    output_path = run_dir / "commit_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    _append_trace(run_dir, {"event": "commit_command_rendered", "run_id": run_id})
    return output_path


def run_commit_command(target: Path, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise GitPublishError("timeout must be greater than 0")
    run_dir, run, cwd = _load_writer_workspace(target, run_id)
    command_path = run_dir / "commit_command.json"
    if not command_path.exists():
        raise GitPublishError(f"commit command is missing for {run_id}")
    command = json.loads(command_path.read_text())
    message = command.get("message") or f"[AI:{run.get('agent_id')}] {run.get('task_summary', run_id)}"
    expected = _expected_commit_command(run_id=run_id, run=run, message=message)
    _validate_command_fields(
        command,
        expected,
        ["run_id", "agent_id", "worktree", "message", "steps"],
        "commit command does not match rendered git policy",
    )
    steps = command.get("steps")
    if not isinstance(steps, list) or not steps:
        raise GitPublishError("commit command steps must be a non-empty list")

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    results: list[dict[str, Any]] = []
    status = "succeeded"
    started_at = _now()
    _append_trace(run_dir, {"event": "commit_command_started", "run_id": run_id})

    for step in steps:
        argv = step.get("argv") if isinstance(step, dict) else None
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise GitPublishError("commit step argv must be a non-empty string list")
        result = _run_attempt(argv, cwd, timeout_seconds)
        result["name"] = step.get("name", "step")
        results.append(result)
        stdout_parts.append(result["stdout"])
        stderr_parts.append(result["stderr"])
        if result["exit_code"] != 0 or result["timed_out"]:
            status = "failed"
            break

    (run_dir / "commit_stdout.log").write_text("".join(stdout_parts))
    (run_dir / "commit_stderr.log").write_text("".join(stderr_parts))
    commit_sha = _current_commit(cwd) if status == "succeeded" else ""
    post_gate = _post_commit_gate(run_dir, run_id, cwd)
    finished_at = _now()
    execution = {
        "run_id": run_id,
        "status": status if post_gate["status"] == "clean" else "failed",
        "steps": results,
        "commit_sha": commit_sha,
        "post_commit_diff_gate": "post_commit_diff_gate.json",
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_log": "commit_stdout.log",
        "stderr_log": "commit_stderr.log",
    }
    (run_dir / "commit_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    _append_trace(
        run_dir,
        {
            "event": "commit_command_finished",
            "run_id": run_id,
            "status": execution["status"],
            "commit_sha": commit_sha,
        },
    )
    return execution


def render_push_command(target: Path, run_id: str, remote: str = "origin") -> Path:
    run_dir, run, _cwd = _load_writer_workspace(target, run_id)
    execution_path = run_dir / "commit_execution.json"
    if not execution_path.exists():
        raise GitPublishError(f"commit execution is missing for {run_id}")
    execution = json.loads(execution_path.read_text())
    if execution.get("status") != "succeeded" or not execution.get("commit_sha"):
        raise GitPublishError(f"commit execution is {execution.get('status', 'missing')}")
    branch = run.get("branch")
    if not isinstance(branch, str) or not branch:
        raise GitPublishError(f"run branch is missing for {run_id}")

    command = _expected_push_command(run_id=run_id, run=run, remote=remote)
    command["created_at"] = _now()
    output_path = run_dir / "push_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    _append_trace(run_dir, {"event": "push_command_rendered", "run_id": run_id, "remote": remote, "branch": branch})
    return output_path


def run_push_command(target: Path, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise GitPublishError("timeout must be greater than 0")
    run_dir, run, cwd = _load_writer_workspace(target, run_id)
    command_path = run_dir / "push_command.json"
    if not command_path.exists():
        raise GitPublishError(f"push command is missing for {run_id}")
    command = json.loads(command_path.read_text())
    remote = command.get("remote", "origin")
    if not isinstance(remote, str) or not remote:
        raise GitPublishError("push command remote must be a non-empty string")
    expected = _expected_push_command(run_id=run_id, run=run, remote=remote)
    _validate_command_fields(
        command,
        expected,
        ["run_id", "agent_id", "worktree", "remote", "branch", "argv", "display"],
        "push command does not match rendered git policy",
    )
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise GitPublishError("push command argv must be a non-empty string list")

    started_at = _now()
    _append_trace(run_dir, {"event": "push_command_started", "run_id": run_id})
    result = _run_attempt(argv, cwd, timeout_seconds)
    (run_dir / "push_stdout.log").write_text(result["stdout"])
    (run_dir / "push_stderr.log").write_text(result["stderr"])
    status = "succeeded" if result["exit_code"] == 0 and not result["timed_out"] else "failed"
    execution = {
        "run_id": run_id,
        "status": status,
        "argv": argv,
        "timeout_seconds": timeout_seconds,
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "duration_seconds": result["duration_seconds"],
        "started_at": started_at,
        "finished_at": _now(),
        "stdout_log": "push_stdout.log",
        "stderr_log": "push_stderr.log",
    }
    (run_dir / "push_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    _append_trace(
        run_dir,
        {
            "event": "push_command_finished",
            "run_id": run_id,
            "status": status,
            "exit_code": result["exit_code"],
            "timed_out": result["timed_out"],
        },
    )
    return execution


def _load_writer_workspace(target: Path, run_id: str) -> tuple[Path, dict[str, Any], Path]:
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise GitPublishError(f"run metadata is missing for {run_id}")
    run = json.loads(run_path.read_text())
    if run.get("mode") != "writer":
        raise GitPublishError("git publication commands require a writer run")
    worktree = run.get("worktree")
    if not isinstance(worktree, str) or not worktree:
        raise GitPublishError(f"run worktree is missing for {run_id}")
    cwd = target / worktree
    if not cwd.exists() or not cwd.is_dir():
        raise GitPublishError(f"run worktree does not exist: {worktree}")
    return run_dir, run, cwd


def _expected_commit_command(
    run_id: str,
    run: dict[str, Any],
    message: str,
    user_name: str = "AI Harness",
    user_email: str = "ai-harness@example.invalid",
) -> dict[str, Any]:
    steps = [
        {"name": "stage", "argv": ["git", "add", "--all"]},
        {
            "name": "commit",
            "argv": [
                "git",
                "-c",
                f"user.name={user_name}",
                "-c",
                f"user.email={user_email}",
                "commit",
                "-m",
                message,
            ],
        },
    ]
    return {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "worktree": run.get("worktree"),
        "message": message,
        "steps": [{**step, "display": shlex.join(step["argv"])} for step in steps],
    }


def _expected_push_command(run_id: str, run: dict[str, Any], remote: str) -> dict[str, Any]:
    branch = run.get("branch")
    if not isinstance(branch, str) or not branch:
        raise GitPublishError(f"run branch is missing for {run_id}")
    argv = ["git", "push", remote, branch]
    return {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "worktree": run.get("worktree"),
        "remote": remote,
        "branch": branch,
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
            raise GitPublishError(f"{error}: {key}")


def _porcelain_path(line: str) -> str:
    value = line[3:] if len(line) > 3 else line
    if " -> " in value:
        return value.split(" -> ", 1)[1]
    return value


def _worktree_diff_patch(cwd: Path, status_lines: list[str]) -> str:
    diff_result = _run_git(["git", "diff", "--binary"], cwd)
    patches = [diff_result["stdout"]]
    for line in status_lines:
        if not line.startswith("?? "):
            continue
        path = _porcelain_path(line)
        full_path = cwd / path
        if not full_path.is_file():
            continue
        result = _run_git(["git", "diff", "--no-index", "--", "/dev/null", path], cwd)
        if result["stdout"]:
            patches.append(result["stdout"])
    return "".join(patches)


def _run_git(argv: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


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
            "argv": argv,
            "exit_code": completed.returncode,
            "timed_out": False,
            "duration_seconds": _duration_seconds(start, end),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        end = datetime.now(timezone.utc)
        return {
            "argv": argv,
            "exit_code": None,
            "timed_out": True,
            "duration_seconds": _duration_seconds(start, end),
            "stdout": _decode_timeout_output(exc.stdout),
            "stderr": _decode_timeout_output(exc.stderr),
        }


def _post_commit_gate(run_dir: Path, run_id: str, cwd: Path) -> dict[str, Any]:
    status_result = _run_git(["git", "status", "--porcelain=v1"], cwd)
    status_lines = [line for line in status_result["stdout"].splitlines() if line.strip()]
    gate = {
        "run_id": run_id,
        "status": "clean" if not status_lines else "dirty",
        "status_porcelain": status_lines,
        "created_at": _now(),
    }
    (run_dir / "post_commit_diff_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    return gate


def _current_commit(cwd: Path) -> str:
    result = _run_git(["git", "rev-parse", "HEAD"], cwd)
    return result["stdout"].strip() if result["exit_code"] == 0 else ""


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
