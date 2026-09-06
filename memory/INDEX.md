# memory/ — Project Knowledge Base (Tier 2)

> Tier 1 (hot cache) = `CLAUDE.md ## Current State` (≤40 lines). Tier 2 = yeh directory. Dated history archive = `docs/SESSION_LOG.md`.

## RULES OF THE MEMORY SYSTEM

1. **Read this INDEX.md before any non-trivial task.** Load ONLY the files relevant to the task — not everything (token discipline).
2. **Write-back protocol:** after any task that produced a decision, incident, or new procedure, append to the correct file IN THE SAME SESSION. A session that changes architecture but doesn't update memory is an incomplete session.
3. **No secrets ever.** Env var NAMES allowed, values never. (`scripts/check_secrets.py` enforces repo-wide.)
4. **Pruning:** monthly, move stale `## Current State` items into `decisions.md` or delete. CLAUDE.md working memory must stay under 40 lines — if it grows, something belongs here in Tier 2.
5. **Single source of truth: code wins.** If code and memory disagree, code is right — then fix the memory. (Pricing truth = `packages.py`, flags truth = `GET /api/growth/infra/flags`, schedule truth = `team_scheduler.py`.)
6. **Every entry dated (YYYY-MM-DD) and atomic** — one fact/decision per entry. `decisions.md` is append-only: never edit past entries; supersede with a new entry.

## TABLE OF CONTENTS

| File | What's inside | Read when |
|---|---|---|
| `decisions.md` | Architecture Decision Records (append-only) | changing architecture/pricing/providers, ya "pehle aisa kyun kiya tha?" |
| `glossary.md` | Domain terms, internal shorthand, AI-staff roster, entity names | naye naam/codename mile, staff-agent ya plan-key confuse ho |
| `integrations.md` | Per external service: purpose, env-var NAME, rate limits, observed failure modes, retry policy | koi provider wire/debug karna ho, 429/quota issue |
| `incidents.md` | Postmortems: what broke, root cause, fix, prevention rule | similar symptom dikhe, ya risky area touch karne se pehle |
| `playbooks.md` | Repeatable procedures: deploy, rollback, new feature, client onboarding, flag enable, key rotation | koi operational kaam repeat karna ho |
| `backlog.md` | Parked ideas WITH the why, so context survive kare | "ab kya banaye" / kisi purane idea pe wapas aana ho |

## OKF curated bundle (Tier-2 companion)

Repo-root **`knowledge/`** = Open Knowledge Format v0.1 draft bundle (ADR-119). Curated product/agent/ops/architecture pointers for agents. **Not** a RAG replacement — large-scale retrieval stays Qdrant; live truth stays Postgres; deep ADRs stay in `decisions.md`. No secrets in OKF.

## FILE STATUS (2026-09-02 consolidation)

| File | Lines | Last updated | Notes |
|---|---|---|---|
| `decisions.md` | ~2915 | 2026-09-06 | Append-only ADRs; latest ADR-191 (OmniRoute gateway health vs desktop-auth readiness). ~182 entries. **Durable.** |
| `glossary.md` | ~100 | 2026-08-21 | Core terms stable. **Durable** — add new terms as they appear. |
| `integrations.md` | ~50 | 2026-08-21 | Core providers stable. **Durable** — update rate limits/failure modes as observed. |
| `incidents.md` | ~150 | 2026-09-07 | Latest covers central-ledger overdue-active truth normalization. **Durable** — prevention rules = operational knowledge. |
| `playbooks.md` | ~350 | 2026-09-07 | Canonical council-ledger sync now includes 6h temporal stale rule. **Durable.** |
| `backlog.md` | ~250 | 2026-09-02 | **Consolidated** — 23 active/parked items + 33 archived (shipped/superseded). Competitor research appended. |

## CONSOLIDATION NOTES (2026-09-02)

### Durable keep (no action needed)
- `decisions.md` — all ADRs remain authoritative
- `glossary.md` — stable domain vocabulary
- `integrations.md` — provider contracts stable
- `incidents.md` — postmortems with prevention rules
- `playbooks.md` — operational runbooks current

### Dated/retired → ARCHIVED in backlog.md (see ARCHIVED section)
- 33 items moved to backlog.md ARCHIVED section with SESSION_LOG.md date references (Unity, GSC deployed, referral/evergreen DONE, meta-brand-posting DONE, OpenClaw Stage A LIVE, Customer Delivery OS complete, DKIM/SPF/DMARC, Postiz channels, etc.)

### Active backlog (23 items)
- DeepSeek Harness patterns #2-4, FREEBUFF Hot Queue, GSC enable, Cloudflare OS patterns, MetaGPT steals #2-4, Social channels (LinkedIn/Threads/Pinterest), WAHA secret rotation, Approval-reminder idem key, RL flywheel lopsided, Agentic/LightRAG eval, .env.example drift, pytest CI-blocking, key rotations, STUDIO_ENTITLEMENT_GATE, enterprise audit follow-ups, own telephony, missed-call callback, GBP API, Hybrid RAG, OKF ingest Phase-2/3, Voice fine-tune, vobiz_stream refactor, P4-3 eval_gate, Competitor research

### Cross-file overlaps (merge/fix)
- `CURRENT_SESSION.md` (OmniRoute audit 2026-07-12/13) → **DELETED** — content merged into `decisions.md` ADR-081 through ADR-084 and `integrations.md` OmniRoute entry. This file was a temporary session scratchpad.
- `docs/SESSION_LOG.md` — dated history archive, keep as-is (append-only)
- `docs/context/CURRENT_STATE.md` + `ACTIVE_WORK.md` + `SESSION_HANDOFF.md` — Tier 1 hot cache, sync from `CLAUDE.md ## Current State`
