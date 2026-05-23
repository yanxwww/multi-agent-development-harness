from __future__ import annotations

import json
from pathlib import Path


ROLE_PROFILES: dict[str, str] = {
    "issue-compiler": """id: issue-compiler
type: read-only
version: 1
default_pr_policy: none
mission: Compile user requests into issue specs and acceptance criteria.
inputs:
  - user request
  - product specs
outputs:
  - issue_spec.json
  - issue comment
allowed_changes: []
restricted_changes:
  - "**/*"
required_validation: []
allowed_skills:
  - issue-compiler
escalation:
  - requirements conflict
  - acceptance criteria cannot be made testable
""",
    "architect": """id: architect
type: read-only
version: 1
default_pr_policy: none
mission: Produce architecture recommendations, task graphs, and ADR proposals.
inputs:
  - issue_spec.json
  - docs/architecture/**
  - docs/adr/**
outputs:
  - task_graph.json
  - architecture findings
allowed_changes: []
restricted_changes:
  - "**/*"
required_validation: []
allowed_skills:
  - architecture-planning
  - pr-evidence-bundle
escalation:
  - ADR must be committed
  - production architecture boundary changes
""",
    "backend-implementer": """id: backend-implementer
type: writer
version: 1
default_pr_policy: required
mission: Implement backend changes according to task specs and acceptance criteria.
inputs:
  - issue_spec.json
  - task.json
  - AGENTS.md
  - docs/architecture/**
outputs:
  - isolated branch
  - code diff
  - tests added or updated
  - validation results
  - evidence bundle
  - pull request
allowed_changes:
  - src/backend/**
  - services/**
  - packages/api/**
  - tests/backend/**
restricted_changes:
  - .github/workflows/**
  - infra/**
  - migrations/**
  - auth/**
  - billing/**
  - production config
  - secrets
required_validation:
  - pnpm lint
  - pnpm typecheck
  - pnpm test backend
allowed_skills:
  - backend-implementation
  - ci-failure-repair
  - pr-evidence-bundle
escalation:
  - migration required
  - auth or payment code touched
  - production data affected
""",
    "frontend-implementer": """id: frontend-implementer
type: writer
version: 1
default_pr_policy: required
mission: Implement frontend changes according to task specs, design constraints, and acceptance criteria.
inputs:
  - issue_spec.json
  - task.json
  - AGENTS.md
  - design references
outputs:
  - isolated branch
  - UI code diff
  - tests added or updated
  - validation results
  - evidence bundle
  - pull request
allowed_changes:
  - src/frontend/**
  - app/**
  - components/**
  - tests/frontend/**
restricted_changes:
  - auth/**
  - billing/**
  - production config
  - secrets
required_validation:
  - pnpm lint
  - pnpm typecheck
  - pnpm test frontend
allowed_skills:
  - frontend-implementation
  - pr-evidence-bundle
escalation:
  - accessibility acceptance criteria conflict
  - design source is ambiguous
""",
    "qa-agent": """id: qa-agent
type: hybrid
version: 1
default_pr_policy: required_when_writing
mission: Verify behavior, reproduce failures, and add tests when assigned as a writer.
inputs:
  - issue_spec.json
  - pull request diff
  - acceptance criteria
outputs:
  - test report
  - reproduction notes
  - tests added or updated when writing
allowed_changes:
  - tests/**
  - e2e/**
restricted_changes:
  - production code
  - secrets
required_validation:
  - pnpm test
allowed_skills:
  - test-design
  - pr-evidence-bundle
escalation:
  - flaky test suspected
  - production behavior unclear
""",
    "security-reviewer": """id: security-reviewer
type: read-only
version: 1
default_pr_policy: none
mission: Review security risks and produce structured findings.
inputs:
  - pull request diff
  - security policy
outputs:
  - security findings
  - risk classification
allowed_changes: []
restricted_changes:
  - "**/*"
required_validation: []
allowed_skills:
  - security-review
escalation:
  - secret exposure suspected
  - authentication or authorization risk
""",
    "pr-reviewer": """id: pr-reviewer
type: read-only
version: 1
default_pr_policy: none
mission: Review pull requests and produce actionable structured findings.
inputs:
  - pull request diff
  - evidence bundle
  - review rubric
outputs:
  - review_findings.json
  - inline comments
  - risk classification
allowed_changes: []
restricted_changes:
  - "**/*"
required_validation: []
allowed_skills:
  - pr-reviewer
escalation:
  - blocking findings
  - missing validation evidence
""",
    "ci-repair-agent": """id: ci-repair-agent
type: writer
version: 1
default_pr_policy: required
mission: Repair validation and CI failures through an isolated writer run.
inputs:
  - failing logs
  - pull request diff
  - run evidence
outputs:
  - repair diff
  - validation results
  - evidence bundle
  - pull request or owner-transfer trace
allowed_changes:
  - src/**
  - tests/**
  - package.json
  - pnpm-lock.yaml
restricted_changes:
  - secrets
  - production config
  - branch protection
required_validation:
  - pnpm lint
  - pnpm typecheck
  - pnpm test
allowed_skills:
  - ci-failure-repair
  - pr-evidence-bundle
escalation:
  - failure source is ambiguous
  - repair requires changing protected infrastructure
""",
    "skill-curator": """id: skill-curator
type: writer
version: 1
default_pr_policy: required
mission: Convert repeated feedback patterns into skill, eval, lint, schema, or documentation updates.
inputs:
  - traces
  - review findings
  - CI failures
outputs:
  - skill patch
  - eval update
  - rollback notes
  - pull request
allowed_changes:
  - .ai/skills/**
  - .ai/evals/**
  - .ai/rules/**
  - .ai/schemas/**
  - docs/runbooks/**
restricted_changes:
  - production code
  - secrets
required_validation:
  - harness validate
allowed_skills:
  - skill-evolution
  - pr-evidence-bundle
escalation:
  - skill changes broaden permissions
  - eval cannot prove improvement
""",
    "release-agent": """id: release-agent
type: hybrid
version: 1
default_pr_policy: required_when_writing
mission: Prepare release checklists, changelogs, and release readiness findings.
inputs:
  - merged PRs
  - release policy
outputs:
  - release checklist
  - changelog updates when writing
allowed_changes:
  - CHANGELOG.md
  - docs/runbooks/**
restricted_changes:
  - production config
  - secrets
required_validation:
  - harness validate
allowed_skills:
  - release-checklist
  - pr-evidence-bundle
escalation:
  - release risk is high
  - rollback plan is missing
""",
}


