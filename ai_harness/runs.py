from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import load_assignments, load_harness_config, load_roles, load_runtimes, validate_scaffold


class RunError(Exception):
    pass


def create_run(
    target: Path,
    issue: str,
    role_id: str,
    task_path: Path,
    run_id: str | None = None,
    base_ref: str = "HEAD",
    create_worktree: bool = True,
) -> dict[str, Any]:
    validate_scaffold(target)
    if not task_path.exists():
        raise RunError(f"task file does not exist: {task_path}")

    roles = load_roles(target)
    runtimes = load_runtimes(target)
    assignments = load_assignments(target).get("assignments", {})
    harness = load_harness_config(target)

    if role_id not in roles:
        raise RunError(f"unknown role: {role_id}")
    assignment = assignments.get(role_id)
    if not assignment:
        raise RunError(f"role has no runtime assignment: {role_id}")
    runtime_id = assignment.get("runtime")
    if runtime_id not in runtimes:
        raise RunError(f"unknown runtime for role {role_id}: {runtime_id}")

    task = json.loads(task_path.read_text())
    if "summary" not in task:
        raise RunError("task JSON must include a summary")

    run_id = run_id or _new_run_id()
    issue_id = normalize_issue_id(issue)
    branch = harness.get("branch_template", "ai/{issue_id}/{role_id}/{run_id}").format(
        issue_id=issue_id,
        role_id=role_id,
        run_id=run_id,
    )
    worktree = harness.get("worktree_template", ".worktrees/{run_id}-{role_id}").format(
        run_id=run_id,
        role_id=role_id,
    )
    run_dir = target / ".ai" / "runs" / run_id
    if run_dir.exists():
        raise RunError(f"run already exists: {run_id}")
    run_dir.mkdir(parents=True)

    role_path = target / ".ai" / "roles" / f"{role_id}.yml"
    role_hash = _sha256(role_path)
    state = "planned"
    worktree_created = False
    if create_worktree and roles[role_id].get("type") != "read-only":
        _create_git_worktree(target, branch, target / worktree, base_ref)
        state = "workspace_ready"
        worktree_created = True

    run = {
        "run_id": run_id,
        "issue_id": issue_id,
        "issue_reference": _issue_reference(issue_id),
        "role_id": role_id,
        "role_type": roles[role_id].get("type"),
        "runtime_id": runtime_id,
        "branch": branch,
        "worktree": worktree,
        "worktree_created": worktree_created,
        "state": state,
        "task_summary": task["summary"],
        "created_at": _now(),
        "role_profile": f".ai/roles/{role_id}.yml",
        "role_profile_hash": f"sha256:{role_hash}",
    }
    evidence = {
        "agent": {
            "role_id": role_id,
            "runtime": runtime_id,
            "run_id": run_id,
            "role_profile": run["role_profile"],
            "role_profile_hash": run["role_profile_hash"],
            "skills_used": assignment.get("allowed_skills", []),
        },
        "issue": {
            "id": issue_id,
            "reference": run["issue_reference"],
        },
        "scope": task["summary"],
        "validation": [{"command": command, "status": "not_run"} for command in roles[role_id].get("required_validation", [])],
        "risk": "Not assessed yet.",
        "rollback": "Revert this PR.",
        "unresolved_questions": [],
    }

    (run_dir / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    (run_dir / "assignment.json").write_text(json.dumps(assignment, indent=2) + "\n")
    (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    (run_dir / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    (run_dir / "trace.jsonl").write_text(json.dumps({"ts": _now(), "event": "run_created", "run_id": run_id}) + "\n")
    return run


def render_pr_body(target: Path, run_id: str) -> Path:
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    evidence_path = run_dir / "evidence.json"
    if not run_path.exists() or not evidence_path.exists():
        raise RunError(f"run evidence is missing for {run_id}")

    run = json.loads(run_path.read_text())
    evidence = json.loads(evidence_path.read_text())
    agent = evidence["agent"]
    validation = evidence.get("validation", [])
    validation_lines = "\n".join(
        f"- `{item.get('command')}`: {item.get('status', 'unknown')}" for item in validation
    ) or "- Not required or not recorded."
    skills = "\n".join(f"  - {skill}" for skill in agent.get("skills_used", [])) or "  - none"
    unresolved = evidence.get("unresolved_questions", [])
    unresolved_lines = "\n".join(f"- {question}" for question in unresolved) or "- None."
    issue_line = _closing_issue_line(run.get("issue_reference", run.get("issue_id", "")))

    body = f"""## Agent

- Agent ID: {agent["role_id"]}
- Runtime: {agent["runtime"]}
- Run ID: {agent["run_id"]}
- Agent doc: {agent["role_profile"]}
- Agent doc hash: {agent["role_profile_hash"]}
- Skills used:
{skills}

## Issue

{issue_line}

## Scope

{evidence.get("scope", run.get("task_summary", ""))}

## Validation

{validation_lines}

## Risk

{evidence.get("risk", "Not assessed yet.")}

## Rollback

{evidence.get("rollback", "Revert this PR.")}

## Unresolved Questions

{unresolved_lines}
"""
    body_path = run_dir / "pr-body.md"
    body_path.write_text(body)
    return body_path


def normalize_issue_id(issue: str) -> str:
    value = issue.strip().lstrip("#")
    if value.startswith("issue-"):
        return value
    if value.isdigit():
        return f"issue-{value}"
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return value or "issue-unknown"


def _issue_reference(issue_id: str) -> str:
    match = re.fullmatch(r"issue-(\d+)", issue_id)
    if match:
        return f"#{match.group(1)}"
    return issue_id


def _closing_issue_line(reference: str) -> str:
    if reference.startswith("#"):
        return f"Closes {reference}"
    return f"Related: {reference}"


def _new_run_id() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _create_git_worktree(target: Path, branch: str, worktree: Path, base_ref: str) -> None:
    if worktree.exists():
        raise RunError(f"worktree already exists: {worktree}")
    probe = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--verify", base_ref],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if probe.returncode != 0:
        raise RunError(f"cannot create worktree from {base_ref}: {probe.stderr.strip()}")
    result = subprocess.run(
        ["git", "-C", str(target), "worktree", "add", "-b", branch, str(worktree), base_ref],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RunError(f"git worktree add failed: {result.stderr.strip()}")

