# Deterministic Runtime Resume Command Plan

## Goal

Connect the scheduler's `resume_runtime_session` decision to auditable deterministic command artifacts that can resume local Codex or Claude Code runtime sessions.

## Checklist

- [x] Add failing tests for rendering Codex and Claude resume commands.
- [x] Add failing tests for executing a rendered resume command and rejecting mutated artifacts.
- [x] Implement `resume-command` artifact rendering from `runtime_state_decision.json` and `connector_execution.json`.
- [x] Implement `run-resume-command` execution with prompt hash validation, stdout/stderr capture, JSON event capture, exit status, and trace.
- [x] Allow scheduler-authored `runtime_state_decision` inside SchedulePlan and attach resume decisions to the observed target run.
- [x] Wire both commands into the CLI.
- [x] Document the resume command chain and bump package version.

## Verification

Run targeted and full CLI verification before merging:

```bash
python3 -m unittest tests.test_cli.HarnessCliTests.test_resume_command_renders_codex_and_claude_cli_resume tests.test_cli.HarnessCliTests.test_run_resume_command_executes_rendered_command_and_rejects_mutation -v
python3 -m unittest tests.test_cli.HarnessCliTests.test_scheduler_resume_decision_enables_deterministic_resume_command -v
python3 -m ai_harness validate --target .
python3 -m ai_harness connector-contracts --target .
python3 -m py_compile ai_harness/resume.py ai_harness/cli.py
python3 -m unittest discover -s tests -v
```
