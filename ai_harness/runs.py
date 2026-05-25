from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import (
    load_agents,
    load_harness_config,
    load_private_bindings,
    validate_scaffold,
)
from .yaml_lite import load_yaml


class RunError(Exception):
    pass


RUN_ID_RE = re.compile(r"^run-[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise RunError(
            "run_id must match ^run-[A-Za-z0-9][A-Za-z0-9._-]*$ and must not contain path separators"
        )


def create_run(
    target: Path,
    issue: str,
    agent_id: str,
    task_path: Path,
    run_id: str | None = None,
    base_ref: str = "HEAD",
    create_worktree: bool = True,
    mode: str | None = None,
) -> dict[str, Any]:
    validate_scaffold(target)
    if not task_path.exists():
        raise RunError(f"task file does not exist: {task_path}")

    agents = load_agents(target)
    bindings = load_private_bindings(target).get("bindings", {})
    harness = load_harness_config(target)

    if agent_id not in agents:
        raise RunError(f"unknown agent: {agent_id}")
    binding = bindings.get(agent_id)
    if not binding:
        raise RunError(f"agent has no private connector binding: {agent_id}")

    task = json.loads(task_path.read_text())
    if "summary" not in task:
        raise RunError("task JSON must include a summary")

    agent_type = agents[agent_id].get("type")
    mode = mode or ("read_only" if agent_type in {"read-only", "read-only-orchestrator"} else "writer")
    if mode not in {"read_only", "writer"}:
        raise RunError(f"invalid run mode: {mode}")
    if mode == "writer" and agent_type in {"read-only", "read-only-orchestrator"}:
        raise RunError(f"agent cannot run in writer mode: {agent_id}")

    run_id = run_id or _new_run_id()
    validate_run_id(run_id)
    issue_id = normalize_issue_id(issue)
    branch = ""
    worktree = ""
    if mode == "writer":
        branch = harness.get("branch_template", "ai/{issue_id}/{agent_id}/{run_id}").format(
            issue_id=issue_id,
            agent_id=agent_id,
            run_id=run_id,
        )
        worktree = harness.get("worktree_template", ".worktrees/{run_id}-{agent_id}").format(
            run_id=run_id,
            agent_id=agent_id,
        )

    agent_path = target / ".ai" / "agents" / f"{agent_id}.md"
    agent_hash = _sha256(agent_path)
    state = "planned"
    worktree_created = False

    run = {
        "run_id": run_id,
        "issue_id": issue_id,
        "issue_reference": _issue_reference(issue_id),
        "agent_id": agent_id,
        "agent_type": agent_type,
        "mode": mode,
        "connector": binding.get("connector"),
        "connector_profile": binding.get("profile"),
        "branch": branch,
        "worktree": worktree,
        "worktree_created": worktree_created,
        "state": state,
        "task_id": task.get("task_id", ""),
        "task_summary": task["summary"],
        "risk_level": str(task.get("risk_level", "medium")),
        "validation_commands": _validation_commands(target, agent_id, mode),
        "created_at": _now(),
        "agent_doc": f".ai/agents/{agent_id}.md",
        "agent_doc_hash": f"sha256:{agent_hash}",
    }
    evidence = {
        "agent": {
            "agent_id": agent_id,
            "connector": binding.get("connector"),
            "connector_profile": binding.get("profile"),
            "run_id": run_id,
            "agent_doc": run["agent_doc"],
            "agent_doc_hash": run["agent_doc_hash"],
            "skills_used": agents[agent_id].get("allowed_skills", []),
        },
        "issue": {
            "id": issue_id,
            "reference": run["issue_reference"],
        },
        "scope": task["summary"],
        "validation": [{"command": command, "status": "not_run"} for command in run["validation_commands"]],
        "risk": "Not assessed yet.",
        "rollback": "Revert this PR.",
        "unresolved_questions": [],
    }

    run_dir = target / ".ai" / "runs" / run_id
    if run_dir.exists():
        raise RunError(f"run already exists: {run_id}")
    worktree_path = target / worktree if worktree else None
    try:
        if create_worktree and mode == "writer":
            _create_git_worktree(target, branch, worktree_path, base_ref)
            state = "workspace_ready"
            worktree_created = True
            run["state"] = state
            run["worktree_created"] = worktree_created

        run_dir.mkdir(parents=True)
        (run_dir / "task.json").write_text(json.dumps(task, indent=2) + "\n")
        (run_dir / "binding.json").write_text(json.dumps(binding, indent=2) + "\n")
        (run_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        (run_dir / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        (run_dir / "prompt.md").write_text(_render_run_prompt(run, task))
        (run_dir / "trace.jsonl").write_text(json.dumps({"ts": _now(), "event": "run_created", "run_id": run_id}) + "\n")
    except Exception:
        if run_dir.exists():
            shutil.rmtree(run_dir)
        if worktree_created and worktree_path is not None and worktree_path.exists():
            _remove_git_worktree(target, worktree_path)
        if worktree_created and branch:
            _delete_git_branch(target, branch)
        raise
    return run


def cleanup_run_workspace(target: Path, run: dict[str, Any]) -> None:
    if not run.get("worktree_created"):
        return
    worktree = run.get("worktree")
    if isinstance(worktree, str) and worktree:
        worktree_path = target / worktree
        if worktree_path.exists():
            _remove_git_worktree(target, worktree_path)
    branch = run.get("branch")
    if isinstance(branch, str) and branch:
        _delete_git_branch(target, branch)


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

- Agent ID: {agent["agent_id"]}
- Connector: {agent["connector"]}
- Connector profile: {agent["connector_profile"]}
- Run ID: {agent["run_id"]}
- Agent doc: {agent["agent_doc"]}
- Agent doc hash: {agent["agent_doc_hash"]}
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


def _render_run_prompt(run: dict[str, Any], task: dict[str, Any]) -> str:
    mode = run.get("mode", "")
    boundary = "Do not modify repository files." if mode == "read_only" else (
        "Modify only files required for this task in the assigned workspace. "
        "Do not commit, push, create pull requests, merge branches, or bypass gates."
    )
    task_json = json.dumps(task, indent=2, ensure_ascii=False)
    return f"""# Agent Run Prompt

## Run

- Run ID: {run.get("run_id", "")}
- Agent ID: {run.get("agent_id", "")}
- Mode: {mode}
- Issue: {run.get("issue_reference", run.get("issue_id", ""))}
- Branch: {run.get("branch", "") or "none"}
- Worktree: {run.get("worktree", "") or "."}
- Agent doc: {run.get("agent_doc", "")}

## Instructions

- Follow AGENTS.md and the assigned agent identity document.
- Use only the role skills and permissions exposed for this run.
- {boundary}
- Return the final answer as JSON matching the output schema supplied by the connector command.

## Task

{run.get("task_summary", "")}

## Task JSON

```json
{task_json}
```
"""


def normalize_issue_id(issue: str) -> str:
    value = issue.strip().lstrip("#")
    if value.startswith("issue-"):
        return value
    if value.isdigit():
        return f"issue-{value}"
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return value or "issue-unknown"


def _validation_commands(target: Path, agent_id: str, mode: str) -> list[str]:
    if mode == "read_only":
        return []
    policy_commands = _validation_policy_commands(target, agent_id, mode)
    if policy_commands is not None:
        return policy_commands
    if agent_id == "backend-implementer":
        commands = ["pnpm lint", "pnpm typecheck", "pnpm test backend"]
    elif agent_id == "frontend-implementer":
        commands = ["pnpm lint", "pnpm typecheck", "pnpm test frontend"]
    elif agent_id == "ci-repair-agent":
        commands = ["pnpm lint", "pnpm typecheck", "pnpm test"]
    else:
        commands = ["harness validate"]
    return commands


def _validation_policy_commands(target: Path, agent_id: str, mode: str) -> list[str] | None:
    path = target / ".ai" / "rules" / "validation-policy.yml"
    if not path.exists():
        return None
    policy = load_yaml(path)
    if not isinstance(policy, dict):
        return None
    agents = policy.get("agents", {})
    if isinstance(agents, dict) and agent_id in agents:
        return _coerce_command_list(agents[agent_id], f"validation policy for {agent_id}")
    defaults = policy.get("defaults", {})
    if isinstance(defaults, dict) and mode in defaults:
        return _coerce_command_list(defaults[mode], f"validation policy default {mode}")
    return None


def _coerce_command_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise RunError(f"{label} must be a list of commands")
    commands = []
    for index, item in enumerate(value):
        command = item.get("command") if isinstance(item, dict) else item
        if not isinstance(command, str) or not command.strip():
            raise RunError(f"{label}[{index}] must be a non-empty command string")
        commands.append(command)
    return commands


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


def _remove_git_worktree(target: Path, worktree: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(target), "worktree", "remove", "--force", str(worktree)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 and worktree.exists():
        shutil.rmtree(worktree)


def _delete_git_branch(target: Path, branch: str) -> None:
    subprocess.run(
        ["git", "-C", str(target), "branch", "-D", branch],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
