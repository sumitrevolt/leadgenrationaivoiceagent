# 5 Admin CLI Bots + 31 Agents — Master Plan & Worker Handoff Prompt

**Status:** PLAN (awaiting owner approval — nothing executed, no deploy, no commit)
**Author:** Nova / WorkBuddy (coordinator)
**Date:** 2026-09-11 14:05 IST
**Repo:** `main` @ `33189b70` (working tree dirty — 13 modified files, see §1.4)
**Mode:** `/plan` — Phase 0 execution starts only after owner sign-off

---

## 0. VERDICT — kya plan sahi hai?

**Haan, 5-Admin-CLI + 31-agent + OmniRoute model sahi hai.** Lekin main 10 corrections ke saath
final karunga. Har correction ke saath repo evidence hai — koi bhi "lagta hai" nahi.

| # | Correction | Evidence | Impact |
|---|---|---|---|
| **C1** | **Claude → OpenCode swap is correct AND auth-safe** — `opencode` is *already* in `_KNOWN_TOOLS`. But `combo_distribution.yaml` still maps 5 combos to app id `claude`. Swap must be **rename-with-alias** (`id: opencode`, `aliases: [claude]`), not delete — warna `leadgen-swara-flagship` + `kimi-coding` orphan ho jayenge. | `app/platform/coordination_hub_auth.py:23`; `config/desktop_apps/combo_distribution.yaml:40-53` | HIGH |
| **C2** | **FreeBuff is PARTIAL, not "not installed".** `.freebuff/worktrees/<uuid>/` exists (it ran and created worktrees) + `.agents/skills/freebuff/SKILL.md` exists. But `freebuff` is **absent** from `combo_distribution.yaml` desktop_apps (only 5: hermes/claude/workbuddy/openclaw/verdant) and from `_KNOWN_TOOLS`. Correction to your note: FreeBuff *has executed* — it just has **no worker registration, no combo assignment, no heartbeat**. | `.freebuff/worktrees/26773706-.../`; `.agents/skills/freebuff/` | HIGH |
| **C3** | **31 agents = CODE-PRESENT ✅ but the REGISTRY DOC is STALE ❌.** `app/platform/team.py` → `STAFF` = exactly **31**. `docs/AGENT_REGISTRY.md` §2 documents only **19** and is dated 2026-06-20. 12 agents (ananya, riya, lekha, raksha, kabir, diya, aryan, arya, priya, zara, anika, ira) doc mein hain hi nahi. **Fix = registry ko generated banao (`team.py` se), haath se mat likho** — warna phir drift hoga. | `app/platform/team.py` STAFF parse; `docs/AGENT_REGISTRY.md` | HIGH |
| **C4** | **"14 combos" is a curated SUBSET of 18.** Config khud kehta hai: *"User stated 14 combos but OmniRoute exports 18. We use the 14 most production-critical."* Dashboard ko "14 = all" bolna galat hoga. Owner decide kare: freeze-14 (4 excluded ko document karke) ya expand-to-18. | `config/desktop_apps/combo_distribution.yaml:7-11` | MED |
| **C5** | **QA/Governance ka koi Admin owner nahi.** Arnav (security/compliance), Kavya (ops monitor), Guru (skill trainer), Arjun (voice QA) — 4 agents jinka koi department head nahi. **Recommendation: 6th CLI mat banao.** QA ek *gate* hai, department nahi — usse **Hermes/Pilot ke niche cross-cutting guild** rakho, taaki wo kisi bhi Admin ke kaam ko veto kar sake. Agar QA kisi Admin ke andar hoga to wo apne hi department ko veto nahi kar payega. | `app/platform/team.py` STAFF roles | HIGH |
| **C6** | **LeadGen vs Billing split karo, naam badlo.** WorkBuddy Admin ko "Revenue" kehne se prospecting/SEO/churn chhup jata hai. Naam rakho **"Revenue & Growth Admin"** (email + leadgen + CRM + cadence + billing + finops) — 9 agents. | see §3 | MED |
| **C7** | **OmniRoute authority vs combo→app binding mein conflict hai.** `combo_distribution.yaml` combos ko apps se hard-bind karta hai (`claude` owns `kimi-coding`). Aapka rule kehta hai "bot ko provider se permanently bind mat karo". **Resolution:** combo→app mapping = **affinity hint (soft)**; router = **authoritative selector**. Dashboard ko *preferred combo* aur *actual selected combo* dono dikhane padenge. | `config/desktop_apps/combo_distribution.yaml:26-88` | HIGH |
| **C8** | **Ledger abhi DO hain, ek nahi.** (a) DevTask = Postgres, already has atomic claim / lease / heartbeat / reconcile / missions. (b) `command_center/data/tasks.json` = 44 tasks + `CENTRAL_LEDGER.md`. **Decision: DevTask DB = canonical execution ledger.** `tasks.json` = read-only **projection/export** for Command Center UI + Hermes Kanban. JSON mein lease logic dobara mat banao. | `app/api/dev_tasks.py` routes; `app/dev_control/claims.py` | CRITICAL |
| **C9** | **4 of 5 Admin CLIs enrol hi nahi ho sakte.** `_KNOWN_TOOLS = ("cursor","claude","monkeycode","opencode","bolt","buzz","hermes")`. Allowed: `opencode` ✅, `hermes` ✅. Blocked: `freebuff` ❌ `verdant` ❌ `openclaw` ❌ `workbuddy` ❌. Better fix than a one-line edit: make the tuple **config-driven** from `data/coordination_hub/known_tools.json`. Owner-gated code change. | `app/platform/coordination_hub_auth.py:23,169` | CRITICAL |
| **C10** | **Naming collision:** agent id `hermes` (Infrastructure Handler) vs **Hermes/Pilot** (central coordinator). Dashboard mein ye confuse karega. Rename agent → `hermes-infra` (display-only alias OK, STAFF key change risky). | `app/platform/team.py` STAFF | LOW |

**Bottom line:** architecture freeze karne layak hai. C8 aur C9 bina solve hue Phase 2 shuru karna bekaar hai.

---

## 1. REPO TRUTH SNAPSHOT (verified 2026-09-11)

