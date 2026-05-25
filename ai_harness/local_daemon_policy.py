from __future__ import annotations

from pathlib import Path


class LocalDaemonPolicyError(Exception):
    pass


VALID_TRIGGER_ACTIONS = {"run", "plan", "repair", "review", "status"}
DEFAULT_LABEL_ACTIONS = {
    "ai:auto": "run",
    "ai:plan": "plan",
    "ai:repair": "repair",
    "ai:review": "review",
}
DEFAULT_COMMENT_ACTIONS = {
    "/ai run": "run",
    "/ai repair": "repair",
    "/ai status": "status",
}
POLICY_RELATIVE_PATH = ".ai/rules/local-daemon.yml"


def load_trigger_policy(target: Path) -> dict[str, dict[str, str]]:
    path = target / POLICY_RELATIVE_PATH
    if not path.exists():
        return {
            "label_actions": dict(DEFAULT_LABEL_ACTIONS),
            "comment_actions": dict(DEFAULT_COMMENT_ACTIONS),
        }
    return parse_trigger_policy_text(path.read_text(), source=POLICY_RELATIVE_PATH)


def validate_trigger_policy(target: Path) -> None:
    path = target / POLICY_RELATIVE_PATH
    if path.exists():
        parse_trigger_policy_text(path.read_text(), source=POLICY_RELATIVE_PATH)


def parse_trigger_policy_text(text: str, source: str = POLICY_RELATIVE_PATH) -> dict[str, dict[str, str]]:
    policy = {
        "label_actions": _parse_action_section(text, "label_actions", source),
        "comment_actions": _parse_action_section(text, "comment_actions", source),
    }
    for section, actions in policy.items():
        for trigger, action in actions.items():
            if action not in VALID_TRIGGER_ACTIONS:
                raise LocalDaemonPolicyError(
                    f"{source} {section}.{trigger} uses unsupported action: {action}"
                )
    return policy


def _parse_action_section(text: str, section: str, source: str) -> dict[str, str]:
    actions: dict[str, str] = {}
    in_section = False
    section_seen = False
    section_indent = 0
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = raw.strip()
        if indent == 0:
            key, sep, rest = content.partition(":")
            in_section = sep == ":" and key == section and not rest.strip()
            if in_section:
                section_seen = True
                section_indent = indent
            continue
        if not in_section:
            continue
        if indent <= section_indent:
            in_section = False
            continue
        trigger, sep, action = content.rpartition(":")
        if not sep or not trigger.strip() or not action.strip():
            raise LocalDaemonPolicyError(
                f"{source} {section} entries must use '<trigger>: <action>'"
            )
        actions[_strip_quotes(trigger.strip())] = _strip_quotes(action.strip())
    if not section_seen:
        raise LocalDaemonPolicyError(f"{source} is missing required section: {section}")
    return actions


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value
