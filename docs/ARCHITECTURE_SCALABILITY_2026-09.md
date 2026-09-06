# Backend Architecture Refactor — Scalability & Stability Blueprint (2026-09)

> Council output (1000-engineer lens), grounded in THIS repo's real production
> incidents. Constraint spine: **free-stack only (₹0 marginal AI/infra cost
> mandate), single Hostinger VPS today, revenue stage = 1 paying customer.**
> Guiding rule: **scale-path-without-rewrite** — every decision must be
> executable on the current single node and survive 10x without re-platforming.

## 0. Current topology (verified, not assumed)

```
Internet ── Caddy (TLS) ── FastAPI app :8000→8080 (uvicorn WEB_CONCURRENCY=2)
   ├── Postgres (PgBouncer :6432)          [SQLite = rollback backup only]
   ├── Redis :6379                          [broker + cache + call-state + DLQ]
   ├── Qdrant 127.0.0.1:6333                [kb_main, niche:/client: namespaces]
   ├── Celery worker (conc=4) + beat        [+ worker-heavy / worker-video queues]
   ├── FreeSWITCH + WS /telephony/vobiz/stream (L16/16k)
   └── Obs: Prometheus/Grafana/Loki/Tempo/Uptime/Gatus (~13 containers)
~1400 API ops · ~8500 tests · beat registry 63 entries · JSONL append-only logs
```

## 1. Separation of concerns — modular monolith, planes not microservices

**Decision: formalize the existing 5 planes inside one deployable, not split services.**

