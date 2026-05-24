# Lifecycle Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic post-publication lifecycle gates for CI/Eval, review findings, writer ownership locks, merge readiness, and skill evolution scheduling.

**Architecture:** Keep scheduler decisions runtime-blind and make each lifecycle step a local artifact-producing gate. The dispatcher still does not merge directly; it records readiness, ownership, and follow-up plans through JSON artifacts that can be reviewed and composed by later automation.

**Tech Stack:** Python standard library CLI, `unittest`, JSON artifacts, git branch metadata already produced by writer runs.

---

### Task 1: Lifecycle Gate Red Tests

**Files:**
- Modify: `tests/test_cli.py`

- [x] Add tests for `ci-eval-gate` pass/fail behavior.
- [x] Add tests for `review-gate` unresolved blocking/major findings.
- [x] Add tests for `writer-lock` and `writer-transfer` branch ownership.
- [x] Add tests for `merge-gate` requiring push, PR gate, CI/Eval, review, current lock owner, and high-risk human approval.
- [x] Add tests for `skill-evolution-plan` generating a skill-curator SchedulePlan from repeated feedback patterns.

### Task 2: Lifecycle Gate Implementation

**Files:**
- Create: `ai_harness/lifecycle.py`
- Modify: `ai_harness/cli.py`

- [x] Implement CI/Eval result loading and `ci_eval_gate.json`.
- [x] Implement review finding loading and `review_gate.json`.
- [x] Implement branch lock acquisition and owner transfer under `.ai/locks/branches/`.
- [x] Implement `merge_gate.json` readiness evaluation.
- [x] Implement `skill_evolution_plan.json` plus a generated skill-curator SchedulePlan artifact.

### Task 3: Scaffold, Docs, Version

**Files:**
- Modify: `ai_harness/scaffold.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-23-ai-harness-mvp-design.md`
- Modify: `ai_harness/__init__.py`
- Modify: `pyproject.toml`

- [x] Add lifecycle runtime directories and gitignore rules.
- [x] Document the new gate chain.
- [x] Bump version.

### Task 4: Verification

**Files:**
- No source changes expected.

- [x] Run `python3 -m unittest discover -s tests -v`.
- [x] Run `python3 -m ai_harness validate --target .`.
- [x] Run `python3 -m compileall ai_harness`.
- [x] Run `git diff --check`.
