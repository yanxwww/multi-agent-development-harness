# Automation Hardening Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining automation gaps by adding executable repair dispatch, sanitized scheduler workspaces, connector permission contract checks, event-driven entrypoints, and artifact retention/redaction policy.

**Architecture:** Keep AI decisions outside the deterministic kernel. New commands and helpers produce auditable JSON artifacts, reuse existing `dispatch-run` / `automation-run` paths, and avoid giving the scheduler direct access to private connector bindings. Safety-sensitive actions default to report/dry-run unless the caller explicitly requests execution.

**Tech Stack:** Python stdlib CLI, existing YAML-lite loader, GitHub CLI oriented workflows, unittest coverage.

---

### Task 1: Auto Repair Dispatch Loop

**Files:**
- Create: `ai_harness/repair.py`
- Modify: `ai_harness/automation.py`
- Modify: `ai_harness/cli.py`
- Test: `tests/test_cli.py`

- [x] Add a failing test that `automation-run --auto-repair --run-auto-repair` dispatches the generated `repair_schedule_plan.json`.
- [x] Implement `run_auto_repair(...)` to render or reuse a repair schedule, call `dispatch_run`, and write `auto_repair_run.json`.
- [x] Wire `automation-run` to invoke `run_auto_repair` when lifecycle blocks and `--run-auto-repair` is set.
- [x] Run the targeted test and full CLI test suite.

### Task 2: Scheduler Sanitized Workspace

**Files:**
- Modify: `ai_harness/scheduler.py`
- Modify: `ai_harness/scaffold.py`
- Modify: `.gitignore`
- Test: `tests/test_cli.py`

- [x] Add a failing test proving `scheduler-run` executes from `.ai/scheduler-workspaces/<run-id>` and that workspace lacks `.ai/private`.
- [x] Build a sanitized scheduler workspace containing only AGENTS, visible agent catalog/docs/rules/schemas/skills/docs, never private bindings.
- [x] Update scheduler run metadata before rendering connector commands.
- [x] Ensure scaffold `.gitignore` ignores scheduler workspaces.

### Task 3: Connector Permission Contract

**Files:**
- Create: `ai_harness/connector_contracts.py`
- Modify: `ai_harness/validation.py`
- Modify: `ai_harness/cli.py`
- Test: `tests/test_cli.py`

- [x] Add failing tests for read-only profiles that expose write tools and for CLI contract reports.
- [x] Validate Codex sandbox expectations and Claude bare/json-schema expectations.
- [x] Integrate contract validation into `validate`.
- [x] Add `connector-contracts` command that writes `.ai/connector_contracts.json`.

### Task 4: Event-Driven Automation Entrypoint

**Files:**
- Create: `ai_harness/daemon.py`
- Modify: `ai_harness/cli.py`
- Modify: `ai_harness/scaffold.py`
- Create: `.github/workflows/ai-harness-automation.yml`
- Test: `tests/test_cli.py`

- [x] Add a failing dry-run test for `automation-daemon --event-file`.
- [x] Convert GitHub issue/PR/workflow events into `scheduler_task.json` under `.ai/events/<run-id>/`.
- [x] Add `--execute` mode that calls `automation-run` from the generated scheduler task.
- [x] Add a GitHub Actions workflow that defaults to dry-run unless explicitly enabled with repository configuration.

### Task 5: Artifact Retention and Redaction Policy

**Files:**
- Create: `ai_harness/retention.py`
- Modify: `ai_harness/cli.py`
- Modify: `ai_harness/scaffold.py`
- Create: `.ai/rules/artifact-retention.yml`
- Test: `tests/test_cli.py`

- [x] Add a failing test that a retention report detects secret-like content in run artifacts.
- [x] Implement `artifact-retention-report` to scan `.ai/runs`, classify local-only artifacts, and report redaction findings.
- [x] Add artifact retention/redaction policy to scaffold and current repo.
- [x] Document the new operational boundary in `README.md`.