| Plane | Modules today | Boundary contract |
|---|---|---|
| Control (sync HTTP) | `app/api/*`, `app/platform/*` | FastAPI routes only orchestrate; heavy work → Celery (rule: web kabhi heavy nahi) |
| Async (jobs) | `app/tasks/*`, `app/worker.py` | Single beat registry + task-name contract tests (post-#468 pattern) |
| Voice (realtime) | `app/voice_agent/*`, `app/telephony/*` | WS + FreeSWITCH; all writers must hook the reward/compliance spines |
| Data | Postgres/PgBouncer, Redis, Qdrant, JSONL logs | Single accessor modules; no direct driver imports in routes |
| AI gateway | `app/voice_agent/free_ai.py`, `omniroute_client.py` | Only path to providers; 429 circuit ladder; key rotation |

**Why not microservices:** team-of-1 + agent fleet, ₹0-cost mandate, single VPS
revenue stage. Microservices buy independent scaling at the cost of an ops
surface (per-service deploy, tracing, version skew) this project cannot staff —
and the 2026-07-14 `:latest` skew incident proved even ONE app has provenance
drift problems. **Trade-off accepted:** deploys are all-or-nothing; mitigated
by `deploy_vps.sh` atomic tags + health-gated exit + rollback tags.

**Actionable (Phase 1, low risk):** enforce plane boundaries with import-linter
contract (`app.api` must not import `requests`/DB drivers directly; only
`app.platform.*` accessors). Turns the existing convention into a CI-checked
seam so a later physical split is a move, not a rewrite.

## 2. Horizontal scaling & load distribution

**Web (stateless already):** uvicorn workers behind Caddy. Session/cache state
already in Redis → N app replicas is a Caddy `upstream` block + shared volume
decision, not a refactor. **Blocker to document:** local-disk artifacts
(`data/*.jsonl`, uploads, `frontend/office_unity/`) — replica #2 needs either
shared volume (same host) or object storage (Phase 2).

**Async (already queue-routed):** `_route_video_task` / heavy-queue routing
means worker pools scale horizontally per queue: `worker`, `worker-heavy`,
`worker-video` are independent containers (R10 deploy script deploys all 5
images to prevent skew). Add: per-queue concurrency metrics → autoscale is
manual but *directional* today.

**Load distribution rules (from incidents):**
- Countdown/ETA tasks live in broker `unacked`, NOT `llen celery` — backlog
  runbooks must check both (the `del celery >500` landmine stays valid).
- acks_late=False for self-requeueing chains (duplicate-chain flood lesson:
  2501 ticks); acks_late=True only for at-least-once work with idempotency keys
  (`@idempotent_task` decorator is the pattern).
- Boot-grace: heavy daily beat jobs must SKIP on boot window (restart-storm
  postmortem) — keep, and extend to any new beat entry via the staff-registry
  contract test.

**Voice plane:** FreeSWITCH + WS handlers pin to the single node by nature
(SIP/trunk termination). Scaling voice = second trunk region, NOT replicas —
out of scope until revenue demands it; the compliance spine (DND fail-closed,
TRAI window, caps) is node-local state in Redis + Postgres and must move to the
shared data plane before any second voice node.

## 3. Data layer — caching, partitioning, JSONL graduation

**Caching discipline (keep + codify):** Redis is cache + broker + call-state on
one instance — acceptable blast-radius today ONLY because cache TTLs follow the
"must exceed poll interval" rule and call-state is fail-safe on loss. **Phase 2
trigger:** when call-state traffic doubles, split Redis into broker vs
state/cache instances (one config change per consumer via `settings`, no code
restructure — accessor modules make this a swap).

**Partitioning — the real Phase-1 item:** append-only JSONL files
(`rl_rewards.jsonl` 3860+ rows, `call_qualifications.jsonl`, `invoices.jsonl`,
`gsc_daily.jsonl`) are the scale ceiling: unqueryable, single-file corruption
risk, backup-inconsistent. **Graduate them to Postgres monthly-partitioned
tables** (`PARTITION BY RANGE (ts)`) behind the SAME accessor modules, with a
reader fallback to the JSONL for transition. One writer, append-only, monthly
partitions + rclone-to-Drive archival = zero new infra, big queryability win.
This also fixes the "can't backfill historical quals" problem (SQL INSERT is a
normal migration, not a hand-scripted prod write).

**Postgres scaling path:** PgBouncer transaction pooling (already) → read
replica when reporting queries hurt the primary → monthly partitions for
`call_attempts`, `content_items`, graduated JSONL tables. Qdrant stays
single-node with namespace-per-tenant (customer isolation is a DPDP gate) +
scheduled snapshots to Drive (backup restore already PROVEN).

## 4. Fault tolerance & graceful degradation

The project's strongest existing pattern — **codify the open/closed split:**

| Failure domain | Posture | Example |
|---|---|---|
| Billing meters, tenant middleware | **fail-OPEN** (never block revenue path) | meters degrade to estimates |
| DND scrub, webhook signatures, compliance | **fail-CLOSED** (never risk illegal/bad send) | lookup fail = block promo |
| LLM/STT/TTS providers | circuit-breaker ladder | free_ai.py 60s→30min 429 escalation |
| Scheduler chains | dead-man watchdog, cap-aware | self_improve ensure_alive (won't revive through intentional cap-pause — 2026-09-06 verified working-as-designed) |
| Task delivery | idempotency keys + DLQ | `dlq:failed_tasks`, `@idempotent_task`, retry/DLQ/metrics/rollback SOP |

**Gaps this design closes (all have real postmortems):**
1. **Dormant-wiring observability** — social-post task was never registered
   (3x/day beat → unregistered, silent) and voice RL rewards had no hooks on 2
   of 3 writers. Rule now: every beat/task/writer contract-test
   (registry-pin tests exist post-#468/#470) AND `automation_health`
   wiring_gaps daily brief must include "task registered?" not just "flag on?".
2. **Health zones** — `/health` gains `zone: liveness|readiness|
   dependency-degraded` so Caddy can shed traffic on dependency loss without
   container restarts (today a PgBouncer blip still 200s the liveness path —
   correct — but readiness signals for LB are absent).
3. **Watchdog asymmetry** — cap-paused vs dead distinction (ensure_alive
   docstring) must be replicated for every self-requeue chain; the generic
   pattern is: heartbeat + next-allowed-ETA check + NX revive-lock + day-scoped
   cap awareness.

## 5. Communication patterns (keep boring)

- **Sync internal:** HTTP over service names, port **8080** in-network
  (8000-in-network = silent ECONNREFUSED, 612 events/24h incident). Codify in
  one `settings.internal_app_url`.
- **Async:** Celery via the single worker.py registry (63 beat entries;
  parity-test pinned). No second broker. **Outbox pattern** ONLY for
  billing-critical events when a second writer emerges (UPI confirmation
  ledger is append-only file+DB today — graduate with the JSONL migration).
- **Event-ish:** Redis pub/sub for call-state fan-out, ntfy for owner push,
  WhatsApp 1-click human gate. No Kafka/RabbitMQ — violates ₹0 mandate and
  solves nothing at this scale.
- **Scheduled:** beat → registry → parity test → wiring_gaps brief. New
  entries MUST ship with: flag + idempotency + retry/DLQ + metrics + rollback
  + runbook (existing automation-change rule, now with teeth via contract
  tests).

## 6. Trade-off ledger (decisions and what they cost)

| Decision | Chose | Paid | Buy back later via |
|---|---|---|---|
| Modular monolith vs services | monolith | all-or-nothing deploys | import-linter seams → physical split when 2nd node arrives |
| Single Redis | simpler ops | broker/cache blast radius | accessor-module swap config |
| JSONL → partitioned PG | queryability + backup consistency | migration work + dual-read window | phased per-file, reader-fallback |
| No service mesh / HTTP internal | boring, ₹0 | no mTLS/retry depth | Caddy + typed clients + timeouts everywhere |
| Manual UPI rail | zero provider fees/fail-closed | no auto-webhooks | n/a (owner decision, closed ADR #243) |
| Free AI providers | ₹0 marginal | 429 variance | circuit ladders + OmniRoute combos (already) |

## 7. Sequenced execution order (no-rewrite path)

1. **Now (hardening, zero infra):** health zones; wiring_gaps "registered?"
   check; import-linter plane contract; internal URL codification.
2. **Next (Phase 1, 1 PR each):** JSONL→PG monthly partitions (rewards first —
   smallest, freshest incident knowledge); readiness endpoint in Caddy
   fallback; backlog runbook updates (unacked vs llen).
3. **Later (Phase 2, revenue-triggered):** 2nd app replica behind Caddy;
   broker/state Redis split; read replica; object storage for artifacts.
4. **Never (until owner says):** second voice node, paid queues/AI, microservice
   split without staffing.

*Every item maps to an incident or a measured constraint in this repo — nothing
here is resume-driven design.*
