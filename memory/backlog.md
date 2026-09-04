# Backlog — parked ideas WITH the why (so context isn't lost)

Schema: `[DATE parked] Idea — WHY it matters | what unblocks it`

> **Consolidation note (2026-09-02):** Shipped/superseded items archived to `docs/SESSION_LOG.md`. Only active+parked items remain below. See `docs/SESSION_LOG.md` 2026-06-08 through 2026-08-30 for the 56 shipped items relocated from this file.

## Active / Parked (need work or await user action)

[2026-08-14] **DeepSeek Harness (`dsh`) remaining patterns (ADR-179 REJECT vendor; ADR-180 shipped #1)** — WHY: #1 typed SessionEvent + hash-chain is CODE-PRESENT INERT (`HARNESS_SESSION_EVENTS=0`). Still parked: named plugin profiles beyond existing `profile=` arg, tools/pre-execute→post-execute as a separate pipeline (we already have ordered Harness.step controls), durable Redis-tip WORM for the hash chain | unblocks: measure canary jsonl locally, then maybe steal #2. Never submodule `deepseek-ai/deepseek-harness`.

[2026-08-12] **FREEBUFF Hot Queue read connector (PARKED spec)** — narrow read+draft-preview bridge for agent-side ranking; final send owner-only; most capability ALREADY EXISTS (`GET /api/growth/reply/hot-queue` + `wa_link` + `hot_queue_brief` job), so no new engine proposed | un-parks ONLY on correlated defect evidence from a real attempted funnel step (mission phase-change rule); spec: `docs/FREEBUFF_HOTQUEUE_CONNECTOR_SPEC_20260812.md`.

[2026-08-11] **ADR-177 GSC rank tracking + referral kit (Phase B: enable + verify)** — WHY: code INERT (`GSC_ENABLED=0`); creds PRESENT in prod (`GSC_SERVICE_ACCOUNT_JSON` + `google_sheets_credentials` SET). Only flag flip + GCP DNS TXT verify remains. Referral kit UI (`/app/affiliates`) code ready, owner 1-click to deploy | unblocks: programmatic SEO observability; owner can flip `GSC_ENABLED=1` after DNS TXT verification.

[2026-08-08] **ADR-174 Cloudflare OS (`cloudflare/cloudflare-os`): vendor REJECT · P1+P2 patterns-only** — WHY: Apache-2.0 CF internal AI productivity OS (5.1k★). Authority model fails same ADR-148/155 test — poora apna kernel/users/ACLs/agent runtime; productivity/gadget workspace hai, coding-agent orchestrator nahi; C1 canary sawaal ko chhuta nahi. Kill facts: runtime mismatch (Workers/DO/TS/pnpm vs Hostinger Docker FastAPI/Postgres/Redis/Qdrant); DPDP/data-residency unanswered for lead PII on CF edge vs 90-din retention+purge+cross-client isolation; early-access + "not seeking outside contribution" = fork-and-maintain. **DO NOT write ADR-174 or evaluate mid-C1** | unblocks: after C1 Claude AT Observed (or contaminated) recorded + #283 path clear; then ADR-174 same shape as ADR-173.

[2026-08-05] **MetaGPT steal-list #2 — two-stage roster recommendation (BM25 recall → LLM rank) for `coordinator.plan()`** — WHY: `coordinator.plan()` injects the whole 31-agent roster into every planning prompt (L235); `docs/context/SYSTEM_MAP.md:51` already flags "429 storms if coordinator uncapped" — direct token reduction on the hottest prompt + attacks that written-down risk | implement via `tool_recommend.py:195,129` pattern: `recall_tools` (BM25 L195 / embedding L231) → `rank_tools` (LLM L129), top-k reaches the prompt. Zero new deps: `rank-bm25` NOT in lock, but `app/ml/reranker.py:42` already ships a dep-free BM25-style scorer; reuse it or `agent_recall._keyword_recall`. unblocks: #1 (`COORD_PLAN_NODE`) proves a measured improvement in prod (ADR-159).

[2026-08-05] **MetaGPT steal-list #3 — plan precheck + repair-retry (invalid plan → ask model to fix itself)** — WHY: `coordinator.plan()` drops silently to a deterministic hardcoded chain when the parsed plan is invalid; we never ask the model to repair its own plan | lift `precheck_update_plan_from_rsp` + bounded `max_retries` regeneration (`strategy/planner.py:83+`), keeping our deterministic chain as the *final* fallback. unblocks: after #1 (`COORD_PLAN_NODE`) proves out; that ADR-159 ship already gets a partial version (review/revise rounds), so this item is mostly already absorbed unless a measured gap remains.

[2026-08-05] **MetaGPT steal-list #4 — `exp_cache` semantics for `agent_recall.py`** — WHY: two uncoordinated memory tiers (`coordinator._MEMORY` jsonl hard cap `_MAX_MEM=3`; `agent_recall.py` hybrid keyword+vector) — neither scores an experience, neither can skip an LLM call outright, read/write not independently controllable | lift three ideas from `exp_pool/decorator.py:30`: a `scorer`, a `perfect_judge` (perfect prior ⇒ return it, NO LLM call), and separate `enable_read` / `enable_write` flags so reads can canary before writes are armed — read/write split fits the INERT-by-default convention exactly. unblocks: after #1 proves in prod (ADR-159); dormant today (`AGENT_MEMORY` OFF).

[2026-07-18] **Social channel expansion (user-picked 2026-07-18)** — LinkedIn = #1 priority, Postiz env vars empty → USER-BLOCKED: LinkedIn DigiLocker identity verification. Threads 80% DONE: remaining = USER action (secret + reconnect). GBP API approval external-blocked (~60d). Pinterest 90% DONE (USER reCAPTCHA+Submit) | content job deferred-retry bug: late-morning sweep job (~10:30 IST) to re-enqueue stale daily jobs (additive fix).

[2026-07-18] **Hardcoded WAHA secrets — script PATCHED (ADR-086), rotation still user-pending** — `scripts/activate_waha_vps.sh` had a real `WAHA_API_KEY`/`WAHA_WEBHOOK_TOKEN` hardcoded in plaintext; script now requires them exported by the operator | remaining: Sumit rotates values on VPS `.env` + WAHA container.

[2026-07-14] **Approval-reminder idem key me RECIPIENT nahi hai — DELIBERATELY abhi fix nahi kiya (risk > gap)** — `idem_key(client_id, approval_id, version)` recipient-agnostic; dedupe `existing.status == "sent"` blocks retries. **Kyun abhi nahi kiya:** real failure mode source pe ruk chuka (`_finalize(row,"skipped","invalid_email")` — skipped dedupe NAHI block karta); gap sirf "real-but-wrong address pe sent" narrow edge case. Fix = recipient sha256[:12] in key + backfill + contract test. **Jab karo to:** key format badalne se existing rows stale → migration needed; rollback-safe dual-key lookup.

[2026-07-07] **RL flywheel signal lopsided (funnel only, not voice/outreach)** — RL_ENGINE=1 prod; 696 rewards collected but only `funnel` domain (1730–4178 trajectory). Voice/outreach/dev = 0 rewards (no product events, not missing wiring). `skill_library` rates ~0.87–0.9994 = "ran without error" not "business value" | unblocks: fix reward signal so PRODUCT domains collect OUTCOME rewards → THEN build Phase-1 Thompson policy. DON'T build Thompson on funnel-only self-referential data.

[2026-07-07] **Agentic RAG / LightRAG evaluation** — Agentic RAG (`agentic_rag.py`) opt-in `USE_AGENTIC_RAG=1` never tested against real call data; LightRAG (`graph_rag.py`) opt-in `USE_LIGHTRAG=1` never exercised | unblocks: `agent_tester.py` comparison → telecaller_brain KB-grounding me wire (better answers on vague/misspelled queries).

[2026-07-05] **`.env.example` + `pyproject.toml` drift cleanup** — both advertise paid/stale stack (Deepgram/ElevenLabs/gemini-1.5/DEFAULT_STT=deepgram) vs real free stack; onboarding-misleading | small PR; keep requirements.lock.txt authoritative.

[2026-07-05] **Make full pytest CI-blocking** — currently continue-on-error; regressions can reach main | fix team_pulse-area hang first, then flip gate in `deploy-vps.yml`.

[2026-07-04] **POSTHOG_API_KEY + .codex key rotate** — analytics wired-but-off; old stitch key revoke provider-side | user actions.

[2026-07-04] **STUDIO_ENTITLEMENT_GATE flip** — studio tools entitlement enforcement | user go-ahead.

[2026-07-02] **Enterprise-audit follow-ups (2026-07-02)** — k6 load run, SLO burn-rate slice, live alembic verify, trivy enforce | audit scored SLO 3/Capacity 2/DB-mig 5/Supply 5.

[2026-06-2X] **Own telephony stack (P3)** — cost ladder Plivo ₹0.60 → Vobiz ₹0.45 → operator-direct ₹0.30-0.40/min | Plan in `docs/superpowers/plans/PENDING_PLANS.md`; needs volume + DLT.

[2026-06-2X] **Missed-call auto-callback** — classic Indian lead-capture pattern, zero-DLT inbound | Vobiz DID + webhook (user paperwork).

[2026-06-2X] **GBP API auto-post** — Google Business posts = highest-ROI local-marketing channel | Google ~60-din API approval (user applied?).

[2026-06-2X] **Hybrid Agentic RAG upgrade (ADR-119)** — Qdrant dense-only today (e5-small); target dense+sparse/RRF + BGE-M3 + optional bge-reranker + query router + tenant_id payload | Phase flags; model bake + deadline + disable-switch.

[2026-06-2X] **Okf ingest bridge (Phase-2/3)** — Phase-1 CODE committed (feature branch); remaining: owner-arm ingest on prod + hybrid dense+sparse/RRF (Phase-2) + BGE-M3 (Phase-3) | not a Qdrant replacement (ADR-119).

[2026-06-29] **Voice fine-tune pipeline ramp (50→200→1500/day)** — own telecaller data flywheel (~45k recs/mo at scale) | DLT + Vobiz balance + platform_dial re-enable conditions (ADR-019).

[2026-06-20] **vobiz_stream refactor** — last god-file, deferred as voice-unsafe | needs live-call regression harness first.

[2026-06-21] **P4-3 eval_gate-live + ear-test** — last SWARA roadmap item | manual listening session.

[2026-06-29] **Agentic RAG / LightRAG evaluation** — opt-in flags never tested against real data | `agent_tester.py` comparison → telecaller_brain wire.

## ARCHIVED (shipped/superseded — see SESSION_LOG.md for dates)
- **Unity WebGL build** (2026-08-04 LIVE on prod `041501c2`; `/app/office?mode=3d`; `UNITY_VIRTUAL_OFFICE_ENABLED=1`; artifacts in `frontend/office_unity/`) — moved to SESSION_LOG 2026-06-08 entry
- **Meta/FB/IG auto-posting (own brand)** (2026-07-14, ADR-099) — Postiz LIVE with 4 channels (FB/IG/X/YT); own-brand social poora wired
- **Marketing Calendar view** (2026-07-07, Loop 4) — customer-facing UI + backend wired (3 new events: post_approved/post_published/post_failed)
- **Interactive Setup Wizard** (2026-07-07, Loop 5 / ADR-030) — `GET/POST /api/customer/profile` + `/app/office` wizard tab (marketing_only gated)
- **Leads Inbox + Reports wiring** (2026-07-07, Loop 6) — 3 final ledger events (lead_captured/followup_sent/weekly_report_generated) call-sited
- **Customer Delivery OS: nav + hide/merge** (2026-07-07, Loop 7) — orphan pages mapped, nav collision fixed, agent-tools under "Advanced"
- **Admin "Deliver Now" button** (2026-07-07, Loop 2) — `frontend/clients.html` + deliverNow(), COMMITTED+DEPLOYED
- **Customer Delivery OS: land + deploy** (2026-07-07, ADR-033) — all 7 loops merged+deployed, production verified
- **Approval-reminder sweep fix** (2026-07-14, ADR-092) — Jiya reminder triage, counter fix, validation PASS
- **DKIM/SPF/DMARC** (2026-07-14) — all records published and verified (`deliverability_monitor.py`)
- **WSL distro recovery** (2026-07-16) — OmniRoute 3.8.48 + Node 22 rebuilt on Ubuntu-24.04
- **Docker compose legacy-stack landmine** (2026-07-18) — `-f docker-compose.vps.yml` mandatory, documented in incidents
- **Postiz multi-channel** (2026-07-18) — 4 channels connected (FB/IG/X/YT), YouTube OAuth Published
- **Postiz queue stuck fix** (2026-08-05) — orchestrator zombie recovery documented
- **Postiz publish readiness** (2026-08-05) — `/api/growth/social/postiz/status` + plan_publish_channels dry-run
- **GSC rank tracking** (2026-08-11, ADR-177) — code DEPLOYED, INERT (`GSC_ENABLED=0`), creds present in prod
- **Referral kit** (2026-06-08) — `referral_kit.py` + `/app/affiliates` + API; owner 1-click via Hot Queue Owner Pack
- **Evergreen recycling** (2026-06-08) — `evergreen.py` + daily content job wired
- **Meta/FB/IG auto-posting** (2026-06-08 — own brand DONE 2026-07-14, ADR-099; customer pages still blocked)
- **Pinterest** (2026-07-18 — 90% DONE: personal→biz account, dev portal unlocked, form filled; USER reCAPTCHA+Submit + env wire remaining)
- **WAHA QR scan** (2026-06-08 — session linked 2026-08-23: `default` session WORKING, volume-persisted, 2607 sweep sent:2/2)
- **Trial-nudge ADMIN UI tab** (2026-08-23 — job LIVE, API-only surface pending; Sharma-trials reconciliation noted)
- **Full test-suite drift sweeps** (2026-07-06) — 8 stale tests fixed, full-suite sweep now standard per wave end

## COMPETITOR RESEARCH (2026-08-17)
**Product 1 (Marketing) Gaps:** CRM Pipeline (Kanban deal view), Social media scheduling (deeper Postiz), Google Business Profile auto-posting (moat at ₹1,999).
**Product 2 (Voice) Gaps:** No-code agent builder, 8+ Indian regional languages, Call analytics dashboard.
**Quick Wins (Revenue):** ₹1,999/mo Starter Voice tier (100 min), freemium (10 free calls/month), '₹66/day' framing.
