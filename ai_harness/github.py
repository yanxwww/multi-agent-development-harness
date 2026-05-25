from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GitHubError(Exception):
    pass


CHECK_FIELDS = "bucket,completedAt,description,event,link,name,startedAt,state,workflow"


def run_github_doctor(target: Path, executable: str = "gh") -> dict[str, Any]:
    auth = _run_attempt([executable, "auth", "status"], target, timeout_seconds=30)
    repo = _run_attempt([executable, "repo", "view", "--json", "nameWithOwner,url"], target, timeout_seconds=30)
    remote = _run_attempt(["git", "remote", "-v"], target, timeout_seconds=30)

    repo_data: dict[str, Any] = {}
    if repo["exit_code"] == 0:
        try:
            parsed = json.loads(repo["stdout"] or "{}")
            if isinstance(parsed, dict):
                repo_data = parsed
        except json.JSONDecodeError:
            repo_data = {}

    checks = {
        "auth": _doctor_check(auth),
        "repo": _doctor_check(repo),
        "remote": {
            **_doctor_check(remote),
            "remotes": [line for line in remote["stdout"].splitlines() if line.strip()],
        },
    }
    status = "passed" if all(check["status"] == "passed" for check in checks.values()) and checks["remote"]["remotes"] else "failed"
    if not checks["remote"]["remotes"]:
        checks["remote"]["status"] = "failed"
        checks["remote"]["error"] = "no git remotes configured"
    doctor = {
        "status": status,
        "executable": executable,
        "repo": repo_data,
        "checks": checks,
        "created_at": _now(),
    }
    output_path = target / ".ai" / "github_doctor.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(doctor, indent=2) + "\n")
    return doctor


def render_github_checks_command(
    target: Path,
    run_id: str,
    executable: str = "gh",
    watch: bool = False,
    interval: int = 10,
) -> Path:
    if interval <= 0:
        raise GitHubError("interval must be greater than 0")
    run_dir = target / ".ai" / "runs" / run_id
    run = _load_run(run_dir, run_id)
    pr_execution = _load_pr_execution(run_dir, run_id)
    selector = _pr_selector(pr_execution, run)
    command = _expected_checks_command(
        run_id=run_id,
        run=run,
        selector=selector,
        executable=executable,
        watch=watch,
        interval=interval,
    )
    command["created_at"] = _now()
    output_path = run_dir / "github_checks_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    _append_trace(run_dir, {"event": "github_checks_command_rendered", "run_id": run_id, "selector": selector})
    return output_path


