# ADR-193: OmniRoute provider-health rotation

**File:** `deliverables/engineering-assurance/adr-omniroute-provider-health-2026-09-14.md`
**Author:** Archi (阿奇) · System Architect · Engineering Assurance Team
**Date:** 2026-09-14 · **Base:** git HEAD `20e4180b` · **Status:** Proposed
**Task:** #8 — OmniRoute provider-health rotation ADR (supersedes the shutdown request)
**Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

> **Scope note:** this ADR is **design only**. No application code was modified. The gateway
> (`leadgen_omniroute`, `http://127.0.0.1:20128`) is **local-only and non-essential** (ADR-111 / ADR-189);
> every recommendation below keeps it **fail-open** and never makes the app depend on it.

---

## 需求与目标 (Requirements & Goals)

### 1.1 The observed problem
Live-verified by team-lead on 2026-09-14 against the owner's gateway (`PRODUCTION-PROVEN`):

| Observation | Value |
|---|---|
| Combos | 14 × `leadsgen combo 1..14`, 42 model slots each (588 total) |
| Connections | **294** = 14 email accounts × 21 providers; all `isActive: true` |
| `testStatus` | **70 active / 224 expired** |
| Providers with ≥1 working credential | **5 / 21** — `nvidia`, `auggie`, `aug`, `xiaomi`, `opencode` |
| Providers 0/14 working | **16** — `opencode-zen`, `huggingface`, `sensetime`, `baidu`, `alibaba`, `volcengine`, `tencent`, `ppio`, `siliconflow`, `moonshotai`, `minimax`, `deepseek`, `google`, `z-ai`, `thinkingmachines`, `qwen` |
| E2E | `POST /v1/responses {"model":"leadsgen combo 1"}` → **HTTP 200**, resolved `nvidia/nemotron-3-super-120b-a12b`, **25.6 s**; combos 13 & 14 → 200, **same** resolved model, 19–26 s |

**Structure is correct and works. Rotation is the defect:** it burns attempts on 16 dead providers before
landing on `nvidia`.

