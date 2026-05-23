# AI Harness MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable local CLI that scaffolds, validates, and dispatches runtime-blind agent identity runs for a Codex CLI / Claude Code CLI automation harness.

**Architecture:** A Python standard-library CLI owns the scaffold templates, a YAML-subset parser for generated config files, run metadata generation, SchedulePlan validation, deterministic dispatch preparation, and PR body rendering. The scheduler sees only `.ai/agent-catalog.yml`; the dispatcher privately resolves `.ai/private/assignments.yml` into connector profiles.

**Tech Stack:** Python 3.13, `argparse`, `json`, `unittest`, git CLI for optional worktree creation.

---

### Post-MVP Hardening Added

- [x] Enforce safe `run-*` ids before using ids in filesystem paths, worktree paths, or branch templates.
- [x] Validate SchedulePlan dependencies, including duplicate task ids, unknown dependencies, and cycles.
- [x] Clean up owned child run directories, worktrees, and local branches when `dispatch-plan` fails partway through worktree creation.
- [x] Re-derive managed connector, commit, push, and PR command artifacts before subprocess execution so mutable JSON artifacts cannot change execution authority.
- [x] Source managed validation commands from run metadata, not mutable evidence JSON.
- [x] Require successful branch push before rendering or executing PR creation commands.
- [x] Block dependent child runs in `dispatch-run` when prerequisites fail.

---

### Task 1: Runtime-Blind Scaffold Tests

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Test canonical scaffold**

Assert that `harness init` creates `AGENTS.md`, `.ai/agent-catalog.yml`, `.ai/private/assignments.yml`, `.ai/agents/scheduler-agent.md`, `.ai/schemas/schedule_plan.schema.json`, `.claude/settings.json`, and `.gitignore` with `CLAUDE.md`.

- [x] **Step 2: Test scheduler catalog visibility**

Assert that `.ai/agent-catalog.yml` contains agent identities but no `codex-cli` or `claude-code-cli`, while `.ai/private/assignments.yml` contains connector bindings.

### Task 2: Agent Identity Run Tests

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `ai_harness/runs.py`
- Modify: `ai_harness/cli.py`

- [x] **Step 1: Test `create-run --agent`**

Assert that a backend writer run resolves `agent_id`, private connector, connector profile, branch name, worktree path, trace, and evidence.

- [x] **Step 2: Test PR body rendering**

Assert that PR body output includes agent identity, connector, run id, issue closure, validation placeholders, risk, rollback, and unresolved questions.

### Task 3: Deterministic Dispatcher Tests

**Files:**
- Create: `ai_harness/dispatch.py`
- Modify: `tests/test_cli.py`
- Modify: `ai_harness/cli.py`

- [x] **Step 1: Test valid SchedulePlan dispatch**

Given a SchedulePlan with `backend-implementer` and `pr-reviewer`, assert that `dispatch-plan` creates a schedule run directory, copies the plan, writes `dispatch_log.jsonl`, creates child run metadata, and resolves connector bindings privately.

- [x] **Step 2: Test forbidden scheduler leakage**

Assert that a SchedulePlan containing `connector`, `runtime`, `model`, or credential-like fields is rejected before dispatch.

### Task 4: Scaffold and Validation Implementation

**Files:**
- Modify: `ai_harness/scaffold.py`
- Modify: `ai_harness/validation.py`

- [x] **Step 1: Generate new scaffold**

Generate `AGENTS.md`, `.ai/agent-catalog.yml`, `.ai/private/assignments.yml`, `.ai/agents/*.md`, `.ai/connectors/*.yml`, rules, schemas, skill registry, `.agents/skills/.gitkeep`, `.claude/skills/.gitkeep`, `.claude/settings.json`, docs directories, and `.ai/runs/.gitkeep`.

- [x] **Step 2: Validate new scaffold**

Check required files, agent doc front matter ids, scheduler-visible catalog safety, private binding references, connector profile references, schema JSON syntax, and `CLAUDE.md` gitignore policy.

### Task 5: Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-23-ai-harness-mvp-design.md`

- [x] **Step 1: Run tests**

Run: `python3 -m unittest discover -s tests -v`

- [x] **Step 2: Run scaffold validation**

Run: `python3 -m ai_harness validate --target .`

- [x] **Step 3: Run final smoke dispatch**

Run:

```bash
tmp="$(mktemp -d)"
python3 -m ai_harness init --target "$tmp"
python3 -m ai_harness validate --target "$tmp"
cat > "$tmp/schedule_plan.json" <<'JSON'
{"run_plan":[{"agent_id":"backend-implementer","task_id":"T3","mode":"writer","depends_on":[],"expected_output":"branch_pr","requires_pr":true,"risk_level":"medium","success_criteria":["Backend tests pass"]}],"blocked":[],"risk_notes":[]}
JSON
python3 -m ai_harness dispatch-plan --target "$tmp" --issue 1 --plan "$tmp/schedule_plan.json" --run-id run-schedule-smoke --no-worktree
```

Expected: every command exits `0`, and the schedule run contains `schedule_plan.json`, `dispatch_log.jsonl`, and a child backend run.
