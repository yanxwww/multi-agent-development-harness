# Runtime State Resume Assessment

## Goal

Make resume decisions state-aware: a retry must first expose the previous runtime state to an assessor agent before the dispatcher executes a CLI resume or repair path.

## Tasks

- [x] Add failing tests for runtime session extraction from connector output.
- [x] Add failing tests for retry scheduler tasks carrying a runtime state request.
- [x] Capture resumable Codex thread IDs and Claude session IDs in `connector_execution.json`.
- [x] Write scheduler-visible `runtime_state_request.json` for retry attempts.
- [x] Keep raw runtime binding decisions private to dispatcher-owned artifacts.
- [x] Run targeted and full verification.
