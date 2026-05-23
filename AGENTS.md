# AGENTS.md

## Mission

This repository is developed through a PR-gated AI automation development harness.
All agents must work through issues, task specs, branches, validation, reviews, and pull requests.

## Canonical Project Knowledge

Read only what is relevant to the assigned task.

- Architecture: `docs/architecture/`
- ADRs: `docs/adr/`
- Product specs: `docs/product-specs/`
- Runbooks: `docs/runbooks/`
- Role profiles: `.ai/roles/`
- Runtime assignments: `.ai/assignments.yml`
- Skills: `.ai/skills/`
- Review rubric: `.ai/rules/review-rubric.yml`
- Security policy: `.ai/rules/security-policy.yml`
- Merge policy: `.ai/rules/auto-merge-policy.yml`

## Agent Operating Rules

1. Confirm assigned role before acting.
2. Confirm allowed paths before editing.
3. Use the assigned branch and worktree only.
4. Do not push to `main`.
5. Do not approve your own PR unless explicitly allowed.
6. Do not access production secrets.
7. Do not bypass branch protection.
8. Run required validation before opening or updating a PR.
9. Attach an Evidence Bundle to every writer PR.
10. Respond to every review finding with `fixed`, `rejected-with-reason`, or `escalated`.

## Workspace Isolation

Every writer agent run must work in its own git worktree and branch.
Reviewer, planner, and QA agents may use read-only snapshots unless explicitly assigned as writers.

## Runtime Adaptation

`AGENTS.md` is the only canonical repository-level instruction source.
Do not commit `CLAUDE.md`. Claude Code adapters may bridge to this file at run time with an ephemeral symlink, `@AGENTS.md` import, or injected instructions.

## Skills

Use only skills allowed by the resolved role assignment.
Do not treat a skill as permission escalation.

## PR Requirements

Every writer PR must include:

- linked issue
- task summary
- changed files
- tests added or updated
- validation results
- risk notes
- rollback plan
- unresolved questions
