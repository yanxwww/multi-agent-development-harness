# AGENTS.md

## Mission

This repository is developed through a PR-gated AI automation development harness.
The scheduler targets agent identities. A deterministic dispatcher privately maps each agent identity to a CLI connector.

## Canonical Project Knowledge

Read only what is relevant to the assigned task.

- Agent catalog visible to scheduler: `.ai/agent-catalog.yml`
- Agent identity docs: `.ai/agents/`
- Dispatcher-only bindings: `.ai/private/assignments.yml`
- Connector contracts: `.ai/connectors/`
- Skills: `.ai/skills/`
- Review rubric: `.ai/rules/review-rubric.yml`
- Security policy: `.ai/rules/security-policy.yml`
- Merge policy: `.ai/rules/auto-merge-policy.yml`

## Scheduler Boundary

The scheduler must output only agent identities, tasks, dependencies, expected outputs, and risk. It must not choose Codex, Claude Code, model names, credentials, shell commands, or connector flags.

## Dispatcher Boundary

The deterministic dispatcher resolves `agent_id -> connector profile`, creates worktrees and branches, records traces, validates schemas, runs gates, and prepares pull request evidence.

## Automated Risk Approval

High-risk writer runs are approved or rejected by `risk-approval-agent` through `risk_approval.json` and `risk-approval-gate`.
The merge gate relies on agentic approval by default.

## Workspace Isolation

Every writer agent run must work in its own git worktree and branch.
Reviewer, planner, scheduler, and read-only QA runs may use read-only snapshots unless explicitly assigned as writers.

## Runtime Adaptation

`AGENTS.md` is the only canonical repository-level instruction source.
Do not commit `CLAUDE.md`. Claude Code connectors may inject this file explicitly with bare non-interactive CLI flags.

## PR Requirements

Every writer PR must include linked issue, task summary, changed files, tests, validation results, risk notes, rollback plan, unresolved questions, agent identity, connector, and run id.