### 1.1 Agents — 31, CODE-PRESENT
`app/platform/team.py` → `STAFF` = **31 keys** (full roster with real roles in §3).

### 1.2 Combos — 14 curated / 18 exported
`config/desktop_apps/combo_distribution.yaml`:
- `total_combos: 14`, `42 provider slots` (14 × 3 failover)
- Groups: `leadgen-*` (revenue-critical) + `hermes-*` (per-agent) + `leadgen-project-best` + `kimi-coding`
- Kill fences: `combo_all_providers_down` → hard halt; budget fence on `leadgen-project-best`
- 5 desktop apps: hermes · claude · workbuddy · openclaw · verdant

### 1.3 Control plane — already 80% there
`app/api/dev_tasks.py` already implements:
`POST /claim-next` · `/{id}/claim` (atomic conditional UPDATE) · `/{id}/heartbeat` (non-owner refused — **koi lease steal nahi**) · `/{id}/report` · `/reconcile` · `/status` · `/{id}/usage` · `/{id}/approve-production` · `/{id}/finalize-delivery` · **missions**: claim/heartbeat/start/result/review/advance/cancel/retry/rollback/`recover-stale`.

→ **Phase 2 = build nahi, wire karna hai.** Naya orchestrator banana mana hai.

### 1.4 Working tree (dirty — pehle reconcile karo)
Modified: `AGENTS.md`, `HERMES_CONTROL_PLANE.md`, `app/api/admin_dashboard.py`,
`app/api/owner_command_center.py`, `app/platform/team.py`, `app/telephony/vobiz_handler.py`,
`progress.md`, `docs/context/SESSION_HANDOFF.md`, `docs/coordination/desktop_registry.json`,
`scripts/autonomous_workforce_orchestrator.py`, `data/leadgen_dev.db`, + runtime jsonl.
Untracked: `.agents/`, `.freebuff/`, `docs/context/WORKER_ROSTER.md`,
`docs/context/PHASE3_Q4_Q5_TRUTH_LAYER_2026-09-10.md`, `build_bots_json.py`, `build_tasks_json.py`.

⚠️ **Koi commit/push nahi** bina owner ask ke (project rule).

### 1.5 Workers — truth gate
`data/workforce_live_status.json` claims `RUNNING_24_7_PARALLEL`, `actions_today=592` but
`active_workers=0`, `task_execution_verified=false`, `evidence_kind=inference_probe_only`.
**Dashboard/Telegram ko ye green dikhana prohibited hai** jab tak T-05 probe fix na ho.

### 1.6 Live bot fleet — 9 bots, ACTIVE TODAY (v1 mein MISS tha)

`command_center/data/bots.json` = **9 bots**, abhi GHANTI task IDs dispatch kar rahe hain
(SUC-016, SAL-016, HNT-016, GRD-016, ENG-016, PLT-016, OPS-016, BRD-016). Ye koi purana concept
nahi — **aaj live hain.** Inhe 5 Admin departments mein consolidate karna hoga, parallel nahi chalana:

| Bot | Live status (08:42 IST, 2026-09-11) | Consolidates into |
|---|---|---|
| Commander | ✅ RUN — 08:30 sweep, 8 GHANTIs dispatched | **Hermes / Pilot** |
| QA / Evidence Gate | 🟡 GRD-016 6-scope audit, verdict pending | **Hermes / Pilot** (QA guild) |
| Visualization | 🟡 BRD-016 VPS mirror, page-200 verify pending | **Hermes / Pilot** |
| Engineering | 🟡 ENG-016 scheduler wiring fix | **OpenCode CLI** |
| Operations | 🟡 OPS-016 `call_loop` root cause | **OpenCode CLI** (DevOps) |
| Lead Discovery | 🟡 HNT-016 20 leads, date-lock bug | **WorkBuddy CLI** |
| Revenue Executor | 🟡 SAL-016 pitch v2, no ACK on VPS | **WorkBuddy CLI** |
| Customer Success | 🟡 SUC-016 Jiya retention UPI window | **WorkBuddy CLI** |
| Infra / Telephony | 🔴 **BLOCKED** PLT-016 | **OpenClaw CLI** |

**9/9 mapped. FreeBuff + Verdant = bilkul naye departments — inka koi legacy bot nahi.**
Isliye dono ko zero se establish karna hoga (C2 dekho: FreeBuff PARTIAL).

### 1.7 Feature inventory — 376 features / 32 domains (dashboard scope, v1 mein MISS tha)

`docs/FEATURE_INVENTORY.md`: **346 LIVE · 21 WORKING_BUT_INERT · 3 PARTIAL ·
3 EXTERNALLY_BLOCKED · 3 REMOVED = 376**, across **32 domains**.

⚠️ **v1 dashboard IA sirf ~10 domains cover karta tha.** "Koi feature miss nahi hona chahiye"
tabhi sach hoga jab dashboard **32/32 domains** map kare. v1 mein ye sab missing the:
Booking (8) · Multi-Tenant SaaS (11) · Knowledge/RAG (10) · MCP/External Tooling (6) ·
Search/Prospecting (6) · Push Notifications (6) · Data Layer (10) · Wiring Audit (9) ·
Boss Autonomy (10) · Harness Control Plane (20) · Harness Execution Families (5) ·
AI Provider Router (12) · Observability (12) · Compliance/Privacy (9) ·
Frontend/Customer UX (14) · Deployment/Release (13) · Agent Orchestration (13).

### 1.8 Scheduler — 54 jobs (AGENT_REGISTRY bola 43 → STALE)

`app/platform/scheduler_config.py` → `JOB_META` = **54** (doc "currently 43 as of 2026-08-03"
purana hai). Pehle se maujood: `task_lease_reap`, `heartbeat`, `content_approval_sweep`,
`approval_email_sweep`, `social_drain`, `whatsapp_automation`, `daily_video`, `platform_dial`,
`sales_autopilot`, `hot_queue_owner_pack`, `daily_owner_brief`, `reply_auto_send`,
`content_approval_notify`, `hq_auto_chase`.

→ **Lease reaping + heartbeat already scheduled.** Phase 2 aur bhi zyada "wire, not build" hai.

### 1.9 Canonical ledger live state