def init_scaffold(target: Path, force: bool = False) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for directory in [
        ".ai/roles",
        ".ai/runtimes",
        ".ai/skills",
        ".ai/rules",
        ".ai/schemas",
        ".ai/runs",
        ".agents/skills",
        ".claude/skills",
        "docs/architecture",
        "docs/adr",
        "docs/runbooks",
        "docs/product-specs",
        "docs/exec-plans",
        ".worktrees",
    ]:
        (target / directory).mkdir(parents=True, exist_ok=True)

    _write(target / "AGENTS.md", AGENTS_MD, force)
    _merge_gitignore(target / ".gitignore")
    _write(target / ".ai" / "harness.yml", HARNESS_YML, force)
    _write(target / ".ai" / "assignments.yml", ASSIGNMENTS_YML, force)
    _write(target / ".ai" / "skills" / "registry.yml", SKILL_REGISTRY_YML, force)
    _write(target / ".claude" / "settings.json", json.dumps(CLAUDE_SETTINGS, indent=2) + "\n", force)

    for role_id, content in ROLE_PROFILES.items():
        _write(target / ".ai" / "roles" / f"{role_id}.yml", content, force)

    for runtime_id, content in RUNTIME_PROFILES.items():
        _write(target / ".ai" / "runtimes" / f"{runtime_id}.yml", content, force)

    for rule_name, content in RULES.items():
        _write(target / ".ai" / "rules" / f"{rule_name}.yml", content, force)

    for schema_name, schema in SCHEMAS.items():
        _write(target / ".ai" / "schemas" / f"{schema_name}.schema.json", json.dumps(schema, indent=2) + "\n", force)

    for keep in [".ai/runs/.gitkeep", ".agents/skills/.gitkeep", ".claude/skills/.gitkeep"]:
        _write(target / keep, "", force=False)


