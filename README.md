# AI Development Harness

This repository implements a local CLI scaffold for a Codex / Claude Code AI automation development harness.

The harness is intentionally runtime-blind at the scheduling layer:

- The scheduler targets agent identities from `.ai/agent-catalog.yml`.
- Agent identity docs live in `.ai/agents/*.md`.
- Dispatcher-only connector bindings live in `.ai/private/assignments.yml`.
- Codex CLI and Claude Code CLI are connector contracts in `.ai/connectors/*.yml`.
- Local daemon GitHub triggers live in `.ai/rules/local-daemon.yml`.
- `AGENTS.md` is the only canonical repository-level instruction entry point.
- `CLAUDE.md` is not committed; Claude Code connectors inject `AGENTS.md` explicitly at run time.

## Commands

```bash
python3 -m ai_harness init --target .
python3 -m ai_harness validate --target .
python3 -m ai_harness connector-contracts --target .
python3 -m ai_harness artifact-retention-report --target .
python3 -m ai_harness create-run --target . --issue 123 --agent backend-implementer --task task.json --no-worktree
python3 -m ai_harness pr-body --target . --run run-20260523-001
python3 -m ai_harness skill-sync --target . --run run-20260523-001
python3 -m ai_harness scheduler-run --target . --issue 123 --task scheduler_task.json --run-id run-scheduler-001 --timeout 900 --retries 1
python3 -m ai_harness dispatch-plan --target . --issue 123 --plan schedule_plan.json --run-id run-schedule-001 --no-worktree
python3 -m ai_harness connector-command --target . --run run-20260523-001
python3 -m ai_harness run-connector --target . --run run-20260523-001 --timeout 900 --retries 1
python3 -m ai_harness validation-gate --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness pr-gate --target . --run run-20260523-001
python3 -m ai_harness diff-gate --target . --run run-20260523-001
python3 -m ai_harness commit-command --target . --run run-20260523-001
python3 -m ai_harness run-commit-command --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness push-command --target . --run run-20260523-001 --remote origin
python3 -m ai_harness run-push-command --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness pr-command --target . --run run-20260523-001 --base main --draft
python3 -m ai_harness run-pr-command --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness github-doctor --target .
python3 -m ai_harness github-checks-command --target . --run run-20260523-001 --watch --interval 10
python3 -m ai_harness run-github-checks-command --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness ci-eval-gate --target . --run run-20260523-001
python3 -m ai_harness review-gate --target . --run run-20260523-001
python3 -m ai_harness writer-lock --target . --run run-20260523-001
python3 -m ai_harness writer-transfer --target . --from-run run-20260523-001 --to-run run-repair-001 --reason "CI repair"
python3 -m ai_harness risk-approval-gate --target . --run run-20260523-001
python3 -m ai_harness merge-gate --target . --run run-20260523-001
python3 -m ai_harness merge-command --target . --run run-20260523-001 --method squash --delete-branch
python3 -m ai_harness run-merge-command --target . --run run-20260523-001 --timeout 900
python3 -m ai_harness skill-evolution-plan --target . --source-run run-20260523-001 --run-id run-skill-evolution-001
python3 -m ai_harness lifecycle-run --target . --run run-20260523-001 --skill-run-id run-skill-evolution-001
python3 -m ai_harness integration-plan --target . --issue 123 --schedule-run run-schedule-001 --run-id run-integration-001
python3 -m ai_harness integration-command --target . --run run-integration-001
python3 -m ai_harness run-integration-command --target . --run run-integration-001 --timeout 900
python3 -m ai_harness dispatch-run --target . --issue 123 --plan schedule_plan.json --run-id run-dispatch-001 --timeout 900 --retries 1 --commit-and-push --push-remote origin --prepare-pr-command --pr-base main --draft-pr
python3 -m ai_harness automation-run --target . --issue 123 --scheduler-task scheduler_task.json --run-id run-automation-001 --timeout 900 --retries 1 --commit-and-push --prepare-pr-command --run-pr-command --github-checks --lifecycle --auto-review --auto-risk-approval --auto-repair --run-auto-repair --merge
python3 -m ai_harness automation-daemon --target . --event-file "$GITHUB_EVENT_PATH" --run-id run-gh-001
python3 -m ai_harness github-sync-poll --target . --run-id run-local-poll-001
python3 -m ai_harness local-daemon --target . --run-id run-local-daemon --once
python3 -m ai_harness local-daemon --target . --run-id run-local-daemon --execute --status-sync
python3 -m ai_harness github-status-sync --target . --event-id issue-42-ai-run --status planned --message "scheduler task ready"
```

Installable entry point:

```bash
pip install -e .
harness init --target .
```

