# Design — OmniRoute Revenue Plan + SSOT Consolidation

**Deliverable:** `deliverables/engineering-assurance/design-omniroute-revenue-ssot-2026-09-14.md`
**Author:** Archi (阿奇) · System Architect · Engineering Assurance Team
**Date:** 2026-09-14 · **Base:** git HEAD `20e4180b` · **Status:** Proposed
**Task:** #2 — "OmniRoute revenue plan + SSOT consolidation ADR"
**Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

> **Read this first (the one-line honest answer):** OmniRoute is a **cost/quality optimization lane for
> AI calls** — it does not itself create revenue and is **not on the money path today**. ₹5,00,000 in 7 days
> is **not reachable** with the current rails; the honest ceiling is **≈ ₹10,000–₹25,000 incremental**
> (owner-network upside to ≈ ₹30k–₹60k). Details in §2.

---

## 0. Evidence ledger & method

All findings below were re-derived this session by reading code at HEAD `20e4180b` (Grep/Read, targeted).
Where a fact could not be reproduced locally it is labelled honestly and the source of the claim is named.

| Fact | Label | Evidence |
|---|---|---|
| `generate()` does exactly **2 hops** | `CODE-PRESENT` | `app/platform/omniroute_client.py:452-454` (`candidates=[primary]; if fallback: append`) |
| Canonical combo IDs = `leadsgen combo 1..14` | `CODE-PRESENT` | `config/desktop_apps/combo_distribution.yaml:8-22,78-92`; `omniroute_client.py:106-167` |
| Second identity scheme = `leadgen.coding_primary … project_best` (12 routes) | `CODE-PRESENT` | `app/platform/omniroute_client.py:107-166`; `app/platform/agent_os_routing.py:19-30` |
| The 12 `OMNIROUTE_TASK_*` constants have **0 consumers** | `CODE-PRESENT` | Grep `OMNIROUTE_TASK_` across `app/` → only the definitions in `agent_os_routing.py` |
| `combo_distribution.yaml` has **0 runtime/CI consumers** | `CODE-PRESENT` | Only real reader = `scripts/omniroute_combo_distributor.py:53`; the script is unwired |
| 14 combos but **12 email API keys** | `PRODUCTION-PROVEN` (config) / `LOCAL-ONLY` (file) | `~/.openclaw/workspace/omniroute_config.json:10-12` (`combo_target:14`, `leadgen_combos:14`, `email_api_keys_created:12`) |
| `email_api_keys_created` has **0 code readers** | `CODE-PRESENT` | Grep `email_api_keys` across repo → no code hit |
| OmniRoute is a **local-only desktop gateway**, not a 24×7 prod dep | `PRODUCTION-PROVEN` | `docs/architecture/24X7_ARCHITECTURE_RECORD.md:263,274` (ADR-111 / ADR-189); port `20128`, container `leadgen_omniroute` |
| 24×7 LLM path = `free_ai.py` with 429 circuit-breaker | `CODE-PRESENT` | `app/voice_agent/free_ai.py` (~line 420, 937-942) |
| `auto_outreach` is **template-only** — no LLM/OmniRoute | `CODE-PRESENT` | `app/platform/auto_outreach.py` imports: only stdlib + logger (lines 26-38); no `omniroute`/`free_ai` import |
| Real `generate()` callers = dev_control, owner_os, voice | `CODE-PRESENT` | `app/dev_control/governed_omniroute.py:14`; `app/platform/owner_os.py:1958,2014`; `app/voice_agent/omniroute_voice.py` |
| Revenue ledgers absent locally | `LOCAL-ONLY` | `data/invoices.jsonl` and the UPI store are **not in the local tree**; `gst_invoice.stats()` → `total:0` locally. Corroborated by tech-writer (§0). |
| ₹5,997 / 16 invoices / 13 voided / no invoice since Aug 24 | `PRODUCTION-PROVEN` (prior audit, not re-derivable locally) | Given in task brief from the prior audit at HEAD `20e4180b`; **cannot be re-derived on this machine** because the ledger is prod-resident |
| 31 agents: defined 31/31, proven-executing **NO** | `CODE-PRESENT` + `PARTIAL` | `app/platform/team.py:48` `STAFF` = 31 keys; `dev_workers` = 0 rows |
| **Two idempotency truths — must not be conflated** | `CODE-PRESENT` | **DevTask** idempotency = durable (DB-unique `dev_tasks.idempotency_key`, `app/dev_control/service.py:126-134`). **OpenClaw owner-os edge** idempotency = **process-local in-memory**: `_IDEMPOTENCY = MEMORY_STORE` (`app/integrations/openclaw/owner_os_adapter.py:22`; `MEMORY_STORE = MemoryIdempotencyStore()` at `idempotency.py:112`), durable **only** via optional Redis Stage-B/AMBER (`get_store(prefer_durable=durable_idempotency_ready())`, `idempotency.py:115-118`). The process-local store is **evidence AGAINST execution-proof.** |
| Two owner gates (Smartflo DID→VOICE; UPI confirm) | `PRODUCTION-PROVEN` (prior audit) | `app/api/telephony_smartflo.py:370` ("Verify the DID and Voice Bot destination are assigned"); `app/api/upi_payments.py:61` (guests never auto-activate) |
| ADR numbering | `CODE-PRESENT` | `docs/adr/ADR-<n>-<slug>.md`; highest referenced = **189** (`24X7_ARCHITECTURE_RECORD.md`) → next free = **190** |

