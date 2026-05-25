# Configurable Local Daemon Triggers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move local daemon GitHub label/comment trigger mappings out of hardcoded Python constants and into committed harness policy.

**Architecture:** Add `.ai/rules/local-daemon.yml` as the canonical trigger policy. `ai_harness.local_daemon` loads that policy when present, validates its shape, falls back to the current defaults when absent, and uses it for polling issue/PR labels and comments.

**Tech Stack:** Python stdlib, existing `yaml_lite` parser, unittest CLI coverage, scaffold validation.

---

### Task 1: Trigger Policy Tests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `ai_harness/scaffold.py`

- [x] Add a failing scaffold test that `.ai/rules/local-daemon.yml` exists after `harness init`.
- [x] Add a failing poll test that custom policy labels/comments create events and built-in defaults do not trigger after override.
- [x] Run the targeted tests and verify they fail for the missing policy loader.

### Task 2: Policy Loading

**Files:**
- Modify: `ai_harness/local_daemon.py`
- Modify: `ai_harness/scaffold.py`
- Create: `.ai/rules/local-daemon.yml`

- [x] Add a default scaffold policy matching the current built-in trigger mappings.
- [x] Load `.ai/rules/local-daemon.yml` as daemon trigger policy.
- [x] Validate `label_actions` and `comment_actions` entries as trigger-to-action mappings.
- [x] Use the loaded policy in `_trigger_events`.
- [x] Keep default behavior when the policy file is absent.

### Task 3: Docs and Version

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `ai_harness/__init__.py`

- [x] Document `.ai/rules/local-daemon.yml`.
- [x] Bump the package version.
- [x] Run targeted tests, `validate`, `connector-contracts`, `git diff --check`, and full unittest discovery.
