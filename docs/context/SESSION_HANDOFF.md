# SESSION_HANDOFF — 2026-08-05 merge+deploy OKF + memory stack

## Merged
- **#251 OKF Phase-1** → `main` @ `b572527` (pre-memory)

## In flight
- Branch `feat/agent-memory-stack-pr` (ADR-159 + ADR-158/161 memory stack) rebased on `b572527`
- Flags: `MEMORY_STACK_ENABLED` OFF default; `OKF_INGEST_ENABLED` OFF
- Deploy: code-only via `deploy_vps.sh`; kill-gate restore after

## Do not
Arm memory/OKF ingest with this deploy · Safe Pack mutate · fake PAID · force-merge on red CI