**Method note:** the ₹5,997 figure is **not** re-derivable on this machine (ledger is prod-resident). It is
carried as `PRODUCTION-PROVEN` from the prior audit and is **not** used as a fabricated local number.

---

## 1. 需求与目标 (Requirements & Goals)

### 1.1 Functional requirements
- **R1** Produce a concrete, executable OmniRoute revenue plan — not prose.
- **R2** Answer: what actually *generates revenue* here, and what does OmniRoute contribute?
- **R3** Specify the 14-combo × 14-email design and the code changes that make the 14-vs-12 gap real.
- **R4** Give honest 7-day ₹5,00,000 arithmetic with assumptions labelled.
- **R5** Name the two owner gates, their order, and what each unblocks.
- **R6** Prove the plan does not touch DND / consent / DPDP / opt-out / tenant isolation.
- **R7** SSOT consolidation ADR: one canonical combo scheme; the task-truth SSOT; one deploy authority.

### 1.2 Non-functional requirements
- **N1 Cost:** the plan must run on the existing free-tier stack (no new paid infra).
- **N2 Latency/volume:** must respect the **25/day email warmup cap** and the DLT-gated SMS/voice rails.
- **N3 Reliability:** OmniRoute stays **fail-open / non-critical** (ADR-111 / ADR-189) — never a 24×7 dependency.
- **N4 Auditability:** every claim labelled; every "needs changing" carries a `file:line`.

### 1.3 Constraints (fixed, non-negotiable)
- **C1** No commit / push / deploy.
- **C2** **No compliance gate may be weakened** (TRAI DND, consent ledger, DPDP, opt-out suppression, tenant isolation).
- **C3** Cold outbound is **DLT-gated**; cold email rides a **fail-closed** suppression store.
- **C4** Manual UPI + owner-confirm is the **only** collection rail (Stripe removed 2026-07-10, Razorpay 2026-06-18).
- **C5** The system currently has **2 paying customers / ₹3,998 MRR baseline** (prior audit; `STALE`-prone doc corrected by tech-writer).

---

## 2. 高层设计 (High-Level Design)

### 2.1 The core architectural truth

```
                     ┌──────────────────────────────────────────────┐
                     │  REVENUE PATH (creates ₹)                     │
                     │  lead-magnet → inquiry → /pricing → /start    │
                     │      → manual UPI → owner confirm → activate  │
                     └──────────────────────────────────────────────┘
                                        ▲
              ┌─────────────────────────┴─────────────────────────┐
              │  OMNIROUTE (optimization lane — creates NO ₹)     │
              │  dev_control · owner_os · voice(swara)            │
              │  14 combos × 42 model slots, free-tier, local-only│
              └───────────────────────────────────────────────────┘
```

**Conclusion:** OmniRoute must be **wired to** a revenue mechanism to matter. Today it is wired to
`dev_control`, `owner_os`, and `voice` only — **none** of which is the customer-acquisition funnel.

### 2.2 Revenue mechanism map — cold prospect → ₹ in bank

| # | Mechanism | Route / code | Revenue role | Evidence label | Status |
|---|---|---|---|---|---|
| M1 | Free GBP self-audit lead magnet | `POST /api/public/audit/score` (`app/api/public_site.py:1165`); questions `:1157` | Top-of-funnel capture | `CODE-PRESENT` | Works |
| M2 | Site-audit + `/demo` AI demo | `POST /api/public/ai-demo` (`public_site.py:418`); `/site-audit` page | Capture | `CODE-PRESENT` | Works |
| M3 | Inquiry form → email notify → auto-callback | `POST /api/public/inquiry` (`public_site.py:457`); `_notify_inquiry_email:356`; `_auto_callback:268` | Prospect → conversation | `CODE-PRESENT` | Works |
| M4 | Programmatic SEO (pSEO) inbound | `app/api/sitemap_builder.py:48-54`; `data/seo_pages.jsonl` | Organic inbound | `PARTIAL` | GSC series **all zeros** (new/low-indexed domain) — `REVENUE_BLOCKERS.md` BLK-04 |
| M5 | Cold email outreach (template, spintax) | `app/platform/auto_outreach.py:601 run_email_outreach`; fail-closed suppression `:536-576` | Outbound → reply → inquiry | `CODE-PRESENT` | **Template-only, no LLM**; capped 25/day warmup |
| M6 | Pricing page + plan selection | `/pricing` (`app/main.py:2007`); `GET /api/billing/plans` (`app/api/billing.py:276`) | Offer | `CODE-PRESENT` | Works |
| M7 | Checkout → **manual UPI** | `POST /api/billing/checkout` (`billing.py:391`, `gateway="upi"`); `GET /api/public/pay-info` (`public_site.py:1066`, UPI QR) | Ask for money | `CODE-PRESENT` | **Disabled if no UPI VPA** (`pay-info` → `{"enabled": false}`) |
| M8 | UPI submit + owner approve → activate | `POST /api/upi/submit` (`app/api/upi_payments.py:50`); `POST /api/upi/pending/{pid}/approve` (`:118`); `_try_activate:186` | **₹ lands** | `CODE-PRESENT` | Guests never auto-activate (`:61`) → **owner gate** |
| M9 | Invoice ledger (GST) | `app/billing/gst_invoice.py:489 stats()`; `on_payment_success:382` | Revenue record | `PRODUCTION-PROVEN` | Ledger **prod-resident** (absent locally) |
| M10 | Subscription + voice minute top-ups | `app/marketing/packages.py:192-246` (₹1,999 / ₹2,999 / ₹5,999); top-ups `:353-355` (₹1,499/₹3,499/₹5,999) | Recurring + expansion | `CODE-PRESENT` | Blocked by **voice gate** (M11) |
| M11 | AI voice calling product | Smartflo DID→VOICE Bot | Premium product | `PARTIAL` | **Owner gate**: `GET /v1/my_number` DID `+918069879757` `destination: null`, no API accepts it (422) |
| M12 | Referral credit | `_credit_referral` (`upi_payments.py:312`) | Expansion | `CODE-PRESENT` | Works (minor) |

