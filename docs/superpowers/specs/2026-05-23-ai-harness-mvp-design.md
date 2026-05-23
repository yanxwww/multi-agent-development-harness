# AI Automation Development Harness MVP Design

## Goal

Build a user-configurable AI automation development harness where the scheduler targets neutral agent identities, Codex CLI and Claude Code CLI are private connector bindings, and every writer run is isolated by worktree, branch, trace, evidence, and pull request ownership.

## Core Principles

The repository has one canonical project instruction entry point: `AGENTS.md`.
Runtime-specific files may bridge into that instruction at run time, but they must not become separate sources of truth. `CLAUDE.md` is treated as an ephemeral adapter artifact and is ignored by git.

The scheduler does not decide that Codex is an implementer or Claude Code is a reviewer. The scheduler only sees `.ai/agent-catalog.yml` and emits `SchedulePlan` JSON targeting `agent_id`. The deterministic dispatcher privately resolves `agent_id -> connector profile` from `.ai/private/assignments.yml`.

Every writing run has a single owner and must use an isolated workspace. Read-only runs may share clean checkouts or PR diffs, but the moment a run writes repository files it must become a writer run with its own worktree, branch, trace, and PR.

## MVP Scope

The first version is a local CLI scaffold. It does not invoke Codex or Claude Code directly. It creates the repo contract that future CLI connectors will use.

The CLI provides:

- `harness init` to create the canonical scaffold.
- `harness validate` to check scaffold consistency.
- `harness create-run` to allocate a run id, branch name, worktree path, private connector binding, trace skeleton, and evidence bundle for one agent identity.
- `harness dispatch-plan` to validate a runtime-blind SchedulePlan and prepare deterministic AgentRun records through private connector bindings.
- `harness pr-body` to render a PR body from run evidence.

The MVP includes connector contract metadata for Codex CLI and Claude Code CLI, but execution is intentionally deferred. This keeps the architecture neutral and testable before integrating actual agent processes.

## Repository Contract

The generated target repository layout is:

```text
AGENTS.md
.ai/
  harness.yml
  agent-catalog.yml
  private/
    assignments.yml
  agents/
  connectors/
  skills/
  rules/
  schemas/
  runs/
.agents/
  skills/
.claude/
  skills/
  settings.json
.worktrees/
docs/
  architecture/
  adr/
  runbooks/
  product-specs/
  exec-plans/
```

`AGENTS.md` contains the hard operating rules and navigation map. `.ai/agent-catalog.yml` is the scheduler-visible catalog. `.ai/agents/*.md` contains agent identity docs. `.ai/private/assignments.yml` maps agent ids to connector profiles and is only for the dispatcher. `.ai/connectors/*.yml` describes CLI connector contracts. `.ai/rules/*.yml` contains policy such as state transitions, review rubrics, PR gates, CI/eval gates, permission boundaries, and skill evolution. `.ai/schemas/*.schema.json` defines structured artifacts.

`.agents/skills` and `.claude/skills` are connector-specific installation targets. `.ai/skills` is the neutral registry. Connectors may sync selected skills into connector-specific directories per assignment policy.

## Agent Identities

Each agent identity document is a neutral identity document. It defines:

- `id`
- `type`: `read-only`, `writer`, or `hybrid`
- mission
- input artifacts
- output artifacts
- allowed and restricted paths
- required validation
- allowed skills
- escalation rules
- default PR policy

Writer agent identities require an isolated worktree, branch, trace, evidence bundle, and PR. Read-only agent identities must not modify repository files.

## Scheduler / Dispatcher Boundary

The scheduler sees only agent identities and produces a `SchedulePlan`:

```json
{
  "run_plan": [
    {
      "agent_id": "backend-implementer",
      "task_id": "T3",
      "mode": "writer",
      "depends_on": ["T1", "T2"],
      "expected_output": "branch_pr",
      "requires_pr": true,
      "risk_level": "medium",
      "success_criteria": ["Backend tests pass"]
    }
  ],
  "blocked": [],
  "risk_notes": []
}
```

The dispatcher sees `.ai/private/assignments.yml` and resolves `backend-implementer -> codex-cli / writer-workspace`. Connector, model, credentials, and CLI flags are not part of scheduler output.

## Run Model

An Agent Run is:

```text
Agent Identity + Connector Binding + Task + Worktree + Branch + Permissions + Skills + Trace
```

Writer runs use:

```text
branch: ai/<issue-id>/<agent-id>/<run-id>
worktree: .worktrees/<run-id>-<agent-id>
trace: .ai/runs/<run-id>/
```

Read-only runs may omit branch and worktree creation but still produce trace artifacts.

## PR Policy

Every writer run should correspond to one PR. A PR has one current writer owner. Reviewers do not directly modify implementer branches. Review and CI failures are repaired by the PR owner by default. Future versions may support owner transfer with a branch lock and trace entry.

Every AI PR body includes:

- agent identity id
- connector id
- connector profile
- run id
- agent doc path
- agent doc hash
- skills used
- linked issue
- scope
- validation results
- risk notes
- rollback plan
- unresolved questions

## State Machine

The MVP defines the state machine as policy data, not code orchestration:

```text
planned -> workspace_ready -> running -> validation_ready -> pr_ready -> review_ready -> merge_ready
running -> failed
validation_ready -> repair_required
review_ready -> repair_required
repair_required -> running
```

Future orchestrators can enforce the same state transitions.

## Validation

`harness validate` checks:

- required files exist
- agent ids match `.ai/agents/*.md` front matter
- agent catalog references existing agent docs
- scheduler-visible catalog does not expose connector/runtime/model keys
- private bindings reference existing agents, connectors, and profiles
- connector definitions exist
- schemas are valid JSON
- `CLAUDE.md` is ignored instead of committed as canonical memory

## Non-Goals

The MVP does not:

- invoke Codex or Claude Code
- create GitHub PRs
- run CI
- install skills into external agent environments
- implement stacked PRs or integration PRs
- enforce branch locks

These are adapter and orchestration layers that can be added after the repo contract is stable.
