# AI Automation Development Harness MVP Design

## Goal

Build a user-configurable AI automation development harness where the scheduler targets neutral agent identities, Codex CLI and Claude Code CLI are private connector bindings, and every writer run is isolated by worktree, branch, trace, evidence, and pull request ownership.

## Core Principles

The repository has one canonical project instruction entry point: `AGENTS.md`.
Runtime-specific files may bridge into that instruction at run time, but they must not become separate sources of truth. `CLAUDE.md` is treated as an ephemeral adapter artifact and is ignored by git.

The scheduler does not decide that Codex is an implementer or Claude Code is a reviewer. The scheduler only sees `.ai/agent-catalog.yml` and emits `SchedulePlan` JSON targeting `agent_id`. The deterministic dispatcher privately resolves `agent_id -> connector profile` from `.ai/private/assignments.yml`.

Every writing run has a single owner and must use an isolated workspace. Read-only runs may share clean checkouts or PR diffs, but the moment a run writes repository files it must become a writer run with its own worktree, branch, trace, and PR.

## MVP Scope

The first version is a local CLI scaffold. It creates the repo contract and deterministic connector execution path that Codex CLI, Claude Code CLI, or test connectors can use.

The CLI provides:

- `harness init` to create the canonical scaffold.
- `harness validate` to check scaffold consistency.
- `harness create-run` to allocate a run id, branch name, worktree path, private connector binding, trace skeleton, and evidence bundle for one agent identity.
- `harness dispatch-plan` to validate a runtime-blind SchedulePlan and prepare deterministic AgentRun records through private connector bindings.
- `harness connector-command` to render the Codex CLI or Claude Code CLI command for a prepared AgentRun without executing it.
- `harness run-connector` to re-derive and execute a rendered connector command with stdout/stderr capture, JSON event extraction, timeout, retry, and exit trace.
- `harness validation-gate` to run or explicitly skip policy validation commands and write validation gate artifacts.
- `harness pr-gate` to render a PR body for writer runs and block runs missing connector, validation, evidence, or PR body requirements.
- `harness dispatch-run` to chain `dispatch-plan -> connector-command -> run-connector -> validation-gate -> pr-gate` deterministically, with optional commit/push and PR command preparation.
- `harness pr-body` to render a PR body from run evidence.
- `harness diff-gate` to confirm the writer worktree contains auditable changes and capture `diff.patch`.
- `harness commit-command` and `harness run-commit-command` to render and execute deterministic git add/commit steps with trace.
- `harness push-command` and `harness run-push-command` to render and execute deterministic branch push commands with trace.
- `harness pr-command` to render a gated `gh pr create` command after PR readiness passes.
- `harness run-pr-command` to execute a rendered PR command with stdout/stderr, timeout, exit code, and trace capture.
- `harness ci-eval-gate` to evaluate run-local CI and eval result artifacts.
- `harness review-gate` to block unresolved blocking or major review findings.
- `harness writer-lock` and `harness writer-transfer` to enforce single branch writer ownership and audited repair handoff.
- `harness risk-approval-gate` to validate autonomous high-risk approval from `risk-approval-agent`.
- `harness merge-gate` to evaluate merge readiness without merging.
- `harness merge-command` and `harness run-merge-command` to render and execute deterministic `gh pr merge` commands after merge readiness passes.
- `harness skill-evolution-plan` to recommend a dedicated skill-curator writer PR from repeated feedback patterns.
- `harness lifecycle-run` to chain post-publication lifecycle gates and skill evolution planning deterministically.

The MVP includes connector contract metadata for Codex CLI and Claude Code CLI. Connector, git publication, and PR execution are mediated through rendered command artifacts so the dispatcher remains deterministic, traceable, and testable.

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
  locks/
    branches/
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

`dispatch-plan` validates the task dependency graph before creating child runs. Unknown dependencies, duplicate task ids, and cycles are rejected. Schedule and child run ids must match the safe run id grammar, so plan input cannot escape `.ai/runs`, `.worktrees`, or branch templates.

`dispatch-run` keeps this boundary intact. It first prepares child AgentRun records from the scheduler-visible plan, then the dispatcher privately renders and executes each connector command, records connector execution, runs validation, and evaluates PR readiness. Child runs are released only after their declared dependencies have succeeded; dependents are marked `blocked` if a prerequisite fails. When `--commit-and-push` is enabled, it runs the deterministic publication chain for gated writer runs. When `--prepare-pr-command` is enabled, it also renders PR creation commands after the writer branch has passed the enabled publication gates.

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

After the PR gate passes and the branch push has succeeded, `harness pr-command` can produce a deterministic `gh pr create` command artifact. `harness run-pr-command` can execute that artifact if the local GitHub CLI is authenticated. The command artifact is separate from gate evaluation so audit and execution can be split.

The deterministic writer publication chain is:

