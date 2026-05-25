from __future__ import annotations

import json
from pathlib import Path


AGENT_FRONT_MATTER: dict[str, str] = {
    "scheduler-agent": """---
id: scheduler-agent
type: read-only-orchestrator
version: 1
default_pr_policy: none
allowed_skills:
  - schedule-planning
---
# Scheduler Agent

## Mission

Given issue state, task graph state, pull request state, CI state, review findings, trace summaries, and the visible agent catalog, decide the next agent identities to dispatch.

## You Can See

- `.ai/agent-catalog.yml`
- issue specs
- task graphs
- pull request states
- CI results
- review findings
- trace summaries
- skill availability by agent identity

## You Must Not See

- runtime bindings
- connector names
- model names
- credentials
- raw API keys
- hidden dispatcher config

## Output

Return only a SchedulePlan JSON object matching `.ai/schemas/schedule_plan.schema.json`.

## Do Not

- run shell commands
- modify files
- create branches
- open pull requests directly
- choose Codex vs Claude Code
- choose models
- bypass policy gates
""",
    "issue-compiler": """---
id: issue-compiler
type: read-only
version: 1
default_pr_policy: none
allowed_skills:
  - issue-compiler
---
# Issue Compiler

## Mission

Convert raw user requests into structured issue specs and acceptance criteria.

## Outputs

- `issue_spec.json`
- issue comments

## Must Not

- modify repository files
- create branches
- open pull requests
""",
    "architect": """---
id: architect
type: conditional-writer
version: 1
default_pr_policy: required_when_writing
allowed_skills:
  - architecture-planning
  - pr-evidence-bundle
---
# Architect

## Mission

Produce architecture plans, ADR proposals, dependency boundaries, and task graphs.

## Writer Transition

If this agent writes ADRs or architecture docs, the run becomes a writer run and must use an isolated worktree, branch, trace, and pull request.
""",
    "backend-implementer": """---
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
""",
    "frontend-implementer": """---
id: frontend-implementer
type: writer
version: 1
default_pr_policy: required
allowed_skills:
  - frontend-implementation
  - pr-evidence-bundle
---
# Frontend Implementer

## Mission

Implement frontend changes according to task specs, design constraints, and acceptance criteria.

## Allowed Changes

- `src/frontend/**`
- `app/**`
- `components/**`
- `tests/frontend/**`

## Required Validation

- `pnpm lint`
- `pnpm typecheck`
- `pnpm test frontend`
""",
    "qa-agent": """---
id: qa-agent
type: conditional-writer
version: 1
default_pr_policy: required_when_writing
allowed_skills:
  - test-design
  - pr-evidence-bundle
---
# QA Agent

## Mission

Reproduce bugs, run validation, report coverage gaps, and add tests when assigned as a writer.

## Writer Transition

If this agent adds or updates tests, the run becomes a writer run and must open a pull request.
""",
    "security-reviewer": """---
id: security-reviewer
type: read-only
version: 1
default_pr_policy: none
allowed_skills:
  - security-review
---
# Security Reviewer

## Mission

Review security risks and produce structured findings.

## Must Not

- modify code
- push commits
- approve its own implementation
""",
    "risk-approval-agent": """---
id: risk-approval-agent
type: read-only
version: 1
default_pr_policy: none
allowed_skills:
  - risk-approval
---
# Risk Approval Agent

## Mission

Continuously evaluate high-risk writer runs after CI/Eval and review gates, then produce an autonomous approval decision for merge gating.

## Inputs

- run metadata
- PR evidence bundle
- CI/Eval gate result
- review gate result
- security policy
- merge policy
- trace summary

## Outputs

- `risk_approval.json`

## Must Not

- modify repository files
- create branches
- open pull requests
- choose runtime bindings
- bypass deterministic gates
- approve its own implementation
""",
    "pr-reviewer": """---
id: pr-reviewer
type: read-only
version: 1
default_pr_policy: none
allowed_skills:
  - pr-reviewer
---
# PR Reviewer

## Mission

Review pull request diffs and produce actionable structured findings.

## If Code Changes Are Needed

Create a repair task. Do not edit the PR branch directly.
""",
    "ci-repair-agent": """---
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
""",
    "integration-agent": """---
id: integration-agent
type: writer
version: 1
default_pr_policy: required
allowed_skills:
  - integration-merge
  - pr-evidence-bundle
---
# Integration Agent

## Mission

Integrate approved child writer branches for one issue into a final integration branch and pull request.

## Rules

- only merge branches listed in the integration plan
- record merge evidence and conflicts
- do not make unrelated code changes
- produce an integration PR through the deterministic PR chain
""",
    "skill-curator": """---
id: skill-curator
type: writer
version: 1
default_pr_policy: required
allowed_skills:
  - skill-evolution
  - pr-evidence-bundle
---
# Skill Curator

## Mission

Convert repeated feedback patterns into skill, eval, lint, schema, or documentation updates.

## Allowed Changes

- `.ai/skills/**`
- `.ai/evals/**`
- `.ai/rules/**`
- `.ai/schemas/**`
- `docs/runbooks/**`
""",
    "release-agent": """---
id: release-agent
type: conditional-writer
version: 1
default_pr_policy: required_when_writing
allowed_skills:
  - release-checklist
  - pr-evidence-bundle
---
# Release Agent

## Mission

Prepare release checklists, changelogs, and release readiness findings.
""",
}


