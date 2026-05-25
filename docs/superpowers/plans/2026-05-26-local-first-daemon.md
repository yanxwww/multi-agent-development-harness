# Local First Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first GitHub sync daemon so GitHub stores issues, PRs, CI, and status comments while Codex/Claude execution stays on the local machine.

**Architecture:** Keep GitHub as the synchronization surface and keep agent runtimes local. A deterministic local daemon polls GitHub through `gh`, converts label/comment triggers into local scheduler tasks, optionally runs the existing `automation-run` chain with full local flags, and syncs concise status comments back to GitHub without uploading raw traces.

**Tech Stack:** Python stdlib CLI, GitHub CLI subprocesses, existing `automation-run`, unittest coverage.

---

### Task 1: Local Daemon State and Trigger Polling

**Files:**
- Create: `ai_harness/local_daemon.py`
- Modify: `ai_harness/cli.py`
- Modify: `ai_harness/scaffold.py`
- Test: `tests/test_cli.py`

- [x] Add failing tests for `github-sync-poll` discovering `ai:auto` label and `/ai run` comment triggers.
- [x] Implement GitHub issue/PR polling through `gh ... --json`.
- [x] Write `.ai/local-daemon/state.json`, `.ai/local-daemon/events/<event-id>/event.json`, and `scheduler_task.json`.
- [x] Skip already processed event ids on later polls.
- [x] Acquire an exclusive local poll lease before processing triggers.

### Task 2: Local Daemon Execution Wrapper

**Files:**
- Modify: `ai_harness/local_daemon.py`
- Modify: `ai_harness/cli.py`
- Test: `tests/test_cli.py`

- [x] Add failing tests for `local-daemon --once` delegating to the same polling path.
- [x] Add `local-daemon` command with `--once`, `--interval`, and `--execute`.
- [x] In execute mode, call `automation-run` with local full-chain flags: commit/push, PR command execution, GitHub checks, lifecycle, reviewer, risk approval, repair, and merge.

### Task 3: GitHub Status Sync

**Files:**
- Modify: `ai_harness/local_daemon.py`
- Modify: `ai_harness/cli.py`
- Test: `tests/test_cli.py`

- [x] Add failing tests for status comment sync using fake `gh`.
- [x] Render a concise status comment under the local event directory.
- [x] Execute `gh issue comment` or `gh pr comment` and capture stdout/stderr/result JSON.
- [x] Ensure raw run traces are not embedded in status comments.

### Task 4: Scaffold, Docs, and Launchd Template

**Files:**
- Modify: `ai_harness/scaffold.py`
- Modify: `.gitignore`
- Create: `.ai/local-daemon/launchd/com.ai-harness.local-daemon.plist`
- Modify: `README.md`

- [x] Add local daemon directories and gitignore retention rules.
- [x] Add a launchd plist template for long-running local operation.
- [x] Document the corrected deployment model: GitHub sync layer, local runtime execution layer.
- [x] Run targeted and full tests.
