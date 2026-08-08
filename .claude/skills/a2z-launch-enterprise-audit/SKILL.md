---
name: a2z-launch-enterprise-audit
description: LeadGen "A-to-Z Launch & Enterprise Audit" master prompt — does NOT stop at audit. Drives Discover → Verify → Fix safe local gaps → Test → Browser proof → Final verdict. Scores Marketing product and standalone Voice product separately, and returns three verdicts (Business Launch Ready, Production Ready, Enterprise Ready /120). Use jab full end-to-end launch+enterprise readiness certification chahiye (investor/big-customer due-diligence, go-live gate, quarterly deep-review). Invoke context-first FIRST.
---

# A-to-Z Launch & Enterprise Audit (execute-not-just-audit)

> **Yeh prompt AUDIT pe rukta NAHI.** Loop Engineer mode: **inspect → plan → implement (safe local fixes) → test → browser-verify → record → verdict.** "Done" sirf evidence pe. Ye `production-ready` (launch gate) + `enterprise-readiness-audit` (12-domain /120) ko ek executable flow me joda hai, PLUS real browser proof + safe-fix loop. Pehle `context-first` Read karo, phir yeh.
>
> **Reply style:** Hinglish Roman, concise. **Har reply ke END me akeli line `🐦 pelican`** (context-drift canary).

---

## 0. HARD ASSUMPTIONS (NEVER weaken — abort > weaken)

- `platform_dial` = **FULL CAMPAIGN LIVE (owner go-ahead 2026-08-02)** — `PLATFORM_DIAL_DAILY=1` (boolean ON/OFF, count NAHI) · `PLATFORM_DIAL_LIMIT=100` (per-run cap) · `VOICE_LAUNCH_KILL=0` · `DIAL_TEST_MODE=0` · `VOICE_DAILY_CALL_CAP=100`; daily 11:30 IST scheduler auto-dials up to per-run cap (niche=all). Compliance spine UNTOUCHED: DND fail-closed · TRAI window · AI-disclosure · consent · `DLT_APPROVED=1`. Kill-switch: hamesha **running-container** `VOICE_LAUNCH_KILL` verify karo (host `.env` ≠ container env; `1` = web/revenue live but calling gated). Rollback: `.env.bak-fullcampaign-20260802075851` (restore + recreate).
- TRAI/DND/AI-disclosure gates INTACT: DND scrub **fail-CLOSED**, promo window 9am–7pm, "ek AI assistant" disclosure at call start, consent opt-out = instant cross-channel suppression. Foreign trunks India-domestic = ILLEGAL.
- DPDP: purpose limitation + data minimisation + 90-din recording retention + purge API + cross-tenant leak KABHI nahi.
- **Free AI-provider stack only** — koi paid STT/TTS/LLM add mat karo.
- **Old Explorer functional rehna chahiye** jab tak Control Center L1–L4 graphs test na ho jaayein — fallback ko todna mat.
- **Working tree me parallel user changes ho sakte hain** — clean / reset / broad-stage KABHI nahi. Sirf is deliverable ke touch-points chhuo.
- **DO alag products** — Marketing vs Voice standalone; "marketing + voice bundle" USP framing GALAT hai.

---

## 1. READ FIRST (context-first, parallel batch)

Ek turn me parallel Read/Grep:
- `.claude/skills/context-first/SKILL.md` (MANDATORY pre-flight) + `.claude/skills/leadgen-composer/SKILL.md`
- `.claude/skills/production-ready/SKILL.md` (launch gate) + `.claude/skills/enterprise-readiness-audit/SKILL.md` (12-domain /120)
- `CLAUDE.md` §5 invariants + §7 landmines + `## Current State` (auto-loaded) + `docs/LOOP_ENGINEER.md` (9-field format, 8 hats)
- `memory/INDEX.md` → sirf task-relevant: `decisions.md` (recent ADRs), `integrations.md`, `incidents.md`
- Graphify protocol: `CLAUDE.md §9.5` + `docs/GRAPHIFY.md`
- Domain dispatch skills (load on demand per domain, see §7): `leadgen-*` audit pack + enterprise pack (list in `.claude/skills/SKILLS_PARITY.md`).

Graphnavigation-first: `graphify query "<subsystem>" --graph app/graphify-out/graph.json --budget 800` (ya MCP `query`/`explain`/`path`/`affected`) — phir raw source/caller/route/test se VERIFY. Graph = navigation, PROOF nahi (~11% edges INFERRED).

---

## 2. PHASE FLOW (stop rules + evidence gates)

Har phase ka apna **stop rule** — bina us phase ka evidence liye agla phase MAT shuru karo.