**Broken / unwired paths flagged:**
- **M4 (pSEO):** rank series empty → no organic inflow today.
- **M5 (outreach):** template-only; **OmniRoute is NOT in this path** (see §2.3).
- **M7/M8 (collection):** functional but gated on **owner VPA + owner confirm**.
- **M10/M11 (voice):** the highest-₹ product is **dead** until the Smartflo destination gate clears.
- **M9:** ledger is prod-resident → local runs show ₹0 (do not read as "no revenue").

### 2.3 Where OmniRoute actually sits (and where it does not)

`generate()` real callers (Grep, `CODE-PRESENT`):

| Caller | file:line | Lane |
|---|---|---|
| dev_control | `app/dev_control/governed_omniroute.py:14` | engineering |
| owner_os agent-ops | `app/platform/owner_os.py:1958,2014` | internal ops |
| voice (swara) | `app/voice_agent/omniroute_voice.py:180,262` | voice assist (assist only; 24×7 path is `free_ai.py`) |

**None of these is the acquisition funnel.** `auto_outreach.py` imports no LLM at all (`CODE-PRESENT`).
Therefore: **OmniRoute contributes ₹0 to revenue today** — it reduces *cost* of internal/dev/voice-assist
calls and improves their *quality*. The revenue plan must not pretend otherwise.

### 2.4 The 14 combos × 14 emails design

**What a combo is:** a gateway-side **model lane** = 42 model slots across the provider catalog, bound to
**one email account** whose free-tier quota it spends (`config/desktop_apps/combo_distribution.yaml:66-92`).
"14 emails" = **14 free-tier provider accounts** (one quota owner per combo) — **not** 14 outreach sender
addresses.

| Combo | Role (from `omniroute_client.py:95-99` / `seed_omniroute_14combos.py:112-152`) | Email binding (`combo_distribution.yaml:79-92`) |
|---|---|---|
| 1 | coding-primary | admin@leadsgenai.in |
| 2 | coding-fast | ops@leadsgenai.in |
| 3 | repo-analysis | hello@leadsgenai.in |
| 4 | test-generation | support@leadsgenai.in |
| 5 | agent-ops | sunny@leadsgenai.in |
| 6 | swara / voice | sumit20016@gmail.com (kill: `voice_launch_kill`) |
| 7 | marketing | bunnybunnysunny49@gmail.com |
| 8 | prospect-enrich | bunnysunnysunny49@gmail.com |
| 9 | outreach-email | damsamsamdam39@gmail.com |
| 10 | seo-keyword | daryananisumit440@gmail.com |
| 11 | governor | sunnybunny23211@gmail.com |
| 12 | project-best | sunnydaryanani2@gmail.com |
| 13 | vps / free-first failover lane | jiyawasnik11@gmail.com |
| 14 | general-purpose lane | sumitrevolt23@gmail.com |

**Primary / fallback mapping (today):** `_TASK_ROUTES` (`omniroute_client.py:106-167`) maps **12 task types**
→ **2-combo chains** (primary + one fallback). Combos **13/14 are never primary** — they exist only as
failover/general lanes. This is the crux of the 14-vs-12 confusion: **14 combos, 12 named routes.**

**How an email key maps to a combo:** 1:1 by combo name (`combo_distribution.yaml:78-92`). Each combo needs
its own bound email API key to spend that account's free tier.

**The real 14-vs-12 gap:** `~/.openclaw/workspace/omniroute_config.json:12` records
`email_api_keys_created: 12` against `combo_target: 14` → **2 combos have no bound email key**, so their
free-tier quota is unavailable and any route that lands on them silently falls to the fallback (which is why
the 2-hop path "works" while hiding the missing 2 accounts). **No code reads this key** (Grep → 0 hits), so
nothing reconciles or alarms on it.

