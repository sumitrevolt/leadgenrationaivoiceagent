# Design Spec — End-to-End Readiness + Infrastructure Improvement

**Date:** 2026-06-20
**Owner:** Sumit
**Status:** Approved for planning (brainstorming complete)
**Mode:** Ship-today, parallel build (flag-gated, additive, defensive)

---

## 1. Context & honest reality (read first)

This request ("complete end-to-end project readiness + infra improvement") is the **4th iteration** of an infra-gap task. Memory + the single-source-of-truth doc (`docs/SAAS_INFRA_TRUTH_AND_GAPS_2026_06_15.md`) establish:

- **Infra layer is SATURATED.** CI/CD + health-gate + rollback, Trivy CVE+SBOM, full Prom/Grafana/Loki/Tempo obs + exporters, durable Celery, event-sourced process-engine, Qdrant RAG, LLM-obs + promptfoo eval CI, semantic cache, plan-tier rate-limit, k6 + chaos, Ansible rebuild, offsite backup wiring, Cloudflare edge — **all already coded** (some active, some gated-OFF). Building new infra here = duplicate + waste.
- **Live readiness is already green.** `GET /api/activation/summary` (2026-06-20): `ready_for_launch: true`, `ready_for_first_paid_customer: true`, `blocker_count: 0`, `warn_count: 2`. Prod `/health` = `environment: production`, healthy.
- App-layer white-space (customer 2FA, customer webhooks) from the truth doc is **already shipped** (H.1/H.2, verified present in code).

**Therefore the genuine remaining work is small and well-bounded.** This spec captures exactly that — not new infra.

### Gap audit result (verified against current code, 2026-06-20)

| Area | Already PRESENT (do not rebuild) | Genuine GAP (this spec) |
|---|---|---|
| Admin | advanced filters, bulk client actions, RBAC UI (`team_access.html`), impersonation (`impersonation.py`) | revenue **time-series**; per-client **activity timeline**; **system-health drill-down** |
| Customer | onboarding wizard, webhooks UI, 2FA, usage view | inline **lead-status editing** |
| Activation | PostHog + UPI armed (OK) | Sentry + Turnstile (**creds-blocked → user action**) |

---

## 2. Goals / Non-goals

**Goals**
1. Close the activation warnings and surface the safe opt-in flags as an operator runbook (Track A).
2. Build the four genuine product-readiness gaps, flag-gated and additive (Track B).
3. Do it in one session, parallel-safe, with no production regression (Track C verification).

**Non-goals (explicitly out of scope)**
- Any new infrastructure / scale work (HA, 2nd server, R2 offsite, new edge): saturated per truth doc; creds/spend-blocked; reject unless a specific genuine gap is proven absent from the truth doc.
- Rebuilding already-present features listed above.
- Flipping QA-sensitive flags blindly (e.g. `AGENT_MEMORY` needs voice-QA first).
- New `@app.get` page-routes (avoids stale-`.pyc` hard-reload risk). All UI lands as **sections inside existing pages**.

---

## 3. Track A — Activation runbook (user-action; no code to build)

All wired; only `.env` on the VPS + app recreate. Rollback = unset the var + recreate.

