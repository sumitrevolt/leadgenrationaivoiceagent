# Lead-Gen Funnel Pipeline Automation — Design Spec

- **Date:** 2026-07-08
- **Status:** Draft — user approved scope in conversation, proceeding to plan/build
- **Scope:** Option 1 + Option 2 only (activate dormant infra + data-quality gates) over ONE vertical slice of the 13-stage funnel. Full lineage/backfill dashboard and multi-orchestrator unification are explicit P1 follow-ups (§7).

## 0. Source

User asked for pipeline-automation improvements inspired by DataTalksClub's `data-engineering-zoomcamp` (orchestration/idempotency/retries/incremental-processing/data-quality/lineage/observability/backfills principles — explicitly NOT its heavy tools: no BigQuery/Spark/Kafka/Kestra/dbt/Terraform), scoped to the full lead-gen funnel end-to-end (prospecting → ... → reporting), not just email deliverability. User then supplied a detailed 14-phase brief with a canonical 13-stage funnel map and an explicit instruction: map what exists first, reuse/extend, don't build a parallel system, and start with one vertical slice rather than all 13 stages.

## 1. Phase 1 inventory (code-verified via 3 parallel research passes, not doc-assumed)

Full per-stage detail is in conversation history; key findings this design relies on:

- **Cross-cutting:** three independent, uncoordinated ingestion orchestrators exist (`app/lead_scraper/scraper_manager.py`, `app/platform/prospector.py`, `app/platform/lead_harvester.py`) — each with its own dedup/validation/budget logic, no shared `Prospect`/`Batch` model (prospects live only in `data/prospects.jsonl`).
- **Stage 1 (source selection):** `app/automation/campaign_manager.py`'s `Campaign` is an in-memory `@dataclass`, NOT `app.models.campaign.Campaign` — decorative, lost on restart.
- **Stage 2 (ingestion):** only 3 of 6 "sources" are reachable (google_maps/web_search/social_media); justdial/indiamart/linkedin are unwired — this matches CLAUDE.md §5's ToS-scraping ban and is **not a bug to fix**.
- **Stage 3 (dedup):** 3 unreconciled implementations, no shared key scheme; an email-only duplicate (no phone) slips past 2 of 3 paths.
- **Stage 4 (validation):** 2 different phone validators; DND fails closed (`dnd_checker.py`, correct); **no quarantine queue anywhere** — invalid leads are inconsistently flagged-and-kept or dropped depending on which orchestrator ran.
- **Stage 5 (enrichment):** no dedicated post-ingestion stage exists at all.
- **Stage 6 (scoring):** confirmed duplicated — two independent scoring engines (`app/platform/lead_scoring.py` for DB leads, `app/marketing/lead_scoring.py` for JSONL inquiries), hot-lead threshold hardcoded inconsistently across ≥4 files (60 in `lead_scoring.py`'s env default vs 70 in `models/lead.py::update_score()`, `call_manager.py::get_hot_leads()`, `campaign.py::hot_lead_threshold` default), no score-reason persisted.
- **Stage 7 (segmentation):** solid (`app/platform/segments.py`, Mautic-style dynamic segments); minor gap — no categorical hot/warm/cold field, no channel dimension.
- **Stage 8 (outreach eligibility):** 3 separate per-channel gates (`compliance.py` for calls, `auto_outreach.py`'s own gate for email, `whatsapp_campaign.py`'s own gate for WhatsApp), 3 independent suppression stores, one-directional opt-out propagation (voice→WhatsApp only, not to/from email).
- **Stage 9 (outreach execution):** calls have real backoff retry + idempotent webhook-based outcome (good). `app/platform/integration_health.py` confirmed **post-hoc only** — never consulted as a pre-send gate in `call_manager.py`/`vobiz_handler.py`/`whatsapp_campaign.py`. No fabricated-success path found; the real risk is email "sent"=accepted-not-delivered, dependent on `reply_agent.py` bounce detection (itself gated `REPLY_AGENT`, default OFF).
- **Stage 10 (reply capture):** `app/models/interaction.py` (`Interaction`) + `app/platform/interaction_log.py` already exist (default-ON) but are inconsistently wired — WhatsApp replies (`reply_agent.py::whatsapp_reply()`) and legacy call-completion (`call_manager.py::handle_call_completed()`) never call `interaction_log.record()`; only the inquiry/email/voice-stream paths do.
- **Stage 11 (conversion):** no discrete conversion event; `clients_store.add_client()` (called from both admin and self-serve onboarding) has zero lead/prospect/deal linkage fields.
- **Stage 12 (CRM/delivery handoff) — confirmed broken:** `prospector.py` documents a `"client"` prospect status but `mark_prospect(pid, "client")` is never called anywhere in the codebase (verified by repo-wide grep). `app/models/customer_deliverable.py`'s `client_id` has a real FK to the legacy SQL `Client` table, but `add_client()` (JSONL-backed) never writes to that table. **Lead-gen and the Customer Delivery OS are two disconnected systems today.** This is the single most concrete finding of the whole inventory, but it does not fit this sprint's vertical slice (see §7).
- **Stage 13 (reporting):** isolated per-store counts only (`revenue_digest.py`, `product_one_delivery.py::delivery_cockpit()`, `client_report.py`, `team_report.py`) — no report chains leads→scored→contacted→converted as one funnel.

## 2. Goals / Non-goals

**Goals**
- Give one already-scheduled, already-tested ingestion path (`prospector.py`) first-class batch tracking: what ran, how many leads at each stage, what went wrong.
- Close the data-quality gaps that let a broken pipeline fail silently (duplicate dedup gap, missing quarantine, duplicated/inconsistent scoring thresholds, scattered outreach-eligibility gates, no pre-send provider-health check).
- Wire the two missing channels (WhatsApp, legacy call-completion) into the existing `Interaction`/`interaction_log` unifier rather than building a parallel event system.
- Surface pipeline health in the existing admin dashboard (new tab, not a new page) and a simplified summary for customers.
- Every stage safe to retry (idempotent), every failure visible (no silent drops), no outreach can spam or fake success.

**Non-goals (this sprint — explicit P1 follow-ups, §7)**
- Unifying all 3 ingestion orchestrators into one.
- Full lineage/backfill dashboard UI; only a read-only backfill-preview endpoint if cheap.
- Fixing Stage 12 (lead→customer handoff) — flagged as the highest-value follow-up, recommended as its own small, focused fast-follow, not bundled here.
- Enrichment as a first-class stage (Stage 5) — no dedicated pass exists today and building one is out of scope for a "turn on + add quality gates" sprint.
- Any new paid/heavy infra (BigQuery, Spark, Kafka, Kestra, dbt, Terraform) — explicitly forbidden by the user's brief and this project's free-stack mandate.

## 3. New database objects

All three follow the existing minimal-event-table convention already established by `app/models/agent_event.py` (`AgentEvent`: id/owner-key/action/status/meta_json/created_at, indexed) — not the heavier ~30-field schema in the user's original brief, which would be premature (YAGNI: `quality_score`, `evidence_payload`, `next_action` fields have no consumer yet).

```
LeadPipelineBatch (app/models/lead_pipeline.py)
  id (str/uuid, pk)
  source          # "prospector" only in this sprint (others documented as P1)
  niche, city     # nullable
  status          # pending | running | completed | partial_failed | failed
  total_raw, total_duplicate, total_invalid, total_valid,
  total_scored, total_eligible, total_outreach_created
  error_count
  started_at, completed_at, created_at
  __table_args__ = Index on (source, created_at), (status, created_at)

LeadPipelineStageRun (same file)
  id (pk), batch_id (FK -> lead_pipeline_batches.id, indexed)
  stage_name      # ingestion | dedup | validation | scoring | eligibility | outreach
  status          # pending | running | passed | warning | failed
  input_count, output_count, rejected_count
  error_message (nullable)
  started_at, completed_at

LeadPipelineQualityIssue (same file)
  id (pk), batch_id (FK, indexed), stage_name
  issue_type      # e.g. zero_output | high_duplicate_rate | invalid_phone_rate | provider_disabled
  severity        # info | warning | critical
  message
  resolved (bool, default False)
  created_at
```

One Alembic migration (`add_lead_pipeline_tables`), idempotent-create pattern matching `008_add_agents_agent_events.py` (no-op if tables already exist).

**Explicitly rejected: a 4th `LeadPipelineEvent` table.** `app/models/interaction.py` (`Interaction`) already has `lead_id`/`channel`/`direction`/`outcome`/`meta_json`/`occurred_at` — exactly what a pipeline event needs on the outreach/reply side. Building a parallel table would violate the user's own "don't duplicate existing tables" instruction.

## 4. Idempotency keys

- **batch_key** = `source:niche:city:date-hour-window` — Redis lock (same pattern as the existing scheduler file-lock), prevents two concurrent batches for the same target; does not prevent re-running the same niche/city on a new day (that's the point — daily re-prospecting is intended).
- **lead_key** = reuse `app/models/lead.py`'s existing `phone_format_variants()` / `lead_exists_for_phone()` (already fixes a real +91-format duplicate bug) as the primary key; add an email-normalized fallback for leads without a phone — this closes the confirmed "email-only duplicate" gap without inventing a new scheme.
- **outreach_task_key** = no new key needed — wrap the 3 existing, individually-tested per-channel gates (`compliance.py`, `auto_outreach.py`'s gate, `whatsapp_campaign.py`'s gate) behind one `is_outreach_eligible(lead, channel) -> (bool, reason)` function in a new small module, rather than rewriting any of the three. This directly closes the confirmed Stage-8 gap at minimal risk.

## 5. Data-quality gates (Phase 3 scope, limited to what this slice touches)

- **Ingestion gate:** batch requires niche/city or explicit manual source; zero-raw-output logs a `LeadPipelineQualityIssue(issue_type="zero_output", severity="warning")` instead of silently completing.
- **Dedup gate:** phone+email dedup (§4); `total_duplicate` recorded on the batch.
- **Validation gate:** reuse existing `PhoneValidator`/`email_verify.verify()`/`dnd_checker` (fail-closed, unchanged); add the missing quarantine concept — invalid leads get a `LeadPipelineQualityIssue(issue_type="invalid_lead")` row instead of the current inconsistent flag-and-keep-or-drop behavior.
- **Scoring gate:** centralize the hot/warm/cold threshold into one `app.config.settings` value; update all ≥4 call sites (`lead_scoring.py`, `models/lead.py::update_score()`, `call_manager.py::get_hot_leads()`, `campaign.py::hot_lead_threshold` default) to read from it; persist `score_reason` (currently computed but discarded) as a new nullable column on `Lead`.
- **Outreach eligibility gate:** the unified wrapper from §4.
- **Execution gate:** add an `integration_health`-based pre-send check before dialing in `call_manager.py`, new and **fail-open** (matches this project's existing fail-open convention for non-compliance systems — a flaky health-check must never block a real, healthy call).
- **Reporting gate:** batch-completion auto-generates its own summary row (already covered by `LeadPipelineBatch`'s counters — no separate report object needed for this slice).

## 6. Surfacing

- **Admin:** new "Lead-Gen Pipeline Health" section inside the existing `admin_dashboard.html` (Growth & Revenue nav group — reusing the exact `data-view`/card pattern already used by `sec-clients`/`sec-recordings`, not a new page). Shows: recent batches, current stage, raw/valid/duplicate/invalid/scored/eligible/outreach counts, open quality issues, DLQ count.
- **Customer:** simplified read-only summary (leads found / verified / hot / contacted / interested replies — no DLQ/worker jargon), added to the existing customer dashboard funnel-relevant tab.
- **API** (reuse-check done — none of these exist today under these exact paths):
  - `GET /api/admin/pipeline/batches`, `GET /api/admin/pipeline/batches/{id}`, `GET /api/admin/pipeline/health`, `GET /api/admin/pipeline/issues`, `POST /api/admin/pipeline/issues/{id}/resolve` — all admin-gated (`Depends(require_admin)`, matching the pattern the 2026-07-01 audit fixed elsewhere).
  - `POST /api/admin/pipeline/backfill/preview` — read-only estimate only, if cheap to build alongside the above; `POST .../backfill/run` deferred to P1 (§7) since safe per-stage resume isn't built yet.
- **Retry:** re-triggering the same prospector run for a niche/city is already safe (existing dedup) — exposed as the batch "retry" action rather than building a new partial-stage-resume mechanism.

## 7. P1 follow-ups (explicitly deferred, documented so nothing is silently dropped)

1. **Stage 12 fix (highest priority follow-up):** wire `add_client()` to accept an optional `source_lead_id`/`source_prospect_id`, call `mark_prospect(pid, "client")` on conversion. Small, focused, high-value — recommended as its own immediate fast-follow, not bundled into this sprint.
2. Full lineage/backfill dashboard UI + `POST .../backfill/run`.
3. Unify `scraper_manager.py`/`prospector.py`/`lead_harvester.py` into one orchestrator.
4. Enrichment as a first-class Stage 5.
5. Bidirectional cross-channel opt-out propagation (currently voice→WhatsApp only).

## 8. Testing plan

Unit: batch/lead idempotency keys, dedup (phone+email), validation quarantine, centralized scoring threshold + reason persistence, `is_outreach_eligible()` per channel, pre-send health-check fail-open behavior, stage status transitions, zero-output-batch warning.
Integration: ingestion→dedup→validation, validation→scoring, scoring→eligibility→outreach-task, provider-disabled→issue-visible-in-admin-health.
Route: admin pipeline endpoints require admin auth; customer summary is tenant-isolated.
Regression: full existing test suite for `prospector.py`, `lead_scoring.py`, `compliance.py`, `interaction_log.py`, Customer Delivery OS tests (must stay green — that system is unrelated but shares `clients_store`/`Interaction` surface area).
Gate: targeted pytest green, `prod_check.py` PASS, `check_secrets.py` clean, duplicate-route grep clean.

## 9. Definition of done (this sprint)

No new duplicate pipeline system created · existing infra reused where possible (`Interaction`, `dlq_retry.py`, `phone_format_variants()`, the 3 existing per-channel gates) · every touched stage has status+metrics · failed stages and zero-output batches are visible, not hidden · retries are safe · outreach cannot spam or fake success · provider-disabled stops the channel and alerts, doesn't silently no-op · admin sees pipeline health · customer sees a simplified summary · tests pass · `prod_check` passes.
