# Validate Local Daemon Trigger Policy

## Goal

Make `harness validate` reject invalid `.ai/rules/local-daemon.yml` trigger policies before a local daemon run attempts to poll or execute automation.

## Tasks

- [x] Add a failing validation test for unsupported local daemon trigger actions.
- [x] Extract local daemon trigger policy parsing into a shared deterministic module.
- [x] Call the shared policy validator from `validate_scaffold`.
- [x] Update documentation and version metadata.
- [x] Run targeted and full verification.