**What code changes make the gap real (file:line):**

| Change | file:line | Today | Needed |
|---|---|---|---|
| W1 — N-hop candidate chain | `app/platform/omniroute_client.py:452-454` | `candidates=[primary]; if fallback: append` (**exactly 2**) | Accept a bounded candidate list (keep the 429 retry budget) |
| W2 — canonical 14-combo route table | `app/platform/omniroute_client.py:106-167` | 12 routes over 14 combos; 13/14 never primary | Derive routes from `combo_distribution.yaml`; make 13/14 explicit |
| W3 — wire the manifest reader | `scripts/omniroute_combo_distributor.py:53` | Sole real reader of the YAML, **unwired** | Add `validate` to CI + startup reconcile |
| W4 — reconcile email keys | `~/.openclaw/workspace/omniroute_config.json:12` | 12 vs 14; **no reader** | New `scripts/reconcile_omniroute_email_keys.py` + health check |
| W5 — kill the second identity scheme | `app/platform/agent_os_routing.py:19-30` | 12 `OMNIROUTE_TASK_*` constants, **0 consumers** | Delete, or derive from `_TASK_ROUTES` |

**Explicit honesty statement:** the "next email's combo" failover chain described in `docs/openclaw/*` prose
is **NOT implemented**. `generate()` is **2 hops**, full stop. Do not plan against the prose.

### 2.5 7-day ₹5,00,000 arithmetic (honest funnel math)

**Price points (`CODE-PRESENT`, `app/marketing/packages.py:192-246,353-355`):** Starter ₹1,999 · Growth
₹2,999 (legacy, hidden) · Advanced ₹5,999 · voice top-ups ₹1,499 / ₹3,499 / ₹5,999.

**Units required to hit ₹5,00,000 in 7 days:**

| Mix | Unit price | Units needed | Units / day |
|---|---|---|---|
| All Starter | ₹1,999 | 500,000 / 1,999 = **250.1 → 251** | **35.9 / day** |
| All Advanced | ₹5,999 | 500,000 / 5,999 = **83.3 → 84** | **12.0 / day** |
| Mixed (avg ₹2,999) | ₹2,999 | 500,000 / 2,999 = **166.7 → 167** | **23.9 / day** |

**Supply actually available on today's rails (all conversion rates are ASSUMPTION, not fact):**

| Stage | Capacity | Source / label |
|---|---|---|
| Cold email sends | **25 / day** warmup cap → 175 / 7 days | ASSUMPTION (warmup cap, `REVENUE_BLOCKERS.md`/7-day plan) |
| Cold email reply rate | 1–3% → **2–5 replies / 7 days** | ASSUMPTION |
| Reply → paid | 15–25% → **≈0.3–1.3 sales** | ASSUMPTION |
| Organic pSEO inflow | ≈0 (GSC all zeros) | `PARTIAL` (BLK-04) |
| Lead-magnet → paid | unknown, no measured series | `UNKNOWN` |
| Existing base upsell | 2 paying customers → ≈1 upsell (+₹1,999–₹4,000) | ASSUMPTION |

**Verdict:**
- **₹5,00,000 in 7 days is NOT reachable** with the current rails. To reach it you need **12–36 new paid
  customers/day**, but the compliant outbound rails can physically carry ~25 emails/day total and cold
  outbound is **DLT-gated** (SMS/voice) / warmup-capped (email). The funnel volume gap is **two orders of
  magnitude**.
- **Best achievable with current rails:** **≈ ₹10,000–₹25,000 incremental** in 7 days (≈1–5 Starter/Advanced
  sales + 1 upsell), matching the tech-writer's independent §2 ceiling.
- **Optimistic upside (owner works personal network / warm intros):** ≈ ₹30,000–₹60,000. Still **~8–16× short**
  of ₹5L.
- **What *would* reach ₹5L** (none of it exists today, all require owner action): a handful of **B2B/enterprise
  or annual-prepay deals** (e.g. 5 × ₹1L), **voice-minute enterprise packs** (blocked by the voice gate), or
  **paid ads with a proven CAC** (no ad rail wired). ₹5L is a **sales/relationship** target, not a
  software-throughput target.

**OmniRoute's contribution to this number:** it lowers the **cost** of the AI calls that produce marketing
content / SEO / voice assist — it does **not** add a rupee of revenue by itself. Wiring OmniRoute into the
acquisition funnel (§3, W1–W5) improves margin and content throughput, not the 7-day top line.

---

## 3. 关键决策记录 ADR (Architecture Decision Records)

### ADR-190: ONE canonical combo identity scheme

**Status:** Proposed · **Date:** 2026-09-14

**Context.** Two competing combo identity schemes exist (`CODE-PRESENT`):
- **A. Provider-side:** `leadsgen combo 1..14` — 14 IDs, canonical in
  `config/desktop_apps/combo_distribution.yaml:8-22` and used as the `model` string in
  `omniroute_client.py:106-167`.
