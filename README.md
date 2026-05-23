# AI Development Harness

This repository implements a local CLI scaffold for a Codex / Claude Code AI automation development harness.

The harness is intentionally role-neutral:

- Role Profiles live in `.ai/roles/*.yml`.
- Runtime assignment lives in `.ai/assignments.yml`.
- Codex and Claude Code are Runtime Adapters in `.ai/runtimes/*.yml`.
- `AGENTS.md` is the only canonical repository-level instruction entry point.
- `CLAUDE.md` is not committed; a future Claude Code adapter can bridge to `AGENTS.md` at run time.

## Commands

```bash
python3 -m ai_harness init --target .
python3 -m ai_harness validate --target .
python3 -m ai_harness create-run --target . --issue 123 --role backend-implementer --task task.json --no-worktree
python3 -m ai_harness pr-body --target . --run run-20260523-001
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

Read-only runs can produce comments, findings, artifacts, and traces without creating a PR. If a read-only role writes repository files, it becomes a writer run.

## Current MVP Boundaries

This version creates and validates the repo contract. It does not invoke Codex or Claude Code, open GitHub PRs, install skills into external runtimes, or enforce branch locks. Those belong in the next orchestration layer.

