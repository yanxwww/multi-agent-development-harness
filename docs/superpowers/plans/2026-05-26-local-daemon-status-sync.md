# Local Daemon Status Sync Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the local daemon automatically publish concise GitHub status comments for local trigger processing without uploading raw traces or runtime logs.

**Architecture:** Keep `github-status-sync` as the deterministic status command and let `github-sync-poll` / `local-daemon` opt into it through a flag. Each event records a local `event_result.json` containing processing status, optional automation run id, and optional status sync result.

## Steps

- [x] Add failing tests for `github-sync-poll --status-sync` posting planned status comments for newly created local events.
- [x] Add failing tests that status comments remain redacted and event results are written locally.
- [x] Add `--status-sync` and status timeout CLI flags to `github-sync-poll` and `local-daemon`.
- [x] Write `.ai/local-daemon/events/<event-id>/event_result.json` for every created event.
- [x] In status-sync mode, post planned or final execution status through the existing deterministic GitHub comment path.
- [x] Update README and version metadata.
- [x] Run targeted and full validation.