### Phase A — DISCOVER (map, no edits)
Graphify-first, phir raw source verify. Map banao:
1. **Product split** — Marketing product surfaces vs standalone Voice product surfaces alag list karo.
2. **Complete customer journey** (dono products): lead capture → outreach (email/social) → reply triage → Hot Queue (`/app/inbox`) → pricing/`/start` → UPI/invoice → onboarding → delivery/reporting → retention. Har hop ka owning route + engine + scheduler job note karo.
3. **All automations:** scheduler↔Celery parity, `AUTOMATION_FLAGS` registry, heartbeats, idempotency keys, retry/DLQ (`dlq:failed_tasks`), budgets/quota fallback, approval gates, suppression/consent ledger, tenant isolation, rollback path.
4. **Routes:** FastAPI duplicate (first-route-wins shadow) + missing + dynamic/function-level imports (startup-gate blind spot, §7 landmine) + frontend→API wiring + public revenue-route contracts.
5. **Surfaces:** Explorer sync, Control Center L1–L4, Old Explorer fallback, Office HQ blueprint, Agent OS/OmniRoute routing (VPS flags OFF = INERT expected).
**Stop rule:** journey map + automation inventory + route/surface list likhe bina Phase B mat karo.

### Phase B — VERIFY (run exact commands; live claims need separate proof)
**Windows = source of truth.** `.venv\Scripts\python.exe` use karo. Exact repo commands:

```bat
.venv\Scripts\python.exe scripts/prod_check.py
.venv\Scripts\python.exe scripts/explorer_sync.py --check
.venv\Scripts\python.exe scripts/cross_path_audit.py
.venv\Scripts\python.exe scripts/deep_wiring_audit.py
.venv\Scripts\python.exe scripts/automation_wiring_audit.py
.venv\Scripts\python.exe scripts/automation_health_audit.py --daily-check
.venv\Scripts\python.exe scripts/automation_health_audit.py --weekly-audit
.venv\Scripts\python.exe scripts/check_html_js.py
.venv\Scripts\python.exe scripts/check_secrets.py
```

Targeted tests (billing/tenant/security/route/admin — pick real suites present in `tests/`, e.g.):
```bat
.venv\Scripts\python.exe -m pytest tests\test_billing_truth_2026.py -q
.venv\Scripts\python.exe -m pytest tests\test_cross_path_telephony.py tests\test_explorer_sync.py -q
.venv\Scripts\python.exe -m pytest tests\test_2026_features.py -q
.venv\Scripts\python.exe scripts/run_tests.bat   # full suite
```
(Phir **`pytest_run.log` Read karo** — console truncate hota hai.)

**LIVE claims = separate evidence (kabhi assume mat karo):**
- `curl.exe -fsS https://leadsgenai.in/health` → `environment:production`, `status:healthy`, aur `version` field note karo (`"latest"` = UNKNOWN-provenance prod, §7 ADR-097).
- `curl.exe -fsS https://leadsgenai.in/api/activation/summary` → `ready_for_first_paid_customer`, `blocker_count`.
- Automation health: `/api/growth/infra/automation-health` + flags `/api/growth/infra/flags`.
- Queue/DLQ depth (Redis `celery` llen + `dlq:failed_tasks`).
- Provider state (LLM/voice/email — free-stack chain healthy?).
- Image SHA / 5-service skew (`/health.version` vs deployed sha).
- Browser-visible proof (Phase E) — surface actually renders + acts.

**CAUSAL-CLAIM DISCIPLINE (§7):** "error gaya" ≠ "mera fix ne kiya". Fix verify me error series ka END timestamp nikalo; absence-of-errors ≠ fix-worked.
**Stop rule:** har check ka PASS/FAIL + live probe ka raw output capture kiye bina scoring mat karo.

### Phase C — FIX SAFE LOCAL GAPS (only verified P0–P2)
- Sirf **verified local** P0–P2 defects fix karo: **minimal additive diff** + **regression test** (naya behaviour = naya test). Padosi convention copy karo.
- Automation change = flag/kill-switch + idempotency/dedupe + timeout + bounded retry + DLQ/fail-record + heartbeat/metric + rollback path + targeted smoke (enterprise automation gate).
- **Dirty-tree preservation:** unrelated user changes ko chhuo mat. `git add -A` FORBIDDEN — sirf apni files stage/diff karo. Clean/reset/checkout FORBIDDEN.
- **FORBIDDEN without explicit user approval:** commit, push, prod deploy, `.env`/secret changes, destructive migration/`DROP`/`reset --hard`, koi bhi external/customer-facing action (email send, call, WhatsApp, social post, payment).
- Fix na ho sakne wale (external/owner-blocked/needs-approval) = P3/owner-action me list karo, chhuo mat.
**Stop rule:** har fix ke saath uska green regression test na ho to fix incomplete.

