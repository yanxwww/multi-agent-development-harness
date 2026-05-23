# AI Development Harness

This repository implements a local CLI scaffold for a Codex / Claude Code AI automation development harness.

The harness is intentionally runtime-blind at the scheduling layer:

- The scheduler targets agent identities from `.ai/agent-catalog.yml`.
- Agent identity docs live in `.ai/agents/*.md`.
- Dispatcher-only connector bindings live in `.ai/private/assignments.yml`.
- Codex CLI and Claude Code CLI are connector contracts in `.ai/connectors/*.yml`.
- `AGENTS.md` is the only canonical repository-level instruction entry point.
- `CLAUDE.md` is not committed; a future Claude Code adapter can bridge to `AGENTS.md` at run time.

## Commands

```bash
python3 -m ai_harness init --target .
python3 -m ai_harness validate --target .
python3 -m ai_harness create-run --target . --issue 123 --agent backend-implementer --task task.json --no-worktree
python3 -m ai_harness pr-body --target . --run run-20260523-001
python3 -m ai_harness dispatch-plan --target . --issue 123 --plan schedule_plan.json --run-id run-schedule-001 --no-worktree
python3 -m ai_harness connector-command --target . --run run-20260523-001
python3 -m ai_harness run-connector --target . --run run-20260523-001 --timeout 900 --retries 1
python3 -m ai_harness validation-gate --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness pr-gate --target . --run run-20260523-001
python3 -m ai_harness pr-command --target . --run run-20260523-001 --base main --draft
python3 -m ai_harness run-pr-command --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness dispatch-run --target . --issue 123 --plan schedule_plan.json --run-id run-dispatch-001 --timeout 900 --retries 1 --prepare-pr-command --pr-base main --draft-pr
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

Read-only runs can produce comments, findings, artifacts, and traces without creating a PR. If a read-only agent identity writes repository files, it becomes a writer run.

## Scheduler / Dispatcher Boundary

The scheduler only emits `SchedulePlan` JSON containing `agent_id`, task, dependency, mode, expected output, PR requirement, and risk. It must not choose Codex, Claude Code, a model, credentials, or CLI flags.

The deterministic dispatcher validates the plan, resolves `agent_id -> connector profile` through `.ai/private/assignments.yml`, creates run records, prepares worktrees for writer runs, and records dispatch trace.

`connector-command` renders the CLI command that a future process supervisor will execute. It writes `.ai/runs/<run-id>/connector_command.json` with `argv`, display text, connector id, connector profile, workspace, and output schema. It does not execute Codex or Claude Code.

`run-connector` executes `connector_command.json` with a per-attempt timeout and retry count. It writes `stdout.log`, `stderr.log`, per-attempt logs, `connector_events.jsonl` for JSON stdout lines, `connector_execution.json`, and trace events in `trace.jsonl`.

`validation-gate` runs or explicitly skips the validation commands in `evidence.json`, writes `validation_gate.json`, updates validation status in the evidence bundle, and appends trace events.

`pr-gate` renders `pr-body.md` for writer runs and blocks the run unless evidence, connector execution, validation status, and PR body requirements are satisfied.

`pr-command` renders a gated `gh pr create` command into `.ai/runs/<run-id>/pr_command.json`. It only runs after `pr_gate.json` has status `passed`.

`run-pr-command` executes `pr_command.json` and records `pr_stdout.log`, `pr_stderr.log`, `pr_execution.json`, and trace events. It depends on the local GitHub CLI environment being authenticated and the target branch being publishable.

`dispatch-run` is the deterministic orchestration path. It calls `dispatch-plan`, renders each child run's `connector_command.json`, executes the connector with timeout/retry trace capture, runs the validation gate, then runs the PR body/gate check. With `--prepare-pr-command`, gated writer children also get a deterministic PR command artifact. The scheduler still targets only `agent_id`; connector selection remains private to the dispatcher.

## Current MVP Boundaries

This version creates and validates the repo contract, prepares dispatch runs from a runtime-blind plan, renders deterministic connector and PR commands, executes connector and PR commands with captured logs and trace, and gates writer runs through validation and PR body checks. It does not yet manage commit creation, branch push policy, skill installation into external runtimes, or branch locks. Those belong in the next orchestration layer.
