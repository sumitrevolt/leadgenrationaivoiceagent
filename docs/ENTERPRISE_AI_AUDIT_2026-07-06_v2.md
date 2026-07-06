# LeadGenAI — Enterprise AI Architecture Audit **v2** (2026-07-06, post-deploy)

> Re-run of the enterprise audit against the **current, deployed** codebase (`c5761b4` LIVE on leadsgenai.in).
> Since v1 ([ENTERPRISE_AI_AUDIT_2026-07-06.md](ENTERPRISE_AI_AUDIT_2026-07-06.md)) every v1 finding was **fixed + deployed**,
> plus the W1-4 reliability program, Product-1/2 delivery, self-serve calling, and vobiz-HMAC shipped. This pass
> **verified the fixes landed in the deployed tree** (grep + live smoke) and fanned out 2 fresh auditors over the
> genuinely-new code. Nothing marked complete without codebase evidence.
>
> **Method:** ground-truth `prod_check` (1033 routes, 46 pages/0 gaps, 78/78 engines, 0 orphans) + live prod smoke
> (health 200 production, security gates 401/403, activation trimmed, celery 0) + 2 read-only auditors
> (wave-program agent-loops · new-surface security).

---

## Scorecard — v1 → v2

| Score | v1 | **v2** | Why it moved |
|---|---|---|---|
| **Production Readiness** | 86 | **91** | Everything DEPLOYED + verified live; the v1 latent all-tenant KB data-loss is fixed; W1-4 reliability (fail-closed lock, real dead-man, per-engine isolation) live. Drag: 2 new MEDIUMs below. |
| **AI Architecture** | 85 | **89** | RAG was the weak spot (78) — KB silent-wipe + dedup + delete-before-reseed all fixed. Prompt-injection sanitized. Perf items still open. |
| **Agentic AI** | 88 | **90** | Wave program hardened loops (fail-closed lock + reclaim-only-on-proven-stale, tick-slot fail-closed, content per-engine isolation, dead-man registry 34/34 complete). Minus the self_improve rollback-heartbeat blind spot. |
| **SaaS** | 85 | **88** | Product-1+2 delivery gaps closed + deployed (day-1 seed, autopilot surface, transcript surface, self-serve calling gated). |
| **Security** | 90 | **93** | v1 anon-leaks/booking/SSRF fixed + deployed + 2nd sweep clean + vobiz-HMAC; new voice-calling route audited (1 finding, **fixed this session**). |
| **Performance** | 84 | **85** | No major perf work this cycle (per-process breaker/cache + realtime-chain reorder still open, documented). |

**Verdict:** the platform moved from "mature but with a latent data-loss bug + undeployed fixes" to **"deployed, hardened, and delivering."** Two new MEDIUM findings remain (both in the wave code, one dormant), plus a self-found voice-calling gap now fixed.

---

## Findings this pass (ranked)

### 🟠 [MEDIUM] self_improve dead-man heartbeat hardcodes `ok=True` on the rollback topology
- **Root cause:** `app/agents/self_improve.py:210` `_heartbeat()` writes `record_run("self_improve", ok=True, …)` (literal). On the **Celery** path `app/tasks/staff_jobs.py:167` overwrites it with the real bool (last-writer-wins) — correct. But on the **in-process/rollback** path (`RUN_IN_PROCESS_SCHEDULER=1`), `app/platform/team_scheduler.py:302-306` calls `run_once()` directly and only `logger.debug`s the result — never re-records real status.
- **Impact:** in rollback mode (exactly when dead-man visibility matters — Celery disabled mid-incident) a failing self_improve iteration always shows `last_ok:true`, never fires an overdue/failure alert. Dormant today (prod default = Celery-durable).
- **Fix (S):** make `_heartbeat()` take a real `ok` param and pass `rec["ok"]` at the `self_improve.py:1478` call site (root fix, both paths), OR add a `record_run` with real status at `team_scheduler.py:303`.
- **Owner:** parallel W1.x session's file — **flagged, not edited** (active-session collision avoidance).

### 🟠 [MEDIUM] auto_outreach bulk-mark double-send risk on crash
- **Root cause:** `app/platform/auto_outreach.py:731-735` — emails sent + counted BEFORE the `emailed_at` marker is flushed (batched every 10). A crash/OOM/SIGKILL between sends #1-9 loses those markers; the dedup gate (`auto_outreach.py:594`) then re-selects + **re-sends duplicate cold emails** on the next run (compounded by DLQ auto-retry).
- **Impact:** deliverability / spam-complaint risk on a warmup-sensitive system; the crash class is not hypothetical (OOM/SIGKILL incident history).
- **Fix (S):** lower the flush threshold `>= 10` → `>= 1` (mark-per-send); the bulk-write is O(≤25) per run (cap-bounded), not the O(N²)×2000-row rewrite the batching was built to avoid. Flag `OUTREACH_BULK_MARK` is the rollback switch.
- **Owner:** parallel W1.x session's file — **flagged, not edited**.

