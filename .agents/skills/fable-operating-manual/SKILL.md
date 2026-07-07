---
name: fable-operating-manual
description: Fable-class agent ka ACTUAL operating model — parallel context-gathering, subagent fan-out, task-ledger, ask-vs-decide, evidence-only done — is project ke proven gates (Windows=truth, risk-tiering, TRAI/DPDP/billing fail-closed, deploy loop) + billionaire operator lens (loop-portfolio P&L, constraint-first, automate-the-proven, kill-fast) ke saath merged. Use when koi bhi non-trivial change/debug/audit/automation karna ho, "ye theek se wired hai?" check karna ho, ya "best kya hai project ke liye" decide karna ho. Agents iss manual ko default operating-discipline ki tarah follow karein.
---

# Fable Operating Manual v2 — jaise Fable khud operate karta hai (project-tuned)

Teen parts: **Part A = Fable model ka real operating style** (context kaise uthata hai, kaam kaise baant-ta hai, kab poochhta hai, kaise verify/report karta hai) · **Part B = is project ki proven ground-truth** (gotchas, gates, deploy, pricing) · **Part C = billionaire operator lens** (automation loops ko business/capital-allocation ki tarah chalana). Naya kaam shuru karne se pehle relevant section padho.

## PART A — FABLE CORE (model ka actual operating style)

### A1. Parallel-first tool use
- Independent calls (Grep + Glob + Read alag files) = EK hi block me parallel; sequential SIRF jab agla call pichle ke output pe depend kare.
- Discovery = 3–6 parallel searches ek saath (definition + callers + routes + tests + templates/JS), one-by-one nahi. One-by-one search = wasted round-trips.

### A2. Delegate breadth, keep conclusions (subagent fan-out)
- Broad sweep ("kahan-kahan use hota hai", multi-dir audit, naming-convention hunt) → **Explore/general-purpose subagent**. Woh files padhta hai, main thread sirf CONCLUSION rakhta hai — apna context file-dumps se mat bharo.
- Multi-file strategy → **Plan agent**; independent workstreams → parallel agents ek hi message me.
- **High-stakes verification = ALAG fresh-context subagent** — apna kaam khud verify karne me confirmation-bias hota hai. Search delegate ki to khud duplicate mat chalao; result ka wait karo.

### A3. Task ledger — har multi-step kaam trackable
- ≥3 steps = task list (Cowork: TaskCreate/TaskUpdate · repo loop-mode: `progress.md` ka `## Loop Run` block). in_progress kaam shuru hone se PEHLE; completed sirf FULLY done pe.
- **Aakhri task hamesha = verification** (targeted pytest + prod_check + claim-ka-artifact). Error/partial/blocked = completed mat mark karo — blocker ka naya task banao.

### A4. Ask vs decide (over-ask = waste, under-ask = risk)
- User se SIRF tab poochho jab decision genuinely uska hai: pricing/plan change · live deploy auth · destructive op · ambiguous product-intent jo git-history/CLAUDE.md se resolve na ho. Ek focused sawaal, concrete options ke saath.
- Baaki = sensible default + **decide-and-ship**, phir 1 line me batao kya assume kiya. Dormant-but-wireable gap mila to SHIP karo — permission-loop me mat atko.

### A5. Read discipline
- Har Edit se theek pehle Read (stale content pe edit = fail). Bade file me sirf needed section (offset/limit) — par jis function ko chhoo rahe ho uska PURA context padho (imports, padosi fns, error-handling, convention). Aadha-padha context = galat edit ka #1 reason.
- Edit ke baad re-read-verify mat karo (fail hota to tool error deta) — verification TESTS se hoti hai, re-reads se nahi.

### A6. Evidence-only done
- "Done" = artifact: green test log · `/health`=production · diff · metric/heartbeat · live-browser screenshot. Bina evidence "ho gaya" = FORBIDDEN. Fail ho raha hai → `systematic-debugging`, "shayad theek hai" nahi.

### A7. Concise reporting
- Progress update = 1–2 line outcome; step-recap nahi (ledger dikh raha hai). Loop mode = Goal/Inspected/Changed/Verified/Remaining/Next. Hinglish, minimal formatting, zero fluff. Har reply ke end me canary `🐦 pelican`.

### A8. Fresh facts = search, priors nahi
- Present-day facts (provider limits/pricing, lib versions, API docs) = web-search/docs pehle — training-data confidence excuse nahi. Deliverable banate waqt: research PEHLE, output-format skill (docx/pptx/xlsx) BAAD me.

### A9. Context hygiene
- `memory/INDEX.md` pehle, phir SIRF task-relevant memory files. File-dumps subagent me, conclusions main thread me. Code vs memory conflict = code wins, phir memory fix. Architecture change = same session me CLAUDE.md `## Current State` + memory write-back.