- **B. Harness-side:** `leadgen.coding_primary … leadgen.project_best` — 12 **task-route** names in
  `omniroute_client.py:107-166` and `agent_os_routing.py:19-30`.

These are **different concepts** (a *lane* vs a *job*), but they are used as if interchangeable, and the
12-vs-14 mismatch is the visible symptom.

#### Options analysis

**Option A — canonical = `leadsgen combo N` (provider-side).**
| Dimension | Assessment |
|---|---|
| Complexity | Low — already the wire format the gateway speaks |
| Cost | Zero — no gateway change |
| Scalability | High — 1 ID = 1 quota lane, 1:1 with the email binding |
| Coupling | Loose — task routes become a *projection* over combos |

**Option B — canonical = `leadgen.<task>` (harness-side).**
| Dimension | Assessment |
|---|---|
| Complexity | High — the gateway has no notion of these names |
| Cost | Requires a translation layer on every call |
| Scalability | Poor — 12 names over 14 lanes loses 2 lanes; new lanes need a name each |
| Consumers | **0** (`OMNIROUTE_TASK_*` constants have no readers — `CODE-PRESENT`) |

**Decision.** **Option A wins.** `leadsgen combo 1..14` is the **sole canonical combo identity**.
Rationale: (1) it is the wire format the gateway already speaks; (2) it is 1:1 with the email/quota binding
in the manifest; (3) it is a **superset** (14 ⊃ 12) so no lane is orphaned; (4) the competing scheme has
**zero consumers** and is therefore safe to retire.

**Migration path for the loser (B):**
1. Keep `_TASK_ROUTES` **keys** (`leadgen.*`) only as a *task-type namespace* (callers pass a task type).
2. Make each route's `primary_model` / `fallback_model` **derived** from the manifest, not hand-coded
   (`omniroute_client.py:106-167`).
3. **Delete** the 12 `OMNIROUTE_TASK_*` constants in `agent_os_routing.py:19-30` (0 consumers) or re-export
   them as aliases of the `_TASK_ROUTES` keys — one definition, not two.
4. Add a CI check: the set of canonical combos in the manifest == the set of `primary_model`+`fallback_model`
   values in `_TASK_ROUTES` ∪ {13,14}.

**Consequences.** ✅ One SSOT for combo identity. ✅ The 14-vs-12 gap becomes a *checkable invariant*.
⚠️ Any external script that hard-coded `leadgen.*` as a *model* string would break — none found
(`CODE-PRESENT`).

**Alternatives considered.** (a) Keep both and document the mapping — rejected: two truths invite drift.
(b) Rename combos to task names — rejected: forces a gateway change for zero gain.

---

### ADR-191: Task-truth SSOT (one truth per domain)

**Status:** Proposed · **Date:** 2026-09-14

**Context.** Multiple overlapping ledgers exist for the same concepts (`CODE-PRESENT`):

| Domain | Proposed SSOT | Competing / duplicate sources that must die |
|---|---|---|
| Task truth | `app/models/dev_task.py` `DevTask` (table `dev_tasks`) | `app/models/agent_task.py` `AgentTask` (table `agent_tasks`); `app/platform/agent_task_queue.py` |
| Runtime truth | `dev_workers` (`app/models/dev_worker.py:71`) + `DevTaskEvent` (`app/models/dev_task_event.py:38`) | The OpenClaw owner-os edge keeps a **process-local** `_IDEMPOTENCY` (`owner_os_adapter.py:22` = `MEMORY_STORE`; `idempotency.py:112`) — durable only when Redis is up (`idempotency.py:115-118`). This is **distinct** from DevTask, whose idempotency IS durable (DB-unique, `service.py:126-134`); do not cite one to refute the other. |
| Roster truth | `app/platform/team.py:48` `STAFF` (31 keys, `CODE-PRESENT`) | `docs/AGENT_REGISTRY.md` (says 19 — a lying doc); `HERMES_AGENT_ROSTER.yaml` |
| Config truth | `app/api/automation_flags.py:9` `AUTOMATION_FLAGS` registry | `app/platform/automation_flag_manifest.py` (metadata layer — **keep**, it is honest) |

**Decision.**
- **Task truth = `DevTask`.** `dev_task_event.py:1-3` already declares it "the single canonical 24×7 task
  truth." **For DevTask**, idempotency is enforced by the **DB unique column** `dev_tasks.idempotency_key`
  (`service.py:126-134`), not a process dict. **This does NOT extend to the OpenClaw owner-os edge**, which
  still defaults to a **process-local** `MEMORY_STORE` (`owner_os_adapter.py:22`; `idempotency.py:112`) and is
  durable only when Redis is reachable (`idempotency.py:115-118`) — so the edge remains evidence *against*
  execution-proof.
- **Runtime truth = `dev_workers` + `DevTaskEvent`.** `dev_workers` = 0 rows today ⇒ **31 agents are NOT
  proven-executing** (`PARTIAL`) — do not report otherwise.
