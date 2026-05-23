from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runs import render_pr_body


class GateError(Exception):
    pass


def run_validation_gate(
    target: Path,
    run_id: str,
    timeout_seconds: float,
    mode: str = "run",
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise GateError("timeout must be greater than 0")
    if mode not in {"run", "skip"}:
        raise GateError(f"invalid validation mode: {mode}")

    run_dir = target / ".ai" / "runs" / run_id
    evidence_path = run_dir / "evidence.json"
    if not evidence_path.exists():
        raise GateError(f"evidence is missing for {run_id}")
    evidence = json.loads(evidence_path.read_text())
    validation = _validation_items(run_dir, evidence)
    if not isinstance(validation, list):
        raise GateError("evidence validation must be a list")

    if mode == "skip":
        results = []
        for item in validation:
            item["status"] = "skipped"
            results.append({"command": item.get("command", ""), "status": "skipped"})
        status = "skipped"
    else:
        cwd = _validation_cwd(target, run_dir)
        results = [_run_validation_command(cwd, item, timeout_seconds) for item in validation]
        status = "passed" if all(result["status"] == "passed" for result in results) else "failed"
        for item, result in zip(validation, results):
            item["status"] = result["status"]
            item["exit_code"] = result["exit_code"]

    evidence["validation"] = validation
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    gate = {
        "run_id": run_id,
        "status": status,
        "mode": mode,
        "results": results,
        "created_at": _now(),
    }
    (run_dir / "validation_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "validation_gate_finished", "run_id": run_id, "status": status, "mode": mode})
    return gate


def run_pr_gate(target: Path, run_id: str) -> dict[str, Any]:
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise GateError(f"run metadata is missing for {run_id}")
    run = json.loads(run_path.read_text())

    if run.get("mode") != "writer":
        gate = {
            "run_id": run_id,
            "status": "not_required",
            "reasons": [],
            "created_at": _now(),
        }
        (run_dir / "pr_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
        _append_trace(run_dir, {"event": "pr_gate_finished", "run_id": run_id, "status": gate["status"]})
        return gate

    if not (run_dir / "pr-body.md").exists():
        render_pr_body(target, run_id)

    reasons: list[str] = []
    execution = _load_optional_json(run_dir / "connector_execution.json")
    validation = _load_optional_json(run_dir / "validation_gate.json")
    evidence_exists = (run_dir / "evidence.json").exists()
    pr_body_exists = (run_dir / "pr-body.md").exists()

    if not evidence_exists:
        reasons.append("evidence bundle is missing")
    if not pr_body_exists:
        reasons.append("PR body is missing")
    if execution.get("status") != "succeeded":
        reasons.append(f"connector execution is {execution.get('status', 'missing')}")
    if validation.get("status") not in {"passed", "skipped"}:
        reasons.append(f"validation gate is {validation.get('status', 'missing')}")

    gate = {
        "run_id": run_id,
        "status": "passed" if not reasons else "blocked",
        "reasons": reasons,
        "connector_status": execution.get("status", "missing"),
        "validation_status": validation.get("status", "missing"),
        "pr_body": "pr-body.md" if pr_body_exists else None,
        "created_at": _now(),
    }
    (run_dir / "pr_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    _append_trace(run_dir, {"event": "pr_gate_finished", "run_id": run_id, "status": gate["status"]})
    return gate


def _run_validation_command(cwd: Path, item: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    command = item.get("command")
    if not isinstance(command, str) or not command.strip():
        return {
            "command": command or "",
            "status": "failed",
            "exit_code": None,
            "timed_out": False,
            "stdout": "",
            "stderr": "validation command is missing",
        }
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        return {
            "command": command,
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "timed_out": False,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "failed",
            "exit_code": None,
            "timed_out": True,
            "stdout": _decode_timeout_output(exc.stdout),
            "stderr": _decode_timeout_output(exc.stderr),
        }


def _validation_items(run_dir: Path, evidence: dict[str, Any]) -> list[Any]:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        return evidence.get("validation", [])
    run = json.loads(run_path.read_text())
    commands = run.get("validation_commands")
    if not commands:
        return evidence.get("validation", [])
    if not isinstance(commands, list) or not all(isinstance(command, str) for command in commands):
        raise GateError("run validation_commands must be a list of strings")
    return [{"command": command, "status": "not_run"} for command in commands]


def _validation_cwd(target: Path, run_dir: Path) -> Path:
    run_path = run_dir / "run.json"
    if not run_path.exists():
        return target
    run = json.loads(run_path.read_text())
    worktree = run.get("worktree")
    if not worktree:
        return target
    cwd = target / str(worktree)
    if not cwd.exists() or not cwd.is_dir():
        raise GateError(f"validation workspace does not exist: {worktree}")
    return cwd


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
