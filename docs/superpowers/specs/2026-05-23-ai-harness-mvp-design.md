# AI Automation Development Harness MVP Design

## Goal

Build a user-configurable AI automation development harness where roles are neutral Role Profiles, Codex and Claude Code are Runtime Adapters, and every writer run is isolated by worktree, branch, trace, evidence, and pull request ownership.

## Core Principles

The repository has one canonical project instruction entry point: `AGENTS.md`.
Runtime-specific files may bridge into that instruction at run time, but they must not become separate sources of truth. `CLAUDE.md` is treated as an ephemeral adapter artifact and is ignored by git.

The harness does not decide that Codex is an implementer or Claude Code is a reviewer. The user decides runtime assignment in `.ai/assignments.yml`. The harness only resolves role, runtime, permissions, skills, workspace isolation, state, trace, and PR evidence.

Every writing run has a single owner and must use an isolated workspace. Read-only runs may share clean checkouts or PR diffs, but the moment a run writes repository files it must become a writer run with its own worktree, branch, trace, and PR.

## MVP Scope

The first version is a local CLI scaffold. It does not invoke Codex or Claude Code directly. It creates the repo contract that future runtime adapters will use.

The CLI provides:

- `harness init` to create the canonical scaffold.
- `harness validate` to check scaffold consistency.
- `harness create-run` to allocate a run id, branch name, worktree path, assignment, trace skeleton, and evidence bundle.
- `harness pr-body` to render a PR body from run evidence.

The MVP includes runtime adapter metadata for Codex and Claude Code, but execution is intentionally deferred. This keeps the architecture neutral and testable before integrating actual agent processes.

## Repository Contract

The generated target repository layout is:

```text
AGENTS.md
.ai/
  harness.yml
  assignments.yml
  roles/
  runtimes/
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

`AGENTS.md` contains the hard operating rules and navigation map. `.ai/roles/*.yml` contains Role Profiles. `.ai/assignments.yml` maps roles to runtimes and allowed skills. `.ai/runtimes/*.yml` describes adapter behavior. `.ai/rules/*.yml` contains policy such as state transitions, review rubrics, PR gates, CI/eval gates, permission boundaries, and skill evolution. `.ai/schemas/*.schema.json` defines structured artifacts.

`.agents/skills` and `.claude/skills` are runtime-specific installation targets. `.ai/skills` is the neutral registry. Runtime adapters may sync selected skills into runtime-specific directories per assignment policy.

## Role Profiles

Each role profile is a neutral identity document. It defines:

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

Writer role profiles require an isolated worktree, branch, trace, evidence bundle, and PR. Read-only role profiles must not modify repository files.

## Runtime Assignment

`.ai/assignments.yml` maps role ids to runtime ids:

```yaml
assignments:
  backend-implementer:
    runtime: codex
    allowed_skills:
      - backend-implementation
      - pr-evidence-bundle
  pr-reviewer:
    runtime: claude-code
    allowed_skills:
      - pr-reviewer
```

The same role can be reassigned to another runtime without editing the role profile.

## Run Model

An Agent Run is:

```text
Role + Runtime + Task + Worktree + Branch + Permissions + Skills + Trace
```

Writer runs use:

```text
branch: ai/<issue-id>/<role-id>/<run-id>
worktree: .worktrees/<run-id>-<role-id>
trace: .ai/runs/<run-id>/
```

Read-only runs may omit branch and worktree creation but still produce trace artifacts.

## PR Policy

Every writer run should correspond to one PR. A PR has one current writer owner. Reviewers do not directly modify implementer branches. Review and CI failures are repaired by the PR owner by default. Future versions may support owner transfer with a branch lock and trace entry.

Every AI PR body includes:

- agent role id
- runtime id
- run id
- role profile path
- role profile hash
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
- role ids match filenames
- assignments reference existing roles and runtimes
- assigned skills are allowed by the role profile
- runtime definitions exist
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