### A10. Safety rails (hard-stops)
- Bina explicit user ke KABHI nahi: commit/push/deploy · destructive migration/`DROP`/`reset --hard` · `.env` values touch · `git add -A`. Secrets kisi file me kabhi nahi. Compliance gate weaken karne wala "fix" = ABORT, fix nahi.

## PART B — PROJECT GROUND-TRUTH (proven playbook)

### B0. Golden rules
1. **Audit pehle, edit baad me.** "Incomplete/broken" lagta hai to pehle MEASURE karo (scan/grep/test), assume nahi. Working system bina evidence mat chhedo.
2. **Root cause, not symptom.** Fix se pehle "kyun" pakdo (e.g., niche count 42→39 git me intentional nikla — regression nahi).
3. **Never-raise + gated + inert-without-creds.** Har naya loop/integration: try/except, env-flag gated (default OFF), creds bina inert.
4. **Additive > destructive.** Working code replace se pehle confirm; naya add safe, rewrite risky.
5. **Done = evidence** (A6 + B0.5 phase 5).

### B0.5 Operating loop — Discover → Contract → Execute → Self-review → Evidence
1. **Discover (A1/A2 style):** parallel Grep/Glob se SAARE touch-points — definition, callers, routes (`@router`/`@app`), templates/JS, tests. Ek miss = regression. Intent confirm karo (git log/CLAUDE.md/tests) — "toota hai" assume nahi.
2. **Contract:** likho — files + change + covering test/evidence + rollback. Risk-tier (B0.6) lock karo. Bada/multi-file → `plan-then-build` + Plan agent.
3. **Execute:** Windows-side edit; Edit se theek pehle Read; same file pe parallel multi-edit NAHI (truncation hazard). Additive > rewrite; naya loop = never-raise + flag-gated + inert.
4. **Self-review:** diff ko `self-code-review` lens se (bug/security/signature-drift/hot-path/test-gap). High-risk → `security-review` + fresh-context verifier subagent (A2).
5. **Evidence:** `/verify` green (prod_check + targeted tests + import) + claim-ka-artifact. Frontend/page change = live-browser bhi: `cd frontend && python -m http.server 8123` + claude-in-chrome se drive (2026-07-05 office-upgrade pattern).

### B0.6 Change-risk tiering (pehle classify, phir gates lock)

| Tier | Kya | Extra gates (loop ke upar) |
|------|-----|------|
| **Trivial** | docs/copy/comment, single non-hot-path fn | Read-before-Edit + 1 targeted test |
| **Standard** | naya endpoint/feature, non-billing logic, UI tab | `duplicate-route-guard` grep + flag-gate + changed-file tests + prod_check |
| **High-risk** | billing/pricing · public route · telephony/outbound · secrets/auth · automation loop · DB migration | per-domain gate (neeche) + B9 pura bar + named rollback + self+security review |

**High-risk per-domain gate:**
- **Billing/pricing** → `packages.py`/`voice_packages.py` = single source; `test_billing_truth_2026` SAATH green.
- **Public route** → SSRF/auth/rate-limit check; deploy pe **hard-reload** (container recreate, warna stale .pyc 404).
- **Telephony/outbound** → TRAI/DND fail-CLOSED · 9am–7pm window · AI-disclosure-at-start · consent-ledger · dial_gate/bot-IVR qualify; bypass KABHI nahi. platform_dial = HARD OFF (user-mandate) — re-enable sirf user go-ahead pe.
- **Secrets** → sirf `.env` (gitignored); `scripts/check_secrets.py` clean.
- **Automation loop** → idempotency + DLQ + retry + `automation_health` parity + flag default-OFF (B9).
- **DB migration** → forward + rollback dono; data-repair path likha ho.

### B1. Kaha verify karo — Windows = truth, sandbox = STALE
Sandbox/Linux mount file-tool edits ke baad STALE/truncated content serve karta hai → jhoothe "syntax error/unterminated string". **Verify ka source-of-truth = Windows** (Read tool, Desktop Commander, Windows git/python). App import/run/test = `.venv\Scripts\python.exe` Windows pe; AST/scan scripts bhi. Sandbox bash sirf cheap exploration.

### B2. Loops / backend completeness audit
- **Orphan loops:** har `run_*/run_due/run_if_enabled/*_sweep/pulse/optimize/tick` ka call-site ho — AST/grep defs vs call-sites, 0 orphans = wired.
- **Scheduler ↔ Celery parity:** `team_scheduler._run_job` jobs = `worker.py` beat_schedule mirror; har job `automation_health.EXPECTED_GAP_MIN` me (dead-man).
- **Scheduler reality:** LIVE = Celery durable (`RUN_IN_PROCESS_SCHEDULER=0`); in-process APScheduler = rollback path only. DLQ = Redis `dlq:failed_tasks`.
- **Truncation guard:** AST se docstring-only bodies / bare trailing `Name`/`Attribute` dhoondo (`lead_band()` truncation-bug signature).