## Local-First GitHub Sync

GitHub is the synchronization surface, not the runtime host. Issues, PRs, CI status, and concise daemon comments live on GitHub. Codex CLI and Claude Code CLI still run on the local machine through the deterministic dispatcher.

The hosted GitHub Actions workflow runs only read-only harness validation and event planning. It does not execute `automation-run`, create local worktrees, start Codex/Claude, push branches, or merge PRs. A local daemon does that from the developer machine:

```bash
python3 -m ai_harness local-daemon --target . --run-id run-local-daemon --execute --status-sync
```

The local daemon polls `gh issue list` and `gh pr list`, creates local events under `.ai/local-daemon/events/`, records processed triggers in `.ai/local-daemon/state.json`, and can wake the full local automation chain from label or comment triggers. Trigger mappings and retry policy live in `.ai/rules/local-daemon.yml`, so teams can choose their own labels, slash commands, retry limit, backoff, and retry trigger without code changes. Poll summaries are written to `.ai/local-daemon/polls/`. Each created event writes `event_result.json`; with `--status-sync`, the daemon also posts a short redacted planned or final status comment back to the source issue or PR. Runtime logs, traces, prompts, GitHub doctor output, dead-letter entries, and connector output remain local and git-ignored.

For long-running macOS operation, edit `.ai/local-daemon/launchd/com.ai-harness.local-daemon.plist`, replace `REPLACE_WITH_REPO_PATH`, and load it with launchd after `gh auth login` and local Codex/Claude credentials are configured.

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

`validate` checks scaffold shape, scheduler-visible catalog boundaries, connector contracts, JSON schemas, canonical instruction rules, and local daemon trigger policy syntax before automation runs.

`connector-contracts` validates connector permission profile contracts and writes `.ai/connector_contracts.json`. Codex read-only profiles must use a read-only sandbox, Codex writer profiles must use workspace-write, Claude profiles must use bare JSON-schema execution, and read-only profiles must not expose write-capable tools.

`connector-command` renders the CLI command that `run-connector`, `dispatch-run`, or `automation-run` can execute. It writes `.ai/runs/<run-id>/connector_command.json` with `argv`, display text, connector id, connector profile, workspace, output schema, prompt file, and prompt hash. It does not execute Codex or Claude Code by itself.

`run-connector` executes `connector_command.json` with a per-attempt timeout and retry count. For configured connector profiles, it re-derives the expected command from run metadata before execution and rejects mutated command artifacts. It verifies the prompt hash, passes the prompt to the connector process over stdin, captures resumable runtime session identifiers from CLI JSON output, and writes `stdout.log`, `stderr.log`, per-attempt logs, `connector_events.jsonl` for JSON stdout lines, `connector_execution.json`, and trace events in `trace.jsonl`.

`scheduler-run` runs `scheduler-agent` as a normal read-only agent identity from a sanitized workspace under `.ai/scheduler-workspaces/<run-id>`. That workspace contains only `AGENTS.md`, visible catalog/docs/rules/schemas/skills, and docs. It physically omits `.ai/private`, connector bindings, locks, runs, events, and connector contracts before rendering the connector command. The command uses the `schedule_plan` output schema, executes with timeout/retry trace capture, extracts a `SchedulePlan` from raw stdout, JSON events, or wrapped/fenced JSON output, validates that the plan remains runtime-blind, and writes `.ai/runs/<run-id>/schedule_plan.json`.

`skill-sync` installs only the run agent's allowlisted skills into the bound runtime skill directory. Codex-bound runs write `.agents/skills/<skill>/SKILL.md`; Claude Code-bound runs write `.claude/skills/<skill>/SKILL.md`. These runtime install directories are git-ignored so ordinary writer commits do not include ephemeral skill material. Skill source changes belong under `.ai/skills/**` and should be proposed by `skill-curator`. It copies concrete `.ai/skills/<skill>/` definitions when present, otherwise generates a minimal runtime skill from `.ai/skills/registry.yml`, then writes `skill_sync.json`.

Writer validation commands are selected from `.ai/rules/validation-policy.yml` when present, with agent-specific commands taking precedence over mode defaults. `validation-gate` runs or explicitly skips the validation commands declared in run metadata, falling back to `evidence.json` for manual runs. This prevents a mutable evidence bundle from becoming execution authority. It writes `validation_gate.json`, updates validation status in the evidence bundle, and appends trace events.

`pr-gate` renders `pr-body.md` for writer runs and blocks the run unless evidence, connector execution, validation status, and PR body requirements are satisfied.

`diff-gate` checks the writer worktree for changed files, writes `diff_gate.json`, and stores `diff.patch` for review evidence.