def init_scaffold(target: Path, force: bool = False) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for directory in [
        ".ai/agents",
        ".ai/private",
        ".ai/connectors",
        ".ai/skills",
        ".ai/rules",
        ".ai/schemas",
        ".ai/runs",
        ".ai/locks/branches",
        ".ai/scheduler-workspaces",
        ".ai/events",
        ".ai/local-daemon/events",
        ".ai/local-daemon/leases",
        ".ai/local-daemon/polls",
        ".ai/local-daemon/launchd",
        ".agents/skills",
        ".claude/skills",
        ".github/workflows",
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
    _write(target / ".ai" / "agent-catalog.yml", AGENT_CATALOG_YML, force)
    _write(target / ".ai" / "private" / "assignments.yml", PRIVATE_ASSIGNMENTS_YML, force)
    _write(target / ".ai" / "skills" / "registry.yml", SKILL_REGISTRY_YML, force)
    _write(target / ".claude" / "settings.json", json.dumps(CLAUDE_SETTINGS, indent=2) + "\n", force)
    _write(target / ".github" / "workflows" / "ai-harness-automation.yml", AI_HARNESS_AUTOMATION_WORKFLOW, force)
    _write(
        target / ".ai" / "local-daemon" / "launchd" / "com.ai-harness.local-daemon.plist",
        LOCAL_DAEMON_LAUNCHD_PLIST,
        force,
    )

    for agent_id, content in AGENT_FRONT_MATTER.items():
        _write(target / ".ai" / "agents" / f"{agent_id}.md", content, force)

    for connector_id, content in CONNECTORS.items():
        _write(target / ".ai" / "connectors" / f"{connector_id}.yml", content, force)

    for rule_name, content in RULES.items():
        _write(target / ".ai" / "rules" / f"{rule_name}.yml", content, force)

    for schema_name, schema in SCHEMAS.items():
        _write(target / ".ai" / "schemas" / f"{schema_name}.schema.json", json.dumps(schema, indent=2) + "\n", force)

    for keep in [
        ".ai/runs/.gitkeep",
        ".ai/locks/branches/.gitkeep",
        ".ai/scheduler-workspaces/.gitkeep",
        ".ai/events/.gitkeep",
        ".ai/local-daemon/events/.gitkeep",
        ".ai/local-daemon/leases/.gitkeep",
        ".ai/local-daemon/polls/.gitkeep",
        ".agents/skills/.gitkeep",
        ".claude/skills/.gitkeep",
    ]:
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
        ".agents/skills/*",
        "!.agents/skills/.gitkeep",
        ".claude/skills/*",
        "!.claude/skills/.gitkeep",
        ".ai/runs/*",
        "!.ai/runs/.gitkeep",
        ".ai/locks/branches/*",
        "!.ai/locks/branches/.gitkeep",
        ".ai/scheduler-workspaces/*",
        "!.ai/scheduler-workspaces/.gitkeep",
        ".ai/events/*",
        "!.ai/events/.gitkeep",
        ".ai/local-daemon/events/*",
        "!.ai/local-daemon/events/.gitkeep",
        ".ai/local-daemon/leases/*",
        "!.ai/local-daemon/leases/.gitkeep",
        ".ai/local-daemon/polls/*",
        "!.ai/local-daemon/polls/.gitkeep",
        ".ai/local-daemon/state.json",
        ".ai/local-daemon/*.log",
        ".ai/artifact_retention_report.json",
        ".ai/connector_contracts.json",
        ".ai/private/*.local.yml",
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
- Validation policy: `.ai/rules/validation-policy.yml`
- Merge policy: `.ai/rules/auto-merge-policy.yml`
- Local daemon trigger policy: `.ai/rules/local-daemon.yml`

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
"""

HARNESS_YML = """version: 2
canonical_instruction: AGENTS.md
schedule_target: agent_identity
dispatcher_private_bindings: .ai/private/assignments.yml
run_id_prefix: run
paths:
  worktrees: .worktrees
  runs: .ai/runs
  agents: .ai/agents
  agent_catalog: .ai/agent-catalog.yml
  connectors: .ai/connectors
policies:
  writer_run_pr_policy: required
  one_pr_owner: true
  scheduler_runtime_blind: true
  scheduler_executes_cli: false
  reviewer_writes_implementation_branch: false
  claude_md_committed: false
branch_template: ai/{issue_id}/{agent_id}/{run_id}
worktree_template: .worktrees/{run_id}-{agent_id}
"""

AGENT_CATALOG_YML = """version: 1
agents:
  scheduler-agent:
    type: read-only-orchestrator
    purpose: Decide next agent identities to dispatch from visible state.
    outputs:
      - schedule_plan
    can_write_repo: false
  issue-compiler:
    type: read-only
    purpose: Convert raw user requests into structured issue specs.
    outputs:
      - issue_spec
    can_write_repo: false
  architect:
    type: conditional-writer
    purpose: Produce architecture plans, ADRs, dependency boundaries, and task graphs.
    outputs:
      - task_graph
      - adr_pr_optional
    can_write_repo: true
    write_requires_pr: true
  backend-implementer:
    type: writer
    purpose: Implement backend tasks and tests.
    outputs:
      - branch
      - pr
      - evidence_bundle
    allowed_domains:
      - backend
      - api
      - tests
    can_write_repo: true
    write_requires_pr: true
  frontend-implementer:
    type: writer
    purpose: Implement UI tasks and frontend tests.
    outputs:
      - branch
      - pr
      - evidence_bundle
    allowed_domains:
      - frontend
      - ui
      - tests
    can_write_repo: true
    write_requires_pr: true
  qa-agent:
    type: conditional-writer
    purpose: Reproduce bugs, add tests, run validation, and report coverage gaps.
    outputs:
      - test_report
      - test_pr_optional
    can_write_repo: true
    write_requires_pr: true
  security-reviewer:
    type: read-only
    purpose: Review security risks and produce structured findings.
    outputs:
      - security_findings
    can_write_repo: false
  risk-approval-agent:
    type: read-only
    purpose: Continuously approve or reject high-risk merge candidates through structured policy decisions.
    outputs:
      - risk_approval
    can_write_repo: false
  pr-reviewer:
    type: read-only
    purpose: Review PR diffs and produce structured findings.
    outputs:
      - review_findings
    can_write_repo: false
  ci-repair-agent:
    type: writer
    purpose: Repair CI, lint, typecheck, or test failures.
    outputs:
      - pr_update_or_repair_pr
      - evidence_bundle
    can_write_repo: true
    write_requires_pr: true
  integration-agent:
    type: writer
    purpose: Merge child writer branches into a final issue integration branch and PR.
    outputs:
      - integration_pr
      - evidence_bundle
    can_write_repo: true
    write_requires_pr: true
  skill-curator:
    type: writer
    purpose: Convert repeated failures into skill, eval, lint, schema, or doc updates.
    outputs:
      - skill_update_pr
    can_write_repo: true
    write_requires_pr: true
  release-agent:
    type: conditional-writer
    purpose: Prepare release checklists, changelogs, and release readiness findings.
    outputs:
      - release_checklist
      - changelog_pr_optional
    can_write_repo: true
    write_requires_pr: true
"""

PRIVATE_ASSIGNMENTS_YML = """version: 1
bindings:
  scheduler-agent:
    connector: claude-code-cli
    profile: scheduler-readonly
  issue-compiler:
    connector: codex-cli
    profile: readonly-json
  architect:
    connector: claude-code-cli
    profile: planner
  backend-implementer:
    connector: codex-cli
    profile: writer-workspace
  frontend-implementer:
    connector: claude-code-cli
    profile: writer-workspace
  qa-agent:
    connector: codex-cli
    profile: qa-workspace
  security-reviewer:
    connector: claude-code-cli
    profile: reviewer-readonly
  risk-approval-agent:
    connector: claude-code-cli
    profile: risk-approval-readonly
  pr-reviewer:
    connector: claude-code-cli
    profile: reviewer-readonly
  ci-repair-agent:
    connector: codex-cli
    profile: writer-workspace
  integration-agent:
    connector: codex-cli
    profile: writer-workspace
  skill-curator:
    connector: claude-code-cli
    profile: skill-writer
  release-agent:
    connector: claude-code-cli
    profile: release-readonly
"""

CONNECTORS = {
    "codex-cli": """id: codex-cli
version: 1
executable: codex
profiles:
  scheduler-readonly:
    sandbox: read-only
    tools: read-only
  readonly-json:
    sandbox: read-only
    tools: read-only
  writer-workspace:
    sandbox: workspace-write
    tools: shell-and-edit
  qa-workspace:
    sandbox: workspace-write
    tools: shell-and-edit
command_templates:
  scheduler-readonly: codex exec --cd {workspace} --sandbox read-only --json --output-schema {output_schema}
  readonly-json: codex exec --cd {workspace} --sandbox read-only --json --output-schema {output_schema}
  writer-workspace: codex exec --cd {workspace} --sandbox workspace-write --json --output-schema {output_schema}
  qa-workspace: codex exec --cd {workspace} --sandbox workspace-write --json --output-schema {output_schema}
""",
    "claude-code-cli": """id: claude-code-cli
version: 1
executable: claude
profiles:
  scheduler-readonly:
    mode: bare-print
    tools: Read,Grep,Glob
  planner:
    mode: bare-print
    tools: Read,Grep,Glob
  writer-workspace:
    mode: bare-print
    tools: Read,Edit,Bash,Grep,Glob
  reviewer-readonly:
    mode: bare-print
    tools: Read,Grep,Glob
  risk-approval-readonly:
    mode: bare-print
    tools: Read,Grep,Glob
  skill-writer:
    mode: bare-print
    tools: Read,Edit,Bash,Grep,Glob
  release-readonly:
    mode: bare-print
    tools: Read,Grep,Glob
command_templates:
  scheduler-readonly: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
  planner: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
  writer-workspace: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
  reviewer-readonly: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
  risk-approval-readonly: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
  skill-writer: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
  release-readonly: claude --bare -p --append-system-prompt-file AGENTS.md --output-format json --json-schema {output_schema_json}
""",
}

SKILL_REGISTRY_YML = """version: 1
skills:
  schedule-planning:
    description: Produce runtime-blind SchedulePlan JSON.
  issue-compiler:
    description: Compile user requests into issue specs.
  architecture-planning:
    description: Produce task graphs and architecture findings.
  backend-implementation:
    description: Implement backend changes under agent boundaries.
  frontend-implementation:
    description: Implement frontend changes under agent boundaries.
  test-design:
    description: Reproduce behavior and add tests when assigned as writer.
  security-review:
    description: Review authentication, authorization, secrets, and data risks.
  risk-approval:
    description: Produce autonomous high-risk approval or rejection decisions for merge gates.
  pr-reviewer:
    description: Produce structured pull request findings.
  ci-failure-repair:
    description: Repair validation and CI failures.
  integration-merge:
    description: Merge child writer branches into an audited integration branch.
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
    "dispatcher-kernel": """version: 1
responsibilities:
  - validate schedule plan schema
  - resolve agent_id through private bindings
  - create worktree and branch for writer runs
  - enforce writer/read-only mode constraints
  - record trace and dispatch log
  - run validation gates
  - prepare pull request evidence
forbidden_to_scheduler:
  - connector choice
  - model choice
  - credentials
  - shell command execution
  - merge execution
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
    "validation-policy": """version: 1
defaults:
  writer:
    - python3 -m ai_harness validate --target .
    - python3 -m unittest discover -s tests -v
agents:
  backend-implementer:
    - python3 -m ai_harness validate --target .
    - python3 -m unittest discover -s tests -v
  frontend-implementer:
    - python3 -m ai_harness validate --target .
    - python3 -m unittest discover -s tests -v
  ci-repair-agent:
    - python3 -m ai_harness validate --target .
    - python3 -m unittest discover -s tests -v
""",
    "local-daemon": """version: 1
label_actions:
  ai:auto: run
  ai:plan: plan
  ai:repair: repair
  ai:review: review
comment_actions:
  /ai run: run
  /ai repair: repair
  /ai status: status
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
  - permissions match agent identity
  - rollback plan is credible
""",
    "security-policy": """version: 1
autonomous_risk_approval_required:
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
  - high-risk approval gate passes when risk is high
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
    "artifact-retention": """version: 1
run_artifacts:
  local_only:
    - .ai/runs/**/stdout.log
    - .ai/runs/**/stderr.log
    - .ai/runs/**/connector_events.jsonl
    - .ai/runs/**/trace.jsonl
    - .ai/runs/**/prompt.md
    - .ai/runs/**/*.attempt-*.log
    - .ai/events/**
    - .ai/scheduler-workspaces/**
  commit_allowed:
    - .ai/runs/.gitkeep
    - .ai/locks/branches/.gitkeep
    - .ai/events/.gitkeep
    - .ai/scheduler-workspaces/.gitkeep
redaction:
  block_patterns:
    - OPENAI_API_KEY
    - ANTHROPIC_API_KEY
    - GITHUB_TOKEN
    - sk-*
    - ghp_*
report:
  command: python3 -m ai_harness artifact-retention-report --target .
  output: .ai/artifact_retention_report.json
""",
}

