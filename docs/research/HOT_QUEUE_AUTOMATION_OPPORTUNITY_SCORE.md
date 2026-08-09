# HOT QUEUE AUTOMATION OPPORTUNITY SCORE (WS-GTM1 → 2nd paid)

> Analysis-only run of `.claude/skills/automation-opportunity-discovery` · 2026-08-09 continuation
> Sources: current `origin/main` (`cad958ce`) via git grep / git archive — code, scheduler wiring, tests, context docs.
> Evidence labels: CODE-PRESENT · TEST-PROVEN · RUNTIME-PROVEN · OUTCOME-PROVEN · UNKNOWN · PARTIAL
> **No runtime change, no fake rows, no flag flip.** Constraint/demand state = owner-gated data (prod DB not queried — not authorized).

## 1. Constraint

Chain: outreach/inquiry → qualification → Hot Queue card → owner review → human outreach → interested → UPI → owner-confirmed → activation → 2nd paying customer.

Evidence (origin/main context):
- ACTIVE_WORK WS-GTM1: **"HQ empty; owner prospect pick"** · next exact action = **real ₹1999 UPI → LEDGER_PAID** · out of scope = fake PAID.
- Sales autopilot LIVE real email (`SALES_AUTOPILOT_ENABLED=1 · DRY_RUN=0 · EMAIL=1 · REFILL=1 · REFILL_CAP=25 · REFILL_MIN_SCORE=0`); cold WA OFF. Manual refill 2026-08-03 upserted 25 `new` prospects.
- Cold email outreach LIVE (2026-08-02: 19 sent + 20 follow-ups). Calling LIVE (`PLATFORM_DIAL_DAILY=1`, `PLATFORM_DIAL_LIMIT=100`).
- 1 real paying customer (jiya makeover, INV/2026-27/0001, MRR ₹1,999).

**Constraint verdict: `OWNER ACTION` (human gate) — qualified prospects entering Hot Queue, upstream of it real inquiries.** Empty queue alone proves nothing; ACTIVE_WORK explicitly names the owner prospect pick as the pending step, and the whole qualification→card→pick chain sits behind owner/consent gates (cold outbound compliance, manual-UPI canonical). Missing automation is NOT the constraint: every mid-funnel primitive exists and is wired (below). Secondary signal (not proven, needs store inspection): `REFILL_MIN_SCORE=0` may push unqualified prospects — flag for owner, not a build.

## 2. Existing Capability Map (origin/main, source-verified)

| Component | Entrypoint (origin/main) | Evidence |
|---|---|---|
| `/app/inbox` (Hot Queue UI) | `app/main.py:1437` route; Owner OS href `owner_os.py:1694` | CODE-PRESENT · TEST-PROVEN (12 hot_queue test files) · runtime state UNKNOWN (HQ empty per context) |
| `reply_agent.hot_queue` / `reply_hot_queue` API | 18 files match `hot_queue`; 1 for `reply_hot_queue` | CODE-PRESENT · TEST-PROVEN |
| `inquiry_hq_bridge` | 3 files | CODE-PRESENT · TEST-PROVEN (1 test file) · inbound inquiry evidence PARTIAL |
| `reply_triage` | 11 files + wired: `scheduler_config.py:45`, `team_scheduler.py` dispatch + `_last_ran`, `staff_jobs.py:115` | CODE-PRESENT · TEST-PROVEN (4 files) · RUNTIME-PROVEN (reply auto-send effective True via Redis runtime flag — CLAUDE.md ops facts, 2026-08-04 probe) |
| `speed_to_lead` | 12 files; manager summary in `team_scheduler.py:747-754` | CODE-PRESENT · TEST-PROVEN (7 files) |
| `hot_queue_brief` (HOT_QUEUE_BRIEF_DAILY) | `scheduler_config.py:184` (daily 08:15, health-gated), `team_scheduler.py:1581` `_last_ran`, `staff_jobs.py:119` | CODE-PRESENT · TEST-PROVEN (3 files) · runtime PARTIAL |
| `hot_wa_draft` (warm draft-only) | 4 files | CODE-PRESENT · TEST-PROVEN (2 files) — cold WA OFF invariant intact |
| `sales_autopilot` | 33 files | CODE-PRESENT · TEST-PROVEN (22 files) · RUNTIME-PROVEN (LIVE real email, refill 25, 2026-08-02/03) |
| Human Done/Park/one-click reply paths | part of reply_triage module | CODE-PRESENT (not separately re-probed) |
| Owner alerts / Boss-Owner OS | `ops_alerts.py:212` (stuck >24h + warm 40-69), `owner_os.py:1694` | CODE-PRESENT |
| Manual UPI confirm → activation | `admin_ops.py:1114 upi_activate`, `upi_payments.py:109`, `billing.py:1036 _activate_subscription_row`; invariants: `sales_autopilot_admin.py` "Never marks paid without proof", `subscription.py` "must NEVER fake a gateway success" | CODE-PRESENT · TEST-PROVEN (billing-truth tests) · OUTCOME-PROVEN (1 paid customer, repo truth) |

Note: `LEDGER_PAID` is owner/context shorthand — no such literal in `app/`/`revenue_pipeline/`/`tests/`.

## 3. Manual Workflow Map