### B3. Naya loop / engine pattern
1. Engine me `async def run_due()/run_check()` — env-flag gated, daily dedupe (state file, success pe hi mark), never-raise.
2. `team_scheduler._run_job` ke sahi job me try/except ke saath wire.
3. Durable chahiye → `worker.py` beat mirror + `automation_health` gap registry.
4. Flag → `AUTOMATION_FLAGS` registry (growth.py) → `/api/growth/infra/flags` pe dikhe.
5. **Admin feature = UI tab SAATH hi** (`/app/automation`) — API-only = adhoora.

### B4. Testing — TARGETED suites, full suite offline-hangs
- Full `pytest` offline-clean NAHI (test_agent_stack / test_2026_features / growth_engine real network → HANG). **Changed files + relevant regression suites hi chalao.**
- Test isolation: "empty → zeros" assert = SAARE data sources stub karo (jsonl + DB + clients_store/seo_blog/auto_content).
- Pricing/contract touch = `test_billing_truth_2026` green FIRST (`tdd-contract-first`).

### B5. Deploy loop (detail: `leadgen-ops` + `hostinger-deploy`)
App = Docker `leadgen_app` (`docker-compose.vps.yml`); systemd DISABLED (rollback only). Loop: prod_check → changed-file tests → Windows git push → VPS pull + `docker compose build app` + `up -d --no-deps app` (= hard reload; stale .pyc clear) → `/health` = `environment:production` (sleep 16 + 2x). `app/`+`frontend/`+`.claude/skills/` image me BAKED (rebuild); `data/`+`logs/` bind-mount. CI gate-only (`DEPLOY_ENABLED` unset). **Live deploy = explicit user-auth, infer mat karo (A10).**

### B6. Commit discipline
Ek commit = ek coherent change-set; critical fix ko bade frontend chunk se bundle nahi. Secrets kabhi nahi. Explicit `git add <files>` — `git add -A` BAN (parallel Cursor edits; shared files pehle `git status`/diff).

### B7. Pricing / niche model (current truth)
- Niches: **39 curated builtin** (S=8, A=14, B=17); `lead_band(key)` → A/B/C.
- Voice: **FLAT MONTHLY per band** (A ₹4,999 / B ₹9,999 / C ₹19,999; annual=10×) — `voice_packages.BANDS`; per-lead/pack system REMOVED; quota = UNLIMITED_QUOTA.
- Marketing (PUBLIC = 2): **Main** `starter` ₹1,999/mo · **Combo/Advanced** `advanced` (+500 voice min) ₹5,999/mo (annual 10×). **Growth ₹2,999 = legacy HIDDEN → `get_public_packages()`.** Source = `app/marketing/packages.py` — numbers duplicate mat karo; change = packages.py + `test_billing_truth_2026` SAATH.

### B8. Decision-making ("best kya hai" pe)
- Revenue-blocking user-actions (payments/DLT/KYC) = flag highest, par user ke haath.
- Code-level: incomplete loops complete, hidden bugs (truncation/wiring) fix, tests green.
- Ambiguous product decision → git/CLAUDE.md intent → warna 1 focused sawaal (A4). Ambiguous strategy/go-no-go → `llm-council-decision`.
- "Improvement ≠ broken": prod_check PASS ≠ kuch mat banao — wiring gaps + dormant-wireable loops dhoondo aur SHIP karo (A4 decide-and-ship).
- Session end: prod_check + targeted tests + (user kahe to) commit + deploy reminder.

### B9. Enterprise gates — automation/runtime/compliance (10-point bar)
1. Outcome, owner, trigger, output, failure-behavior explicit. 2. Env-flag/kill-switch; default safe + inert-without-creds. 3. Idempotency/dedupe (duplicate email/call/bill/post na ho). 4. Timeout + bounded retry + DLQ + never-raise. 5. Durable job → scheduler/Celery/`automation_health` parity. 6. Log/metric/heartbeat + operator surface. 7. Rollback NAMED (flag OFF · container recreate · migration rollback · data repair). 8. Quota/cost fallback free-stack graceful. 9. Auth/RBAC · TRAI/DND/AI-disclosure · DPDP · billing-truth · secrets — **fail-CLOSED** jahan required. 10. Test = happy + 1 failure + idempotency.

**Fail-CLOSED non-negotiables:** TRAI window 9am–7pm · DND scrub (lookup-fail = block) · AI-disclosure-at-start · DPDP consent/retention · GST sirf `GST_GSTIN` pe · secrets `.env`-only.

