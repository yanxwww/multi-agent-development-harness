# One Command Automation Plan

## Goal

Make the harness run from an agentic scheduler output through deterministic dispatch, validation, publication gates, lifecycle gates, and follow-up scheduling.

## Steps

1. Add a `scheduler-run` command that executes `scheduler-agent`, captures connector stdout/events, extracts a runtime-blind `SchedulePlan`, validates it, and writes `schedule_plan.json`.
2. Extend `automation-run` so callers can provide either a ready `--plan` or a `--scheduler-task` that first runs `scheduler-agent`.
3. Add validation policy loading so writer runs get commands from `.ai/rules/validation-policy.yml` instead of hardcoded role defaults.
4. Add deterministic reviewer and risk approval agent runs for publication lifecycle automation, with extracted JSON artifacts copied back to the source writer run.
5. Add repair follow-up scheduling when lifecycle gates block merge readiness.
6. Wire merge execution into `automation-run` after lifecycle says a writer run is merge-ready.
7. Verify with unit tests, scaffold validation, and full unittest discovery.