def run_github_checks_command(
    target: Path,
    run_id: str,
    timeout_seconds: float,
    eval_results_path: Path | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise GitHubError("timeout must be greater than 0")
    run_dir = target / ".ai" / "runs" / run_id
    command_path = run_dir / "github_checks_command.json"
    if not command_path.exists():
        raise GitHubError(f"GitHub checks command is missing for {run_id}")
    command = json.loads(command_path.read_text())
    run = _load_run(run_dir, run_id)
    _load_pr_execution(run_dir, run_id)
    expected = _expected_checks_command(
        run_id=run_id,
        run=run,
        selector=_string_field(command, "selector"),
        executable=_string_field(command, "executable"),
        watch=bool(command.get("watch", False)),
        interval=int(command.get("interval", 10)),
    )
    _validate_command_fields(
        command,
        expected,
        ["run_id", "agent_id", "executable", "selector", "watch", "interval", "argv", "display"],
        "GitHub checks command does not match rendered policy",
    )
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise GitHubError("GitHub checks command argv must be a non-empty string list")

    _append_trace(run_dir, {"event": "github_checks_command_started", "run_id": run_id})
    result = _run_attempt(argv, target, timeout_seconds)
    (run_dir / "github_checks_stdout.log").write_text(result["stdout"])
    (run_dir / "github_checks_stderr.log").write_text(result["stderr"])
    error = ""
    checks: list[dict[str, Any]] = []
    if result["timed_out"]:
        error = "GitHub checks command timed out"
    elif result["exit_code"] not in {0, 8}:
        error = f"GitHub checks command exited with {result['exit_code']}"
    if not error:
        try:
            checks = _parse_checks_stdout(result["stdout"])
        except GitHubError as exc:
            error = str(exc)
    if error:
        ci_results = _failed_ci_results(run_id, error)
    else:
        ci_results = _ci_results_from_checks(run_id, checks)
    eval_results_output_path = run_dir / "eval_results.json"
    if eval_results_path:
        eval_results = _load_eval_results(eval_results_path)
    elif eval_results_output_path.exists():
        eval_results = _load_eval_results(eval_results_output_path)
    else:
        eval_results = _default_eval_results(run_id)
    (run_dir / "ci_results.json").write_text(json.dumps(ci_results, indent=2) + "\n")
    eval_results_output_path.write_text(json.dumps(eval_results, indent=2) + "\n")

    status = "succeeded" if not error and not result["timed_out"] and result["exit_code"] in {0, 8} else "failed"
    execution = {
        "run_id": run_id,
        "status": status,
        "argv": argv,
        "timeout_seconds": timeout_seconds,
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "duration_seconds": result["duration_seconds"],
        "check_count": len(checks),
        "ci_status": ci_results["status"],
        "eval_status": eval_results["status"],
        "stdout_log": "github_checks_stdout.log",
        "stderr_log": "github_checks_stderr.log",
        "created_at": _now(),
    }
    if error:
        execution["error"] = error
    (run_dir / "github_checks_execution.json").write_text(json.dumps(execution, indent=2) + "\n")
    _append_trace(
        run_dir,
        {
            "event": "github_checks_command_finished",
            "run_id": run_id,
            "status": status,
            "ci_status": ci_results["status"],
            "eval_status": eval_results["status"],
        },
    )
    return execution


def _expected_checks_command(
    run_id: str,
    run: dict[str, Any],
    selector: str,
    executable: str,
    watch: bool,
    interval: int,
) -> dict[str, Any]:
    argv = [
        executable,
        "pr",
        "checks",
        selector,
        "--json",
        CHECK_FIELDS,
    ]
    if watch:
        argv.extend(["--watch", "--interval", str(interval)])
    return {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "executable": executable,
        "selector": selector,
        "watch": watch,
        "interval": interval,
        "argv": argv,
        "display": shlex.join(argv),
    }


def _load_run(run_dir: Path, run_id: str) -> dict[str, Any]:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise GitHubError(f"run metadata is missing for {run_id}")
    return json.loads(run_path.read_text())


def _load_pr_execution(run_dir: Path, run_id: str) -> dict[str, Any]:
    pr_execution = _load_optional_json(run_dir / "pr_execution.json")
    if pr_execution.get("status") != "succeeded":
        raise GitHubError(f"PR execution is {pr_execution.get('status', 'missing')}")
    return pr_execution


def _pr_selector(pr_execution: dict[str, Any], run: dict[str, Any]) -> str:
    number = pr_execution.get("number")
    if isinstance(number, int):
        return str(number)
    if isinstance(number, str) and number.strip():
        return number
    url = pr_execution.get("url")
    if isinstance(url, str) and url.strip():
        return url
    branch = run.get("branch")
    if isinstance(branch, str) and branch.strip():
        return branch
    raise GitHubError("PR selector is missing")


def _parse_checks_stdout(stdout: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(stdout or "[]")
    except json.JSONDecodeError as exc:
        raise GitHubError(f"GitHub checks output is not valid JSON: {exc}") from exc
    if not isinstance(value, list):
        raise GitHubError("GitHub checks output must be a list")
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise GitHubError(f"GitHub check at index {index} must be an object")
        checks.append(item)
    return checks


def _ci_results_from_checks(run_id: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not checks:
        return {
            "run_id": run_id,
            "source": "github-pr-checks",
            "status": "pending",
            "checks": [
                {
                    "name": "github-pr-checks",
                    "status": "pending",
                    "reason": "no GitHub checks returned",
                }
            ],
            "created_at": _now(),
        }

    normalized = []
    statuses = []
    for check in checks:
        status = _bucket_status(str(check.get("bucket", "")).lower())
        statuses.append(status)
        normalized.append(
            {
                "name": str(check.get("name", "unnamed")),
                "status": status,
                "bucket": check.get("bucket"),
                "state": check.get("state"),
                "workflow": check.get("workflow"),
                "link": check.get("link"),
            }
        )
    if any(status == "failed" for status in statuses):
        overall = "failed"
    elif any(status == "pending" for status in statuses):
        overall = "pending"
    else:
        overall = "passed"
    return {
        "run_id": run_id,
        "source": "github-pr-checks",
        "status": overall,
        "checks": normalized,
        "created_at": _now(),
    }


def _failed_ci_results(run_id: str, reason: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "source": "github-pr-checks",
        "status": "failed",
        "checks": [
            {
                "name": "github-pr-checks",
                "status": "failed",
                "reason": reason,
            }
        ],
        "created_at": _now(),
    }


def _bucket_status(bucket: str) -> str:
    if bucket == "pass":
        return "passed"
    if bucket == "skipping":
        return "skipped"
    if bucket in {"fail", "cancel"}:
        return "failed"
    return "pending"


def _default_eval_results(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "source": "default-eval-placeholder",
        "status": "passed",
        "checks": [
            {
                "name": "eval",
                "status": "skipped",
                "reason": "no eval result file supplied",
            }
        ],
        "created_at": _now(),
    }


def _load_eval_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise GitHubError(f"eval results file does not exist: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise GitHubError("eval results must be an object")
    return value


def _doctor_check(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "passed" if result["exit_code"] == 0 and not result["timed_out"] else "failed",
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def _validate_command_fields(command: dict[str, Any], expected: dict[str, Any], keys: list[str], error: str) -> None:
    for key in keys:
        if command.get(key) != expected.get(key):
            raise GitHubError(f"{error}: {key}")


def _string_field(command: dict[str, Any], key: str) -> str:
    value = command.get(key)
    if not isinstance(value, str) or not value:
        raise GitHubError(f"GitHub checks command {key} must be a non-empty string")
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
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
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