### Phase D — TEST (regression + gate)
- Naye/badle behaviour ke targeted tests green.
- `prod_check.py` PASS + `check_secrets.py` clean diff + duplicate-route grep clean.
- Voice-path change → agent-tester scorecard chalao (repo `scripts/` me — `agent_tester.py`).
**Stop rule:** koi red test rehte hue Phase E/verdict mat do.

### Phase E — BROWSER PROOF (real clicks, every visible control)
Real browser se (cursor-ide-browser MCP ya browser-use). Auth ke saath login karke. Surfaces:
`/app/admin`, `/app/automation`, `/app/control-center`, `/app/office`.
Har VISIBLE button/tab/form pe:
- **Click test** — action fire hota hai (no dead control).
- **DOM** — expected element render/update.
- **Console** — zero uncaught JS errors.
- **Network** — backing API 2xx/expected (no silent 4xx/5xx, no `app:8000` in-network trap — §7).
- **Mobile 380px** + **dark mode** render OK.
- **Auth/RBAC** — unauth = redirect/401; wrong-tenant = no leak.
- **Destructive-action confirmations** present (delete/purge/disable = confirm gate).
Old Explorer fallback still works jab Control Center graphs test kar rahe ho.
**Stop rule:** button matrix (pass/fail per control) bina verdict mat do. Screenshot/console/network = evidence. Template: `references/BROWSER_EVIDENCE_TEMPLATE.md`.

### Phase F — SCORE & VERDICT
§3 rubrics se score karo, §4 deliverable structure me output do. Evidence ke bina score = us domain me 0 ("hona chahiye" ≠ "hai").

---

## 3. SCORING RUBRICS (scores ≠ vibes — evidence-mandatory)