| Item | Env keys | Status | Who |
|---|---|---|---|
| Sentry error tracking | `SENTRY_DSN`, `ENVIRONMENT=production` | WARN (unset) | **User** (sentry.io DSN) |
| Turnstile bot-protection | `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | WARN (unset) | **User** (Cloudflare widget) |
| Cloudflare Tunnel/WAF | `CLOUDFLARE_TUNNEL_TOKEN` | NEUTRAL (opt-in) | **User** (CF Zero-Trust) |
| Safe code-side flags | `EVAL_GATE=1`, `CUSTOMER_WEBHOOKS=1` | NEUTRAL → optional ON | User decision (no creds) |
| QA-gated flag | `AGENT_MEMORY=1` | NEUTRAL | After `scripts/agent_tester.py` voice QA |

Reference: `docs/ACTIVATION_RUNBOOK_2026_06_16.md`. This track ships as documentation + a one-screen checklist; no application code is built for it.

---

## 4. Track B — Buildable features (this session)

All four: **flag-gated OFF by default, additive, defensive handler, targeted test, no new page-route.** New flags registered in `app/api/growth.py` `AUTOMATION_FLAGS` (so they appear in `GET /api/growth/infra/flags`).

### B1 — Revenue time-series (MRR trend, churn-rate, LTV)
- **Problem:** `GET /api/admin/revenue-analytics` (`app/api/admin_dashboard.py:1002`) returns only point-in-time MRR/churn-risk/LTV. No history → no trend line.
- **Build:**
  - **Snapshot job** (daily, durable Celery-beat): records `revenue_digest._collect()` output (mrr, subscriptions, churn band counts, active clients) as one row/day to an append store `data/revenue_snapshots.jsonl`. Wired into the scheduler like the other staff jobs; boot-grace respected.
  - **Backfill-estimate:** on first run, reconstruct an approximate historical MRR curve from existing clients' start dates + current plan price, so the chart is meaningful on day 1 (clearly labelled "estimated" for pre-snapshot dates).
  - **API:** `GET /api/admin/revenue-trend?days=90` → list of `{date, mrr, active, churn_pct, ltv}` (real snapshots, estimate fallback for gaps). Defensive: empty/error → `{points: [], note: "..."}`, never 500.
  - **UI:** chart in `admin_dashboard.html` revenue section (sparkline/line; reuse existing chart approach already in the file).
- **Flag:** `REVENUE_TRENDS` (snapshot job + endpoint inert when off).
- **Test:** snapshot append + read round-trip; backfill produces ≥1 point; endpoint shape.
- **Success:** admin sees a 90-day MRR/churn line that grows one real point per day.

### B2 — Per-client activity timeline
- **Problem:** audit is global only (`/api/admin/audit-logs`, `activity-feed`); no "what happened with client X" view.
- **Build:**
  - **API:** `GET /api/admin/clients/{client_id}/timeline?limit=50` → merged, time-sorted events for that client from: `AuditLog` (incl. impersonation start/stop), `agent_events`, that client's inquiries/leads (`data/inquiries.jsonl`), and billing/usage records. Each item `{ts, kind, source, summary}`. Read-only, defensive, capped.
  - **UI:** a drawer/expander in the `admin_dashboard.html` clients section ("Timeline" action per client row).
- **Flag:** `CLIENT_TIMELINE`.
- **Stretch (optional, only if cheap):** list recent impersonation sessions from `AuditLog`. Mid-session **revoke** is deferred (needs a Redis session store; impersonation tokens are stateless JWT) — documented, not built this pass.
- **Test:** aggregator merges + sorts sources; unknown client → empty list, not error.
- **Success:** clicking a client shows a unified chronological trail.

### B3 — System-health drill-down panel
- **Problem:** UI shows basic db/redis/llm status; no infra detail.
- **Build:**
  - **API:** `GET /api/admin/system-health-detail` → `{cpu_pct, mem_pct, disk_pct (psutil), redis_ping_ms, celery_queue_depth (redis llen celery), worker_alive (from data/job_heartbeats.json), health_ready (reuse /health/ready)}`. **No docker-socket** (security + simplicity). Must be **cheap + off-loop** — psutil calls are instantaneous; the heartbeat/queue reads are O(1). Hard rule: nothing heavy on this polling endpoint (3 prod-downs came from heavy work on hot paths).
  - **UI:** gauges/rows in the `admin_dashboard.html` System Health area.
- **Flag:** `SYS_HEALTH_DETAIL`.
- **Test:** endpoint returns all keys; missing heartbeat file → `worker_alive: unknown`, not error; queue read failure → `-1`, not 500.
- **Success:** admin sees live CPU/mem/disk + queue depth + worker liveness without SSH.

### B4 — Customer inline lead-status editing
- **Problem:** customer leads are **derived** from append-only `data/inquiries.jsonl` (each inquiry = a lead; outcome/tier computed). No mutable status field, no edit UI.
- **Build:**
  - **Override store:** `data/lead_status_overrides.jsonl` — `{lead_id, client_id, status, set_by, ts}`. Append-only; latest-wins on read. Keeps source inquiries immutable.
  - **API:** `PATCH /api/customer/leads/{lead_id}` `{status}` — authed to the owning `client_id` (reuse the `_authed_client_id` dependency pattern used on billing mutations for IDOR safety). Allowed statuses constrained to a fixed enum (Hot/Warm/Cold/Won/Lost/Follow-up).
  - **Read merge:** `customer_dashboard.py` lead build applies the latest override for each lead before returning.
  - **UI:** inline `<select>` in the `customer_dashboard.html` leads table row with an `onchange` → PATCH.
- **Flag:** none needed (additive; absent override store = current behavior).
- **Test:** PATCH writes override; read reflects latest; cross-client PATCH (wrong client_id) → 403.
- **Success:** customer changes a lead's status inline and it persists across refresh.

---

## 5. Parallelization & file-ownership matrix (prod-down-safe)

CLAUDE.md lesson: **never let two parallel agents edit the same file** (truncation). `admin_dashboard.html` is the contention point for B1/B2/B3.

Because B1 and B2 both add routes to `admin_dashboard.py`, they cannot be two separate parallel agents (same-file conflict). So Wave 1 runs **3 agents**, each owning a disjoint file set:

| Wave | Agent | Work | Files owned (single-owner) |
|---|---|---|---|
| **Wave 1 (parallel)** | A | B1 + B2 backend (both add `admin_dashboard.py` routes) + B1 snapshot job module | new snapshot-job module, `admin_dashboard.py` (new routes only) |
| | B | B3 backend | new system-health route module |
| | C | B4 full (PATCH + override store + customer UI) | `customer_dashboard.py`, `customer_dashboard.html`, new override-store helper |
| **Wave 2 (serial)** | single owner | All `admin_dashboard.html` UI edits for B1 + B2 + B3 | `admin_dashboard.html` (one section at a time) |
| **Wave 3 (serial)** | single owner | Register `REVENUE_TRENDS`, `CLIENT_TIMELINE`, `SYS_HEALTH_DETAIL` in `app/api/growth.py` `AUTOMATION_FLAGS`; wire snapshot job into the scheduler | `growth.py`, scheduler/worker config |

This keeps every file single-owner per wave (no parallel writes to a shared file).

---

## 6. Track C — Verification gate (after each wave, before "done")

1. `python scripts/prod_check.py` → green.
2. Targeted pytest for new tests (`scripts\run_tests.bat` → **read `pytest_run.log`**; avoid full-suite team_pulse hang).
3. `python scripts/check_secrets.py` (the `.env` fragments surfaced during audit must never enter committed files).
4. Deploy per standard loop; verify live `/health` = `environment:production` + `/api/activation/readiness` still 0 blockers.
5. "Done" only when green with proof.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Parallel edits truncate `admin_dashboard.html` | Wave-2 serial single-owner (matrix §5). |
| Heavy work on `/system-health-detail` hot path → prod freeze | psutil + O(1) reads only; hard rule, no KB/ML/network. |
| B4 IDOR (edit another client's lead) | `_authed_client_id` dependency; cross-client → 403; test asserts it. |
| New flags forgotten in registry | Wave-3 explicitly registers in `AUTOMATION_FLAGS`. |
| Snapshot job restart-storm | Boot-grace + durable Celery-beat pattern, like existing staff jobs. |
| Secret leakage | `check_secrets.py` in verify; no `.env` values in any doc/code. |

---

## 8. Success criteria (whole spec)

- Live `/api/activation/readiness` stays `blocker_count: 0`; Track A items documented for the user with exact keys.
- B1–B4 shipped, flag-gated, tests green, prod healthy.
- Admin can see: MRR/churn trend, per-client timeline, infra health — without SSH.
- Customer can edit lead status inline, persisted.
- No new infrastructure built; no already-present feature rebuilt.