`command_center/data/tasks.json` = **8 tasks** (1 🔵 RUNNING · 5 🆕 NEW · 1 🔴 BLOCKED ·
1 🟡 UPDATE). Kal ke 44 se alag — ye **live bot dispatch board** hai, archive nahi.
C8 confirm: **DevTask DB = execution canonical**; `tasks.json` = read-only projection + bot dispatch board.

### 1.10 LIVE incidents — migration se PEHLE address hone chahiye (v1 mein MISS tha)

| ID | Issue | Owner dept | Severity |
|---|---|---|---|
| **PLT-016** | **DID REVOKED 10d, SIP empty, `api.vobiz.com` TCP-000**, Jio 08-26 no proof, RMS never called → OWNER-ESC vendor-gated, PIVOT to WAHA-only | OpenClaw (Voice) | **P0** |
| **ENG-016** ⚠️ **PARTLY MISREPORTED — verified 14:20 IST** | Bot ne kaha "0 call sites". **Galat.** `app/tasks/whatsapp_automation.py` **maujood hai** (487 lines) aur `team_scheduler.py:1630-1634` se wired hai (hourly Celery task `run_whatsapp_automation`, full compliance spine: `WHATSAPP_AUTO_SEND` + HARD_OFF kill switch, Redis daily cap, per-day idempotency, fail-closed DND/TRAI scrub). Sach: `sendText` count in `app/platform/auto_outreach.py` = **0** ✅ (ye part sahi tha) — lekin WhatsApp **INERT BY DESIGN** hai (`WHATSAPP_AUTO_SEND=0` → "wa.me links only"). Ye **compliance gate hai, bug nahi** — isse "fix" karna = gate weaken karna = **ABORT**. | FreeBuff + **owner gate** | **NOT P0 — owner decision** |
| **OPS-016** | `call_loop` dead 10d — no cron, no proc; circuit-breaker cron unknown | OpenCode (DevOps) | **P1** |
| **HNT-016** | Date-lock bug — `2026-09-11a.csv` NOT FOUND on VPS, manual batch workaround | WorkBuddy | **P1** |

⚠️ **Correction 14:20 IST:** WhatsApp **toota nahi hai** — wo compliance gate ki wajah se INERT hai
(arm karne ke liye owner decision + canary allowlist chahiye, ghante lagenge, din nahi).
**Voice hi asli P0 hai**, kyunki uska trunk armed nahi hai.

### 1.10.1 CHANNEL REALITY — ₹5L/7din kis channel se aayega (verified 14:20 IST)

| Channel | Inventory | Sach | Revenue-ready? |
|---|---|---|---|
| **Email Automation** | **11 / 11 LIVE** (0 inert) | Poora live | ✅ **HAAN — aaj** |
| **Lead Generation** | 14 LIVE / 1 EXT_BLOCKED | Live, sirf date-lock bug (HNT-016) | ✅ **HAAN** |
| **CRM + Pipeline** | 10 LIVE / 3 INERT | Mostly live | ✅ haan |
| **WhatsApp** | 13 LIVE / 1 EXT_BLOCKED | Code+compliance ready, **INERT by design** | 🟡 **owner gate ke baad** |
| **Voice Calling** | 23 LIVE / 1 EXT_BLOCKED | **Trunk armed nahi** — Vobiz DID revoked; `TATA_SMARTFLO_ENABLED=0` (INERT default, ₹1,250/license/mo); Jio SIP config maujood par unverified | 🔴 **NAHI — vendor + paisa** |

**Conclusion:** ₹5L/7din ka rasta **email + leadgen + CRM** se jayega, voice se nahi. Voice ek
paid license (₹1,250/license/mo Smartflo) ya Vobiz DID restore ke baad hi aayega. Dashboard
banaane se revenue nahi aata — **funnel chalane se aata hai.**

### 1.11 Unreconciled worker identities (v1 mein MISS tha)

- **`buzz`** — `data/workforce_live_status.json:desktop_apps` mein tracked hai, lekin
  `combo_distribution.yaml` mein nahi (5 apps) aur Docker par sirf infra containers hain
  (`buzz-postgres`, `buzz-redis`, `buzz-prometheus`, `buzz-keycloak` **unhealthy**, `buzz-minio`).
  **Decision needed:** de-register ya `INFRA_ONLY` mark karo.
- **`codex`** — headless processes maujood (pid 4680), koi declared task nahi.
  **Decision needed:** 6th admin bot? Ya OpenCode ke niche sub-worker? Ya retire?

---

## 2. FINAL AUTHORITY MODEL

```
OWNER                    → ultimate authority
  ↓
HERMES / PILOT           → orchestration authority (+ QA/Compliance GUILD, cross-cutting veto)
  ↓
5 ADMIN CLI BOTS         → domain authority
  ↓
31 AGENTS                → execution authority
  ↓
OMNIROUTE                → model-routing authority (single)
  ↓
14 COMBOS                → 42 provider slots

DEV TASK DB              → state / source-of-truth authority
ADMIN DASHBOARD          → owner-visible truth (projection)
```

**Koi bhi Admin apne local memory / chat history ko project truth nahi manega.**
Desktop apps = **owner-manual only** (migration/emergency/debug), 24×7 dependency nahi.

---

## 3. 31 AGENTS → 5 ADMINS (real roles from `team.py`, zero fabrication)