def _write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _merge_gitignore(path: Path) -> None:
    required = [
        ".worktrees/",
        "CLAUDE.md",
        ".ai/runs/*",
        "!.ai/runs/.gitkeep",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
    ]
    existing = path.read_text().splitlines() if path.exists() else []
    merged = existing[:]
    for entry in required:
        if entry not in existing:
            merged.append(entry)
    path.write_text("\n".join(merged).rstrip() + "\n")


AGENTS_MD = """# AGENTS.md

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
"""

HARNESS_YML = """version: 1
canonical_instruction: AGENTS.md
run_id_prefix: run
paths:
  worktrees: .worktrees
  runs: .ai/runs
  roles: .ai/roles
  runtimes: .ai/runtimes
policies:
  writer_run_pr_policy: required
  one_pr_owner: true
  reviewer_writes_implementation_branch: false
  claude_md_committed: false
branch_template: ai/{issue_id}/{role_id}/{run_id}
worktree_template: .worktrees/{run_id}-{role_id}
"""

ASSIGNMENTS_YML = """version: 1
assignments:
  issue-compiler:
    runtime: codex
    allowed_skills:
      - issue-compiler
  architect:
    runtime: claude-code
    allowed_skills:
      - architecture-planning
  backend-implementer:
    runtime: codex
    allowed_skills:
      - backend-implementation
      - ci-failure-repair
      - pr-evidence-bundle
  frontend-implementer:
    runtime: codex
    allowed_skills:
      - frontend-implementation
      - pr-evidence-bundle
  qa-agent:
    runtime: claude-code
    allowed_skills:
      - test-design
      - pr-evidence-bundle
  security-reviewer:
    runtime: claude-code
    allowed_skills:
      - security-review
  pr-reviewer:
    runtime: claude-code
    allowed_skills:
      - pr-reviewer
  ci-repair-agent:
    runtime: codex
    allowed_skills:
      - ci-failure-repair
      - pr-evidence-bundle
  skill-curator:
    runtime: codex
    allowed_skills:
      - skill-evolution
      - pr-evidence-bundle
  release-agent:
    runtime: claude-code
    allowed_skills:
      - release-checklist
      - pr-evidence-bundle
"""

RUNTIME_PROFILES = {
    "codex": """id: codex
version: 1
adapter: codex
project_instruction_source: AGENTS.md
skill_install_target: .agents/skills
ephemeral_instruction_bridge: none
supports:
  - worktree
  - shell
  - trace
""",
    "claude-code": """id: claude-code
version: 1
adapter: claude-code
project_instruction_source: AGENTS.md
skill_install_target: .claude/skills
ephemeral_instruction_bridge: AGENTS.md
supports:
  - worktree
  - shell
  - trace
""",
}

SKILL_REGISTRY_YML = """version: 1
skills:
  issue-compiler:
    description: Compile user requests into issue specs.
  architecture-planning:
    description: Produce task graphs and architecture findings.
  backend-implementation:
    description: Implement backend changes under role boundaries.
  frontend-implementation:
    description: Implement frontend changes under role boundaries.
  test-design:
    description: Reproduce behavior and add tests when assigned as writer.
  security-review:
    description: Review authentication, authorization, secrets, and data risks.
  pr-reviewer:
    description: Produce structured pull request findings.
  ci-failure-repair:
    description: Repair validation and CI failures.
  pr-evidence-bundle:
    description: Produce PR evidence, validation, risk, and rollback notes.
  skill-evolution:
    description: Convert repeated findings into skill, eval, or rule updates.
  release-checklist:
    description: Prepare release readiness findings and changelog updates.
"""

