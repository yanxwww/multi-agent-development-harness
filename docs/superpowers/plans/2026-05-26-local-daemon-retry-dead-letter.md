# Local Daemon Retry And Dead Letter

## Goal

Make failed executable local daemon events recoverable instead of permanently processed after the first failed or interrupted automation attempt.

## Tasks

- [x] Add failing tests for retry state, backoff, retry triggers, and dead-letter quarantine.
- [x] Add retry policy parsing and validation to `.ai/rules/local-daemon.yml`.
- [x] Preserve failed event state without adding failed executable events to `processed_event_ids`.
- [x] Catch interrupted automation attempts and write deterministic event results.
- [x] Inject retry continuation context and use distinct automation run ids per attempt.
- [x] Support `/ai retry` and `ai:retry` to force retry or requeue dead-lettered events.
- [x] Update scaffold, gitignore, docs, and version metadata.
- [x] Run targeted and full verification.