| Admin CLI | Domain it FINALIZES | Agents | Count |
|---|---|---|---|
| **Hermes / Pilot** (central) | Control, routing, QA/Compliance guild, stale recovery | `manager` (Supervisor), `kavya` (Ops Monitor), `arnav` (Security/Compliance), `guru` (Skill Trainer) | **4** |
| **1. OpenCode CLI** — Chief Engineering | Control plane, Admin Dashboard, DevOps/SRE, DB, supply-chain, MCP, **Video Automation pipeline** | `vikram` (Code Upgrader), `pranav` (SRE), `hermes`→`hermes-infra` (Infrastructure), `kabir` (DB Reliability), `diya` (Data Integrity), `aryan` (Supply-chain), `arya` (MCP) | **7** |
| **2. WorkBuddy CLI** — Revenue & Growth | **Email Automation**, leadgen, enrichment, scoring, SEO, CRM sync, cadence, journey, billing, finops | `rohan` (Leads Manager), `dev` (Data Analyst), `ravi` (SEO Scout), `neha` (Pipeline Ops), `priya` (CRM Sync), `anika` (Cadence), `ira` (Journey Automation), `nikhil` (Revenue Ops), `vidya` (FinOps) | **9** |
| **3. FreeBuff CLI** — Communications | **WhatsApp Automation**, inbound conversation, escalation/handoff, booking chat | `riya` (AI Receptionist), `raksha` (Human Escalation), `ananya` (Appointment Booker) | **3** |
| **4. Verdant CLI** — Creative | **Video Creation** (script → assets → render → creative QA), social assets, A/B creative | `isha` (Marketing Executive), `zara` (Social Media Manager), `kiran` (Campaign Optimizer) | **3** |
| **5. OpenClaw CLI** — Voice | **Swara Calling**, Smartflo/telephony, call QA, training, analytics | `swara` (Telecaller), `tara` (Voice Infra Ops), `arjun` (QA Engineer), `meera` (Trainer), `lekha` (Call Analytics) | **5** |

**Total = 4 + 7 + 9 + 3 + 3 + 5 = 31 ✅**

**Why this split is evidence-based, not arbitrary:**
- FreeBuff gets `riya`/`raksha`/`ananya` because those three are the **conversation lifecycle** agents (inbound → escalation → booking). WhatsApp *is* that lifecycle.
- Verdant gets `isha`/`zara`/`kiran` because those are the **content/creative/optimization** agents. Video creation is a creative deliverable.
- `isha` owns the live `whatsapp_campaign` module → when FreeBuff needs campaign copy it creates a **child task** and borrows `isha`. Result returns to the WhatsApp parent task. This is the borrow mechanism working as designed.

**Borrow rule:** har agent ka **primary supervisor** fixed hai, lekin cross-domain kaam child-task ke through hota hai:
`Parent Objective → Admin Owner → child task → borrowed agent → evidence → QA → Parent Result`.
Koi agent-to-agent direct spawning nahi.

---

## 4. AUTOMATION FINALIZATION OWNERSHIP (aapka sawal — kaun final karega)

| Automation | Finalizes | Creates | Executes | QA gate |
|---|---|---|---|---|
| **Email Automation** | **WorkBuddy CLI** | `rohan` | `rohan`, `anika`, `ira`, `neha` | `arnav` (compliance) + Hermes/Pilot |
| **Video Automation** (queue→approve→schedule→publish→retry) | **OpenCode CLI** | `vikram` | `vikram`, `pranav` | `kavya` + `arnav` |
| **Video Creation** (script→assets→render→creative QA) | **Verdant CLI** | `isha` | `isha`, `zara`, `kiran` | `arjun` (QA) |
| **WhatsApp Automation** | **FreeBuff CLI** | `riya` | `riya`, `raksha`, `ananya` | `arnav` (consent/opt-in) |
| **Swara Calling** | **OpenClaw CLI** | `swara` | `swara`, `tara`, `lekha` | `arjun` + `arnav` (TRAI/DND/consent) |
| **Social Automation** (connections, approval, schedule, publish, channel limits, Postiz, backlog) | **OpenCode CLI** (pipeline) + **Verdant CLI** (creative/assets) | `zara` | `zara`, `pranav`; `isha` borrowed for copy | `arnav` + `kavya` |
| **Lead Generation** (source, harvest, enrich, score, qualify, dedupe, route, cadence enrol) | **WorkBuddy CLI** | `rohan` | `dev`, `ravi`, `neha`, `rohan` | `diya` (data integrity) + `arnav` |
| **CRM / Follow-up** (pipeline, stage, next action, stale opps, assigned agent, conversion) | **WorkBuddy CLI** | `priya` | `priya`, `anika`, `ira`, `neha` | `kabir` (DB) |
| **Billing / Revenue** (plans, invoices, payments, evidence, MRR, dunning, lifecycle, churn) | **WorkBuddy CLI** | `nikhil` | `nikhil`, `vidya` | **owner-confirmation gate** (kabhi auto-pass nahi) |
| **Customer Delivery** (onboarding, tenant isolation, per-customer automations, SLA, delivery evidence) | **OpenCode CLI** | `pranav` | `pranav`, `dev`, `arya` | `arnav` + `diya` |

**9/9 automation domains ab assigned hain** (v1 mein sirf 5 the — social, leadgen, CRM, billing,
customer delivery missing the).

**Hard separation:** Verdant **banata** hai, OpenCode **chalata** hai. Dono ek nahi hain.
Video automation abhi repo mein **PARTIAL** hai → explicitly harden karna hoga (Phase 5).

---

## 5. OMNIRoute CONTRACT

- **One** routing config: `config/desktop_apps/combo_distribution.yaml` + `.omniroute-cutover/combos.json`.
- Combo→app mapping = **affinity**, not binding. Router decides.
- Dashboard per combo: health · enabled · provider · models · latency · errors · circuit-breaker · quota · usage · last used · worker usage · fallback status.
- **Secrets: kabhi bhi UI/log/chat mein nahi.** Sirf `configured: yes/no` + last-4 (agar zaroori).
- Status: 14 curated vs 18 exported → owner decision C4.

---

## 6. ADMIN DASHBOARD IA (extend, rebuild nahi)

Existing surfaces jo **discard nahi** karne: `app/api/admin_dashboard.py`,
`app/api/owner_command_center.py`, `frontend/admin_dashboard.html`, `app/dev_control/*`,
`app/api/dev_tasks.py`, `command_center/`.

**Progressive disclosure:**
- **L1 — Owner home:** platform healthy? customers served? revenue automations working? koi bot/agent stuck? channel failing? telephony armed? pending approvals? kya badla? next action?
- **L2 —** 24×7 worker control · 31-agent command view · automation center · combo center
- **L3 —** task ledger/kanban · per-agent detail · incident detail
- **L4 —** raw evidence, logs, metrics, audit