### 🟢 [FIXED this session] Voice self-serve TOCTOU re-dial window
- **Root cause:** `POST /api/customer/voice/call-queue` anti-joined `CallLog.lead_id`, but `queue_call` only Redis-enqueues — the `CallLog` row lands *post-call*, leaving a window where the same lead could be re-queued → **repeat-dial a real person** (TRAI/DPDP; minutes/quota is fail-open).
- **Fix (SHIPPED):** in-flight Redis SET (`voice_inflight:{cid}`, TTL) skipped in addition to `CallLog`; per-client daily cap (`VOICE_SELFSERVE_DAILY_CAP`, default 200); per-IP `rate_limit` on the route; honest docstring. `app/api/customer_dashboard.py`. Tests: `test_customer_voice_selfserve.py` (6 green incl. in-flight-skip + cap). Gated OFF (not live) — hardened before enable.

### Verified-GOOD (codebase-confirmed this pass)
- **v1 fixes all present + live:** KB `KB_ALLOW_DIM_WIPE` guard, `_kb_point_id` dedup, `delete_source`/`KB_REPLACE_ON_RESEED`, `_sanitize_prompt_content` (×6 sites), vobiz `hmac.compare_digest`, `require_admin` on `/api/platform/health` + `/api/v1/status` (live **401**), activation `/summary` trimmed (live, no `blockers`/`warns`).
- **Wave reliability confirmed:** W1.1 lock fail-closed + reclaim-only-on-proven-stale (`team_scheduler.py:56-118`); W1.2 dead-man real-status on Celery path, no `raise`-regression; W1.3 content per-engine isolation (`_run_content_engine`, 12 engines); W1.5 tick-slot fail-closed (no stack-storm); W4.x office momentum never-raise/no-PII; `job_metrics` never-raise + bounded cardinality; **dead-man registry 34/34 jobs, 0 gaps**.
- **New voice surface safe (except the fixed TOCTOU):** IDOR — client_id from JWT, `Lead.assigned_to==client_id`; compliance chokepoint (`queue_call`) un-bypassable + fail-closed; queue-status read-only client-scoped; transcript surface `CallLog.client_id`-scoped; `limit` clamped.

---

## Requested checklists (v2)

**Missing Features:** none at product level — Product-1 (86 tools + daily drafts + day-1 seed + autopilot surface) and Product-2 (calls table + transcript/report + self-serve calling gated) both deliver. Gaps are quality/enablement.
**Missing AI Components:** cross-process Redis-backed LLM circuit-breaker/key-rotation/semantic-cache (still per-process — enhancement); real measured cost accounting (still estimated).
**Missing Agent Loops:** none. All loops bounded + dead-man-watched; RL Phase-0 deliberate.
**Missing Tool Calls:** none broken (tool layer defensive; never-raise + spoken fallback + anti-fake).
**Missing Memory Features:** one-time KB purge/reseed to migrate old random-uuid4 points (delete-before-reseed shipped); Redis semantic-cache (flag exists, OFF).
**Missing Automation:** none missing — ~110 gated. Gap is prod-`.env` enablement of draft-safe flags.

**N/A for this architecture (unchanged):** Kubernetes (single-VPS deliberate), GGUF/Ollama-in-prod/GPU (free-CPU stack; faster-whisper int8 is the local quantization), knowledge-graph (LightRAG opt-in exists).

---

## Roadmap to true enterprise-grade autonomous AI platform

**P0 — the 2 new MEDIUMs (parallel session's files; S-effort each):**
1. `auto_outreach` mark-per-send (`>= 10` → `>= 1`) — kill the double-send-on-crash.
2. `self_improve` heartbeat real-`ok` (both scheduler paths) — close the rollback dead-man blind spot.

**P1 — enablement + robustness (mostly your prod ops):**
3. Enable draft-safe autopilot flags + `AUTO_DELIVER_VALUE`; arm one transactional WhatsApp; `METRICS_TOKEN`; one-time KB purge/reseed.
4. Live-test then enable `CUSTOMER_VOICE_SELFSERVE` (now TOCTOU-hardened) + `VOBIZ_STREAM_REQUIRE_TOKEN`.
5. Redis-back the LLM circuit-breaker + key-rotation + semantic cache (cross-process correctness); reorder realtime chain by measured p50.

**P2 — scale ceiling (only when growth demands):**
6. jsonl→Postgres for hotter stores; cluster-safe scheduler lock; then (and only then) multi-node/HA. K8s remains unnecessary at current scale.

**Coverage debt:** ~50 `app/api/*` routers got a 2nd security sweep (2 batches) — the surface is now well-covered; a full-repo third pass is not warranted yet.
