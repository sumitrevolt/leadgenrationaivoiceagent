# Reliable Event Delivery (Outbox) — Research & Integration

**Date:** 2026-06-15 · **Scope:** Deeper SOTA reliability/durability/guardrails research; add the one genuinely-missing high-value backend item.
**Outcome:** Outbound-webhook **outbox** (retry-queue + exponential backoff + jitter + DLQ) — outbound events ab at-least-once (pehle at-most-once, transient fail pe LOST). Pairs with consumer-side idempotency (pichhli baar). Free-stack, never-raise, prod_check green.

---

## 1. Deep research (broader SOTA) + verdict

| Pattern / repo | Core idea | Verdict for this project |
|---|---|---|
| **Outbox pattern** (Microsoft/Conduktor/Temporal-community 2026) | DB me state + event ATOMIC persist; background publisher deliver; consumer event-id se dedupe | **LIYA** — exact gap tha (neeche) |
| **Temporal / durable execution** | Replayable crash-safe workflow orchestration; exactly-once *workflow logic* | **SKIP** — heavy server + new infra; single-VPS ke liye over-engineering. Outbox + Celery durable kaafi |
| **NeMo Guardrails** | Colang policy middleware, 5-stage input/output checks | **SKIP** — NVIDIA khud bolta "not prod-ready (beta)" |
| **Guardrails-AI** | Pydantic JSON-schema output validation | **SKIP** — naya dep; humari Instructor (`structured.py`) + draft-only/gated-send/DND/consent safety already defense-in-depth |
| **Langfuse / AgentOps** | Agent run tracing/cost | **SKIP** — `llm_metrics` (per-provider ok-rate/latency, ab Prometheus me — audit P1-3) + Sentry already cover |

**Best-practice checklist (2026 webhook reliability):** idempotent consumers ✓ (pichhli baar) · exponential backoff + jitter ✓ (ab) · DLQ you watch ✓ (ab) · transactional outbox ✓ (ab, file-based). Sab tick.

**Discipline:** ek REAL high-value fix > speculative bloat. Baaki sab ya already-covered ya single-VPS ke liye galat fit — isliye jaan-bujhke skip (duplicate nahi banaya).

---

## 2. The gap (proven)

`app/platform/outbound_webhooks.py` `emit()` — client systems (Zapier/n8n/CRM/Sheets) ko `payment_captured`, `inquiry_received`, `lead_hot`, `booking`, `call_completed`, etc. POST karta tha **5s timeout pe par RETRY NAHI** (docstring: "retries nahi"). Matlab:
- Receiver ek pal ke liye down/slow/5xx → event **HAMESHA ke liye LOST** (sirf deliveries.jsonl me ek failed-log, koi redelivery nahi). **At-most-once.**
- Yeh consumer-side idempotency (jo maine pichhli baar add kiya) ka producer-side counterpart missing tha.

## 3. Fix — outbox (reliable delivery)

`outbound_webhooks.py`:
- **`_enqueue_retry()`** — failed delivery (exception ya non-2xx) → `data/webhook_retry_queue.jsonl` (file_lock-safe, bounded 2000).
- **`retry_pending()`** — outbox worker: due items ko **exponential backoff + jitter** (~60s→4m→16m→1h→4h, cap 6h, ±25% jitter) ke saath redeliver. Deliver/hook-gaya → queue se drop; **`_MAX_ATTEMPTS=6`** ke baad → **DLQ** (`webhook_dlq.jsonl`). Concurrency-safe: single-flight `asyncio.Lock` + reconcile-by-id (flush ke dauraan emit ne naye items add kiye to woh na khoyein). Never raises.
- **`emit()`** — ab failure pe `_enqueue_retry` + har event pe **opportunistic flush** (`create_task(retry_pending())`, non-blocking) = scheduler-free, bursty-traffic pe queue khud nikalti.
- **`ops_watchdog.run_watchdog()`** (hourly) — best-effort `retry_pending()` call = **time-based** retry (zero-traffic/raat me bhi). Watchdog ko kabhi block nahi karta.
- **`dlq_recent()`** — DLQ inspection/manual-replay ke liye.

**Net:** outbound events ab **at-least-once** (transient fail survive, backoff-retry, max-attempts pe DLQ for inspection). Consumer-side idempotency ke saath = **reliable + dedupe** (textbook outbox + idempotent-consumer). Tunable: `_MAX_ATTEMPTS`.

---

## 4. Verification
`python scripts/prod_check.py` → **ALL CHECKS PASSED**, `app.main` imports OK, routes **652** (unchanged — no endpoint, pure reliability), env OK. Free-stack (file + httpx, already present), never-raise, no new dep. Deploy-pending (same pipeline).

### Files
- `app/platform/outbound_webhooks.py` (outbox: enqueue/retry/DLQ + emit wiring)
- `app/platform/ops_watchdog.py` (hourly flush hook)

## Sources
- Outbox pattern (2026) — https://www.conduktor.io/glossary/outbox-pattern-for-reliable-event-publishing · https://james-carr.org/posts/2026-01-15-transactional-outbox-pattern/
- Temporal vs outbox — https://community.temporal.io/t/use-temporal-to-replace-transactional-outbox-pattern/7684
- Background jobs & queues 2026 — https://www.digitalapplied.com/blog/background-job-queue-patterns-2026-engineering-reference
- LLM guardrails 2026 — https://www.digitalapplied.com/blog/llm-guardrails-production-safety-layers-reference-2026
