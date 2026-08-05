# DECISIONS — future-implementation affecting only

Link ADRs; do not duplicate full text. Full ADRs live in `memory/decisions.md`.

| Decision | Reason | Date | Affected | Supersedes |
|---|---|---|---|---|
| Canonical context lives in `docs/context/*` | Chat/agents fragmented truth | 2026-07-20 | all AI tools | Informal CLAUDE-only Current State as sole handoff |
| Max 3 active workstreams | Prevent parallel thrash | 2026-07-20 | ACTIVE_WORK.md | Open-ended multi-agent plans |
| Swara/voice FROZEN for this upgrade wave | User mandate; burn + false-interested risk | 2026-07-20 | voice stack | Any “upgrade all 32 agents” voice edits |
| Agent count = 31 STAFF (+ Agent-OS control plane) | Code `team.STAFF` / registry | 2026-07-19 | AGENT_OWNERSHIP | Docs saying 32 agents as roster size |
| ADR-128 Agent Runtime + pilots | Shared fail-closed runtime | 2026-07-19/20 | agent_runtime* | Inert registry-only Phase-A |
| ADR-123 identity canonicalize | Jiya portal orphan drafts | 2026-07-19 | customer_auth, delivery status | Raw billing id on marketing reads |
| platform_dial HARD OFF | User mandate | 2026-07-05 | Swara dial | Re-enable without allowlist |
| platform_dial FULL CAMPAIGN LIVE (`PLATFORM_DIAL_DAILY=1` bool, `PLATFORM_DIAL_LIMIT=100` cap, test-mode removed) | Owner go-ahead | 2026-08-02 | dial path | supersedes 2026-07-05 HARD OFF; compliance spine (DND fail-closed, TRAI 10-19 IST, AI-disclosure, consent, DLT_APPROVED=1) unchanged |
| Production SHA truth = `/health.version` | Provenance | 2026-07-14 ADR-097 | deploy | CLAUDE memory without probe |
| Delivery assurance = read-only compose under nikhil | Paid customer miss detection without new persona | 2026-07-19/20 | delivery_assurance | Inventing 32nd delivery agent |