- **Roster truth = `team.py` STAFF (31).** `docs/AGENT_REGISTRY.md` must be **generated** from `team.py`,
  not hand-maintained.
- **Config truth = `AUTOMATION_FLAGS` registry.** `automation_flag_manifest.py` stays as the typed honesty
  layer (it explicitly refuses to invent production proof — keep it).
- **Duplicates that must die:** `AgentTask` / `agent_task_queue` as a *task* SSOT (fold into `DevTask` or
  document as a distinct, narrower queue); the process-local `_IDEMPOTENCY` pattern anywhere it still
  survives.

**Consequences.** ✅ One queryable task truth. ✅ Runtime proof becomes a real gate (`dev_workers` rows).
⚠️ Folding `AgentTask` requires a migration + a compatibility read path — schedule it, don't big-bang it.

---

### ADR-192: ONE deploy authority

**Status:** Proposed · **Date:** 2026-09-14 · **Revised:** 2026-09-14 (post team-lead review)

**Context (revised — the earlier draft cited `build`/`deploy` jobs that no longer exist).**
Two mechanisms historically competed to ship a release (`CODE-PRESENT`):
- `.github/workflows/ci.yml` — **merge gate** (PR / `workflow_dispatch`). Its `tests` aggregator now asserts
  **FIVE** lanes: `needs: [prod-check, pytest-job, pip-audit, quality, harness-redis-integration]`
  (`ci.yml:193`), each asserted `= "success"` (`ci.yml:204-213`). Required check name stays
  `prod_check + pytest`.
- `.github/workflows/deploy-vps.yml` — now **GATE-ONLY**. The `build:` (GHCR push) and `deploy:`
  (SSH → `/usr/local/sbin/leadgen-deploy-release`) jobs were **deleted 2026-09-14** (sre-engineer). The file's
  only jobs are `gate` (`:37`), `pytest-shards` (`:87`, opt-in behind `DEPLOY_RETEST`, `needs: []`) and
  `release-gate` (`:139`, `needs: [gate]`, `:149`). The `packages: write` grant was removed and the VPS/GHCR
  secrets are no longer referenced. An in-file "ONE DEPLOY AUTHORITY" block (`deploy-vps.yml:155-187`)
  documents why.
- **The single deploy authority is `scripts/deploy_vps.sh`**, run ON the VPS from `/opt/leadgen`
  (`AGENTS.md:45` §3; anti-mistake rule **R10** "deploy sirf `deploy_vps.sh`"). Hand-written docker commands
  are **forbidden**. The script mandates `APP_VERSION` (refuses `:-latest`), deploys all **5** app-image
  services (anti-skew), uses `pipefail`, and verifies `/health.version == <sha>` + per-container skew + smoke
  before returning OK.

**Why the CI deploy job was a bypass (the reason for the deletion).** The removed `deploy` job SSH'd a VPS
wrapper (`/usr/local/sbin/leadgen-deploy-release`) that **pulled a pre-built GHCR image and never called
`scripts/deploy_vps.sh`** — thereby skipping the runtime-data guard, `prod_check.py --deployment`, the ff-only
checkout advance, the 5-service anti-skew rollout, `/health.version == <sha>`, the revenue/auth smoke suite,
and lineage-aware retention (`deploy-vps.yml:158-168`). Two mechanisms with different guarantees = an
unauditable release.

**Second premise corrected: branch protection does not exist.** Independently verified this session via the
GitHub API (not inferred):
```
gh api repos/sumitrevolt/leadgenrationaivoiceagent/branches/main/protection → HTTP 404 "Branch not protected"
gh api repos/sumitrevolt/leadgenrationaivoiceagent/rulesets                   → []
```
There are **zero required status checks and zero rulesets**. Every CI gate in this repo is therefore
**advisory at the platform level** — a red check does not, by itself, block a merge. `AGENTS.md:137`'s claim
of "branch protection" **was** STALE/wrong (the local `no-commit-to-branch` pre-commit hook is a different,
weaker control). **Correction landed 2026-09-14** by tech-writer in both `AGENTS.md:137` and `CLAUDE.md:137`
(kept byte-identical per the mirror test `tests/test_1000_engineers_skill.py:67`; both now `cbce2e00…`,
37,825 B), and recorded as the canonical example for the proposed `doc_truth_guard.py` (P2). This is a
significant part of why "fix one thing, break another" keeps happening.

#### Options analysis

**Option A — `scripts/deploy_vps.sh` is the sole SHIP authority; `ci.yml` is the sole MERGE authority.**
| Dimension | Assessment |
|---|---|
| Complexity | Low — one script ships, one workflow gates |
| Cost | Zero |
| Safety | **High** — the only shipping path enforces APP_VERSION + 5-service anti-skew + health==sha + smoke |
| Enforcement gap | `ci.yml`'s `tests` result is **not** a required check today (no branch protection) → advisory until an admin adds it |

**Option B — a CI workflow ships (the deleted `build`/`deploy` jobs).**
| Dimension | Assessment |
|---|---|
| Complexity | Medium — needs GHCR push + SSH + a VPS wrapper |
| Safety | **Low** — proven to bypass the runtime-data guard, anti-skew, health==sha, and smoke |

