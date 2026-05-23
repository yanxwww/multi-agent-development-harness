---
id: ci-repair-agent
type: writer
version: 1
default_pr_policy: required
allowed_skills:
  - ci-failure-repair
  - pr-evidence-bundle
---
# CI Repair Agent

## Mission

Repair validation and CI failures through an isolated writer run.

## Required Validation

- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
