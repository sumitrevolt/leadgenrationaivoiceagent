# PRD — Per-Customer Video Personalization & End-to-End Video Automation

**Product:** LeadGen AI (https://leadsgenai.in)
**Author:** 许清楚 (Xu) — Product Manager, Software Development Team
**Date:** 2026-09-11
**Repo:** `leadgenrationaivoiceagent` · branch `main` @ `33189b70`
**Form:** Simple PRD (no competitor/market research — not essential to this internal fix)
**Status:** For architect + owner review. Every code claim below was read from the repo at `33189b70`.

---

## 1. Project Info

| Field | Value |
|---|---|
| Language | English |
| Programming Language | Python 3.11 (FastAPI + Celery) · React 18 + Vite + TS + Tailwind (existing `admin-dashboard`) |
| Project Name | `video_personalization_v2` |
| Original ask (owner, verbatim) | "abhi same video roz customer ko ja raha hai aur quality kharab hai" |
| Owner scope | (1) per-customer social-profile analysis → personalised videos; (2) local render / VPS data plane; (3) full per-video lifecycle; (4) Telegram delivery (group + individual); (5) Archify-style admin dashboard; (6) maximum automation in parallel; (7) self-improvement; (8) automation health check |

---

## 2. Validated Root Cause (hypothesis → verdict)

The three hypotheses in the brief are **CONFIRMED**, and the investigation found **two additional defects that are more severe than the original three**.

| # | Hypothesis | Verdict | Code evidence |
|---|---|---|---|
| RC1 | Fixed recipe → identical video daily | **CONFIRMED** | `daily_video.py:441` `recipe = os.getenv("DAILY_VIDEO_RECIPE","offer_announcement")`; `service.py:87` default `recipe="offer_announcement"`; `spec.py:210` probe hardcodes it. Learning override only when `flags.learning_enabled()` (`daily_video.py:443`). |
| RC2 | No per-customer social-profile analysis | **CONFIRMED** | `brief.resolve_brand_profile` reads `business_name / niche / city / colors / tagline / socials(handles only) / services / kb_facts`. `grep -r "social_profile\|profile_analysis\|instagram_profile"` → **0 hits**. `_brand_facts` passes no social analysis. |
| RC3 | `before_after` / `testimonial` blocked → falls back to generic | **CONFIRMED** | `recipes.py:10` `_BLOCKED_WITHOUT_SOURCE = {"before_after","testimonial"}`; `recipe_allowed` refuses without `source_asset_ids`/`verified_quote`; `daily_video._enqueue_advanced` passes **neither** → the two money formats for a makeover client are unreachable. |

### NEW — RC4: the learning loop can never accumulate (self-improvement is dead code)

- `learning.py:65` `_MEM_STORE: dict[str, list[dict]] = {}` — **process-local, in-memory, never persisted**. `_DEFAULT_DIR` (line 22) is declared but never written to.
- Consequence: `get_learning_history()` returns `[]` after every worker restart → `sample_count: 0` → `prefer_recipe: ""` → `daily_video` falls back to the env default. **The "self-improvement hook" is structurally unable to learn.**
- `grep -rn "record_learning\|CreativeLearningLink(" app/` → **0 production callers.** Nothing feeds it even within one process lifetime.
- Evidence label: **CODE-PRESENT, not wired, not persisted.** This directly blocks owner scope item (7).

### NEW — RC5: "network disabled" render is a flag, not an enforcement

- `hyperframes_provider.py:131` `network_disabled()` is defined and re-exported (`:783`) but **never called** anywhere. `_run_renderer` (`:519`) passes `_hermetic_env()` which only blanks `HYPERFRAMES_API_KEY` and unsets npm vars — it does **not** block network egress.
- Evidence label: **PARTIAL / CODE-PRESENT (flag only).** Must not be described as "hermetic render" in any status report.

### Secondary finding — fixed composition is a second, independent cause of "same video"

Even when the recipe changes, the output stays near-identical because both the copy and the composition are templated:
- `recipes.py:_texts_for` emits **fixed literal strings per recipe** (only `business_name`/`niche`/`offer` are interpolated).
- `hyperframes_provider._bind_beauty` / `_bind_local_service` / `_bind_agency` bind a **fixed variable set**; `proof_line` is hardcoded `""` in both `_bind_beauty` and `_bind_local_service`.
- Template registry holds only **3 templates** (`beauty_luxury_offer_v1`, `local_service_promo_v1`, `agency_product_launch_v1`), 9:16 only.
- ⚠️ **Reconcile note:** the brief stated the default template is `local_service_promo_v1`. The **code default is `beauty_luxury_offer_v1`** (`hyperframes_provider.py:141`, env `CREATIVE_HYPERFRAMES_DEFAULT_TEMPLATE`). PRD follows the code.

**Net root cause:** recipe is fixed *and* copy is templated *and* composition is fixed *and* the learning that would break the tie is dead *and* the two differentiating formats are gate-blocked. Four independent causes, all fixable without weakening any gate.

---

## 3. Product Goal & Success Metrics

### 3.1 Product goal

Turn the daily video engine from **one templated video per customer per day** into a **per-customer creative system** that (a) analyses each customer's own social presence, (b) produces a *provably different* video each day, (c) renders locally with the VPS as the data/control plane, (d) carries every video through a full evidence-backed lifecycle to Telegram delivery, and (e) measurably improves from QA + approval + engagement signals.

### 3.2 "High quality" — measurable definition (no adjectives)

| # | Metric | Target | Measurement source (existing) |
|---|---|---|---|
| Q1 | Resolution floor | 1080×1920 for 9:16 | `enterprise_qa.MIN_PIXELS` |
| Q2 | Enterprise classification | ≥ 95% of published videos = `CUSTOMER_APPROVABLE` | `enterprise_qa.evaluate().classification` |
| Q3 | Base QA pass | 100% of published videos pass `run_qa` (`ok=true`) | `qa.run_qa` |
| Q4 | Non-degenerate media | bitrate ≥ 600 kbps, duration 6–90 s, ≥ 2 scenes, no excess black frames | `enterprise_qa.MIN_VIDEO_BITRATE_BPS`, `qa._blackframe_probe` |
| Q5 | **Novelty** | 0 pairs of consecutive-day videos for one tenant with scene-text Jaccard ≥ 0.6 **or** identical `(recipe, template_id)` | new `novelty` gate (§6 P0-1) over `spec_hash`/`input_hashes` |
| Q6 | Cross-customer distinctness | 0 pairs of different tenants sharing identical `spec_hash` | `CreativeSpec.spec_hash()` |
| Q7 | Hook retention | first-2s hook retention ≥ 2.5 s rolling avg (the existing `hook_improvement_needed` threshold) | `learning.get_tenant_recipe_stats` |
| Q8 | First-pass approval | ≥ 80% of videos approved with no `changes_requested` | `store` `approval_history` |
| Q9 | Time-to-approvable | ≤ 15 min p50 from enqueue → `approval_pending` | `spec.render_duration_ms` + ledger |
| Q10 | Delivery proof | 100% of published videos have a Telegram delivery receipt | `delivery_ledger` + Telegram response id |

### 3.3 Business metrics (₹5,00,000 / 7 days)

| # | Metric | Target | Honest framing |
|---|---|---|---|
| B1 | Video-attributed inbound | ≥ 25 verified WhatsApp/call intents from published videos in 7 days | Tracked, **not** assumed |
| B2 | Publishing cadence | ≥ 1 quality-approved video per active tenant per day, 7/7 days | This is the system's only controllable lever |
| B3 | Gate integrity | 0 compliance gates weakened; 0 secrets exposed | Binary, non-negotiable |
| B4 | Pipeline uptime | ≥ 95% of daily runs produce a rendered artifact (or an explicit labelled refusal) | `automation health check` (P0-9) |

> **Honesty flag (do not paper over):** the system today has **1 paying customer** and a **free-tier-only AI stack**. ₹5L in 7 days cannot be produced by video quality alone — it requires new paying customers, which is a sales/fulfilment question, not a rendering question. Video quality is a **necessary, not sufficient** input. This is listed as Open Question OQ-1, not assumed away.

---

## 4. Scope

**In scope:** per-customer social-profile analysis; novelty/dedup gate; per-tenant recipe+template selection; working self-improvement; verified-asset capture to legitimately unlock `before_after`/`testimonial`; local-render + VPS data plane; full per-video lifecycle with evidence; Telegram per-customer + group delivery; automation end-to-end health check; admin dashboard video section (L1–L4).

**Out of scope (explicit):** any change to Swara voice; any change to DND/TRAI/DPDP/consent gates; any paid AI provider; a general-purpose Archify clone (only the video section is specified here); Telegram *ingress* / `getUpdates` (owned by Hermes).

---

## 5. User Stories

| ID | As a… | I want… | So that… |
|---|---|---|---|
| US-1 | Owner | to see, per customer, today's video's QA grade, novelty score and delivery receipt in one card | I can trust the system without opening logs |
| US-2 | Owner | the system to tell me *why* a customer's video was generic or refused (missing brand facts / missing proof assets) with a one-click fix | I stop guessing why quality is poor |
| US-3 | Owner | to receive the finished video on Telegram, both in a per-customer thread and in an ops group | delivery and review happen where I already work |
| US-4 | Customer ("jiya makeover") | a video that looks and sounds like *my* brand — my tone, my audience, my content style — and is different every day | my feed stops looking automated |
| US-5 | Customer | to submit my before/after photos and a real testimonial once, and then have those formats used | my strongest selling formats actually appear |
| US-6 | End-viewer | a video with a clear first-2s hook, legible text, real proof, and a working CTA | I understand the offer and act on it |
| US-7 | Operator | one dashboard where every automation shows end-to-end health (not "route exists") and drills from L1 status to L4 raw evidence | I can prove what works |

---

## 6. Requirement Pool

Legend — **REUSED**: extend the existing component, build nothing parallel. **NEW**: genuinely absent. Evidence labels per the project vocabulary.

### P0 — Must have (blocking the complaint and the target)

| ID | Requirement | Addresses | REUSED / NEW | Evidence base |
|---|---|---|---|---|
| **P0-1** | **Novelty gate.** Before enqueue, compare the candidate `CreativeSpec` against the tenant's last N=7 records. Refuse (`ok:false, error:"near_duplicate"`) when scene-text Jaccard ≥ 0.6 **or** `(recipe, template_id)` is identical to yesterday's, unless the operator explicitly forces it. Must re-select recipe/template/hook rather than silently ship a clone. | RC1, secondary finding | **REUSED:** `CreativeSpec.spec_hash()`, `compute_input_hashes()`, `store.list_records` · **NEW:** `creative_os/novelty.py` + gate call inside `service.enqueue_generate` | `spec.py:159-182`, `store.py:54` |
| **P0-2** | **Per-customer social-profile analysis → Creative DNA.** Analyse each tenant's linked social profiles (Instagram first — `clients_store.socials.instagram` already stored) and persist a versioned `SocialProfile` (tone, audience, content pillars, visual style, posting cadence, top-performing format). Feed it into scene-copy generation, template selection and hook wording. No profile → explicit `needs_customer_input`, never a fabricated profile. | RC2 | **REUSED:** `brief.resolve_brand_profile`, `clients_store.socials`, `brand_kit`, `kb_personalize.client_context`, `runtime_data_authority` store pattern · **NEW:** `creative_os/social_profile.py` + persistence + brief wiring | `brief.py:180-281`, `clients_store.py:114-117` |
| **P0-3** | **Per-tenant dynamic recipe + template selection.** Replace the fixed `DAILY_VIDEO_RECIPE` default as the *sole* selector with a deterministic, tenant-seeded selector over all **8 existing recipes** and the 3 templates. Env value becomes a *default for cold-start tenants only*. Selection must be reproducible (same inputs → same choice) and recorded on the spec. | RC1, secondary finding | **REUSED:** all 8 recipes in `recipes.RECIPES`, `hyperframes_templates.TEMPLATE_REGISTRY`, `learning.suggest_next_creative_strategy` · **NEW:** cold-start rotation strategy | `recipes.py:12-47`, `hyperframes_templates.py:33` |
| **P0-4** | **Make self-improvement actually work.** Persist the learning ledger to disk (per-tenant, via `runtime_data_authority`, mirroring `daily_video._STATE` atomic-replace) and wire real callers: QA verdicts, approvals, rejections (`changes_requested` reason), and post-publish engagement. Learning stays **advisory-only** — never auto-mutates prompts or spends. | RC4 | **REUSED:** `learning.get_tenant_recipe_stats/recommend/suggest_next_creative_strategy`, `runtime_data_authority`, `delivery_ledger` · **NEW:** disk persistence + 4 feed sites | `learning.py:65,68`, `daily_video.py:79-107` |
| **P0-5** | **Legitimately unlock `before_after` / `testimonial`.** Add a customer capture flow (Telegram + dashboard) that collects consent-flagged before/after photos and a verified testimonial quote, registers them via the existing asset registry, and passes them as `source_asset_ids` / `verified_quote`. **The gate in `recipe_allowed` stays exactly as-is.** | RC3 | **REUSED:** `recipes.recipe_allowed`, `assets.register_asset` (has `consent_status`), `approval.bind_approval`, Telegram egress · **NEW:** capture flow + verified-quote store | `recipes.py:54-67`, `assets.py`, `service.py:138` |
| **P0-6** | **Local render + VPS data plane.** Video renders on the owner's local machine; specs/assets/downloads come from the VPS. Transport must be idempotent and resumable: survives network loss, worker restart and VPS restart without double-render or lost artifact; artifact + manifest hash returned upstream. Runs **concurrently** across tenants — no global lock, no serialisation of the render queue. Also: **actually enforce** `network_disabled()` in `_run_renderer` (today it is a flag only). | Scope 2, 6 · RC5 | **REUSED:** `HyperFramesProvider.generate`, `build_manifest`, `manifest_hash`, `render_timeout_s`, `_kill_tree`, `output_root`, `media_roots`, Celery `video` queue, `_enqueue_celery` idempotency key · **NEW:** job transport + resume protocol + network enforcement | `hyperframes_provider.py:465-705`, `service.py:50-80` |
| **P0-7** | **Full per-video lifecycle + evidence projection.** Every video must traverse and *prove*: spec → assets → render → QA → enterprise grade → approval → publish → delivery → evidence. Expose one tenant-scoped lifecycle view. A video with a missing stage shows the stage as failed, never as passed. | Scope 3 | **REUSED:** `states.assert_transition`, `store`, `qa.run_qa`, `enterprise_qa.evaluate`, `approval.bind_approval`, `delivery_ledger`, `service.resolve_output_path` · **NEW:** lifecycle projection + endpoint | `states.py`, `service.py:240-434` |
| **P0-8** | **Telegram delivery — per-customer AND group.** Deliver the final approved video + caption to (a) a per-customer chat/thread and (b) an ops group. Failure is queued and retried, never silently dropped. **Egress only — no `getUpdates` consumer** (Hermes owns Telegram ingress). No tokens/chat-ids in UI, logs or chat. | Scope 4 | **REUSED:** `app/social_engine/providers.py` (`sendMessage`/`sendVideo`), `social_oauth` `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` readiness, `app/utils/owner_feed.py` (T-02, 24/24 tests green) · **NEW:** per-customer router + group binding + retry queue | `OWNER_TELEGRAM_FEED_DESIGN.md:20,25`, §6.2 egress-only constraint |
| **P0-9** | **Automation end-to-end health check.** For each video-related automation, assert an **end-to-end artifact with freshness** — not that a route/scheduler entry exists. Each automation reports: last successful run, last attempt, last artifact id/hash, staleness, and `verified: true/false`. Reuse the `owner_feed` truth gate so unverified sources are force-labelled. | Scope 8 | **REUSED:** `app/api/automation_flags.AUTOMATION_FLAGS`, `admin-dashboard/src/pages/Automations.tsx`, `owner_feed.emit/build_event` truth gate, `daily_video.status()` · **NEW:** probe layer asserting end-to-end evidence | `automation_flags.py:9`, `Automations.tsx`, `daily_video.py:583-630` |
| **P0-10** | **Admin dashboard — Video section (L1→L4).** Single source of truth for the video system (spec §7). | Scope 5 | **REUSED:** `admin-dashboard` `AppShell`/`primitives`/`Card`/`Badge`/`DataTable`, `service.list_cockpit`, `daily_video.status()` · **NEW:** Video section + progressive-disclosure L1–L4 | `admin-dashboard/src/**`, `service.py:34-47` |

### P1 — Should have

| ID | Requirement | Addresses | REUSED / NEW |
|---|---|---|---|
| **P1-1** | **Engagement feedback ingest** — pull post-publish metrics (watch time, hook retention, CTR) into the learning ledger, marked `verified` only when the source is verifiable. | Scope 7 | REUSED: `CreativeLearningLink.metrics/verified`, `record_learning` · NEW: ingest adapters |
| **P1-2** | **Template expansion** — add ≥ 3 tenant-niche compositions (makeover/beauty, salon, local service) so template variety is real, not just recipe variety. | secondary finding | REUSED: `TEMPLATE_REGISTRY` allowlist + binder contract · NEW: templates + binders |
| **P1-3** | **Concurrency budget controls** — per-tenant and global render concurrency caps + backpressure, replacing unbounded fan-out. | Scope 6 | REUSED: `flags.tenant_gen_budget`, `daily_video.max_pending/max_per_run` · NEW: concurrency limiter |
| **P1-4** | **Per-video cost/latency telemetry** surfaced in the dashboard (render ms, retries, transport bytes). | Scope 5 | REUSED: `render_duration_ms`, `budget.count_attempts_today` · NEW: transport metrics |

### P2 — Nice to have

| ID | Requirement | REUSED / NEW |
|---|---|---|
| **P2-1** | A/B variants per video (two hooks) with automatic winner selection from engagement | REUSED: learning loop · NEW: variant orchestration |
| **P2-2** | Multi-aspect / multi-platform auto-variants (9:16 + 1:1 + 16:9) from one spec | REUSED: `_ALLOWED_ASPECTS`, `RESOLUTION_PRESETS` · NEW: multi-render fan-out |
| **P2-3** | Customer self-serve profile re-analysis trigger from the customer portal | REUSED: P0-2 module · NEW: portal surface |

---

## 7. Admin Dashboard — Video Section (Archify style)

**Design language:** dark, card-based, generous spacing, one accent colour, progressive disclosure **L1 → L4**. Nothing on L1 requires a click to be understood; nothing is hidden that would change a decision.

### 7.1 Layout

```
┌─ Video  ─────────────────────────────────────────────────────────────┐
│ [All tenants ▾]  [Today ▾]   ● 4 healthy  ● 1 degraded  ● 0 down     │  ← L1
│ ─────────────────────────────────────────────────────────────────────│
│ ┌─ Health strip (one card per automation) ─────────────────────────┐ │
│ │ daily_video      ● OK    last artifact 6m ago   ✓ verified        │ │
│ │ local_render     ● OK    2 concurrent, 0 queued ✓ verified        │ │
│ │ novelty_gate     ● WARN  1 near-duplicate blocked ⚠ unverified    │ │
│ │ tg_delivery      ● OK    12 delivered / 0 failed ✓ verified       │ │
│ └──────────────────────────────────────────────────────────────────┘ │
│ ┌─ Tenant cards (L2) ──────────────────────────────────────────────┐ │
│ │ jiya makeover · Mumbai          [Approved] [Novelty 0.21 ✓]      │ │
│ │ today: beauty_luxury_offer_v1 · recipe before_after               │ │
│ │ QA: CUSTOMER_APPROVABLE · 1080×1920 · 24.8s · 8.1 Mbps            │ │
│ │ ▸ Profile DNA   ▸ Lifecycle   ▸ Evidence                          │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.2 Progressive disclosure levels

| Level | Shows | Answers |
|---|---|---|
| **L1 — Health** | One card per automation: state (OK/WARN/DOWN), last-successful-artifact age, `verified` badge. No numbers that need interpretation. | "Is anything broken right now?" |
| **L2 — Per tenant / per video** | Today's recipe, template, novelty score, QA classification, resolution, duration, approval state. | "Is *this customer's* video good and different?" |
| **L3 — Lifecycle** | The 9 stages as a horizontal stepper with per-stage status, timestamp and reason. Failed stage is red and names the cause (e.g. `NEEDS_CUSTOMER_INPUT: services.price_inr`). One-click action where a fix exists. | "Where exactly did it stop, and what do I do?" |
| **L4 — Raw evidence** | Raw record JSON, manifest hash, `spec_hash`/`input_hashes`, QA check list, `enterprise_qa` blockers, render stdout tail, Telegram message id, delivery-ledger entries. Copy/download. | "Prove it." |

### 7.3 Dashboard rules

- **Every L1 number is a link** to the exact records that produced it.
- **Refusals are first-class UI**, not errors — `NEEDS_CUSTOMER_INPUT` renders as an actionable card with the missing field names.
- **`verified: false` sources are force-labelled** in the UI (reuse `owner_feed` truth gate) — no unverified number may look like a fact.
- **No secrets**: chat ids, tokens and phone numbers are masked; the API never returns them.
- **Tenant-scoped**: every query is tenant-filtered server-side; the dashboard cannot widen scope.

---

## 8. Hard Constraints (non-negotiable)

| # | Constraint |
|---|---|
| C1 | **Never weaken a compliance gate** (DND / TRAI / DPDP / consent ledger). A "fix" that disables a gate is an **ABORT**, not a deliverable. This explicitly covers `recipe_allowed`, `entitlement_gate`, consent checks in `assets`/`_resolve_photo`, and the publish gate. |
| C2 | **Free-tier AI providers only.** No paid STT/TTS/LLM. If a requirement cannot be met on free tier, it must be labelled and escalated — not silently upgraded. |
| C3 | **Never expose secrets / API keys / tokens / OTPs** in UI, logs or chat. Telegram tokens and chat ids come from env only. |
| C4 | **Preserve tenant isolation and auth boundaries.** Every new store, endpoint and transport is tenant-scoped and refuses cross-tenant reads. |
| C5 | **Do not revive a deprecated feature because an old doc mentions it** — reconcile against code at `33189b70`. (e.g. Telegram publishing was removed 2026-06-28 for ban-risk; that is *publishing*, distinct from *delivery to the owner/customer*.) |
| C6 | **Swara voice = FROZEN.** No modification without regression evidence. |
| C7 | **Evidence labels only:** PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN. Nothing may be described as "working" without evidence. |
| C8 | **No duplicate infrastructure.** If `creative_os`, `hyperframes_provider`, `qa`, `enterprise_qa`, `learning`, `assets`, `approval`, `states`, `store` or `automation_flags` already does it, the requirement says "extend", never "build new". |
| C9 | **Telegram egress only** — never add a `getUpdates` consumer (Hermes owns ingress). |
| C10 | **Fail-closed defaults** for every new flag, consistent with `creative_os/flags.py` and `daily_video` (empty allowlist = nobody). |

---

## 9. Reuse Map (what must NOT be rebuilt)

| Capability | Existing component | Requirement must say |
|---|---|---|
| Scene planning / 8 recipes | `creative_os/recipes.py` | extend (P0-3) |
| Typed spec + hashing | `creative_os/spec.py` | extend (P0-1) |
| Lifecycle state machine | `creative_os/states.py` | extend (P0-7) |
| Render orchestration | `creative_os/service.py` | extend (P0-1, P0-3) |
| Local hermetic render | `hyperframes_provider.py` | extend (P0-6) — renderer already code-present |
| Template allowlist + binders | `hyperframes_templates.py` | extend (P1-2) |
| Brand-fact / entitlement gate | `creative_os/brief.py` | extend (P0-2) |
| Asset registry + consent | `creative_os/assets.py` | extend (P0-5) |
| Base QA | `creative_os/qa.py` | reuse as-is |
| Commercial QA grade | `creative_os/enterprise_qa.py` | reuse as-is (defines Q1/Q2/Q4) |
| Learning contract | `creative_os/learning.py` | extend (P0-4) |
| Approval binding | `creative_os/approval.py` | reuse as-is |
| Record store | `creative_os/store.py` | reuse as-is |
| Flags | `creative_os/flags.py` | extend (C10) |
| Scheduler entrypoint | `marketing/daily_video.py` | extend (P0-3) |
| Celery video seam | `tasks/video_jobs.py` | extend (P0-6) |
| Media roots | `video_media_paths.media_roots()` | reuse as-is |
| Delivery audit | `marketing/delivery_ledger.py` | extend (P0-7, P0-8) |
| Automation registry | `api/automation_flags.py` + `admin-dashboard/pages/Automations.tsx` | extend (P0-9) |
| Owner feed / truth gate | `app/utils/owner_feed.py` | extend (P0-8, P0-9) |
| Telegram egress | `social_engine/providers.py`, `social_oauth` | extend (P0-8) |
| Runtime data resolution | `platform/runtime_data_authority` | reuse as-is (P0-4, P0-6) |

---

## 10. Open Questions (owner decision — not answerable from the repo)

| ID | Question | Why it blocks |
|---|---|---|
| **OQ-1** | **₹5L / 7 days: what is the acquisition plan?** With 1 paying customer and free-tier AI only, video quality alone cannot produce this. Is the intent (a) upsell/expand the existing customer, (b) land new customers via the existing sales engine, or (c) something else? | Sets whether B1 (video-attributed inbound) is even the right success metric, and whether the PRD needs a fulfilment/onboarding workstream. |
| **OQ-2** | **How does the local machine reach the VPS data plane?** Is there an always-on local box, or is "local" the owner's laptop (intermittent)? This decides the resume protocol and whether renders must tolerate the machine being asleep. | Blocks P0-6 design (pull vs push, polling cadence, offline window). |
| **OQ-3** | **Which Telegram surfaces exist today?** Confirm `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` are set and confirm the ops-group chat id, plus who may add a customer thread. | Blocks P0-8 acceptance test. |
| **OQ-4** | **Instagram access method for P0-2** — official Graph API (needs a business account + app review) or manual owner-supplied profile link + screenshots? Free-tier and no-scraping constraints make this a real choice. | Blocks P0-2 feasibility; determines whether analysis is automatic or assisted. |
| **OQ-5** | **Consent wording for before/after photos and testimonials.** These are personal images and quotes of the customer's own clients. Who signs, and where is the consent recorded? | Blocks P0-5 — must not ship a proof format without a consent trail. |
| **OQ-6** | **Which is authoritative for `DAILY_VIDEO_RECIPE`** after P0-3 — should the env value remain a hard override for specific tenants, or be retired? | Determines the cold-start vs override semantics. |

---

## 11. Acceptance Criteria (P0 summary)

1. Two consecutive days for one tenant produce specs with scene-text Jaccard < 0.6 and different `(recipe, template_id)` — or the run is explicitly refused with `near_duplicate`. (Q5)
2. Every tenant has a persisted, versioned `SocialProfile` whose tone/pillars/style visibly influence scene copy and template choice; absence yields `NEEDS_CUSTOMER_INPUT`, never a generic video. (RC2)
3. `record_learning` has ≥ 4 real callers and survives a worker restart with non-empty history. (RC4)
4. `before_after` and `testimonial` render for `jiya makeover` **with** registered consent-flagged assets/quote, and still refuse when absent. (RC3 — gate unchanged)
5. A render survives a forced network drop and a worker restart mid-render with no duplicate artifact and no lost video. (P0-6)
6. `network_disabled()` is enforced (proven by a failed outbound call during render), not merely defined. (RC5)
7. Every published video has a Telegram delivery receipt in `delivery_ledger`. (Q10)
8. Each video automation reports end-to-end health with a real artifact + freshness, and unverified sources are labelled. (P0-9)
9. Dashboard drills L1 → L4 for any tenant/video with zero secrets exposed. (P0-10)
10. All C1–C10 constraints hold; **zero** compliance gates weakened.

---

*Evidence vocabulary: PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN.*
*All code references read at `main` @ `33189b70`. Discrepancies between the brief and the code (default template name) are resolved in favour of the code.*
