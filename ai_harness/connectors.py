from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

from .validation import load_connectors, validate_scaffold


class ConnectorError(Exception):
    pass


def render_connector_command(
    target: Path,
    run_id: str,
    output_schema: str = ".ai/schemas/agent_result.schema.json",
) -> Path:
    command = build_connector_command(target, run_id, output_schema=output_schema)
    run_dir = target / ".ai" / "runs" / run_id
    output_path = run_dir / "connector_command.json"
    output_path.write_text(json.dumps(command, indent=2) + "\n")
    return output_path


def build_connector_command(
    target: Path,
    run_id: str,
    output_schema: str = ".ai/schemas/agent_result.schema.json",
) -> dict[str, Any]:
    validate_scaffold(target)
    run_dir = target / ".ai" / "runs" / run_id
    run_path = run_dir / "run.json"
    if not run_path.exists():
        raise ConnectorError(f"run metadata is missing for {run_id}")

    run = json.loads(run_path.read_text())
    connectors = load_connectors(target)
    connector_id = run.get("connector")
    profile = run.get("connector_profile")
    connector = connectors.get(str(connector_id))
    if not connector:
        raise ConnectorError(f"unknown connector: {connector_id}")

    templates = connector.get("command_templates", {}) if isinstance(connector, dict) else {}
    template = templates.get(str(profile))
    if not template:
        raise ConnectorError(f"connector profile has no command template: {connector_id}.{profile}")

    workspace = run.get("worktree") or "."
    workspace_path = target / workspace
    schema_path = target / output_schema
    prompt_file = f".ai/runs/{run_id}/prompt.md"
    prompt_path = target / prompt_file
    if not prompt_path.exists():
        raise ConnectorError(f"run prompt is missing for {run_id}")
    values = {
        "workspace": shlex.quote(str(workspace_path)),
        "output_schema": shlex.quote(str(schema_path)),
    }
    display = _render_template(template, values)
    command: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": run.get("agent_id"),
        "connector": connector_id,
        "profile": profile,
        "executable": connector.get("executable"),
        "workspace": workspace,
        "output_schema": output_schema,
        "prompt_file": prompt_file,
        "prompt_sha256": _sha256(prompt_path),
        "display": display,
        "argv": shlex.split(display),
    }
    return command


def validate_connector_command_artifact(target: Path, run_id: str, command: dict[str, Any]) -> None:
    output_schema = command.get("output_schema", ".ai/schemas/agent_result.schema.json")
    if not isinstance(output_schema, str) or not output_schema:
        raise ConnectorError("connector command output_schema must be a non-empty string")
    expected = build_connector_command(target, run_id, output_schema=output_schema)
    checked_keys = [
        "run_id",
        "agent_id",
        "connector",
        "profile",
        "executable",
        "workspace",
        "output_schema",
        "prompt_file",
        "prompt_sha256",
        "display",
        "argv",
    ]
    for key in checked_keys:
        if command.get(key) != expected.get(key):
            raise ConnectorError(f"connector command does not match rendered connector policy: {key}")


def has_connector_command_policy(target: Path, run_id: str) -> bool:
    run_path = target / ".ai" / "runs" / run_id / "run.json"
    if not run_path.exists():
        return False
    run = json.loads(run_path.read_text())
    connector = load_connectors(target).get(str(run.get("connector")))
    if not isinstance(connector, dict):
        return False
    templates = connector.get("command_templates", {})
    return isinstance(templates, dict) and str(run.get("connector_profile")) in templates


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