### 1.2 Derived findings (this session)
- **D-1 — the 70/224 split is exactly per-provider, all-or-nothing.** 70 = **5 × 14** and 224 = **16 × 14**
  (`CODE-PRESENT` arithmetic on the lead's probe). So *every* combo has the *same* 5 working providers and the
  *same* 16 dead ones. **Degradation is uniform across combos — no combo is individually dead.** This
  single fact decides Q2 below.
- **D-2 — single-model concentration risk.** Combos 1, 13 and 14 all resolve to the *same* model
  (`nvidia/nemotron-3-super-120b-a12b`). Effective diversity today is **1 model**, not 588 slots. If the
  `nvidia` free tier expires, the entire lane dies at once.
- ~~**D-3 — the seed hardcodes `isActive: True`.** … Re-seeding re-marks dead connections as active — so the
  224-expired state will **regenerate itself** after any re-seed unless this is fixed.~~

  > ### 🔴 D-3 RETRACTED (2026-09-15, verified by lead)
  >
  > **This claim is false.** The `"isActive": True` at `scripts/seed_omniroute_14combos.py:253` is a field on
  > the **combo** payload written to the `combos` table — it is **not** a provider connection.
  >
  > The script issues exactly **two** SQL statements, both verified by grepping every `INSERT INTO` /
  > `UPDATE` in the file:
  > - `INSERT INTO combos (…)` — `:262` and `:278` (aliases)
  > - `UPDATE api_keys SET allowed_combos = …` — `:290`
  >
  > It **never writes to any provider-connection table**, never touches `testStatus`, and has no
  > `connections` reference at all. Therefore re-seeding **cannot** regenerate, repair, or influence the
  > 224-expired credential state in any direction.
  >
  > `isActive: True` on the combos is in fact **correct and PROVEN**: all 14 combos return HTTP 200
  > (14/14, two independent runs, 2026-09-14/15). Combos are active; it is the underlying *credentials* that
  > are expired — and those live in a different table this script does not touch.
  >
  > **Action A3 below is withdrawn** — there is no landmine to fix here. The provider-expiry remediation
  > stays where it belongs: the gateway (A2/§5 of the runbook), not this seeder.
- **D-4 — gateway retry config inflates latency.** The seeded combo config sets `maxRetries: 3` and
  `retryDelayMs: 1000` (`scripts/seed_omniroute_14combos.py:241-242`). Walking 16 dead providers with 3
  retries × 1 s delay each is a sufficient explanation for 19–26 s p50.
- **D-5 — the app timeout is dangerously tight.** `_timeout_seconds()` defaults to
  `OMNIROUTE_TIMEOUT_SECONDS=30`, clamped 1..90 (`app/platform/omniroute_client.py:371-377`). Against a
  **25.6 s p50**, 30 s leaves ~1.2× headroom: any tail >30 s burns the **first** hop, then the 2-hop ladder
  costs up to another 30 s → worst case ≈ 60 s.
- **D-6 — voice is already 100 % fail-open today.** `leadgen.swara_live` runs with
  `first_token_timeout_s()` = **3.0 s** default (clamp 0.5–15) and `stream_total_timeout_s()` = **10.0 s**
  (clamp 2–30) (`app/voice_agent/omniroute_voice.py:92-101`). The voice breaker trips after **2**
  consecutive failures and quarantines the gateway for **120 s** (`:115-123`). At 19–26 s, **every** voice
  attempt misses first-token → 2 fails → breaker OPEN → voice routes to `free_ai`. So `swara_live` buys
  nothing today and only costs latency risk. The breaker comment records the original injury:
  *"measured 9-14s of dead air on a live call"* (`:106-111`).
- **D-7 — a combo-level prober already exists.** `scripts/omniroute_combo_watchdog.py` (wrapper) →
  `docs/openclaw/scripts/omniroute_combo_watchdog.py` probes each combo through the same `/v1/responses`
  path and persists consecutive-failure counters to `data/omniroute_combo_state.json`; the read side is
  `app/platform/omniroute_combo_health.py` (OCC module 5). That module's docstring states the rule this ADR
  adopts: *"Re-probing here would have created a second, competing truth"* (`:12-16`).
- **D-8 — no app code reads `/api/providers`.** Grep across the repo: only `scripts/update_combos_42.py:82`
  reads `/api/combos`; `scripts/omniroute_combo_distributor.py:55` references a **filesystem**
  `.omniroute-cutover/providers.json`. There is no existing consumer of the live provider-health endpoint.
- **D-9 — only 3 of 12 routes are actually called.** Live callers of `generate()`:
  `app/dev_control/governed_omniroute.py:14` (`leadgen.coding_primary`), `app/platform/owner_os.py:1958,2014`
  (`leadgen.agent_ops`), `app/voice_agent/omniroute_voice.py` (`leadgen.swara_live`). The other 9 routes are
  defined but uncalled, matching the earlier finding that the `OMNIROUTE_TASK_*` constants have 0 consumers.

### 1.3 Constraints (non-negotiable)
- **C1** Never weaken a compliance gate (TRAI DND, consent ledger, DPDP, opt-out suppression, tenant
  isolation). **This ADR touches none of them** — OmniRoute carries only `INTERNAL_SANITIZED` /
  `CUSTOMER_MASKED` dev/voice- assist traffic and `get_task_route()` hard-rejects customer/payment/
  compliance work (`app/platform/omniroute_client.py:352-364`).
- **C2** OmniRoute stays **fail-open and non-essential** (ADR-111 / ADR-189). The 24×7 path remains
  `app/voice_agent/free_ai.py` with its escalating 429 breaker (60 s → cap 30 min,
  `free_ai.py:264-266,332`).
- **C3** **Free-tier only** — owner mandate. No paid providers.
- **C4** Do not modify application code in this ADR's delivery.

---

## 高层设计 (High-Level Design)

### 2.1 The rotation boundary — who owns what

```
┌─────────────────────────────────────────────────────────────┐
│ GATEWAY  (owns provider rotation — 42 slots, 21 providers)   │
│   • walk slots in health order                               │
│   • skip testStatus != active                                │
│   • maxRetries / retryDelayMs tuning                          │
│   exposes: /api/combos, /api/providers  (diagnostic only)    │
└───────────────────────┬─────────────────────────────────────┘
                        │  ONE abstraction: "leadsgen combo N"
┌───────────────────────▼─────────────────────────────────────┐
│ APP  (owns combo selection + fail-open — NOT provider health)│
│   omniroute_client.generate(): 2 hops (primary → fallback)   │
│   watchdog → combo_state.json → OCC module 5 (read-only)     │
│   swara_live: 3 s first-token + breaker → free_ai            │
└─────────────────────────────────────────────────────────────┘
```

**The combo is the contract.** The gateway promises "ask for `leadsgen combo N`, get an answer." If the app
must inspect which of a combo's 21 providers are alive, that contract is broken.

---

## 关键决策记录 (Decisions)

### D1 — Disable vs re-auth vs health-aware composition

| Option | Effort | Cost | Capacity gain | Latency gain | Durability |
|---|---|---|---|---|---|
| **(a) Disable the 16 dead providers** | Hours (gateway config) | **₹0** | none (already 5) | **large** (removes ~16 wasted hops) | regresses if a provider expires |
| **(b) Re-auth all 16** | **224 credentials** of manual work | **₹0 cash, very high labour** | 5 → 21 providers | medium | regresses on next expiry |
| **(c) Health-aware rotation** | Days (gateway feature) | ₹0 | none | medium | **permanent** |

**Recommendation: (a) now → (c) next → (b) selectively, and only if the owner wants provider diversity.**

Reasoning:
1. **(a) is the only zero-cost, zero-code lever with a large, immediate win.** It removes 16/21 of the search
   space. Capacity is unchanged (it is *already* 5 providers) so there is **no downside** — disabling a
   provider with 0/14 working credentials cannot lose a single successful call.
2. **(b) is the wrong primary bet.** 224 credentials is not a task, it is a project — and several of the 16
   (`volcengine`, `alibaba`, `baidu`, `tencent`, `moonshotai`, `qwen`, `z-ai`, `minimax`, `deepseek`,
   `siliconflow`, `sensetime`) typically require local phone/payment verification. **Nuance that changes the
   economics:** re-auth scales **per provider, not per connection** — 1 provider = 14 credentials
   (1 per email account). So it is *graded*, not all-or-nothing: re-authing 2 providers ≈ 28 credentials.
   Still cheap to defer.
3. **(c) is the durable fix** and is what prevents this ADR from being needed again in a month. Without it,
   every future expiry silently recreates the 19–26 s behaviour.
4. **Free-tier-only (C3) is satisfied by all three** — none introduces a paid provider.

**Do not do (b) across all 16.** If diversity is wanted, do it for **2–3** providers (see D2 risk below),
purely to break the single-model concentration — not to restore 21.

### D2 — Should the app read `/api/providers` and skip dead combos?

**Recommendation: NO. Provider rotation is the gateway's job. The app must not read provider health.**

Five arguments, in order of weight:

1. **It cannot help — the failure is uniform (D-1).** 70 = 5×14 and 224 = 16×14 means *every* combo has the
   same 5 working providers. There is no "dead combo" to skip. App-side combo skipping would **remove
   capacity and improve nothing.**
2. **It breaks the abstraction.** The app would need to maintain a 21-provider × 14-combo health map in
   code. Every gateway config change becomes an app change — exactly the coupling ADR-190 exists to eliminate.
3. **It creates a second, competing truth.** `omniroute_combo_health.py:12-16` already forbids this pattern,
   and a **combo-level prober already exists** (`scripts/omniroute_combo_watchdog.py` → 
   `data/omniroute_combo_state.json`, surfaced by OCC module 5). The correct app posture is **consume the
   existing watchdog**, never add a second probe.
4. **It adds a failure mode to a lane that must stay fail-open (C2).** A health fetch that hangs or 500s would
   degrade a *non-essential optimization lane* into a source of app latency. The current design already
   degrades correctly: bad gateway → `generate()` returns `None` → caller uses its own fallback
   (`omniroute_client.py:413-439`); voice → breaker → `free_ai`.
5. **There is no precedent for it** (D-8) — no app code reads `/api/providers` today; adding the first
   consumer is a new dependency, not a completion.

**What the app SHOULD do differently (all small, all non-invasive):**
- **A1 — Raise the async timeout.** `OMNIROUTE_TIMEOUT_SECONDS` 30 → **60** (clamp allows ≤90). Env-only,
  no code. Removes first-hop timeouts at current p50 (D-5).
- **A2 — Feed the existing watchdog into ops, not into the request path.** Surface
  `data/omniroute_combo_state.json` (already produced) in the owner brief / OCC. Read-only, zero risk.
- ~~**A3 — Fix the seed** so re-seeding cannot re-mark dead connections active (D-3)…~~
  **WITHDRAWN (2026-09-15)** — D-3 was false; see the retraction above. `seed_omniroute_14combos.py` only
  writes `combos` and `api_keys.allowed_combos`, so there is nothing to fix. **Do not "fix" `:253`.**
- **A4 — Gate `leadgen.swara_live` off** (see D3).

### D3 — Is 19–26 s acceptable? Which task types must leave OmniRoute?

**Answer: acceptable for async/offline work, categorically unacceptable for voice.**

| Task type | Live caller? | Latency budget | 19–26 s verdict |
|---|---|---|---|
| `leadgen.swara_live` | ✅ voice | **3.0 s first-token / 10 s total** (`omniroute_voice.py:92-101`) | ❌ **REMOVE** — 2–8× over budget; already 100 % fail-open (D-6) |
| `leadgen.coding_primary` | ✅ dev_control | offline batch | ✅ keep, with A1 (60 s) |
| `leadgen.agent_ops` | ✅ owner_os | offline batch | ✅ keep, with A1 (60 s) |
| `coding_fast`, `repo_analysis`, `test_generation`, `marketing_content`, `prospect_enrich`, `outreach_email`, `seo_keyword`, `governor_review`, `project_best` | ❌ none (D-9) | offline batch | ⛔ **do not enable** until p50 < ~8 s |

**Decisions:**
- **Remove `leadgen.swara_live` from OmniRoute routing.** Voice has a 3 s first-token budget; 19–26 s is an
  order of magnitude wrong. Because the breaker already routes 100 % of voice traffic to `free_ai` (D-6),
  this is a **pure win with zero functional loss** — it removes wasted 3 s waits and breaker churn. If it is
  ever re-enabled, the gate must be: measured p50 **< 1.5 s first-token**.
- **Keep `coding_primary` + `agent_ops`** (the only live non-voice routes) with the timeout raised to 60 s.
- **Do not enable the remaining 9 routes** — they have no callers today, so enabling them would add risk for
  no benefit. Revisit only after D1(a)+(c) land.
- **Naming defect to log:** `leadgen.coding_fast` promises speed it cannot deliver at 19–26 s. Rename or
  delete; do not let the name imply a latency SLO.

### D4 — Ordered remediation plan

| # | Step | Owner | Effort | Expected improvement |
|---|---|---|---|---|
| **1** | **Disable the 16 dead providers** in the gateway (`isActive: false` / drop connections) — 0/14 working, so no successful call can be lost | Gateway config | Hours, ₹0 | p50 **25.6 s → ~5–8 s** (ASSUMPTION: ~1 s saved per dead hop incl. 1 s retry delay); removes the >30 s tail that currently threatens the app's 30 s timeout |
| **2** | **Raise `OMNIROUTE_TIMEOUT_SECONDS` 30 → 60** (async lanes) | Env only | Minutes, ₹0 | Eliminates first-hop timeouts; 2-hop worst case ≈ 120 s, acceptable offline |
| **3** | **Turn OFF `leadgen.swara_live`** | Env/route gate | Minutes, ₹0 | Removes 100 % of voice dead-air risk; **zero functional loss** (already fail-open) |
| **4** | **Reduce gateway `retryDelayMs` 1000 → 250** (seed `:242`) and cap `maxRetries` for dead-provider walking | Gateway config | Hours, ₹0 | Further p50 reduction; faster dead-slot abandonment |
| **5** | **Make rotation health-aware (c)**: order slots by last-known-good, skip `testStatus != active` | Gateway feature | Days, ₹0 | **Permanent fix.** Prevents the 224-expired regression from ever recurring |
| **6** | **Fix `isActive: True` hardcode** (`:253`) + add a reconcile check asserting `working_providers >= 1` | Script + CI | Hours, ₹0 | Stops re-seeds from resurrecting dead connections (D-3) |
| **7** | **Optional — re-auth 2–3 providers only** (graded: 14 credentials each) to break single-model concentration | **Owner** | Days, labour | Diversity 1 model → 3–4; protects against `nvidia` free-tier expiry (D-2) |

**Steps 1–4 are the 7-day win: all zero-cost, no code, and together should take p50 from ~25 s to ~4–8 s.**
Steps 5–6 make it durable. Step 7 is an owner-funded backlog item, **not** required for correctness.

---

## 可运维性 (Operability)

- **Keep it fail-open.** Every step above is a config/removal; none adds a dependency. If the gateway is
  down, `generate()` returns `None` (`omniroute_client.py:413-439`) and callers use their existing fallback;
  voice uses `free_ai` (`free_ai.py:264-266`).
- **Observability:** consume the **existing** watchdog output (`data/omniroute_combo_state.json`) via
  `omniroute_combo_health.py` / OCC module 5. Add an alert when `working_providers < 3` — that is the
  single number that predicts this incident.
- **Port truth:** `20128` = OmniRoute (`leadgen_omniroute`); `18789` = OpenClaw tray (not OmniRoute).
- **Runbook after step 1:** re-probe `POST /v1/responses {"model":"leadsgen combo 1"}`; expect ≤8 s and a
  200. Re-probe combos 13/14. Record p50 before/after so step 1's ASSUMPTION becomes `TEST-PROVEN`.
- **Concentration watch:** today all combos resolve to one model (D-2). Any alert on "all traffic to a single
  provider" should be treated as a capacity emergency, not a curiosity.

---

## 测试策略 (Testing Strategy)

| Area | Test | Type | Priority |
|---|---|---|---|
| Rotation improvement | Re-probe combos 1/13/14 after step 1; assert 200 + p50 ≤ 8 s | Manual/CI probe | **P1** |
| Voice fail-open | With `swara_live` off, voice turns still succeed via `free_ai`; no dead air | Regression | **P0** |
| Voice breaker | 2 consecutive timeouts still open the breaker for 120 s and recover half-open | Unit (existing) | P1 |
| Timeout clamp | `_timeout_seconds()` respects 1..90 clamp; `OMNIROUTE_TIMEOUT_SECONDS=60` honoured | Unit | P2 |
| Seed integrity | Re-seed must NOT mark unverified connections `isActive` (fixes D-3) | Unit/CI | P2 |
| Provider reconcile | CI check: `working_providers >= 1`, else fail | CI | P2 |
| Compliance | PII masking + `get_task_route()` still rejects customer/payment/compliance task types | Unit (existing) | **P0** |

**P0 tests are compliance/availability gates — they must never be weakened to land this ADR.**

---

## 文档结构 (Documentation Structure)

```
deliverables/engineering-assurance/
├── design-omniroute-revenue-ssot-2026-09-14.md   ← ADR-190/191/192 (combo identity, task SSOT, deploy authority)
└── adr-omniroute-provider-health-2026-09-14.md   ← THIS ADR-193
docs/adr/
└── ADR-193-omniroute-provider-health-rotation.md ← extract on acceptance (193 = next free after 192)
```
- Supersedes nothing; complements ADR-190 (`leadsgen combo 1..14` is canonical — this ADR assumes it).
- The 5-working-provider list in §1.1 is a **point-in-time snapshot**; the durable number to track is
  `working_providers`, published by the watchdog.

---

## 风险与权衡 (Risks & Tradeoffs)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Single-model concentration** (D-2) — all combos → `nvidia/nemotron`; one expiry kills the lane | **High** | High | Alert on provider concentration; do step 7 for 2–3 providers; keep `free_ai` as the real 24×7 path |
| Disabling 16 providers reduces *headline* slot count 588 → ~140 | Certain | Low | Cosmetic only — those slots were already returning errors; no successful call is lost |
| Step 1's latency estimate (~5–8 s) is an **ASSUMPTION** | Medium | Medium | Measure before/after and relabel as `TEST-PROVEN`; do not report the estimate as fact |
| Re-seed resurrects dead connections (D-3) | High | Medium | Step 6 (fix `:253` + reconcile check) before any re-seed |
| Health-aware rotation (step 5) is a gateway feature we may not control | Medium | Medium | Steps 1–4 deliver most of the win without it; step 5 is durability, not the win |
| Someone re-enables `swara_live` for "free capacity" | Medium | **High** (customer-facing dead air) | Hard gate: re-enable only at measured p50 < 1.5 s first-token; document in OCC |
| Re-auth creep (224 creds) | Medium | Low | Explicitly scoped to 2–3 providers (≈28–42 creds), owner-funded, backlog |

**Tradeoff accepted:** we trade *nominal* capacity (21 providers on paper) for *actual* latency and
predictability. The 16 dead providers were never capacity — they were a latency tax.

---

## Appendix — Decisions at a glance

1. **(a) Disable the 16 dead providers** → then **(c) health-aware rotation** → re-auth **(b)** only 2–3
   providers if diversity is wanted. Reject full re-auth (224 creds).
2. **The gateway owns provider rotation; the app must NOT read `/api/providers`.** Degradation is uniform
   (70 = 5×14), so app-side combo skipping has zero benefit. Consume the existing watchdog instead.
3. **19–26 s: remove `leadgen.swara_live`** (3 s first-token budget, already 100 % fail-open). Keep
   `coding_primary` + `agent_ops` with `OMNIROUTE_TIMEOUT_SECONDS=60`. Do not enable the other 9 routes.
4. **Top 3 ordered steps:** (1) disable the 16 dead providers, (2) raise `OMNIROUTE_TIMEOUT_SECONDS` to 60,
   (3) switch off `leadgen.swara_live` — all zero-cost, no code, targeting p50 ~25 s → ~4–8 s.