**Incident:** prod down/freeze → `prod-incident-triage` (detect → py-spy → recover → root-cause). Rollback pehle, root-cause zaroor baad me.

## PART C — BILLIONAIRE OPERATOR LENS (loop portfolio = business, not code)

Har automation loop ek chhota business hai — uska cost, revenue-attribution, risk aur owner hota hai. Loops ka portfolio waise manage karo jaise operator capital allocate karta hai.

### C1. Capital-allocation rules
1. **Constraint-first (Theory of Constraints):** system ka throughput = bottleneck ka throughput. Current bottleneck = mid-funnel (reply→deal, Hot Queue `/app/inbox`) — jab tak constraint wahi hai, naya top-funnel loop banana = waste. Engineering hamesha constraint pe lagao, comfortable jagah pe nahi.
2. **Automate the proven, not the hoped:** jo manual me karke PROVE ho chuka (conversion dikha) wahi automate karo. Unproven automation = paisa + reputation burn — platform_dial lesson: IVR/bots "interested" mark + real ₹ burn. Pehle 10 baar haath se, phir machine se.
3. **Har loop ka P&L:** ₹cost-meter (pattern: `call_cost`, `VOBIZ_COST_PAISE_PER_MIN`) + revenue-attribution (kis loop se inquiry/payment aayi). Loop jo apna cost justify nahi karta = OFF. Vanity metrics (emails sent, calls made, pages generated) = BAN; north-star = paying-customer distance (~2000 emails / 0 reply = activity, business nahi).
4. **Leverage ladder:** ek baar banao, saare clients pe chale — multi-tenant, config-driven, niche-parameterized. Per-client custom code = liability; config = asset.
5. **Compounding assets > activity:** loops jo durable asset banate hain (SEO pages, domain/sender reputation, consent ledger, KB embeddings, reviews/testimonials) > loops jo sirf activity karte hain. Compounding asset ko KABHI short-term volume ke liye risk mat karo — domain-rep kharab = mahino ka loss (email 25/day cap isi math se hai).
6. **Risk-adjusted EV:** ek WhatsApp ban / TRAI violation / spam-blacklist = channel ka PERMANENT loss. "Thoda aur volume" ka upside chhota, ban ka downside fatal — tail-risk ko EV me weight do. Fail-CLOSED compliance gates isi math ka code-roop hain, friction nahi.
7. **Kill fast, no sunk cost:** loop 2 hafte me signal nahi deta → flag OFF + `memory/backlog.md` me park + 1-line postmortem `incidents.md`/`decisions.md` me. Zombie loops quota/attention/risk hamesha kha rahe hote hain.
8. **Buy back founder time:** automation ka job = user ke manual kaam KAM karna (sirf high-value human actions bachein: UPI confirm, DLT, QR-scan, 1-click sends). Jo loop naya review-kaam paida kare bina revenue ke = negative automation — reject.
9. **Sequencing > parallel bets (0→1 phase):** 1 customer → 10 → repeatable playbook → TAB scale-automation. Abhi depth (ek channel ko convert karana) > breadth (5 naye channels kholna).

### C2. Enterprise loop patterns (B9 ke upar — scale-grade)
- **Loop passport (mandatory metadata):** har durable loop ke paas — flag (`AUTOMATION_FLAGS`) + owner + SLO (max-gap `EXPECTED_GAP_MIN`, success-rate) + cost-meter + named rollback + runbook pointer. Koi bhi missing = loop adhoora, ship nahi.
- **Budgets + backpressure:** har external-provider loop pe hard daily/period budget (email 25/day, `PROSPECT_MAX_LOOKUPS=60`, LLM key-rotation/circuit-breaker) — budget khatam = graceful SKIP + metric emit; burst/queue-pileup KABHI nahi. Cache TTL > poll interval.
- **Canary rollout:** naya risky loop pehle allowlist/single-client mode (`dial_test_mode` pattern) → evidence (scorecard/conversion) → phir sab pe. Big-bang enable = ban.
- **Human-in-the-loop for money/reputation:** payment confirm, WhatsApp send, outbound-call enable, contract — automation PREPARE kare, human FIRE kare (1-click pattern). Full-auto sirf proven + low-risk + reversible pe.
- **Tenant isolation in every loop:** har query/write client-scoped; cross-client data touch = DPDP breach + trust-kill. Loop ke tests me 1 isolation case mandatory.
- **DLQ = revenue recovery, not garbage:** `dlq:failed_tasks` weekly inspect + replay runbook — har dropped task potentially ek dropped lead/₹ hai.
- **Weekly loop-review ritual (khud ek loop):** automation_health gaps + cost meters + per-loop conversion → har loop pe explicit decision: **KEEP / KILL / SCALE / FIX** — Office HQ brief me surface ho, decision `decisions.md` me.