`commit-command` renders deterministic git add/commit steps into `commit_command.json`. `run-commit-command` re-derives the expected git steps before execution, rejects mutated artifacts, executes those steps in the run worktree, writes `commit_execution.json`, captures logs, records the commit SHA, and verifies the post-commit worktree is clean.

`push-command` renders deterministic `git push <remote> <branch>` into `push_command.json`. `run-push-command` re-derives the expected push command before execution, rejects mutated artifacts, executes it in the run worktree, and records `push_execution.json` plus stdout/stderr logs.

`pr-command` renders a gated `gh pr create` command into `.ai/runs/<run-id>/pr_command.json`. It only runs after `pr_gate.json` has status `passed` and `push_execution.json` has status `succeeded`.

`run-pr-command` re-derives the expected PR command before execution for writer runs, rejects mutated artifacts, executes `pr_command.json`, and records `pr_stdout.log`, `pr_stderr.log`, `pr_execution.json`, and trace events. It depends on the local GitHub CLI environment being authenticated and the target branch being publishable.

`github-doctor` checks local GitHub readiness by running `gh auth status`, `gh repo view`, and `git remote -v`, then writes `.ai/github_doctor.json`.

`github-checks-command` renders `gh pr checks` into `github_checks_command.json` after a PR exists. `run-github-checks-command` re-derives the expected command, executes it with timeout, captures stdout/stderr, normalizes GitHub check buckets into `ci_results.json`, preserves an existing `eval_results.json` unless an explicit replacement is supplied, and writes a default skipped eval artifact only when no eval artifact exists. Empty GitHub check output is treated as pending CI, not a passing result.

`dispatch-plan` rejects unsafe run ids, duplicate tasks, unknown dependencies, and dependency cycles before creating child runs. If child worktree creation fails mid-plan, the dispatcher removes already-created child run directories, worktrees, and local branches it owns.

`dispatch-run` is the deterministic orchestration path. It calls `dispatch-plan`, executes child runs only after dependencies have succeeded, syncs each child run's allowlisted skills, renders each child run's `connector_command.json`, executes the connector with timeout/retry trace capture, runs the validation gate, then runs the PR body/gate check. Downstream child tasks are marked `blocked` if a prerequisite fails. With `--commit-and-push`, gated writer children run `diff-gate -> commit-command -> run-commit-command -> push-command -> run-push-command`. With `--prepare-pr-command`, pushed writer children also get a deterministic PR command artifact. The scheduler still targets only `agent_id`; connector selection remains private to the dispatcher.

`ci-eval-gate` evaluates run-local `ci_results.json` and `eval_results.json` artifacts and writes `ci_eval_gate.json`. It does not run CI directly; external CI adapters can write the result artifacts.

`review-gate` evaluates `review_findings.json`, blocks unresolved `blocking` or `major` findings, allows open minor notes, and writes `review_gate.json`.

`writer-lock` creates or confirms the single current branch owner lock under `.ai/locks/branches/` and mirrors it into the run as `writer_lock.json`. `writer-transfer` moves that lock from the current owner run to a repair run with a required reason and trace entries.

`risk-approval-agent` is the autonomous continuous approver for high-risk runs. It produces `risk_approval.json`; `risk-approval-gate` validates that decision and writes `risk_approval_gate.json`.

When `automation-run --auto-review` is set, the harness dispatches a read-only `pr-reviewer` run and copies its structured `review_findings.json` back to the source writer run before lifecycle gates. When `--auto-risk-approval` is set, high-risk writer runs dispatch `risk-approval-agent` and attach `risk_approval.json` before `risk-approval-gate`. When `--auto-repair --run-auto-repair` is set and lifecycle blocks, the harness renders the source run's `repair_schedule_plan.json`, dispatches that plan through a dedicated repair schedule run, executes the `ci-repair-agent` child through the normal connector/validation/PR gate chain, and writes `auto_repair_run.json` on the source run.

`automation-daemon` converts GitHub event payloads into `.ai/events/<run-id>/scheduler_task.json` and `automation_daemon.json`. The scaffolded GitHub Actions workflow invokes it only as a dry-run planning artifact so hosted GitHub can observe events safely without holding local runtime credentials. Local machines should use `local-daemon --execute` for runtime execution.

