from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class ArtifactError(Exception):
    pass


def extract_json_artifact_from_run(
    target: Path,
    run_id: str,
    required_keys: set[str],
    artifact_name: str,
) -> dict[str, Any]:
    run_dir = target / ".ai" / "runs" / run_id
    texts = []
    for filename in ["stdout.log", "connector_events.jsonl"]:
        path = run_dir / filename
        if path.exists():
            texts.append(path.read_text())
    if not texts:
        raise ArtifactError(f"{artifact_name} output is missing for {run_id}")

    for candidate in _iter_json_candidates("\n".join(texts)):
        if isinstance(candidate, dict) and required_keys.issubset(candidate):
            return candidate
    raise ArtifactError(f"could not extract {artifact_name} JSON from connector output for {run_id}")


def _iter_json_candidates(text: str) -> Iterable[Any]:
    seen: set[int] = set()
    stack: list[Any] = list(_decode_json_values(text))
    while stack:
        value = stack.pop(0)
        value_id = id(value)
        if value_id in seen:
            continue
        seen.add(value_id)
        yield value
        if isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, str):
                    stack.extend(_decode_json_values(nested))
                elif isinstance(nested, (dict, list)):
                    stack.append(nested)
        elif isinstance(value, list):
            for nested in value:
                if isinstance(nested, str):
                    stack.extend(_decode_json_values(nested))
                elif isinstance(nested, (dict, list)):
                    stack.append(nested)


def _decode_json_values(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    values = []
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        values.append(value)
    return values