RULES = {
    "state-machine": """version: 1
states:
  - planned
  - workspace_ready
  - running
  - validation_ready
  - pr_ready
  - review_ready
  - repair_required
  - merge_ready
  - failed
transitions:
  - planned -> workspace_ready
  - workspace_ready -> running
  - running -> validation_ready
  - running -> failed
  - validation_ready -> pr_ready
  - validation_ready -> repair_required
  - pr_ready -> review_ready
  - review_ready -> merge_ready
  - review_ready -> repair_required
  - repair_required -> running
""",
    "pr-gate": """version: 1
requirements:
  - linked issue
  - evidence bundle
  - validation results
  - risk notes
  - rollback plan
  - single writer owner
""",
    "ci-eval-gate": """version: 1
required_results:
  - lint
  - typecheck
  - tests
  - role-specific validation
failure_policy: return_to_pr_owner
""",
    "review-rubric": """version: 1
finding_levels:
  - blocking
  - major
  - minor
  - note
reviewer_must_check:
  - scope matches issue
  - tests cover acceptance criteria
  - validation evidence is fresh
  - permissions match role profile
  - rollback plan is credible
""",
    "security-policy": """version: 1
human_gate_required:
  - secrets
  - production data
  - authentication
  - authorization
  - payment flows
  - migrations
""",
    "auto-merge-policy": """version: 1
enabled: false
minimum_requirements:
  - ci passes
  - eval passes
  - no blocking review findings
  - human gate not required
""",
    "permission-boundaries": """version: 1
hard_denies:
  - production secrets
  - bypass branch protection
  - push directly to main
  - approve own PR
  - modify another writer run worktree
""",
    "skill-evolution": """version: 1
trigger_sources:
  - repeated review findings
  - repeated CI failures
  - trace analysis
skill_pr_requirements:
  - before trace
  - after eval
  - rollback plan
  - permission impact notes
""",
}

CLAUDE_SETTINGS = {
    "permissions": {
        "allow": [
            "Bash(git status:*)",
            "Bash(git diff:*)",
            "Bash(git log:*)",
        ],
        "deny": [
            "Read(.env*)",
            "Read(**/secrets/**)",
            "Bash(git push --force*)",
            "Bash(git reset --hard*)",
        ],
    },
    "harness": {
        "canonical_instruction": "AGENTS.md",
        "do_not_commit_claude_md": True,
    },
}

SCHEMAS = {
    "agent_task": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["summary"],
        "properties": {
            "summary": {"type": "string"},
            "acceptance": {"type": "array", "items": {"type": "string"}},
            "issue": {"type": "string"},
        },
    },
    "run": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["run_id", "role_id", "runtime_id", "issue_id", "state"],
        "properties": {
            "run_id": {"type": "string"},
            "role_id": {"type": "string"},
            "runtime_id": {"type": "string"},
            "issue_id": {"type": "string"},
            "state": {"type": "string"},
        },
    },
    "evidence_bundle": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["agent", "issue", "scope", "validation", "risk", "rollback"],
        "properties": {
            "agent": {"type": "object"},
            "issue": {"type": "object"},
            "scope": {"type": "string"},
            "validation": {"type": "array"},
            "risk": {"type": "string"},
            "rollback": {"type": "string"},
        },
    },
    "review_finding": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["severity", "file", "body"],
        "properties": {
            "severity": {"enum": ["blocking", "major", "minor", "note"]},
            "file": {"type": "string"},
            "line": {"type": "integer"},
            "body": {"type": "string"},
        },
    },
    "skill_patch": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["skill_id", "before_trace", "after_eval", "rollback"],
        "properties": {
            "skill_id": {"type": "string"},
            "before_trace": {"type": "string"},
            "after_eval": {"type": "string"},
            "rollback": {"type": "string"},
        },
    },
}