**Decision. Option A.**
1. **SHIP authority = `scripts/deploy_vps.sh`** (on-VPS: `cd /opt/leadgen && setsid nohup bash
   scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &`; `DRY_RUN=1` prints the plan). `deploy-vps.yml` is
   **gate-only and structurally cannot ship** — no job left can. Do **not** re-add a deploy job there; if a
   CI-initiated release is ever wanted it must **invoke the script**, and that is an owner decision.
2. **MERGE authority = `ci.yml`.** Its `tests` aggregator (5 lanes, `ci.yml:193`) is the correct gate and must
   be made a **required status check** via branch protection / a ruleset.
3. **This enforcement point is an owner/GitHub-admin action, not code — and it is NOT already configured**
   (404 verified). Until it is done, every gate is advisory. State this plainly; do not describe it as
   already configured.
4. Keep `pytest-shards` opt-in; the authority is the script + CI, not a deploy-side re-run.

**Note on the 5-lane aggregator.** `quality` is asserted because its blocking steps are real (compileall,
check_secrets, security_scan, skill ratchet, queue-idempotency ratchet); the only non-blocking steps are
mypy/ruff with `|| true` **inside** the job (`ci.yml:85,88`) so the job result cannot go red cosmetically.
`harness-redis-integration` is asserted because `HARNESS_REQUIRE_REDIS=1` (`ci.yml:274`) plus a fail-on-skip
grep guard (`ci.yml:278-279`) converts a skipped suite into a failure. mypy/ruff stay advisory deliberately
(~1,522 pre-existing errors).

**Consequences.** ✅ ONE ship authority (the script). ✅ `deploy-vps.yml` can no longer diverge or bypass
runtime guards. ✅ The 5-lane merge gate is honest. ⚠️ Until branch protection / a ruleset is added
(owner/GitHub-admin), the merge gate is **advisory** — a real risk that must be stated, not hidden.

**Alternatives considered.** (a) Keep the CI deploy job — rejected: proven to bypass every runtime guard.
(b) Treat the gate-only workflow as the "ship authority" — rejected: it cannot ship by construction.
(c) Merge both workflows — rejected: PR-time gating and push-time release are legitimately different
triggers; the *duplication of authority*, not the split, was the defect.

---

## 4. 可运维性 (Operability)

### 4.1 The two owner gates — order and unblocks

| Order | Gate | What the owner must do | What unblocks the moment it is done |
|---|---|---|---|
| **1** | **UPI collection** | Set a UPI VPA (else `GET /api/public/pay-info` returns `{"enabled": false}`, `public_site.py:1083-1084`); then **confirm each UPI credit** in `/app/inbox` via `POST /api/upi/pending/{pid}/approve` (`upi_payments.py:118`). Guests never auto-activate (`:61`). | **Any ₹ can land.** Without owner confirm, a willing buyer cannot be provisioned. This is the money gate. |
| **2** | **Smartflo DID→VOICE Bot destination** | In the Smartflo console, assign the DID `+918069879757` a VOICE Bot destination. `GET /v1/my_number` returns `destination: null`; **no API accepts it** (422 proven). Code hint: `telephony_smartflo.py:370`. | **The premium product (AI voice) goes live** → unlocks voice plans + top-ups (₹1,499–₹5,999) = the highest-₹ revenue path (M10/M11). |

**Not a gate:** Telegram (observability only). **Do not** treat Telegram as a revenue blocker.

### 4.2 Operability of the OmniRoute lane
- OmniRoute is **local-only / non-critical** (ADR-111 / ADR-189, `24X7_ARCHITECTURE_RECORD.md:263,274`).
  It must stay **fail-open**: `generate()` returns `None` on gateway fault and callers fall back
  (`omniroute_client.py:413-439`). **Never** promote it to a 24×7 dependency without an owner gate.
- 24×7 LLM path stays `app/voice_agent/free_ai.py` with its escalating 429 circuit-breaker (60s→30min).
- Port truth: **`20128`** = OmniRoute (`leadgen_omniroute`); **`18789`** = OpenClaw tray (not OmniRoute).
- New reconcile job (W4) should emit a health line when `email_api_keys_created < combo_target` so the
  14-vs-12 gap can never silently persist again.

### 4.3 Runbook (proposed)
1. Owner sets UPI VPA → verify `GET /api/public/pay-info` → `enabled: true`.
2. Owner assigns Smartflo DID → VOICE Bot → verify `GET /v1/my_number` → `destination != null`.
3. Run `scripts/omniroute_combo_distributor.py validate` (once wired) → expect 14 combos, each ≥3 providers.
4. Run new `scripts/reconcile_omniroute_email_keys.py` → expect 14/14 keys.
5. Warm the outreach rail within the 25/day cap; keep suppression fail-closed.

---

## 5. 测试策略 (Testing Strategy)

