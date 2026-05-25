from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runs import create_run, validate_run_id
from .validation import validate_scaffold


class IntegrationError(Exception):
    pass


def render_integration_plan(
    target: Path,
    issue: str,
    schedule_run_id: str,
    run_id: str,
    base_ref: str = "HEAD",
    create_worktree: bool = True,
) -> Path:
    validate_scaffold(target)
    validate_run_id(run_id)
    schedule_dir = target / ".ai" / "runs" / schedule_run_id
    dispatch_log = _load_dispatch_log(schedule_dir / "dispatch_log.jsonl")
    children = _integration_children(target, dispatch_log)
    if not children:
        raise IntegrationError("integration plan requires at least one writer child PR")

    task_path = schedule_dir / "tasks" / f"{run_id}-integration-task.json"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        json.dumps(
            {
                "task_id": "integration",
                "summary": f"Integrate {len(children)} child writer branches for {issue}",
                "issue": issue,
                "acceptance": ["child branches merge cleanly", "integration branch remains publishable"],
            },
            indent=2,
        )
        + "\n"
    )
    create_run(
        target=target,
        issue=issue,
        agent_id="integration-agent",
        task_path=task_path,
        run_id=run_id,
        base_ref=base_ref,
        create_worktree=create_worktree,
        mode="writer",
    )

    run_dir = target / ".ai" / "runs" / run_id
    plan = {
        "run_id": run_id,
        "agent_id": "integration-agent",
        "schedule_run_id": schedule_run_id,
        "base_ref": base_ref,
        "children": children,
        "created_at": _now(),
    }
    output_path = run_dir / "integration_plan.json"
    output_path.write_text(json.dumps(plan, indent=2) + "\n")
    _append_trace(run_dir, {"event": "integration_plan_rendered", "run_id": run_id, "children": len(children)})
    return output_path


def render_integration_command(target: Path, run_id: str, strategy: str = "merge") -> Path:
    if strategy != "merge":
        raise IntegrationError("integration strategy must be merge")
    run_dir, run, _cwd = _load_writer_workspace(target, run_id)
    plan = _load_integration_plan(run_dir, run_id)
    command = _expected_integration_command(run_id, run, plan, strategy)
    command["created_at"] = _now()
    output_path = run_dir / "integration_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    _append_trace(run_dir, {"event": "integration_command_rendered", "run_id": run_id, "children": len(plan["children"])})
    return output_path