| Step | Owner | Data source | Existing automation | Human gate | Failure mode | Evidence | Revenue distance |
|---|---|---|---|---|---|---|---|
| Prospect/inquiry enters | autopilot/owner | sales_autopilot store / inquiries | autopilot refill (real email) | consent/DLT | low-score prospects (REFILL_MIN_SCORE=0) | RUNTIME-PROVEN (refill 25) | 5 steps |
| Qualification | owner (via triage) | reply_triage | reply_triage auto | warm-score threshold | HQ stays empty (current) | CODE-PRESENT | 4 steps |
| Hot Queue card | system/owner | hot_queue | bridge + API | — | no qualified rows | CODE-PRESENT, HQ empty | 4 steps |
| Owner review/pick | **OWNER** | `/app/inbox` | daily brief + alerts | **owner pick** | **no pick (current constraint)** | context: "owner prospect pick" | 3 steps |
| Human outreach | owner | HQ card | draft-only prep (hot_wa_draft) | one-click send | cold-send risk | draft-only safe | 3 steps |
| Interested response | prospect | reply triage | triage + speed-to-lead alert | — | missed follow-up | RUNTIME-PROVEN (auto-send) | 2 steps |
| UPI instructions | system | pricing/start | canonical UPI resolver (PR #236) | — | payment not made | CODE-PRESENT | 1 step |
| Owner-confirmed payment | **OWNER** | bank credit | manual UPI confirm (`upi_activate`) | **owner confirm** | fake-payment forbidden | OUTCOME-PROVEN (1 customer) | 0 steps → revenue |
| Activation | system | billing | `_activate_subscription_row` | owner approve | activation drift | CODE-PRESENT | 0 steps |

## 4. Opportunity Score

Axes 1–10. **Direction explicit:** Frequency, Revenue impact, Owner-time saved = higher-better (10 = best). Effort, Risk = lower-better (10 = worst) → denominator.
**Composite = (Frequency × Revenue impact × Owner-time saved) ÷ (Effort + Risk)**, normalized ÷ set max (max = 1.0) before ranking.

| Candidate | Freq | Rev | Owner-time | Effort | Risk | Raw | Norm |
|---|---|---|---|---|---|---|---|
| Speed-to-lead owner alert | 7 | 7 | 5 | 1 | 1 | 122.5 | 1.00 — **EXISTS** (operate) |
| Warm-reply prioritisation | 9 | 7 | 5 | 1 | 2 | 105.0 | 0.86 — **EXISTS** (operate) |
| Hot Queue daily brief | 10 | 6 | 6 | 1 | 1 | 90.0 | 0.73 — **EXISTS** (operate) |
| Draft-only follow-up prep (hot_wa_draft) | 8 | 6 | 5 | 1 | 2 | 80.0 | 0.65 — **EXISTS** (operate) |
| Stale-card chase alert | 5 | 5 | 4 | 1 | 1 | 50.0 | 0.41 — **EXISTS** (operate) |
| Owner prospect-pick prep (brief extension) | 8 | 7 | 5 | 6 | 2 | 35.0 | 0.29 |
| Payment-close checklist | 3 | 10 | 4 | 4 | 3 | 17.1 | 0.14 |
| Qualified-prospect refill (score-gated) | 5 | 6 | 4 | 5 | 3 | 15.0 | 0.12 |
| Post-payment activation verification | 3 | 8 | 3 | 3 | 2 | 14.4 | 0.12 |

Reading: har high-frequency revenue-adjacent candidate ALREADY exists and is wired. Jo candidates missing hain wo low-frequency hain (payment-close, activation verify) — ye bottleneck nahi hain jab tak HQ empty hai. Ek low-risk vanity task kisi revenue-distance step ko outrank nahi karta — ranking me revenue-distance step hi top pe hain (aur wo already live hain).

## 5. Decision

**`OWNER ACTION`** — current constraint owner prospect selection + real inquiry → ₹1,999 UPI → owner-confirmed activation hai, missing automation nahi. "Build another automation" ka answer nahi. (Any file-level extension like prospect-pick shortlist in the daily brief would land on WS-GTM1-owned files → `WAIT — OVERLAPPING WRITER`.)

## 6. Proposed Vertical Slice

None this run — decision is OWNER ACTION. Proposal-only (owner asked kabhi): extend `office_briefing.run_scheduled()` with a "top-5 scored store prospects for owner pick" section — **WAIT — OVERLAPPING WRITER** (WS-GTM1 owns Hot Queue workstream). If authorized: typed flag `HQ_PICK_SHORTLIST` OFF default (inert), idempotent daily render (day-key), no sends (draft-only), retry via scheduler `_last_ran` pattern, metrics = brief render + pick count, admin visibility = `/app/inbox` + Aaj tab, success = owner picks ≥1 prospect → HQ card, canary = 1 client, kill = no pick in 2 weeks → flag OFF, rollback = flag OFF + recreate, owner boundary = pick + UPI confirm remain human.

## 7. Success Metric (revenue-distance, primary)

1. Qualified Hot Queue cards (count + score distribution)
2. Owner action latency (prospect pick → outreach)
3. Interested → UPI conversion
4. UPI → owner-confirmed activation
5. **Real second paying customer (₹1,999, LEDGER_PAID)**

Supporting signals only (kabhi primary nahi): "job ran", "draft created", "email sent", "queue empty", "/health 200", "prod_check 0 gaps".

## Evidence-bucket summary

Skill routing TEST-PROVEN · Code wiring CODE-PRESENT · Scheduled execution PARTIAL (wired, not re-probed) · Runtime success PARTIAL (context-probed 2026-08-02/03/04/09) · Customer outcome PARTIAL (1 paid PRODUCTION-PROVEN) · Revenue outcome NOT PROVEN (2nd) · Owner authorization PENDING.
