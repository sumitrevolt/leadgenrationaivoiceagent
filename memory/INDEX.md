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