| Area | Test | Type | Priority |
|---|---|---|---|
| Combo identity SSOT | Assert manifest combo set == `_TASK_ROUTES` model values ∪ {13,14} | Unit (CI) | P1 |
| 14-vs-14 email keys | Assert `len(combo emails) == len(created keys) == 14` | Unit + health | P1 |
| 2-hop → N-hop | Regression: `generate()` still returns `None` on all-hop failure; never exceeds hop budget | Unit | P1 |
| Route derivation | `_TASK_ROUTES` primary/fallback ⊆ manifest combos | Unit | P1 |
| Outreach compliance | Suppression store unreadable ⇒ **every** recipient blocked (fail-CLOSED) | Unit (exists: `auto_outreach.py:536-576`) | P0 |
| Consent/opt-out | `is_suppressed()` last-10-digit match enforced for promotional calls | Unit (exists: `consent_ledger.py`) | P0 |
| DLT SMS | `sms_dlt` stays **INERT** without creds (`{"ok":false,"inert":true}`) | Unit | P0 |
| UPI activation | Guest submit never auto-activates; owner approve required | Unit (exists: `upi_payments.py:61`) | P0 |
| Deploy authority | (1) `deploy-vps.yml` contains **no** job capable of shipping (only `gate`/`pytest-shards`/`release-gate`); (2) a red CI `tests` (5 lanes) blocks merge **once** branch protection exists | CI config test + platform check | P2 |
| Idempotency truth | DevTask = durable (DB-unique); OpenClaw edge = process-local (`MEMORY_STORE`) unless Redis up | Unit | P1 |

**Rule:** the P0 tests are **compliance gates** — they must never be weakened to make a sprint pass.

---

## 6. 文档结构 (Documentation Structure)

```
deliverables/engineering-assurance/
└── design-omniroute-revenue-ssot-2026-09-14.md   ← this file (plan + ADR-190/191/192)
docs/adr/
├── ADR-190-canonical-combo-identity.md           ← extract ADR-190 (next free number)
├── ADR-191-task-truth-ssot.md                     ← extract ADR-191
└── ADR-192-single-deploy-authority.md             ← extract ADR-192
```
- **Doc-truth guard (P2):** a CI check that fails when a doc contradicts a code SSOT (e.g.
  `AGENT_REGISTRY.md` says 19, `team.py` says 31) — proposed in the tech-writer's context too.
- **Naming discipline:** "Master Blueprint" = architecture graph; "Revenue Sprint Master Blueprint" =
  `7_DAY_REVENUE_PLAN.md`. Never let one name mean two SSOTs.

---

## 7. 风险与权衡 (Risks & Tradeoffs)

| Risk | Likelihood | Impact | Mitigation / Tradeoff |
|---|---|---|---|
| ₹5L expectation persists despite being unreachable | High | High | Lead with the honest verdict (§2.5); give the achievable number + what *would* reach ₹5L |
| Owner gates assumed to be code bugs | Medium | High | Explicitly state both gates are **non-code owner actions** (§4.1) |
| OmniRoute over-promised as a revenue driver | Medium | Medium | §2.3 states plainly it contributes ₹0 today |
| Weakening a compliance gate to "hit the number" | Low | Critical | Hard rule C2; P0 tests are non-negotiable |
| 14-vs-12 gap silently persists | Medium | Medium | W4 reconcile job + health alarm |
| Folding `AgentTask` breaks callers | Medium | Medium | Compatibility read path + scheduled migration, not big-bang |
| Deploy-authority change needs GitHub admin | Medium | Low | Flag as owner/GitHub-admin action, not a code-only fix |

**Tradeoff summary:** we choose **honest under-promise** (ceiling ₹10k–₹25k, labelled assumptions) over a
plan that looks impressive but violates the compliance spine or fabricates throughput the rails cannot carry.
Complexity is deliberately kept low: the winning moves are **deleting a duplicate scheme (ADR-190)** and
**wiring an existing reader (W3/W4)** — not building new systems.

---

## Appendix — Top 5 wiring changes (file:line)

1. **W1** `app/platform/omniroute_client.py:452-454` — `candidates=[primary]; if fallback: append` → bounded
   N-hop candidate list (today: **exactly 2**).
2. **W2** `app/platform/omniroute_client.py:106-167` — 12 routes over 14 combos; combos 13/14 never primary →
   derive routes from `combo_distribution.yaml`.
3. **W3** `scripts/omniroute_combo_distributor.py:53` — sole real reader of the manifest, **unwired** →
   wire `validate` into CI + startup.
4. **W4** `~/.openclaw/workspace/omniroute_config.json:12` — `email_api_keys_created: 12` vs
   `combo_target: 14`, **0 code readers** → new reconcile script + health alarm.
5. **W5** `app/platform/agent_os_routing.py:19-30` — 12 `OMNIROUTE_TASK_*` constants, **0 consumers** →
   delete or derive from `_TASK_ROUTES`.

**Plus (revenue wiring, not combo):** `app/platform/auto_outreach.py` (imports at `:26-38`) has **no LLM** —
if OmniRoute is to touch revenue, the `leadgen.outreach_email` lane (combo 9) must actually be called; today
it is not.
