# AI Development Harness

This repository implements a local CLI scaffold for a Codex / Claude Code AI automation development harness.

The harness is intentionally runtime-blind at the scheduling layer:

- The scheduler targets agent identities from `.ai/agent-catalog.yml`.
- Agent identity docs live in `.ai/agents/*.md`.
- Dispatcher-only connector bindings live in `.ai/private/assignments.yml`.
- Codex CLI and Claude Code CLI are connector contracts in `.ai/connectors/*.yml`.
- `AGENTS.md` is the only canonical repository-level instruction entry point.
- `CLAUDE.md` is not committed; a future Claude Code adapter can bridge to `AGENTS.md` at run time.

## Commands

```bash
python3 -m ai_harness init --target .
python3 -m ai_harness validate --target .
python3 -m ai_harness create-run --target . --issue 123 --agent backend-implementer --task task.json --no-worktree
python3 -m ai_harness pr-body --target . --run run-20260523-001
python3 -m ai_harness dispatch-plan --target . --issue 123 --plan schedule_plan.json --run-id run-schedule-001 --no-worktree
```

Installable entry point:

```bash
pip install -e .
harness init --target .
```

## Writer Run Rule

Every writer agent run should have its own:

- worktree
- branch
- trace
- evidence bundle
- pull request owner

Read-only runs can produce comments, findings, artifacts, and traces without creating a PR. If a read-only agent identity writes repository files, it becomes a writer run.

## Scheduler / Dispatcher Boundary

The scheduler only emits `SchedulePlan` JSON containing `agent_id`, task, dependency, mode, expected output, PR requirement, and risk. It must not choose Codex, Claude Code, a model, credentials, or CLI flags.

The deterministic dispatcher validates the plan, resolves `agent_id -> connector profile` through `.ai/private/assignments.yml`, creates run records, prepares worktrees for writer runs, and records dispatch trace.

## Current MVP Boundaries

This version creates and validates the repo contract and prepares dispatch runs from a runtime-blind plan. It does not invoke Codex or Claude Code, open GitHub PRs, install skills into external runtimes, or enforce branch locks. Those belong in the next orchestration layer.
