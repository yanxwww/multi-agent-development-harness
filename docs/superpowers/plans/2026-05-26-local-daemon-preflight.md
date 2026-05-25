# Local Daemon GitHub Preflight

## Goal

Make executable local daemon runs fail early when local GitHub CLI or repository remote state is not ready for PR automation.

## Tasks

- [x] Add a failing test that `github-sync-poll --execute` runs `github-doctor` before consuming triggers.
- [x] Record the preflight result in the local daemon poll summary.
- [x] Keep read-only polling unaffected.
- [x] Ignore local `github_doctor.json` runtime artifacts in generated scaffolds.
- [x] Update documentation and version metadata.
- [x] Run targeted and full verification.
