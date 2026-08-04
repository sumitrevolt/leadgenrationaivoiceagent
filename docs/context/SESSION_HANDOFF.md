# SESSION_HANDOFF — 2026-08-04 (agent-swarm eval)

## Decision (Chairman)
**desplega-ai/agent-swarm = NOT best as a product dependency.**
**NO full clone / NO second Agent-OS.** FEATURE_HARVEST patterns only into Owner OS / STAFF / ADR-148.

## Evidence
- Swarm = Bun + Hono + SQLite + Docker coding workers (Claude Code/Codex/OpenRouter) — company-internal OS
- LeadGen already: 31 STAFF · Owner OS · Celery · OpenClaw GREEN · llm_council · free LLM · TRAI/DPDP
- Locked by ADR-148/149/OPENCLAW + new **ADR-155**
- Eval clone (outside repo): `C:\Users\Ratanshila\Documents\_agent_swarm_eval_2026-08-04`

## Prod (prior session, still tip unless re-probed)
- Last deploy session: `d451b56c` Dependabot cycle; re-probe `/health` before claiming SHA

## Do NOT
- Vendor agent-swarm into monorepo or compose
- Flip `COORDINATION_HUB_ENABLED` without authorize
- Add 32nd STAFF persona named “swarm”

## Next (enterprise that actually moves GTM)
1. Hot Queue → 2nd paid customer (WS-R3 pay-truth)
2. Optional: pick ONE harvest pattern (HITL litmus / drain loop) as flag-gated Owner OS ticket
3. Scorecard honesty gaps — not a second control plane
