# ADR-150 — Coordination Hub as Owner OS thin projection

**Date:** 2026-08-04
**Status:** Accepted (code canary; flag default OFF)

## Context

A "Coordination Hub" dashboard (tools presence, tasks, git, events) is useful for
owner ops. An earlier reported implementation (`coordination_hub.py` + HTML) was
**never found** in any worktree or Git history — unverified.

Building a second independent task/agent registry would split-brain against:

- Owner OS (sole action authority)
- External-agent mission ledger (leases / path scope / evidence)

## Decision

Ship Coordination Hub as a **flag-gated thin projection/adapter** under the
Owner OS namespace:

- Flag: `COORDINATION_HUB_ENABLED` (default `0`)
- API: `/api/admin/owner-os/coordination-hub/*`
- UI: `/app/owner` → Coord Hub tab (read-only)
- Reads: `owner_os.agent_registry`, external-agent `dashboard_rows`/`summary`,
  `office_hq.build_coordination`, bounded redacted git, Hub events/presence
- Writes: tool presence + append-only events only (HMAC inbound)
- Mutations (pause/kill/mission/deploy): **refused** — pointers to existing APIs

## Security

- Per-tool HMAC secrets (`COORD_HUB_TOOL_<ID>_SECRET`, `COORD_HUB_BUZZ_SECRET`)
- Buzz webhook: dedicated HMAC + timestamp/nonce + replay fingerprints
- Admin JWT / shared `ADMIN_API_KEY` alone **cannot** authenticate tool/Buzz inbound
- Git probe: allowlisted read-only commands, timeout, byte cap, secret redaction
- Events: append-only JSONL with provenance; secrets never persisted

## Consequences

- No 32nd STAFF agent; no second mission ledger
- Prod stays inert until explicit flag flip (separate owner authorize)
- Rollback = leave / set `COORDINATION_HUB_ENABLED=0`