AI_HARNESS_AUTOMATION_WORKFLOW = """name: AI Harness Automation

on:
  issues:
    types: [opened, edited, labeled]
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  workflow_dispatch:

permissions:
  contents: read
  issues: read
  pull-requests: read

jobs:
  automation-daemon:
    name: Event automation daemon
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install harness
        run: python -m pip install -e .

      - name: Validate harness contracts
        run: |
          python -m ai_harness validate --target .
          python -m ai_harness connector-contracts --target .

      - name: Run automation daemon
        run: |
          RUN_ID="run-gh-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
          python -m ai_harness automation-daemon \\
            --target . \\
            --event-file "$GITHUB_EVENT_PATH" \\
            --run-id "$RUN_ID" \\
            --validation-mode skip \\
            --no-worktree

      - name: Artifact retention report
        run: python -m ai_harness artifact-retention-report --target .
"""

LOCAL_DAEMON_LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-harness.local-daemon</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>-m</string>
    <string>ai_harness</string>
    <string>local-daemon</string>
    <string>--target</string>
    <string>REPLACE_WITH_REPO_PATH</string>
    <string>--run-id</string>
    <string>run-local-daemon</string>
    <string>--execute</string>
    <string>--status-sync</string>
  </array>
  <key>WorkingDirectory</key>
  <string>REPLACE_WITH_REPO_PATH</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>REPLACE_WITH_REPO_PATH/.ai/local-daemon/stdout.log</string>
  <key>StandardErrorPath</key>
  <string>REPLACE_WITH_REPO_PATH/.ai/local-daemon/stderr.log</string>
