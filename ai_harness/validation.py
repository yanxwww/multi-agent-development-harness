from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .yaml_lite import load_yaml, loads_yaml


class ValidationError(Exception):
    pass


FORBIDDEN_SCHEDULER_VISIBLE_KEYS = {"runtime", "runtime_id", "connector", "connector_profile", "model", "api_key"}


def validate_scaffold(target: Path) -> None:
    errors: list[str] = []
    required = [
        "AGENTS.md",
        ".ai/harness.yml",
        ".ai/agent-catalog.yml",
        ".ai/private/assignments.yml",
        ".ai/agents",
        ".ai/connectors",
        ".ai/rules",
        ".ai/schemas",
        ".claude/settings.json",
    ]
    for rel in required:
        if not (target / rel).exists():
            errors.append(f"missing required path: {rel}")

    if errors:
        raise ValidationError("; ".join(errors))

    agents = load_agents(target, errors)
    connectors = _load_named_yaml_dir(target / ".ai" / "connectors", errors)
    catalog = _safe_load(target / ".ai" / "agent-catalog.yml", errors)
    bindings = _safe_load(target / ".ai" / "private" / "assignments.yml", errors)

    catalog_agents = catalog.get("agents", {}) if isinstance(catalog, dict) else {}
    for agent_id, entry in catalog_agents.items():
        if agent_id not in agents:
            errors.append(f"agent catalog references missing agent doc: {agent_id}")
        if isinstance(entry, dict):
            _collect_forbidden_scheduler_visible_keys(entry, f"agent-catalog.agents.{agent_id}", errors)

    binding_map = bindings.get("bindings", {}) if isinstance(bindings, dict) else {}
    for agent_id, binding in binding_map.items():
        if agent_id not in catalog_agents:
            errors.append(f"private binding references unknown catalog agent: {agent_id}")
            continue
        connector_id = binding.get("connector") if isinstance(binding, dict) else None
        profile = binding.get("profile") if isinstance(binding, dict) else None
        connector = connectors.get(str(connector_id), {})
        if connector_id not in connectors:
            errors.append(f"binding for {agent_id} references unknown connector: {connector_id}")
            continue
        profiles = connector.get("profiles", {}) if isinstance(connector, dict) else {}
        if profile not in profiles:
            errors.append(f"binding for {agent_id} references unknown connector profile: {connector_id}.{profile}")

    for agent_id in agents:
        if agent_id not in catalog_agents:
            errors.append(f"agent doc is not visible in agent catalog: {agent_id}")
        if agent_id not in binding_map:
            errors.append(f"agent doc has no private binding: {agent_id}")

    for schema_path in sorted((target / ".ai" / "schemas").glob("*.schema.json")):
        try:
            json.loads(schema_path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON schema {schema_path.relative_to(target)}: {exc}")

    gitignore = target / ".gitignore"
    if not gitignore.exists() or "CLAUDE.md" not in gitignore.read_text().splitlines():
        errors.append(".gitignore must include CLAUDE.md because AGENTS.md is canonical")

    if _is_git_tracked(target, "CLAUDE.md"):
        errors.append("CLAUDE.md must not be committed as a canonical instruction file")

    if errors:
        raise ValidationError("; ".join(errors))


def load_agents(target: Path, errors: list[str] | None = None) -> dict[str, dict[str, Any]]:
    local_errors: list[str] = []
    sink = errors if errors is not None else local_errors
    data: dict[str, dict[str, Any]] = {}
    for path in sorted((target / ".ai" / "agents").glob("*.md")):
        item = _load_agent_doc(path, sink)
        if not item:
            continue
        item_id = item.get("id")
        if item_id != path.stem:
            sink.append(f"{path.name} id must be {path.stem}, got {item_id}")
            continue
        item["doc_path"] = f".ai/agents/{path.name}"
        data[path.stem] = item
    if errors is None and local_errors:
        raise ValidationError("; ".join(local_errors))
    return data


def load_agent_catalog(target: Path) -> dict[str, Any]:
    errors: list[str] = []
    catalog = _safe_load(target / ".ai" / "agent-catalog.yml", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return catalog


def load_private_bindings(target: Path) -> dict[str, Any]:
    errors: list[str] = []
    bindings = _safe_load(target / ".ai" / "private" / "assignments.yml", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return bindings


def load_connectors(target: Path) -> dict[str, dict[str, Any]]:
    errors: list[str] = []
    connectors = _load_named_yaml_dir(target / ".ai" / "connectors", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return connectors


def load_harness_config(target: Path) -> dict[str, Any]:
    errors: list[str] = []
    config = _safe_load(target / ".ai" / "harness.yml", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return config


def _load_agent_doc(path: Path, errors: list[str]) -> dict[str, Any]:
    text = path.read_text()
    if not text.startswith("---\n"):
        errors.append(f"agent doc missing front matter: {path.name}")
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"agent doc front matter is not closed: {path.name}")
        return {}
    try:
        value = loads_yaml(text[4:end])
    except Exception as exc:
        errors.append(f"invalid agent front matter {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"agent front matter must be a mapping: {path.name}")
        return {}
    return value


def _load_named_yaml_dir(directory: Path, errors: list[str]) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yml")):
        item = _safe_load(path, errors)
        if not isinstance(item, dict):
            errors.append(f"{path.name} must be a mapping")
            continue
        item_id = item.get("id")
        if item_id != path.stem:
            errors.append(f"{path.name} id must be {path.stem}, got {item_id}")
            continue
        data[path.stem] = item
    return data


def _safe_load(path: Path, errors: list[str]) -> Any:
    try:
        return load_yaml(path)
    except Exception as exc:
        errors.append(f"invalid YAML {path}: {exc}")
        return {}


def _is_git_tracked(target: Path, relpath: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(target), "ls-files", "--error-unmatch", relpath],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def _collect_forbidden_scheduler_visible_keys(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            next_path = f"{path}.{key}"
            if key in FORBIDDEN_SCHEDULER_VISIBLE_KEYS:
                errors.append(f"agent catalog must not expose dispatcher binding key: {next_path}")
            _collect_forbidden_scheduler_visible_keys(nested, next_path, errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _collect_forbidden_scheduler_visible_keys(nested, f"{path}[{index}]", errors)