**Sections A–J:** Executive overview · Worker control (inspect/pause/resume/drain/retry/reassign/quarantine — all gated) · 31-agent view (grouped under Admin, showing Primary Admin / Current Task / Borrowed By / Heartbeat / Combo / Last Evidence) · Task ledger-Kanban (canonical DB, parent-child, deps, lease, retries, audit) · OmniRoute 14-combo center · Automation control center (voice / WhatsApp / email / video / social / leadgen / CRM / billing / customer delivery) · **Approval center — owner vs customer vs deployment vs content vs video vs financial vs compliance ALAG-ALAG** (ek misleading number nahi) · Automation health (scheduler, last run, next run, overdue, owning bot+agent) · Incident center (P0–P3) · Audit/security (no secrets, no PII).

**Colors:** GREEN healthy · AMBER degraded · RED blocked · GREY disabled — **color alone par mat depend karo**, hamesha text label + reason.

**Non-functional:** fast · responsive · **mobile-usable** · actionable · low-noise · drill-down
capable · role-aware · secure · source-backed · consistent. Home page par raw logs kabhi nahi.

### 6.1 32/32 domain coverage (v1 mein MISS tha)

Dashboard ka har section `docs/FEATURE_INVENTORY.md` ke **32 domains** mein se kam se kam ek se
map hona chahiye. Jo domain kisi section mein nahi aata, use **"UNMAPPED"** list mein dikhana
hoga — chhupana mana hai. Ye hi **feature-preservation matrix** ka BEFORE→AFTER proof hoga.

### 6.2 Telegram — SECONDARY owner cockpit (v1 mein POORI TARAH MISS tha)

Dashboard = source of truth. Telegram = **secondary cockpit, egress-only** (koi `getUpdates`
poller nahi — `HERMES_CONTROL_PLANE.md` ke mutabik Hermes hi sole ingress owner hai).

Commands: `/status` · `/workers` · `/agents` · `/combos` · `/revenue` · `/incidents` ·
`/approvals` · `/voice` · `/video` · `/email` · `/whatsapp` · `/leads` · `/tasks`

**Sirf meaningful notifications** (raw logs flood karna mana):
P0/P1 incident · worker repeatedly failing · **no heartbeat** · provider/combo outage ·
important revenue event · approval required · deployment completion/failure · daily owner summary.

⚠️ **Precondition:** `data/workforce_live_status.json` ka probe theek hone tak
(`active_workers=0` + `task_execution_verified=false`) workforce/agent data Telegram par
**bhejna prohibited hai** — T-05 pehle land karna hoga.

---

## 7. PHASED EXECUTION PLAN