`github-sync-poll` polls GitHub through the local `gh` CLI and converts issue/PR label or comment triggers into local daemon events. Trigger actions are configured in `.ai/rules/local-daemon.yml` under `label_actions` and `comment_actions`; supported actions are `run`, `plan`, `repair`, `review`, and `status`. If that file is absent, the harness falls back to the built-in `ai:auto`, `ai:plan`, `ai:repair`, `ai:review`, `/ai run`, `/ai repair`, and `/ai status` mappings. `local-daemon` runs that polling loop once or continuously and, when `--execute` is set locally, first runs `github-doctor`; if local `gh` auth, repo resolution, or git remotes are not ready, it writes a failed poll summary without consuming triggers. After a passed preflight, it feeds new events into the full `automation-run` chain. Failed or interrupted executable events are not marked processed; they stay in `retry_events` until their backoff expires, reach `max_attempts`, or are forced by `retry_label` / `retry_comment`. Retry attempts receive distinct automation run ids and inject `retry_context` plus `runtime_state_request` into the next scheduler task. The scheduler-agent assesses whether the previous runtime state is complete, incomplete, blocked, or unknown before planning continuation; dispatcher-owned artifacts retain raw runtime session ids and execute the actual CLI resume path. Events that exhaust retry attempts are quarantined under `.ai/local-daemon/dead-letter/<event-id>/`, and `/ai retry` or `ai:retry` can requeue them. With `--status-sync`, both commands call the deterministic `github-status-sync` path and write status results into each event's `event_result.json`. `github-status-sync` posts a concise redacted status update back to the source issue or PR without uploading raw traces.

`artifact-retention-report` scans `.ai/runs` for local-only runtime artifacts and secret-like content, then writes `.ai/artifact_retention_report.json`. The policy lives in `.ai/rules/artifact-retention.yml`; redaction findings are blocking, while runtime logs and prompts are local retention notes.

`merge-gate` evaluates merge readiness without merging. It requires PR gate, pushed branch, CI/Eval gate, review gate, current writer ownership, and a passed risk approval gate when the run risk is high, then writes `merge_gate.json`.

`merge-command` renders a deterministic `gh pr merge <branch>` command into `merge_command.json`. It requires `merge_gate.json` to be passed and `pr_execution.json` to show that the PR was created.

`run-merge-command` re-derives the expected merge command before execution, rejects mutated artifacts, executes `merge_command.json`, and records `merge_stdout.log`, `merge_stderr.log`, `merge_execution.json`, and trace events. It relies on GitHub CLI permissions and branch protection rather than bypassing them.

`integration-plan` creates an `integration-agent` writer run from child writer PRs in a schedule run. `integration-command` renders deterministic `git merge --no-ff --no-edit <child-branch>` steps. `run-integration-command` re-derives the expected steps, rejects mutated artifacts, merges in the integration worktree, records conflicts if any, and writes `integration_execution.json` plus a `commit_execution.json` compatible with the push/PR chain.

`skill-evolution-plan` mines repeated review finding patterns from a source run and writes both `skill_evolution_plan.json` and a runtime-blind `skill_evolution_schedule_plan.json` that dispatches `skill-curator` for a dedicated Skill Update PR.

`lifecycle-run` is the deterministic post-publication runner. It chains `writer-lock -> ci-eval-gate -> review-gate -> risk-approval-gate -> merge-gate -> skill-evolution-plan`, writes `lifecycle_run.json`, and returns success only when the run is merge-ready. Skill evolution planning still runs when merge is blocked so repeated failures can create a follow-up Skill Update PR.

`automation-run` is the top-level deterministic one-shot runner. It accepts either `--plan` or `--scheduler-task`; the latter first runs `scheduler-agent` and then feeds the captured `schedule_plan.json` into `dispatch-run`. It can optionally execute prepared PR commands, poll GitHub checks, run lifecycle gates, run reviewer and risk-approval agent follow-ups, render repair schedule plans when lifecycle blocks, execute merge commands after merge readiness, and create an integration run. It writes `automation_run.json` as the audit summary.

## Current MVP Boundaries

This version creates and validates the repo contract, captures scheduler output from a real agent identity in a sanitized workspace, prepares dispatch runs from a runtime-blind plan, enforces safe run ids and task dependencies, installs allowlisted runtime skills, validates connector permission contracts, renders deterministic connector/git/PR/GitHub-checks/integration/merge commands, revalidates mutable command artifacts before execution, captures logs and trace, and gates writer runs through validation policy, PR body, diff, commit, push, GitHub CI result artifacts, eval result artifacts, automated reviewer findings, branch ownership, autonomous high-risk approval, merge readiness, lifecycle-run orchestration, executable auto-repair dispatch, integration execution, merge execution, configurable local-first GitHub sync polling, local daemon execution with GitHub doctor preflight, retry/backoff/dead-letter handling for interrupted local events, runtime session capture for CLI resume, scheduler-visible runtime state assessment requests, per-event status results, redacted status sync, automation-run orchestration, artifact retention/redaction reporting, and skill evolution planning. It still relies on configured local CLI credentials and repository branch protection for hosted GitHub operations; it does not bypass those controls.
