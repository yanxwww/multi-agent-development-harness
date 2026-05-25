from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConnectorContractError(Exception):
    pass


READ_ONLY_PROFILES = {
    "scheduler-readonly",
    "readonly-json",
    "planner",
    "reviewer-readonly",
    "risk-approval-readonly",
    "release-readonly",
}
WRITE_TOOLS = {"edit", "multiedit", "write", "bash"}


def build_connector_contract_report(connectors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for connector_id, connector in sorted(connectors.items()):
        profiles = connector.get("profiles", {}) if isinstance(connector, dict) else {}
        templates = connector.get("command_templates", {}) if isinstance(connector, dict) else {}
        if not isinstance(profiles, dict):
            findings.append(_finding(connector_id, "", "profiles must be a mapping"))
            continue
        if not isinstance(templates, dict):
            findings.append(_finding(connector_id, "", "command_templates must be a mapping"))
            continue
        for profile_name, profile in sorted(profiles.items()):
            if not isinstance(profile, dict):
                findings.append(_finding(connector_id, str(profile_name), "profile must be a mapping"))
                continue
            template = templates.get(str(profile_name))
            if not isinstance(template, str) or not template.strip():
                findings.append(_finding(connector_id, str(profile_name), "profile has no command template"))
                continue
            _validate_profile(connector_id, str(profile_name), profile, template, findings)

    return {
        "status": "passed" if not findings else "failed",
        "connectors_checked": sorted(connectors),
        "findings": findings,
        "created_at": _now(),
    }


def validate_connector_contracts(connectors: dict[str, dict[str, Any]]) -> None:
    report = build_connector_contract_report(connectors)
    if report["findings"]:
        messages = [f"{item['connector']}.{item['profile']}: {item['message']}" for item in report["findings"]]
        raise ConnectorContractError("; ".join(messages))


def write_connector_contract_report(target: Path, connectors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    report = build_connector_contract_report(connectors)
    (target / ".ai" / "connector_contracts.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _validate_profile(
    connector_id: str,
    profile_name: str,
    profile: dict[str, Any],
    template: str,
    findings: list[dict[str, Any]],
) -> None:
    if connector_id == "codex-cli":
        _validate_codex_profile(connector_id, profile_name, profile, template, findings)
    elif connector_id == "claude-code-cli":
        _validate_claude_profile(connector_id, profile_name, profile, template, findings)
    if profile_name in READ_ONLY_PROFILES:
        tools = _tool_set(profile.get("tools", ""))
        leaked = sorted(WRITE_TOOLS.intersection(tools))
        if leaked:
            findings.append(_finding(connector_id, profile_name, f"read-only profile exposes write tools: {leaked}"))


def _validate_codex_profile(
    connector_id: str,
    profile_name: str,
    profile: dict[str, Any],
    template: str,
    findings: list[dict[str, Any]],
) -> None:
    sandbox = str(profile.get("sandbox", ""))
    if profile_name in READ_ONLY_PROFILES and sandbox != "read-only":
        findings.append(_finding(connector_id, profile_name, "read-only Codex profile must use sandbox: read-only"))
    if profile_name not in READ_ONLY_PROFILES and sandbox != "workspace-write":
        findings.append(_finding(connector_id, profile_name, "writer Codex profile must use sandbox: workspace-write"))
    if "--sandbox" not in template:
        findings.append(_finding(connector_id, profile_name, "Codex template must pass --sandbox"))
    if "--output-schema" not in template:
        findings.append(_finding(connector_id, profile_name, "Codex template must pass --output-schema"))
    if "{workspace}" not in template:
        findings.append(_finding(connector_id, profile_name, "Codex template must bind {workspace}"))


def _validate_claude_profile(
    connector_id: str,
    profile_name: str,
    profile: dict[str, Any],
    template: str,
    findings: list[dict[str, Any]],
) -> None:
    required = ["--bare", "--output-format json", "--json-schema", "{output_schema_json}"]
    for fragment in required:
        if fragment not in template:
            findings.append(_finding(connector_id, profile_name, f"Claude template must include {fragment}"))
    if str(profile.get("mode", "")) != "bare-print":
        findings.append(_finding(connector_id, profile_name, "Claude profile mode must be bare-print"))


def _tool_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    return {part.strip().lower() for part in str(value).split(",") if part.strip()}


def _finding(connector: str, profile: str, message: str) -> dict[str, str]:
    return {"connector": connector, "profile": profile, "message": message}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
