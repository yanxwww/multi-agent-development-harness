from __future__ import annotations

from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> Any:
    return loads_yaml(path.read_text())


def loads_yaml(text: str) -> Any:
    lines = _tokenize(text)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError(f"Could not parse YAML near line {index + 1}")
    return value


def _tokenize(text: str) -> list[tuple[int, str]]:
    tokens: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError("Tabs are not supported in harness YAML")
        indent = len(raw) - len(raw.lstrip(" "))
        tokens.append((indent, raw.strip()))
    return tokens


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or not content.startswith("- "):
            break
        item_text = content[2:].strip()
        index += 1
        if item_text:
            items.append(_parse_scalar(item_text))
            continue
        if index < len(lines) and lines[index][0] > indent:
            item, index = _parse_block(lines, index, lines[index][0])
            items.append(item)
        else:
            items.append(None)
    return items, index


def _parse_map(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    data: dict[str, Any] = {}
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or content.startswith("- "):
            break
        key, sep, rest = content.partition(":")
        if not sep:
            raise ValueError(f"Expected mapping entry, got {content!r}")
        key = key.strip()
        rest = rest.strip()
        index += 1
        if rest:
            data[key] = _parse_scalar(rest)
            continue
        if index < len(lines) and lines[index][0] > indent:
            value, index = _parse_block(lines, index, lines[index][0])
            data[key] = value
        else:
            data[key] = None
    return data, index


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "~"}:
        return None
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value

