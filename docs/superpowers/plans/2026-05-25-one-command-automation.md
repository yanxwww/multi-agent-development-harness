# One Command Automation Plan

## Goal

Make the harness run from an agentic scheduler output through deterministic dispatch, validation, publication gates, lifecycle gates, and follow-up scheduling.

## Steps

- [x] Add a `scheduler-run` command that executes `scheduler-agent`, captures connector stdout/events, extracts a runtime-blind `SchedulePlan`, validates it, and writes `schedule_plan.json`.
- [x] Extend `automation-run` so callers can provide either a ready `--plan` or a `--scheduler-task` that first runs `scheduler-agent`.
- [x] Add validation policy loading so writer runs get commands from `.ai/rules/validation-policy.yml` instead of hardcoded role defaults.
- [x] Add deterministic reviewer and risk approval agent runs for publication lifecycle automation, with extracted JSON artifacts copied back to the source writer run.
- [x] Add repair follow-up scheduling when lifecycle gates block merge readiness.
- [x] Wire merge execution into `automation-run` after lifecycle says a writer run is merge-ready.
- [x] Verify with unit tests, scaffold validation, and full unittest discovery.

## Status

Completed in PR #9. Current publication state: draft PR with passing local validation and GitHub CI, ready to move out of draft and merge after this task-status update is pushed.
