from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .yaml_lite import load_yaml


class ValidationError(Exception):
    pass


def validate_scaffold(target: Path) -> None:
    errors: list[str] = []
    required = [
        "AGENTS.md",
        ".ai/harness.yml",
        ".ai/assignments.yml",
        ".ai/roles",
        ".ai/runtimes",
        ".ai/rules",
        ".ai/schemas",
        ".claude/settings.json",
    ]
    for rel in required:
        if not (target / rel).exists():
            errors.append(f"missing required path: {rel}")

    if errors:
        raise ValidationError("; ".join(errors))

    roles = _load_named_yaml_dir(target / ".ai" / "roles", errors)
    runtimes = _load_named_yaml_dir(target / ".ai" / "runtimes", errors)
    assignments = _safe_load(target / ".ai" / "assignments.yml", errors)

    assignment_map = assignments.get("assignments", {}) if isinstance(assignments, dict) else {}
    for role_id, assignment in assignment_map.items():
        if role_id not in roles:
            errors.append(f"assignment references unknown role: {role_id}")
            continue
        runtime_id = assignment.get("runtime") if isinstance(assignment, dict) else None
        if runtime_id not in runtimes:
            errors.append(f"assignment for {role_id} references unknown runtime: {runtime_id}")
        allowed = set(assignment.get("allowed_skills", []) or [])
        role_allowed = set(roles[role_id].get("allowed_skills", []) or [])
        unknown_skills = sorted(allowed - role_allowed)
        if unknown_skills:
            errors.append(f"assignment for {role_id} includes skills not allowed by role: {unknown_skills}")

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


def load_roles(target: Path) -> dict[str, dict[str, Any]]:
    errors: list[str] = []
    roles = _load_named_yaml_dir(target / ".ai" / "roles", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return roles


def load_runtimes(target: Path) -> dict[str, dict[str, Any]]:
    errors: list[str] = []
    runtimes = _load_named_yaml_dir(target / ".ai" / "runtimes", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return runtimes


def load_assignments(target: Path) -> dict[str, Any]:
    errors: list[str] = []
    assignments = _safe_load(target / ".ai" / "assignments.yml", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return assignments


def load_harness_config(target: Path) -> dict[str, Any]:
    errors: list[str] = []
    config = _safe_load(target / ".ai" / "harness.yml", errors)
    if errors:
        raise ValidationError("; ".join(errors))
    return config


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
