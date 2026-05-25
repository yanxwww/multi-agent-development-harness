from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_api_key", re.compile(r"OPENAI_API_KEY\s*=\s*[^\s]+")),
    ("anthropic_api_key", re.compile(r"ANTHROPIC_API_KEY\s*=\s*[^\s]+")),
    ("github_token", re.compile(r"GITHUB_TOKEN\s*=\s*[^\s]+")),
    ("openai_secret_key", re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9_]{10,}\b")),
]
LOCAL_ONLY_NAMES = {
    "stdout.log",
    "stderr.log",
    "connector_events.jsonl",
    "trace.jsonl",
    "prompt.md",
}
LOCAL_ONLY_SUFFIXES = (
    "_stdout.log",
    "_stderr.log",
    ".attempt-1.stdout.log",
    ".attempt-1.stderr.log",
)


def run_artifact_retention_report(target: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    runs_dir = target / ".ai" / "runs"
    if runs_dir.exists():
        for path in sorted(item for item in runs_dir.rglob("*") if item.is_file()):
            relpath = str(path.relative_to(target))
            _collect_retention_findings(path, relpath, findings)
            _collect_redaction_findings(path, relpath, findings)

    report = {
        "status": "findings" if findings else "passed",
        "findings": findings,
        "policy": ".ai/rules/artifact-retention.yml",
        "created_at": _now(),
    }
    (target / ".ai" / "artifact_retention_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _collect_retention_findings(path: Path, relpath: str, findings: list[dict[str, Any]]) -> None:
    if path.name in LOCAL_ONLY_NAMES or path.name.endswith(LOCAL_ONLY_SUFFIXES):
        findings.append(
            {
                "kind": "retention",
                "severity": "note",
                "path": relpath,
                "message": "runtime log artifact should remain local-only unless explicitly redacted",
            }
        )


def _collect_redaction_findings(path: Path, relpath: str, findings: list[dict[str, Any]]) -> None:
    text = _safe_read_text(path)
    if text is None:
        return
    for pattern_id, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(
                {
                    "kind": "redaction",
                    "severity": "blocking",
                    "path": relpath,
                    "pattern": pattern_id,
                    "message": "secret-like content found in run artifact",
                }
            )


def _safe_read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