</dict>
</plist>
"""

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
    "schedule_plan": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["run_plan", "blocked", "risk_notes"],
        "additionalProperties": False,
        "properties": {
            "run_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "agent_id",
                        "task_id",
                        "mode",
                        "depends_on",
                        "expected_output",
                        "requires_pr",
                        "risk_level",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "agent_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "mode": {"type": "string", "enum": ["read_only", "writer"]},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "expected_output": {
                            "type": "string",
                            "enum": [
                                "issue_spec",
                                "task_graph",
                                "branch_pr",
                                "review_findings",
                                "test_report",
                                "skill_update_pr",
                                "schedule_plan",
                                "risk_approval",
                            ],
                        },
                        "requires_pr": {"type": "boolean"},
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                        "success_criteria": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "blocked": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["task_id", "reason"],
                    "additionalProperties": False,
                    "properties": {
                        "task_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
            "risk_notes": {"type": "array", "items": {"type": "string"}},
        },
    },
    "agent_run_request": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["agent_id", "task_id", "mode", "issue_id"],
        "properties": {
            "agent_id": {"type": "string"},
            "task_id": {"type": "string"},
            "mode": {"enum": ["read_only", "writer"]},
            "issue_id": {"type": "string"},
        },
    },
    "agent_result": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "summary", "evidence"],
        "properties": {
            "status": {"enum": ["succeeded", "failed", "blocked"]},
            "summary": {"type": "string"},
            "evidence": {"type": "object", "additionalProperties": False, "properties": {}},
        },
    },
    "agent_task": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["summary"],
        "properties": {
            "summary": {"type": "string"},
            "acceptance": {"type": "array", "items": {"type": "string"}},
            "issue": {"type": "string"},
            "task_id": {"type": "string"},
        },
    },
    "run": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["run_id", "agent_id", "connector", "issue_id", "state"],
        "properties": {
            "run_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "connector": {"type": "string"},
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
    "review_findings": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["findings"],
        "additionalProperties": False,
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["severity", "status", "body"],
                    "properties": {
                        "id": {"type": "string"},
                        "severity": {"enum": ["blocking", "major", "minor", "note"]},
                        "status": {"type": "string"},
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "pattern": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
            },
        },
    },
    "risk_approval": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["status", "approver_agent_id", "source_run_id", "risk_level", "rationale"],
        "additionalProperties": False,
        "properties": {
            "status": {"enum": ["approved", "rejected"]},
            "approver_agent_id": {"const": "risk-approval-agent"},
            "source_run_id": {"type": "string"},
            "risk_level": {"enum": ["low", "medium", "high"]},
            "rationale": {"type": "string"},
            "conditions": {"type": "array", "items": {"type": "string"}},
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
