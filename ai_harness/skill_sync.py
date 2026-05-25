from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import load_agents, load_private_bindings, validate_scaffold
from .yaml_lite import load_yaml


class SkillSyncError(Exception):
    pass


SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def sync_run_skills(target: Path, run_id: str) -> dict[str, Any]:
    validate_scaffold(target)
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise SkillSyncError(f"run metadata is missing for {run_id}")

    run = json.loads(run_path.read_text())
    agent_id = _string(run, "agent_id")
    agents = load_agents(target)
    agent = agents.get(agent_id)
    if not agent:
        raise SkillSyncError(f"unknown agent: {agent_id}")

    bindings = load_private_bindings(target).get("bindings", {})
    binding = bindings.get(agent_id)
    if not isinstance(binding, dict):
        raise SkillSyncError(f"agent has no private connector binding: {agent_id}")

    connector = _string_or_default(run, "connector", _string(binding, "connector"))
    connector_profile = _string_or_default(run, "connector_profile", _string(binding, "profile"))
    destination = _destination_for_connector(connector)
    registry = _load_registry(target)
    skills = _allowed_skills(agent)

    synced: list[dict[str, Any]] = []
    for skill_id in skills:
        _validate_skill_id(skill_id)
        synced.append(_sync_skill(target, skill_id, registry, destination))

    manifest = {
        "run_id": run_id,
        "agent_id": agent_id,
        "connector": connector,
        "connector_profile": connector_profile,
        "destination": destination,
        "skills": synced,
        "created_at": _now(),
    }
    manifest_path = run_dir / "skill_sync.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    _append_trace(run_dir, {"event": "skills_synced", "run_id": run_id, "destination": destination, "count": len(synced)})
    return manifest


def _sync_skill(target: Path, skill_id: str, registry: dict[str, Any], destination: str) -> dict[str, Any]:
    source_dir = target / ".ai" / "skills" / skill_id
    target_dir = target / destination / skill_id
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    description = _registry_description(registry, skill_id)

    if (source_dir / "SKILL.md").exists():
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        status = "copied"
        source = f".ai/skills/{skill_id}"
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(_generated_skill_text(skill_id, description))
        status = "generated"
        source = ".ai/skills/registry.yml"

    return {
        "id": skill_id,
        "status": status,
        "source": source,
        "target": f"{destination}/{skill_id}",
        "description": description,
    }


def _destination_for_connector(connector: str) -> str:
    if connector == "claude-code-cli":
        return ".claude/skills"
    return ".agents/skills"


def _allowed_skills(agent: dict[str, Any]) -> list[str]:
    value = agent.get("allowed_skills", [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SkillSyncError("agent allowed_skills must be a string list")
    return value


def _load_registry(target: Path) -> dict[str, Any]:
    path = target / ".ai" / "skills" / "registry.yml"
    if not path.exists():
        return {}
    value = load_yaml(path)
    if not isinstance(value, dict):
        return {}
    return value.get("skills", {}) if isinstance(value.get("skills"), dict) else {}


def _registry_description(registry: dict[str, Any], skill_id: str) -> str:
    entry = registry.get(skill_id, {})
    if isinstance(entry, dict):
        description = entry.get("description")
        if isinstance(description, str) and description.strip():
            return description
    return f"Skill allowlisted for {skill_id}."


def _generated_skill_text(skill_id: str, description: str) -> str:
    title = skill_id.replace("-", " ").replace("_", " ").title()
    return f"""---
name: {skill_id}
description: {description}
---
# {title}

{description}
"""


def _validate_skill_id(skill_id: str) -> None:
    if not SKILL_ID_RE.fullmatch(skill_id):
        raise SkillSyncError(f"unsafe skill id: {skill_id}")


def _string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SkillSyncError(f"{key} must be a non-empty string")
    return item


def _string_or_default(value: dict[str, Any], key: str, default: str) -> str:
    item = value.get(key, default)
    if not isinstance(item, str) or not item:
        return default
    return item


def _append_trace(run_dir: Path, event: dict[str, Any]) -> None:
    event["ts"] = _now()
    with (run_dir / "trace.jsonl").open("a") as trace:
        trace.write(json.dumps(event) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