```text
diff-gate -> commit-command -> run-commit-command -> push-command -> run-push-command -> pr-command
```

Each stage writes a run-local artifact and trace event so branch publication can be reviewed independently from agent execution.

After publication, lifecycle gates evaluate PR readiness without giving AI agents direct merge authority:

```text
ci-eval-gate -> review-gate -> writer-lock -> risk-approval-gate when high risk -> merge-gate
```

`risk-approval-agent` is the autonomous continuous approver for high-risk runs. It produces `risk_approval.json`, and the deterministic `risk-approval-gate` validates that decision before high-risk merge readiness can pass.

`writer-transfer` supports controlled repair ownership transfer for the same branch. `skill-evolution-plan` converts repeated findings into a runtime-blind SchedulePlan for `skill-curator`, which must produce its own writer run and Skill Update PR.

`lifecycle-run` executes the full deterministic post-publication lifecycle:

```text
writer-lock -> ci-eval-gate -> review-gate -> risk-approval-gate -> merge-gate -> skill-evolution-plan
```

It writes `lifecycle_run.json` and returns success only when `merge-gate` passes. Skill evolution planning still runs when merge is blocked, so repeated review or validation patterns can generate a dedicated `skill-curator` follow-up PR.

After `merge-gate` passes and `pr_execution.json` confirms PR creation, `harness merge-command` can produce a deterministic `gh pr merge <branch>` command artifact. `harness run-merge-command` re-derives that artifact before execution, rejects mutations, captures stdout/stderr, and writes `merge_execution.json`. It uses normal GitHub CLI permissions and branch protection; it does not add an admin or bypass path.

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

`harness validation-gate` checks run-level validation evidence:

- validation commands come from run metadata for managed runs, with evidence-only fallback for manual runs
- every validation command has a pass/fail/skipped status
- command stdout, stderr, exit code, and timeout status are recorded
- `evidence.json` and `validation_gate.json` stay in sync

`harness pr-gate` checks writer PR readiness:

- evidence bundle exists
- connector execution succeeded
- validation passed or was explicitly skipped
- PR body exists

`harness pr-command` checks PR command readiness:

- run is a writer run
- `pr_gate.json` status is `passed`
- `push_execution.json` status is `succeeded`
- PR body exists
- branch name is present

Command execution hardening:

- managed `connector_command.json` artifacts are re-derived from run metadata and connector profile before execution
- managed `commit_command.json`, `push_command.json`, and `pr_command.json` artifacts are re-derived from run metadata before execution
- mutated argv, display strings, git steps, worktree, branch, or PR head values are rejected before subprocess execution
- failed dispatch-plan cleanup removes child run metadata, owned worktrees, and owned branches created before the failure

`harness diff-gate` checks commit readiness:

- run is a writer run
- declared worktree exists
- `git status --porcelain` has changed files
- `diff.patch` is captured

`harness run-commit-command` checks post-commit state:

- commit command steps executed successfully
- commit SHA is recorded
- post-commit worktree status is clean

`harness push-command` checks push readiness:

- commit execution succeeded
- commit SHA exists
- branch name is present

`harness ci-eval-gate` checks post-publication quality readiness:

- `ci_results.json` exists
- `eval_results.json` exists
- both top-level statuses are `passed`
- every listed check is `passed` or explicitly `skipped`

`harness review-gate` checks review readiness:

- unresolved `blocking` findings block
- unresolved `major` findings block
- unresolved `minor` and `note` findings are recorded as nonblocking

`harness writer-lock` and `harness writer-transfer` check branch ownership:

- only one current owner run can hold a branch lock
- a repair run can take ownership only through an explicit transfer from the current owner
- every lock acquisition and transfer writes run-local artifacts and trace events

`harness merge-gate` checks merge readiness:

- PR gate passed
- branch push succeeded
- CI/Eval gate passed
- review gate passed
- current writer lock owner matches the run
- high-risk runs include a passed autonomous risk approval gate

`harness skill-evolution-plan` checks feedback mining readiness:

- repeated review finding patterns are counted
- patterns observed at least twice produce a `skill-curator` SchedulePlan
- skill updates remain writer runs and must open their own PR

`harness lifecycle-run` checks lifecycle orchestration readiness:

- writer ownership is acquired or confirmed
- CI/Eval, review, risk approval, and merge gates are run in order
- merge readiness is summarized in `lifecycle_run.json`
- skill evolution planning runs even when merge is blocked

`harness merge-command` checks merge execution readiness:

- merge gate passed and is merge-ready
- PR execution succeeded
- head branch comes from run metadata
- merge method is one of `merge`, `squash`, or `rebase`
- command artifacts are re-derived and mutation-checked before execution

## Non-Goals

The MVP does not:

- run hosted CI directly
- install skills into external agent environments
- implement stacked PRs or integration PRs
- bypass GitHub branch protection or required checks

These are adapter and orchestration layers that can be added after the repo contract is stable.
