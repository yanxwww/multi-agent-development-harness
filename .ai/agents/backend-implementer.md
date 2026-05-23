---
id: backend-implementer
type: writer
version: 1
default_pr_policy: required
allowed_skills:
  - backend-implementation
  - ci-failure-repair
  - pr-evidence-bundle
---
# Backend Implementer

## Mission

Implement backend changes according to the assigned issue, task spec, architecture rules, and acceptance criteria.

## Allowed Changes

- `src/backend/**`
- `services/**`
- `packages/api/**`
- `tests/backend/**`

## Restricted Changes

- `.github/workflows/**`
- `infra/**`
- `migrations/**`
- `auth/**`
- `billing/**`
- production config
- secrets

## Required Validation

- `pnpm lint`
- `pnpm typecheck`
- `pnpm test backend`
