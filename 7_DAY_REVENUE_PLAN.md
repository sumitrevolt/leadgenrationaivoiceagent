# Revenue Sprint Master Blueprint — 7 Days → ₹5,00,000

> **AUTHORITY — single source of truth for the revenue sprint.**
> This file (`7_DAY_REVENUE_PLAN.md`) is the one authoritative revenue-sprint blueprint. It **supersedes as
> authority** (files kept, not deleted): `DAY_0_REVENUE_BASELINE.md`, `REVENUE_BLOCKERS.md`,
> `docs/REVENUE_SPRINT_AUTOPILOT.md`, `automation-fix-overview.md`. Those remain as inputs/engines; their
> standalone authority is retired.
>
> **Not the same thing as the architecture "Master Blueprint"** (`docs/ARCHITECTURE_BLUEPRINT.md` /
> `app/platform/blueprint_graph.py`) — that is a code-backed architecture graph and a different domain.
> Do not merge the two.
>
> **Updated:** 2026-09-14 · Docu (Technical Writer · Engineering Assurance Team)
> **Baseline:** git HEAD `20e4180b` · prod `/health.version` `95245ce8` · environment `production`
> **Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`
> **Rule:** a claim without a label or a source is a claim you may not act on.

---

## 0. TL;DR (read this before the day-by-day)

- **Target: ₹5,00,000 collected in 7 days.** Honest verdict: **not reachable on current rails.** The
  arithmetic (§2) needs ~251 Starter sales or ~102 mixed sales; the rails cap out at ~875 outbound
  contacts/week. Best achievable is **≈ ₹10k–₹25k** new collections in 7 days — and only if the two
  owner gates open.
- **Verified money baseline (§1): ₹5,997 collected FY 2026-27**, 16 invoices, **13 voided as synthetic**,
  no new invoice since **Aug 24**. `data/revenue_attribution.jsonl` is **not money**.
- **Nothing in code blocks revenue. Two owner/console actions do (§3):**
  1. Smartflo console — set the DID→VOICE Bot destination (`destination: null` today).
  2. UPI collection — owner-authenticated `/app/inbox` + bank credit confirmation.
- **Telegram does NOT block revenue** (observability only). **Inbound calls are NOT working** — the
  `destination: null` root cause is unchanged from 2026-09-12.
- **Automation honesty (§5): defined 31/31 ✅ · armed partial 🟡 · proven-executing ❌ NO.** Never write
  "31 agents running".
- **Token burn (§6):** `AGENTS.md` == `CLAUDE.md` byte-identical (37,371 B each) → every turn pays twice;
  `progress.md` + `docs/SESSION_LOG.md` ≈ 940 KB append-only. Fix = 2-file truth rule + hard budget.

---

## 1. Revenue baseline — the honest starting line

Source of truth for money = **`data/invoices.jsonl`** (GST ledger) read through
`app.billing.gst_invoice.stats()` (`PRODUCTION-PROVEN`). Note: this ledger is **prod-resident** — it is
**not present in the local working tree** (only `data/revenue_attribution.jsonl` is, and that file is not
money). Verify on the VPS only:

```bash
docker exec leadgen_app python -c "from app.billing import gst_invoice as g; print(g.stats())"
```

| Metric | Verified value | Label |
|---|---|---|
| Collected revenue, FY 2026-27 | **₹5,997** | `PRODUCTION-PROVEN` |
| Invoices in FY ledger | **16 total · 13 voided (synthetic) · 3 real** | `PRODUCTION-PROVEN` |
| Voided gross | ₹63,987 | `PRODUCTION-PROVEN` |
| Last new invoice | **Aug 24** (ledger mtime) ⇒ no new invoice in ~3 weeks | `PRODUCTION-PROVEN` |
| `data/revenue_attribution.jsonl` | **NOT money** — 27 rows, `amount_inr` = 0 except 2 test rows | `CODE-PRESENT` |
| Current MRR / active subscriptions | **UNKNOWN** — not re-verified this session | `UNKNOWN` |

**Corrections to earlier figures (this is the "8 months flat" evidence):**

- `DAY_0_REVENUE_BASELINE.md` states **"Total Collected Revenue (Lifetime) ₹7,997"** and
  **"Current MRR ₹3,998 (2 × Starter)"**. Those are **STALE** (dated 2026-08-22, pre-correction) and
  **overstate** the FY 2026-27 ledger truth of **₹5,997 collected / 3 real invoices**. Do **not** quote
  ₹7,997 or ₹3,998 as current. (The ₹7,997 appears to include a test invoice, INV/0016 "Test Hotel Spa".)
- `DAY_0_REVENUE_BASELINE.md` also self-declares *"the sole source of truth for the 7-day revenue
  acceleration sprint"* — that claim is **retired**; this blueprint is the SSOT (§4).
- The old 7-day target in this file was **₹9,995 (5× of ₹1,999)**. It is **superseded** by the owner's
  ₹5,00,000 target (§2). Do not carry the ₹9,995 figure forward.

**Baseline, plainly:** a live SaaS with **₹5,997 collected this FY**, **no invoice in ~3 weeks**, and a
marketing/voice stack that is wired and compliant but not producing revenue. The bottleneck is **not code**.

---

## 2. The ₹5,00,000 / 7-day target — with the arithmetic

**Target (owner-set):** ₹5,00,000 **collected** in 7 days. Every price below is `CODE-PRESENT`
(`app/marketing/packages.py`; manual UPI only).

### 2a. Units required (pure arithmetic — no assumptions)

| Tier | Price | Units for ₹5,00,000 |
|---|---|---|
| Starter | ₹1,999/mo | **251** |
| Combo / Advanced | ₹5,999/mo | **84** |
| Voice Agent Tier 2 | ₹9,999/mo | **51** |
| Mixed example | 40×1,999 + 50×5,999 + 12×9,999 | **102 units = ₹4,99,898** |

### 2b. Funnel volume required (every rate below is an **ASSUMPTION**)

There is **no proven funnel** in the ledger (that is what "8 months flat" means), so these rates are
assumptions, not measurements. Assumed chain: contact→reply **2%** · reply→opportunity **30%** ·
opportunity→paid **20%** (⇒ contact→paid ≈ 0.12%).

| Stage | To close 102 mixed units (ASSUMPTION) |
|---|---|
| Opportunities needed | 102 ÷ 0.20 = **510** |
| Replies needed | 510 ÷ 0.30 = **1,700** |
| Outbound contacts needed | 1,700 ÷ 0.02 = **85,000** in 7 days ≈ **12,143/day** |

### 2c. Rails capacity vs requirement

| Rail | Cap (current) | Source | 7-day capacity |
|---|---|---|---|
| Email outreach | 25/day | `auto_outreach.py` warmup cap (`CODE-PRESENT`) | 175 |
| Outbound voice | `PLATFORM_DIAL_LIMIT=100`/day | `ACTIVE_WORK.md` (`CODE-PRESENT`) | 700 |
| Cold WhatsApp | **OFF by design** | compliance invariant | 0 |
| **Total** | | | **~875 contacts/week** |

**Gap: 85,000 required ÷ 875 available ≈ 97×.** Even at a wildly generous 10% reply / 30% close, the
required volume is ~10× beyond the rails. **Conclusion: ₹5,00,000 in 7 days is not achievable on current
rails without breaking a compliance gate or a channel cap — which this blueprint forbids.**

### 2d. Best achievable (ASSUMPTION-labeled — the honest ceiling)

| Lever | Assumed rate | Expected units | ₹ |
|---|---|---|---|
| Hot Queue 42 warm leads (owner-executed 1-click UPI) | 5% close | ~2 Starter | ₹3,998 |
| Existing customers upsell | 30% | ~1 Combo | ₹5,999 |
| Outbound 875 contacts | 0.12% contact→paid | ~1 Starter | ₹1,999 |
| Voice Tier (needs inbound working) | 0–1 | 0–1 | ₹0–₹9,999 |
| **Realistic 7-day ceiling** | | | **≈ ₹10k–₹25k** |

**State this to the owner plainly:** the sprint target is ₹5,00,000; the evidence-backed ceiling on the
current rails is roughly **₹10,000–₹25,000**. Closing the gap requires **capacity** (more proven-executing
agents + warmed channels), **not** a bigger number in a document.

### 2e. OmniRoute / combo economics (Archi — `CODE-PRESENT` at HEAD `20e4180b`)

| Fact | Value | Label |
|---|---|---|
| Canonical combo scheme | `leadsgen combo 1..14` (provider-side) — **ADR-190** | `CODE-PRESENT` |
| Losing scheme (retire) | `leadgen.coding_primary…project_best` (12 harness names); its 12 `OMNIROUTE_TASK_*` constants (`agent_os_routing.py:19-30`) have **0 consumers** | `CODE-PRESENT` |
| Combo ↔ email binding | **1:1** — 14 combos, 14 emails (`combo_distribution.yaml:78-92`) | `CODE-PRESENT` |
| The 14-vs-12 defect | `~/.openclaw/workspace/omniroute_config.json:12` `email_api_keys_created:12` vs `combo_target:14`; **no code reads that key** → 2 combos have no bound email key → quota unavailable → routes silently fall to fallback | `CODE-PRESENT` |
| Failover depth | `generate()` = **exactly 2 hops** (`omniroute_client.py:452-454`). The "14-step next-email combo" chain exists **only in docs/openclaw prose** — NOT implemented | `CODE-PRESENT` |
| Revenue contribution today | **₹0** — real `generate()` callers = dev_control, owner_os, voice-assist; `auto_outreach.py` imports **no LLM** (template-only). OmniRoute is a **cost/quality lane**, not a money rail | `CODE-PRESENT` |

**Revenue arithmetic cross-check (Archi, aligns with §2):** 5,00,000 / 1,999 = **251 Starter** (35.9/day);
/ 5,999 = **84 Advanced** (12.0/day); mixed avg ₹2,999 = **167** (23.9/day). Supply: 25/day warmup → 175
sends / 7d; reply **1–3% (ASSUMPTION)** → 2–5 replies → ~0.3–1.3 sales. **Verdict: NOT reachable; ceiling
≈ ₹10k–₹25k** (owner-network upside ₹30k–₹60k). **Matches §2d.**

**Gate order (Archi):** **UPI first, then voice.** UPI: pay-info returns `{"enabled":false}` without a VPA
(`public_site.py:1083`); guests never auto-activate (`upi_payments.py:61`). Voice: Smartflo DID→VOICE
destination (`telephony_smartflo.py:370`). Telegram = **NOT** a blocker.

**Full doc:** `deliverables/engineering-assurance/design-omniroute-revenue-ssot-2026-09-14.md` (Archi, task #2).

---

## 3. The two owner gates (nothing else blocks revenue)

All code paths are GO; **revenue is gated on two owner/console actions, not on code** (`PRODUCTION-PROVEN`).

### Gate 1 — Smartflo console: set the DID's VOICE Bot destination

- `GET /v1/my_number` returns DID **`+918069879757`** with **`destination: null`** (`PRODUCTION-PROVEN`).
- **No API can set this** — a POST attempt returns **422** (`PRODUCTION-PROVEN`). It is a **console** action.
- **Owner action:** in the Tata Smartflo console, set the DID → **VOICE Bot** destination.
- **Correction to the owner's belief:** inbound calls are **NOT** working. `destination: null` is
  **unchanged** from the 2026-09-12 root cause. CDR = 11 rows, all `probe`/`unknown`; no `smartflo`/`/stream`
  in the last 400 log lines. **"Inbound calls are arriving" is falsified.**

### Gate 2 — UPI collection via `/app/inbox` + owner bank confirmation

- Owner-authenticated `/app/inbox` Hot Queue session (**15–30 min**) → UPI Bind/Re-Approve → **bank credit
  confirmation**.
- `payment_verification_method = owner_confirmed_upi`. **Never** `PROVIDER_VERIFIED` — manual UPI is the
  **only** rail by owner decision. **Stripe and Razorpay are both REMOVED** (permanent).
- Technical money path = GO (`blocker_count=0`, `payments_ready=true`); `REVENUE GENERATED = WAIT`
  (owner-confirmed bank credit required). `ACTIVE_WORK.md` WS-GTM1 (`CODE-PRESENT`).

### NOT a revenue blocker

- **Telegram** — **observability only.** Prod already has `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` +
  `TELEGRAM_AUTO_PUBLISH`; `config/telegram/setup_spec.yaml` has 10 chat_ids. Missing is egress code +
  owner `api_id`/`api_hash`. **Do not list Telegram as a revenue blocker.**

---

## 4. SSOT ownership map — one truth per domain

One source of truth per domain; next to it, the **competing duplicates that must die**. This is the
answer to the owner's "single source of truth" requirement.

| Domain | THE source of truth | Label | Competing duplicates that must die |
|---|---|---|---|
| **Task truth** | `app/models/dev_task.py` (`DevTask`, Postgres) — atomic claim/lease/heartbeat/reconcile | `CODE-PRESENT` | `command_center/data/tasks.json` (44 tasks) + `CENTRAL_LEDGER.md` → demote to **read-only projection**; never a second truth |
| **Runtime truth** | `dev_workers` (`app/models/dev_worker.py`) + `DevTaskEvent` (`app/models/dev_task_event.py`) | `CODE-PRESENT` | `data/workforce_live_status.json` (**fabricated** telemetry; orchestrator gutted 2026-09-11) — must stay dead |
| **Roster truth** | `app/platform/team.py` → `STAFF` = **31 keys** (verified) | `CODE-PRESENT` | `docs/AGENT_REGISTRY.md` documents **19**, dated 2026-06-20 → **STALE**; must be **generated** from `team.py`, not hand-written |
| **Config truth** | `app/api/automation_flags.py` (417 flags) — **note:** the brief's path `app/platform/automation_flags.py` **does not exist** | `CODE-PRESENT` | `config/desktop_apps/registry.yaml` (0 bytes, no reader — deleted); future `data/coordination_hub/known_tools.json` (does not exist yet) |
| **Combo truth** | `leadsgen combo 1..14` (provider-side) — **ADR-190** (Archi) | `CODE-PRESENT` | `leadgen.coding_primary…project_best` (12 harness names, 0 consumers — **retire**); `config/desktop_apps/combo_distribution.yaml` (still 0 real code consumers) |
| **Money truth** | `data/invoices.jsonl` (GST ledger, prod-resident) via `app.billing.gst_invoice.stats()` | `PRODUCTION-PROVEN` | `data/revenue_attribution.jsonl` (not money); `data/upi_payments.json` (queue only) |
| **Owner alerts** | `app/utils/owner_feed.py` → `data/owner_feed_events.jsonl` | `CODE-PRESENT` | `progress.md` / `docs/SESSION_LOG.md` (append-only, not an alert feed) |

**Drift guard (recommended):** `scripts/ssot_drift_detector.py` + a `doc_truth_guard.py` CI check so a
doc that contradicts a code SSOT (e.g. `AGENT_REGISTRY.md` vs `team.py`) fails the build.

---

## 5. Maximum automation — honestly

The owner wants "maximum automation". Here is what that actually means today. **Do not write "31 agents
running."**

### 5a. The 31-agent verdict

| Question | Verdict | Evidence |
|---|---|---|
| Defined? | ✅ **31/31** | `app/platform/team.py` STAFF = 31 keys (`CODE-PRESENT`) |
| Armed? | 🟡 **partial** | 12 dispatchable / 19 non-dispatchable (`PHASE0_RECONCILIATION §2`); `PILOT_AGENTS` rollout held |
| **Proven-executing?** | ❌ **NO** | `dev_workers` = **0 rows**; heartbeat not instrumented; `service._IDEMPOTENCY` is a **process-local dict**, not a DB unique column |

**Why "proven-executing" is NO:** a fleet is only proven when a worker holds a DB-backed lease, emits a
heartbeat, and completes an idempotent task. None of that is populated. `task_execution_verified` cannot
honestly be `true` until the `dev_workers(lease_id, heartbeat_ts, idempotency_key UNIQUE)` instrumentation
exists.

### 5b. Automation status matrix

| Class | Meaning | Examples | Label |
|---|---|---|---|
| **Genuinely automated (proven)** | Runs on prod, observable output | Celery beat (64 tasks), voice stream (`vobiz_stream.py`), WhatsApp (cold OFF), email (25/day cap), prospector/CRM, billing/UPI truth, owner_feed | `PRODUCTION-PROVEN` |
| **Armed but unproven** | Flag ON, no execution evidence | 31-agent dispatch, DSH runtime, OmniRoute combos, 12-pilot rollout | `PARTIAL` |
| **Dead / must stay dead** | Removed or inert | `workforce_live_status.json` fake telemetry; `content_os.daily_video_run` duplicate producer; `config/desktop_apps/registry.yaml` | `STALE` |

### 5c. The one instrumentation gap blocking the 31-agent claim

- `dev_workers` = **0 rows** (`CODE-PRESENT`) — the table exists (migration `027_add_dev_workers.py`) but
  nothing registers.
- `service._IDEMPOTENCY` is **process-local** — a restart loses it; two workers can double-execute.
- `app/platform/coordination_hub_auth.py:23` `_KNOWN_TOOLS` = `("cursor","claude","monkeycode","opencode",
  "bolt","buzz","hermes")` — **omits `openclaw`, `workbuddy`, `codex`**. Those workers can never reach
  `buzzlock_enrolled: true` until this is edited — and **that edit is owner-gated** (trust boundary).

**Bottom line:** automation is *wired* (417/417 flags, 59/59 jobs dispatchable, 0 frontend wiring gaps) but
not *proven executing*. "Maximum automation" today = **wired and compliant**, not **running**.

---

## 6. Token-burn remediation (policy — owner explicitly asked)

The owner's other ask is token discipline. The cause is measurable and so is the fix.

### 6a. Verified cause

| Cause | Number | Impact |
|---|---|---|
| `AGENTS.md` == `CLAUDE.md` | **byte-identical**, 37,371 B each (same md5) | every turn pays for the same 37 KB **twice** |
| `progress.md` | **524,147 B** append-only | if read whole, ~130k tokens of history |
| `docs/SESSION_LOG.md` | **416,283 B** append-only | +~104k tokens if read whole |
| Stale handoffs | `docs/context/SESSION_HANDOFF.md` (local `33189b70`/prod `0b848b34` — **STALE**), `docs/context/ACTIVE_WORK.md` (prod `658fc20a` — **STALE**) | two files that lie, both re-read every session |
| `docs/PROJECT_HANDOFF.md` | 77,626 B | another whole-file read risk |

`progress.md` + `SESSION_LOG.md` alone ≈ **940 KB (~235k tokens)** of append-only history — that is the burn.

### 6b. The fix (concrete and enforceable)

1. **One per-turn context file:** `docs/context/STATE.md` (≤ **8 KB**). Overwritten each session, **never
   appended**. This is the only file an agent reads at turn start.
2. **Collapse the duplicate:** `AGENTS.md` is canonical; `CLAUDE.md` becomes a **1-line pointer**
   (`See AGENTS.md`) — no second copy. Halves the per-turn context tax immediately.
   ⚠️ **Coupling — this is a 2-file change, not 1:** the byte-identity is **test-enforced**
   (`tests/test_1000_engineers_skill.py:67` — *"AGENTS.md must stay a byte-copy of CLAUDE.md"*). Collapsing
   the duplicate must **retire that assertion in the same change**, or the token fix becomes a red CI lane.
   Owner sign-off item (touches agent bootstrapping).
   - **Blast radius of the test change:** `tests/test_1000_engineers_skill.py` also asserts the **startup
     protocol** is present — so the rewrite must **keep that coverage**, not merely delete the equality:
     assert the startup-protocol section exists in `AGENTS.md` **and** that `CLAUDE.md` points at it.
   - **Keep the filename:** other tooling reads `CLAUDE.md` **by name** (Claude Code, by convention). A
     **one-line pointer preserves that contract; a deletion does not** → recommend the pointer, not deletion.
3. **History moves to dated logs:** `progress.md` and `docs/SESSION_LOG.md` → **archive** to
   `docs/archive/2026-08/progress.md` and `docs/logs/2026-09-14.md`. New session notes append to
   `docs/logs/YYYY-MM-DD.md` (dated, never read at turn start). **Never read `progress.md` whole again.**
4. **Stale handoffs:** refresh `SESSION_HANDOFF.md` (≤ 4 KB) to real HEAD/prod SHAs; delete the stale
   `ACTIVE_WORK.md` snapshot into `STATE.md`.
5. **Budget rule:** per-turn context reads ≤ **16 KB total**. Any file > 16 KB must be opened with a
   targeted offset/Grep, never whole. A CI `doc_truth_guard.py` asserts `STATE.md` ≤ 8 KB and
   `SESSION_HANDOFF.md` ≤ 4 KB, and that `AGENTS.md`/`CLAUDE.md` are not duplicated.

> The **2-file truth rule** (adopted from the engineering-assurance audit, action #14): an agent's per-turn
> context is exactly **`docs/context/STATE.md` (≤8 KB) + `docs/context/SESSION_HANDOFF.md` (≤4 KB)**.
> Everything else is referenced by path, never pasted.

---

## 7. Compliance spine — never loosen

These invariants are **absolute**. No sprint target, no automation, no "maximum" authorises weakening them.
Green tests are **not** permission (`docs/AGENT_WORK_RULES.md` R8).

| Invariant | Rule | Label |
|---|---|---|
| **TRAI DND** | voice window **9am–7pm IST**; DND lookup fail ⇒ **block** (fail-CLOSED) | `PRODUCTION-PROVEN` |
| **Consent ledger** | every contact needs a consent record; no consent ⇒ no send/call | `PRODUCTION-PROVEN` |
| **DPDP** | data minimisation + lawful basis; billing respects consent | `PRODUCTION-PROVEN` |
| **Opt-out suppression** | unreadable opt-out store ⇒ treat **everyone** as suppressed (fail-CLOSED) | `TEST-PROVEN` |
| **Tenant isolation** | agents scoped by `client_id`; no cross-tenant reads | `PRODUCTION-PROVEN` |
| **`DND_FAIL_OPEN`** | **refused in production** — `_is_production()` gate | `PRODUCTION-PROVEN` |
| **Cold WhatsApp / platform_dial** | cold WA auto-send **OFF by design**; `platform_dial` gated | `PRODUCTION-PROVEN` |

**Do NOT re-raise the DND fail-open as live:** the production DND fail-open was **re-hardened
2026-09-14T10:48Z** (`PRODUCTION-PROVEN`); the container `compliance.py` md5 matches the VPS checkout and
git HEAD, `_is_production()` is present, and `DND_FAIL_OPEN` is absent from the container env. The P0 is
**retracted**.

---

## 8. Day-by-day execution (corrected)

The old day-by-day (§ superseded) is retained but **re-based on the two gates** — no day may begin with an
action that violates §7.

### Day 0 — Truth + repair (DONE)
Baseline (§1) established; blockers ranked; two owner gates identified (§3). The old "₹9,995" framing is
retired.

### Day 1 — Open the two gates (owner action; the only thing that unblocks revenue)
1. **Owner** sets Smartflo DID→VOICE Bot destination (§3 Gate 1). Verify `GET /v1/my_number` shows a
   non-null `destination`.
2. **Owner** runs the `/app/inbox` Hot Queue session + UPI re-approve + bank confirm (§3 Gate 2).
3. Verify the end-to-end money path with **zero synthetic revenue** (no fake payments).

### Day 2 — Lead quality + conversion
Activate `GSC_ENABLED=1` (creds present); refine ICP scoring; personalise outreach; prepare upsell for the
existing customer(s). Success = personalised tokens visible, ≥1 trial nudge sent to a **real** target.

### Day 3 — Channel scale (proven-safe only)
Scale **only** channels with stable conversion and **no** compliance violations. Respect 25/day email cap
and `PLATFORM_DIAL_LIMIT`. Cold WA stays OFF.

### Day 4 — Conversion optimisation
Analyse funnel drop-offs (lead→qualified→contacted→reply→opportunity→paid); run one controlled change via
the existing flag infra; measure.

### Day 5 — Reactivation + upsell
Reactivate dormant leads, resume stalled Hot Queue conversations, upsell the paying base. Track
reactivation vs upsell revenue separately.

### Day 6 — Scale winners
Increase volume only in segments with verified positive economics; monitor saturation; keep all §7 gates.

### Day 7 — Close + collect
Follow up hot leads / open offers / pending UPI; clear onboarding blockers; push renewal/upsell. Final KPI =
**actual collected revenue** verified via `data/invoices.jsonl` (§1).

---

## 9. Execution principles

- **Production evidence > assumptions > chat claims.** Never fabricate numbers. Label every non-obvious claim.
- **Two gates, then revenue.** No code change opens the money path; only §3 does.
- **One fix, zero regressions.** Targeted regression tests before/after.
- **Owner-gated actions** (manual UPI confirm, `_KNOWN_TOOLS` edit, deploy, irreversible actions) require
  explicit owner approval.
- **Compliance first (§7).** Any action that would weaken a gate is **ABORT**, not a fix.
- **Token budget (§6).** One per-turn context file; never read append-only history whole.
- **Measure everything.** Track leads, outreach, replies, conversions, revenue, CAC — with labels.

---

**Superseded-as-authority:** `DAY_0_REVENUE_BASELINE.md` · `REVENUE_BLOCKERS.md` ·
`docs/REVENUE_SPRINT_AUTOPILOT.md` · `automation-fix-overview.md`.
**Companion:** `deliverables/engineering-assurance/tech-debt-blueprint-context-2026-09-14.md` (why this file
won, what changed, which docs were marked superseded).