### 3.1 Business Launch Ready (per product: GO / CONDITIONAL GO / HOLD)
Score Marketing product AUR standalone Voice product **separately**. Money-path checklist (each item = evidence or it's a gap):
- Lead capture + magnet live (`/audit`,`/site-audit`,`/demo`) — renders + submits.
- Outreach → reply → Hot Queue actionable (prospect-qualified, not noise).
- Pricing → `/start` → UPI pay-info + `/api/upi/submit` live; invoice Rule-46 sequential.
- Onboarding → delivery/reporting proven for a real client shape.
- `activation/summary` → `ready_for_first_paid_customer:true`, `blocker_count:0`.
- No open **P0** in the money path.
Verdict: **GO** = all green + 0 P0/P1 in money path · **CONDITIONAL GO** = green with named owner/external blocker (env/creds/DLT) · **HOLD** = P0 in money path or journey break.
(Repo truth baseline: Marketing = sellable; Voice standalone = code-ready, cold-outbound **FULL CAMPAIGN LIVE** since 2026-08-02 — DLT approved (`DLT_APPROVED=1`), bounded caps + compliance spine active; treat any "HARD OFF" claim as stale unless re-probed.)

### 3.2 Production Ready (per product: GO / CONDITIONAL GO / HOLD)
- `prod_check.py` ALL PASSED + `/health` `environment:production` + `version` ≠ `"latest"`.
- No open P0/P1 (route/journey/automation).
- Every automation: flag + idempotency + retry/DLQ + rollback + heartbeat present.
- No duplicate/missing route; no function-level-import startup blind spot on public revenue routes.
- Browser smoke green on all 4 admin surfaces.
- Queues/DLQ = 0 (or explained), provider chain healthy.

### 3.3 Enterprise Ready — /120 (12 domains × /10; ≥96 AND no domain <6)
| # | Domain | Pass bar (evidence) | Dispatch skill |
|---|--------|---------------------|----------------|
| 1 | Security & RBAC | zero missing-auth on customer/admin routes; IDOR-guarded billing mutations | `leadgen-security-rbac` |
| 2 | Tenant isolation | zero cross-tenant leak path; wrong-tenant tests green; Qdrant ns scoped | `tenant-isolation-audit` |
| 3 | DR & backups | restore PROVEN <90d; RTO/RPO measured | `dr-restore-drill` |
| 4 | Reliability SLO | SLOs defined + burn alerts + budget tracked | `slo-error-budget` |
| 5 | Secrets rotation | inventory current; no key >90d unreviewed; `.env`-only | `secrets-rotation` |
| 6 | Data retention / DPDP | deletion runbook proven; 90d recording purge live; purge API | `data-retention-dpdp` |
| 7 | Capacity | ceiling measured; headroom ≥40% at peak | `load-capacity-testing` |
| 8 | DB migrations | last 3 expand-contract + rollback; PgBouncer-safe | `db-migration-safety` |
| 9 | Supply chain | pip-audit clean of exploitable HIGH; images <90d; Actions pinned | `supply-chain-security` |
| 10 | Billing truth | `packages.py` single-source ↔ plans ↔ `test_billing_truth_2026`; GST rule-46 | `leadgen-billing-upi` |
| 11 | Voice/comms compliance | TRAI gates INTACT (DND fail-closed, 9–7pm, AI-disclosure) | `leadgen-voice-compliance` |
| 12 | Ops & incident | runbooks current; alerts actionable; heartbeats green | `prod-incident-triage` + `observability-ops` |

Scoring honesty: `prod_check` PASS ≠ domain pass. Single-VPS reality accept — measured 99.5% + proven restore > claimed 99.99% with nothing. Any domain <6 → dispatch its skill immediately, note in verdict.

---

## 4. FINAL DELIVERABLE (executing agent MUST produce all 7)

1. **Executive verdict + evidence confidence** (High/Med/Low, based on how much was live-proven vs static).
2. **Product-wise GO / CONDITIONAL GO / HOLD** — Marketing vs Voice, separately, with the blocker if not GO.
3. **Enterprise score /120** — per-domain table with the evidence line for each score; NO unsupported number.
4. **P0–P3 gap register** — each row: root cause · affected workflow · evidence · fix · test · risk · owner · **named rollback**.
5. **Admin button matrix** (per control: surface · control · pass/fail · console/network note) **+ end-to-end workflow matrix** (per journey hop: works / broken / unverified).
6. **Clear separation:** Broken · Working-but-unverified · Owner/external-blocked (no mixing).
7. **Top 5 business-launch actions** ordered by **revenue impact × risk × effort**.

Feature inventory classified **Keep / Fix / Add / Change / Remove / Owner-action** — no speculative features (only what's in code/surfaces).

Also emit the **Loop Engineer 9-field block** (`docs/LOOP_ENGINEER.md`): Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority.

---

## 5. DEPLOY (only if user explicitly approves)

Approval mile to hi: **ONLY** canonical deploy script (repo `scripts/` me — `deploy_vps.sh`), haath se docker mat likho, **pinned `APP_VERSION=<sha>`**, **5 app-image services skew check**, **`/health.version` == deployed sha**, **post-deploy browser smoke**. `DRY_RUN=1` = plan print. Bina approval = deploy FORBIDDEN.

---

## 6. FIX GATES + FORBIDDEN (recap — non-negotiable)

**Allowed without asking:** read/grep, run audit + test scripts, minimal additive local fix for VERIFIED P0–P2 + its regression test, staging only your own touched files.
**FORBIDDEN without explicit user approval:** commit · push · prod deploy · `.env`/secret edit · destructive migration/`DROP`/`reset --hard` · `git add -A` · clean/reset/checkout of dirty tree · any external/customer action (email/call/WhatsApp/social/payment) · weakening any §5 compliance/security gate (that = ABORT, not a fix).

---

## 7. SKILLS TO LOAD (by name — executor Read on demand)

Pre-flight: `context-first`, `leadgen-composer`. Gates: `production-ready`, `enterprise-readiness-audit`, `verify-ship`, `fable-operating-manual`, `systematic-debugging`, `duplicate-route-guard`, `llm-council-decision` (ambiguous strategy).
Per-domain dispatch (load only the one you're auditing): `leadgen-security-rbac`, `tenant-isolation-audit`, `dr-restore-drill`, `slo-error-budget`, `secrets-rotation`, `data-retention-dpdp`, `load-capacity-testing`, `db-migration-safety`, `supply-chain-security`, `leadgen-billing-upi`, `leadgen-voice-compliance`, `prod-incident-triage`, `observability-ops`.
Journey/automation: `leadgen-customer-journey-e2e`, `leadgen-automation-reliability`, `automation-flags`, `scheduler-job`, `leadgen-revenue-readiness`, `leadgen-product-truth`.

Known landmines to actively check (§7 CLAUDE.md): stale-`.pyc` 404 on new page-route · function-level import hides startup failure (grep ALL callers of retired helpers) · `app:8080` in-network vs `8000` host trap · `${APP_VERSION:-latest}` provenance · `USE_SILERO_VAD=0` · Sentry `search_issues` for real bugs invisible in log-grep.

🐦 pelican