**PHASE 0 — BASELINE** (read-only; ~1 pass)
1. `git status` snapshot + commit pin `33189b70`
2. Machine-readable feature inventory from code → diff vs `docs/FEATURE_INVENTORY.md`
3. Inventory: 31 agents (from `team.py`) · 14 combos · 5 desktop apps · desktop dependencies · 10 automation domains
4. Confirm OmniRoute per-combo health endpoint exists (**currently UNKNOWN — verify, don't assume**)

**PHASE 1 — ARCHITECTURE FREEZE** (docs only)
- This file becomes the canonical architecture record.
- Freeze: bot→agent map (§3) · worker identity contract · OmniRoute contract · task/heartbeat/lease contract · dashboard IA (§6)
- **Regenerate `docs/AGENT_REGISTRY.md` from `team.py`** (generated, not hand-written) — fixes C3

**PHASE 2 — CONTROL PLANE** (blocked by C8 + C9)
- DevTask = canonical; `tasks.json` demoted to read-only projection
- `coordination_hub_auth._KNOWN_TOOLS` → config-driven (`freebuff`, `verdant`, `openclaw`, `workbuddy` add)
- Worker registry with heartbeat + lease + reconcile (reuse `app/dev_control/claims.py`)
- Bot→agent assignment table; combo selection visibility
- `claude` → `opencode` rename-with-alias in `combo_distribution.yaml`

**PHASE 3 — HEADLESS MIGRATION**
- Har desktop worker: DISCOVER → INVENTORY → LOCATE → IDENTIFY DESKTOP DEP → DESIGN HEADLESS → IMPLEMENT → heartbeat/lease/retry → OmniRoute → bot supervisor → agent map → TEST → VERIFY → RECORD → HANDOFF
- Headless = Docker service / systemd / PM2 / Celery. **Random always-running terminal windows = production infra nahi.**
- Prove before decommission: starts w/o GUI · survives terminal close · restart policy · heartbeat visible · claim works · retry works · assignment visible · OmniRoute works · result → ledger · dashboard shows it · rollback exists

**Worker onboarding gate — 9 steps, sequential, koi step skip nahi (v1 mein explicit checklist MISS tha).
Har Admin CLI ko 24×7 ACTIVE declare karne se pehle sab 9 prove karne honge:**

1. Profile create
2. CLI executable **prove** (headless chal gaya — sirf "installed hai" nahi)
3. OmniRoute configure
4. Auth enrol (`_KNOWN_TOOLS` — C9 blocker)
5. Heartbeat visible
6. Claim task works
7. Agent delegation works
8. Retry/recovery test pass
9. Admin Dashboard visibility

→ 9/9 green hone ke baad hi `ACTIVE`. **Fake green status bilkul nahi.**

**PHASE 4 — OWNER COMMAND CENTER**
- Consolidate existing surfaces (§6). Extend `admin_dashboard.py` + `owner_command_center.py`. **Naya duplicate dashboard nahi.**

**PHASE 5 — AUTOMATION E2E** (individually verified)
voice → WhatsApp → email → video → social → leadgen → CRM/follow-up → billing → customer delivery → scheduler/recovery

**PHASE 6 — HARDEN**
concurrency · restart · stale-lease · provider failover · queue recovery · tenant isolation · secret scan · security · regression

**PHASE 7 — HANDOFF**
Machine + human readable report (§8 fields)

---

## 8. ACCEPTANCE GATES (migration tab complete mana jayega)

- [ ] Desktop apps optional/manual — 24×7 ke liye required nahi
- [ ] **Ek** canonical ledger (DevTask DB)
- [ ] 5 Admin CLIs headless, restart-proof
- [ ] 31-agent roster `team.py`-se reconcile + generated registry
- [ ] bot→agent hierarchy dashboard-visible
- [ ] Har worker heartbeat; stale recovery works
- [ ] lease/retry/idempotency works
- [ ] OmniRoute = single routing authority
- [ ] 14 combos inventoried, deduped, health-monitored, dashboard-visible (+ 4 excluded documented)
- [ ] Secrets protected; scan passes
- [ ] Owner vs customer approvals separated
- [ ] voice / WhatsApp / email / video / social / leadgen / CRM / billing / delivery E2E verified
- [ ] Feature preservation matrix: **koi silent feature loss nahi**
- [ ] Rollback path exists; targeted + integration tests green

---

## 9. OWNER DECISIONS REQUIRED (in seedhe block kar rahe hain)

1. **C8** — DevTask DB ko canonical ledger mana jaye? (`tasks.json` = read-only projection)
2. **C9** — `_KNOWN_TOOLS` ko config-driven banane ki permission? (4 CLIs tabhi enrol honge)
3. **C4** — Combos 14 pe freeze ya 18 pe expand?
4. **C10** — Agent `hermes` → `hermes-infra` rename? (display-only vs STAFF key)
5. **C5** — QA/Compliance guild Hermes/Pilot ke niche cross-cutting (meri recommendation) ya 6th CLI?
6. **C7** — combo→app affinity only (soft), router authoritative — confirm?
7. **§1.11** — `buzz` ko de-register karein ya `INFRA_ONLY` mark? (`buzz-keycloak` unhealthy)
8. **§1.11** — `codex` = 6th admin bot, OpenCode ka sub-worker, ya retire?
9. **§1.10** — **PLT-016 (DID revoked) aur ENG-016 (WhatsApp 0 call sites) pehle fix karein ya
   migration ke saath parallel?** Meri recommendation: **pehle** — ye ₹5L/7din goal ko seedhe block
   kar rahe hain.
10. **§1.6** — 9 legacy bots ko turant consolidate karein ya migration complete hone tak
    (read-only) chalne dein? Recommendation: **abhi consolidate** — parallel scheduling abhi
    duplicate kaam kar rahi hai.

---

## 10. HANDOFF RULES (har worker ke liye)

Record karo: task ID · objective · completed work · files changed · tests run · evidence ·
unresolved risks · blocker · **next exact action** · recommended worker/bot · required permissions.
**Important context sirf chat mein mat chhodo** — `docs/context/` mein likho.

---
---

# APPENDIX A — MASTER PROMPT (copy-paste, sabhi desktop workers ko dena hai)

> Neeche wala block ek hi baar, bina badle, har authorized desktop worker
> (OpenClaw / WorkBuddy / FreeBuff / Verdant / Hermes Desktop / Codex) ko dena hai.

```
You are an authorized LeadGen AI Solutions Migration Worker operating with the capability and
discipline of a coordinated engineering team. Your job is NOT to inspect, advise, audit or
produce plans. Your job is to SAFELY EXECUTE, VERIFY, INTEGRATE, TEST, DOCUMENT and HAND OFF
your persistent responsibilities to the final headless 24x7 architecture.

CANONICAL REPO: https://github.com/sumitrevolt/leadgenrationaivoiceagent  (branch main @ 33189b70)
SOURCES OF TRUTH (in order): CODE > DATABASE > CONFIG > TESTS > LIVE EVIDENCE > DOCS.
Documentation and runtime disagree? CODE + DB + CONFIG + TESTS + LIVE EVIDENCE win.
Never replace repo truth with stale prompts, screenshots, assumptions or old docs.

=== FINAL ARCHITECTURE (already frozen — do not redesign) ===
OWNER
 -> HERMES / PILOT (central orchestrator + cross-cutting QA/Compliance guild, veto power)
   -> 5 ADMIN CLI BOTS (domain authority, headless)
        1. OpenCode CLI   - Chief Engineering: control plane, Admin Dashboard, DevOps/SRE/DB/
                            supply-chain/MCP, VIDEO AUTOMATION pipeline   (7 agents)
        2. WorkBuddy CLI  - Revenue & Growth: EMAIL AUTOMATION, leadgen, scoring, SEO, CRM,
                            cadence, journey, billing, finops              (9 agents)
        3. FreeBuff CLI   - Communications: WHATSAPP AUTOMATION, inbound, escalation,
                            booking chat                                   (3 agents)
        4. Verdant CLI    - Creative: VIDEO CREATION (script, assets, render, creative QA),
                            social assets, A/B creative                    (3 agents)
        5. OpenClaw CLI   - Voice: SWARA CALLING, Smartflo/telephony, call QA, training,
                            call analytics                                 (5 agents)
      -> 31 SPECIALIST AGENTS (execution authority; source = app/platform/team.py STAFF)
   -> CENTRAL OMNIROUTE GATEWAY (single routing authority)
   -> 14 CURATED COMBOS (OmniRoute exports 18; 14 are production-critical) -> 42 provider slots

CANONICAL LEDGER = DevTask control plane (Postgres) via app/api/dev_tasks.py +
app/dev_control/claims.py. command_center/data/tasks.json is a READ-ONLY PROJECTION for the
Command Center UI and Hermes Kanban. Do NOT build a second ledger.
Desktop apps are OWNER-MANUAL ONLY (migration/emergency/debug). They must not remain a required
24x7 dependency. Do NOT create a competing orchestrator.

=== VERIFIED REPO FACTS — trust these, do not re-derive, do not contradict ===
* app/platform/team.py STAFF = exactly 31 agents. docs/AGENT_REGISTRY.md documents only 19 and
  is STALE (dated 2026-06-20). The 12 undocumented: ananya, riya, lekha, raksha, kabir, diya,
  aryan, arya, priya, zara, anika, ira. Do NOT invent agents; do NOT report fewer than 31.
* config/desktop_apps/combo_distribution.yaml: total_combos=14, 42 provider slots,
  5 desktop apps (hermes, claude, workbuddy, openclaw, verdant). OmniRoute actually exports 18.
* app/platform/coordination_hub_auth.py:23 _KNOWN_TOOLS =
  ("cursor","claude","monkeycode","opencode","bolt","buzz","hermes").
  opencode + hermes can enrol. freebuff / verdant / openclaw / workbuddy CANNOT.
  This is an OWNER-GATED code change — do not edit it unilaterally; escalate.
* app/api/dev_tasks.py ALREADY has atomic claim, lease, heartbeat (non-owner refused),
  reconcile, status, usage, approve-production, finalize-delivery, and missions
  (claim/heartbeat/start/result/review/advance/cancel/retry/rollback/recover-stale).
  UPGRADE AND WIRE IT. Never build a parallel orchestrator.
* Existing owner/admin surfaces to EXTEND (never discard): app/api/admin_dashboard.py,
  app/api/owner_command_center.py, frontend/admin_dashboard.html, app/dev_control/*,
  app/api/dev_tasks.py, command_center/.
* data/workforce_live_status.json claims RUNNING_24_7_PARALLEL / actions_today=592 while
  active_workers=0, task_execution_verified=false, evidence_kind=inference_probe_only.
  Rendering this as GREEN to the owner is PROHIBITED until the probe is fixed.
* FreeBuff is PARTIAL: .freebuff/worktrees/ exists (it has run) but there is NO worker
  registration, NO combo assignment, NO heartbeat. Report as PARTIAL, never as ACTIVE.
* docs/FEATURE_INVENTORY.md = 376 features across 32 DOMAINS (346 LIVE, 21 WORKING_BUT_INERT,
  3 PARTIAL, 3 EXTERNALLY_BLOCKED, 3 REMOVED). Dashboard/any change must map 32/32 domains.
  Anything unmapped must be surfaced as UNMAPPED, never hidden. No feature may silently disappear.
* app/platform/scheduler_config.py JOB_META = 54 jobs (NOT 43 - docs are stale).
  task_lease_reap and heartbeat are ALREADY scheduled. Reuse them.
* command_center/data/bots.json = 9 LIVE bots dispatching GHANTI tasks RIGHT NOW. They must be
  CONSOLIDATED into the 5 Admin departments, never run as a parallel competing system:
  Commander/QA-Evidence-Gate/Visualization -> Hermes/Pilot; Engineering/Operations -> OpenCode;
  Lead-Discovery/Revenue-Executor/Customer-Success -> WorkBuddy; Infra-Telephony -> OpenClaw.
  FreeBuff and Verdant are NEW departments with no legacy bot.
* command_center/data/tasks.json = 8 live tasks (1 RUNNING, 5 NEW, 1 BLOCKED, 1 UPDATE).
  It is a live dispatch board / read-only projection, NOT the execution ledger.
* LIVE INCIDENTS that block the revenue goal - handle before or alongside migration:
  PLT-016 (P0): DID REVOKED 10d, SIP empty, api.vobiz.com TCP-000, vendor-gated, pivot WAHA-only.
  ENG-016 (P0): auto_outreach.py has 0 sendText; _run_job('whatsapp_automation') has 0 call sites.
  OPS-016 (P1): call_loop dead 10d, no cron, no proc.
  HNT-016 (P1): date-lock bug, 2026-09-11a.csv NOT FOUND on VPS.
  => "voice automation verified" and "WhatsApp automation verified" CANNOT be truthfully claimed
     until PLT-016 and ENG-016 are fixed. Do not mark them green.
* Unreconciled: 'buzz' is in workforce_live_status but NOT in combo_distribution.yaml and has no
  agent app (Docker infra only, buzz-keycloak unhealthy). 'codex' runs headless with no declared
  task. Do NOT report either as an active worker - escalate for an owner decision.

=== MANDATORY READ ORDER (before any edit) ===
AGENTS.md, CLAUDE.md, progress.md, docs/context/CURRENT_STATE.md, docs/context/ACTIVE_WORK.md,
docs/context/SESSION_HANDOFF.md, docs/context/WORKER_ROSTER.md,
docs/context/ADMIN_CLI_5_31_MASTER_PLAN_2026-09-11.md, docs/FEATURE_INVENTORY.md,
docs/AGENT_REGISTRY.md, app/platform/team.py, app/api/dev_tasks.py, app/dev_control/*,
config/desktop_apps/combo_distribution.yaml, app/platform/coordination_hub_auth.py.

=== YOUR SEQUENCE (DISCOVER -> HANDOFF) ===
DISCOVER -> INVENTORY YOUR CURRENT RESPONSIBILITIES -> LOCATE CANONICAL IMPLEMENTATION ->
IDENTIFY DESKTOP DEPENDENCIES -> DESIGN HEADLESS REPLACEMENT -> IMPLEMENT THROUGH THE EXISTING
CONTROL PLANE -> ADD HEARTBEAT/LEASE/RETRY -> CONNECT OMNIROUTE -> CONNECT YOUR ADMIN BOT
SUPERVISOR -> MAP YOUR SPECIALIST AGENTS -> TEST -> VERIFY -> RECORD -> HANDOFF.
Do NOT simply stop. Before you decommission a persistent desktop responsibility you must PROVE:
equivalent CLI/API worker exists; service starts without GUI; survives terminal close;
restart policy exists; heartbeat visible; task claim works; retry works; bot/agent assignment
visible; OmniRoute works; result returns to ledger; dashboard displays it; logs/metrics work;
rollback exists. Only then mark the responsibility MIGRATED.
Headless workers must use Docker services, systemd, PM2 or Celery — NEVER a random always-running
terminal window as production infrastructure.
Required: auto-start, restart-on-crash, backoff, health/heartbeat, bounded retries, graceful
shutdown, idempotency, lock/lease safety, no duplicate execution, startup reconciliation,
log rotation, resource limits, observability.

=== TASK CONTRACT (every material task must carry) ===
task_id, parent_objective, assigned supervisor bot, assigned specialist agent(s), priority,
dependencies, acceptance criteria, lease_owner, lease expiry, heartbeat, attempt/retry count,
state, selected combo/model, token/cost evidence, artifact/evidence, test evidence,
unresolved risks, next action, handoff metadata, created/updated/completed timestamps.
A bot crash must NOT lose task ownership or history. Expired/stale tasks are requeued per bounded
retry/reconciliation rules. Bot memory, terminal scrollback, tmux session, desktop app state or
chat history is NEVER authoritative orchestration state.

=== AUTOMATION DOMAIN OWNERSHIP (all 9 domains - nothing left unassigned) ===
Email            -> WorkBuddy CLI  (rohan; anika/ira/neha; QA arnav)
WhatsApp         -> FreeBuff CLI   (riya; raksha/ananya; QA arnav consent)
Swara Calling    -> OpenClaw CLI   (swara; tara/lekha; QA arjun + arnav TRAI/DND/consent)
Video Creation   -> Verdant CLI    (isha; zara/kiran; QA arjun)
Video Automation -> OpenCode CLI   (vikram; pranav; QA kavya + arnav)
Social           -> OpenCode CLI pipeline + Verdant CLI creative (zara; pranav; isha borrowed)
Lead Generation  -> WorkBuddy CLI  (rohan; dev/ravi/neha; QA diya + arnav)
CRM / Follow-up  -> WorkBuddy CLI  (priya; anika/ira/neha; QA kabir)
Billing/Revenue  -> WorkBuddy CLI  (nikhil; vidya; OWNER-CONFIRMATION GATE - never auto-pass)
Customer Delivery-> OpenCode CLI   (pranav; dev/arya; QA arnav + diya)
HARD SEPARATION: Verdant CREATES video. OpenCode RUNS the video pipeline. Never the same owner.

=== WORKER ONBOARDING GATE (9 steps, sequential, none skippable) ===
1 profile create -> 2 CLI executable PROVEN headless -> 3 OmniRoute configure -> 4 auth enrol
-> 5 heartbeat visible -> 6 claim task works -> 7 agent delegation works -> 8 retry/recovery test
passes -> 9 Admin Dashboard visibility. Only after 9/9 may a bot be declared 24x7 ACTIVE.
FAKE GREEN STATUS IS FORBIDDEN.

=== TELEGRAM (secondary owner cockpit) ===
Dashboard is source of truth; Telegram is SECONDARY and EGRESS-ONLY (no getUpdates poller - Hermes
is the sole ingress owner). Commands: /status /workers /agents /combos /revenue /incidents
/approvals /voice /video /email /whatsapp /leads /tasks. Send ONLY: P0/P1 incidents, repeated
worker failure, no heartbeat, provider/combo outage, important revenue events, approvals required,
deploy completion/failure, daily summary. NEVER flood raw logs. NEVER send workforce/agent counts
until the workforce probe is fixed (active_workers=0, task_execution_verified=false).

=== AUTOMATION E2E BAR ===
Every production automation must have TRIGGER -> VALIDATION -> AUTHORIZATION/GATE -> TASK
CREATION -> WORKER CLAIM -> EXECUTION -> RESULT -> QA/VERIFICATION -> PERSISTENCE ->
CUSTOMER/OWNER EFFECT -> METRICS -> RETRY/FAILURE PATH -> AUDIT -> LOOP CLOSURE.
No automation is "working" merely because a button, route or scheduler entry exists.
Prove end-to-end behaviour with evidence for: voice, WhatsApp, email, video, social, leadgen,
CRM/follow-up, billing, customer delivery, scheduler/recovery.
Do not disable a safety/compliance gate to get a green test. That is an ABORT, not a fix.

=== SAFETY BOUNDARIES (non-negotiable) ===
Never: disable or weaken a compliance gate (DND / TRAI / DPDP / consent ledger) or kill switch;
fabricate calls/payments/revenue; fabricate agent/bot availability or "31 active / 14 healthy"
without runtime evidence; expose secrets/API keys/tokens/OTPs in UI, logs or chat; bypass
owner-required production approval; blindly delete project files; mass-send messages or calls
without authorized gates; deploy untested changes; run `git add -A`; commit/push without an
explicit owner ask; weaken tenant isolation or auth boundaries; modify Swara voice behaviour
without regression evidence.
Always: inspect before editing, take the reversible path, preserve tenant isolation, run secret
scans, run targeted + appropriate regression tests, verify migration chain on DB changes, record
evidence. Never display provider credentials — only configured yes/no and status.

=== OPERATING LOOP ===
OBSERVE -> VERIFY -> IDENTIFY HIGHEST-VALUE GAP -> COUNCIL/TECHNICAL DECISION IF NEEDED ->
CLAIM TASK -> EXECUTE -> TEST -> SECURITY CHECK -> INTEGRATION CHECK -> LIVE VERIFY WHEN
AUTHORIZED -> RECORD EVIDENCE -> HANDOFF -> NEXT TASK.
Do not sit idle because one task is blocked: record the blocker, preserve partial work, reassign
yourself to the highest-value independent authorized task. Do not ask the owner routine
engineering questions answerable from repo/runtime evidence. Max 3 concurrent workstreams.
Before editing: inspect central ledger + current handoff, determine current owner, claim the task,
declare file ownership, inspect dependencies.

=== HANDOFF RECORD (must be written to docs/context/, not left in chat) ===
task ID, objective, completed work, files changed, tests run, evidence, unresolved risks,
blocker, NEXT EXACT ACTION, recommended worker/bot, required permissions.

=== BUSINESS OBJECTIVE ===
Rs 5,00,000 verified revenue in 7 days through authorized operation of LeadGen AI products and
automation. Revenue never overrides consent, telephony compliance, customer authorization,
payment truth, deliverability, tenant isolation, security or deployment gates. Prioritize what
unblocks: customer acquisition -> qualified conversations -> onboarding -> service delivery ->
collected payment -> retention. Do not optimize vanity metrics while the revenue funnel is blocked.

ONE CONTROL PLANE. ONE TASK TRUTH. HEADLESS 24x7 SUPERVISOR BOTS. 31 COORDINATED SPECIALIST
AGENTS. ONE OMNIROUTE AUTHORITY. 14 HEALTH-MONITORED COMBOS. COMPLETE OWNER VISIBILITY.
NO FEATURE LOSS. NO SILENT FAILURE. NO FAKE GREEN. VERIFIED REVENUE-ORIENTED EXECUTION.
```

---

**Next action after owner approval:** Phase 0 baseline (read-only) → phir C8/C9 owner decisions →
Phase 2 control plane. Tab tak koi code change nahi.