def run_integration_command(target: Path, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise IntegrationError("timeout must be greater than 0")
    run_dir, run, cwd = _load_writer_workspace(target, run_id)
    command_path = run_dir / "integration_command.json"
    if not command_path.exists():
        raise IntegrationError(f"integration command is missing for {run_id}")
    command = json.loads(command_path.read_text())
    plan = _load_integration_plan(run_dir, run_id)
    expected = _expected_integration_command(run_id, run, plan, _string_field(command, "strategy", "merge"))
    _validate_command_fields(
        command,
        expected,
        ["run_id", "agent_id", "worktree", "strategy", "children", "steps"],
        "integration command does not match rendered integration policy",
    )

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    results: list[dict[str, Any]] = []
    status = "succeeded"
    started_at = _now()
    _append_trace(run_dir, {"event": "integration_command_started", "run_id": run_id})

    for step in command["steps"]:
        argv = step.get("argv") if isinstance(step, dict) else None
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise IntegrationError("integration step argv must be a non-empty string list")
        result = _run_attempt(argv, cwd, timeout_seconds)
        result["name"] = step.get("name", "step")
        results.append(result)
        stdout_parts.append(result["stdout"])
        stderr_parts.append(result["stderr"])
        if result["exit_code"] != 0 or result["timed_out"]:
            status = "failed"
            break

    (run_dir / "integration_stdout.log").write_text("".join(stdout_parts))
    (run_dir / "integration_stderr.log").write_text("".join(stderr_parts))
    conflict_files = _conflict_files(cwd) if status == "failed" else []
    commit_sha = _current_commit(cwd) if status == "succeeded" else ""
    execution = {
        "run_id": run_id,
        "status": status,
        "steps": results,
        "commit_sha": commit_sha,
        "conflict_files": conflict_files,
        "started_at": started_at,
        "finished_at": _now(),
        "stdout_log": "integration_stdout.log",
        "stderr_log": "integration_stderr.log",
    }
    (run_dir / "integration_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    if status == "succeeded":
        _write_commit_execution(run_dir, run_id, commit_sha, started_at)
    _append_trace(
        run_dir,
        {
            "event": "integration_command_finished",
            "run_id": run_id,
            "status": status,
            "commit_sha": commit_sha,
            "conflict_count": len(conflict_files),
        },
    )
    return execution


def _integration_children(target: Path, dispatch_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for entry in dispatch_log:
        if entry.get("mode") != "writer" or not entry.get("requires_pr", False):
            continue
        child_run_id = _string_field(entry, "run_id", "")
        child_dir = target / ".ai" / "runs" / child_run_id
        run_path = child_dir / "run.json"
        if not run_path.exists():
            raise IntegrationError(f"child run metadata is missing: {child_run_id}")
        run = json.loads(run_path.read_text())
        branch = _string_field(run, "branch", "")
        pr_execution = _load_optional_json(child_dir / "pr_execution.json")
        if pr_execution.get("status") != "succeeded":
            raise IntegrationError(f"child PR execution is {pr_execution.get('status', 'missing')} for {child_run_id}")
        children.append(
            {
                "run_id": child_run_id,
                "agent_id": run.get("agent_id"),
                "task_id": entry.get("task_id"),
                "branch": branch,
                "pr_number": pr_execution.get("number"),
                "pr_url": pr_execution.get("url"),
            }
        )
    return children


def _expected_integration_command(
    run_id: str,
    run: dict[str, Any],
    plan: dict[str, Any],
    strategy: str,
) -> dict[str, Any]:
    if strategy != "merge":
        raise IntegrationError("integration strategy must be merge")
    steps = []
    for child in plan["children"]:
        branch = _string_field(child, "branch", "")
        argv = [
            "git",
            "-c",
            "user.name=AI Harness",
            "-c",
            "user.email=ai-harness@example.invalid",
            "merge",
            "--no-ff",
            "--no-edit",
            branch,
        ]
        steps.append({"name": f"merge-{child['run_id']}", "argv": argv, "display": shlex.join(argv)})
    return {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "worktree": run.get("worktree"),
        "strategy": strategy,
        "children": [
            {
                "run_id": child["run_id"],
                "branch": child["branch"],
                "pr_number": child.get("pr_number"),
                "pr_url": child.get("pr_url"),
            }
            for child in plan["children"]
        ],
        "steps": steps,
    }


def _load_writer_workspace(target: Path, run_id: str) -> tuple[Path, dict[str, Any], Path]:
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise IntegrationError(f"run metadata is missing for {run_id}")
    run = json.loads(run_path.read_text())
    if run.get("mode") != "writer":
        raise IntegrationError("integration commands require a writer run")
    if run.get("agent_id") != "integration-agent":
        raise IntegrationError("integration commands require integration-agent")
    worktree = run.get("worktree")
    if not isinstance(worktree, str) or not worktree:
        raise IntegrationError(f"run worktree is missing for {run_id}")
    cwd = target / worktree
    if not cwd.exists() or not cwd.is_dir():
        raise IntegrationError(f"run worktree does not exist: {worktree}")
    return run_dir, run, cwd


def _load_integration_plan(run_dir: Path, run_id: str) -> dict[str, Any]:
    path = run_dir / "integration_plan.json"
    if not path.exists():
        raise IntegrationError(f"integration plan is missing for {run_id}")
    plan = json.loads(path.read_text())
    children = plan.get("children")
    if not isinstance(children, list) or not children:
        raise IntegrationError("integration plan children must be a non-empty list")
    return plan


def _load_dispatch_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise IntegrationError(f"dispatch log is missing: {path}")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _validate_command_fields(command: dict[str, Any], expected: dict[str, Any], keys: list[str], error: str) -> None:
    for key in keys:
        if command.get(key) != expected.get(key):
            raise IntegrationError(f"{error}: {key}")


def _string_field(value: dict[str, Any], key: str, default: str) -> str:
    item = value.get(key, default)
    if not isinstance(item, str) or not item:
        raise IntegrationError(f"{key} must be a non-empty string")
    return item


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


def _current_commit(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(cwd),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _conflict_files(cwd: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _write_commit_execution(run_dir: Path, run_id: str, commit_sha: str, started_at: str) -> None:
    execution = {
        "run_id": run_id,
        "status": "succeeded",
        "commit_sha": commit_sha,
        "source": "integration_command",
        "started_at": started_at,
        "finished_at": _now(),
    }
    (run_dir / "commit_execution.json").write_text(json.dumps(execution, indent=2) + "\n")


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
