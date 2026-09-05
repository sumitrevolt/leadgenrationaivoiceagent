# MULTI-AGENT WORKFLOW — LeadGenAI Execution OS

> **Status:** CANONICAL (v1.0 · 2026-08-31)
> **Scope:** Ye document batata hai ki *WorkBuddy agent team* kaise kaam karegi is repo par.
> Ye **koi naya agent taxonomy nahi banata** — ye existing assets ko ek execution contract me bind karta hai.
> **Code vs doc conflict = code wins, phir ye doc fix karo.**

## 0. Kya-kya pehle se exist karta hai (reuse karo, duplicate mat karo)

| Asset | Role | Is workflow me kya hai |
|---|---|---|
| `HERMES_AGENT_ROSTER.yaml` | 31 agents → 8 Hermes bots | **Domain ownership map.** Workstream boundaries yahin se derive hote hain. |
| `agent-os/agents/<key>.md` | 33 agent specs (code-derived) | Agent spawn karte waqt **persona + KPI + gates** ka source. |
| `agent-os/standards/**` | backend / voice / billing / frontend / global | Har build task ke spawn prompt me **inject karne wale standards**. |
| `docs/LOOP_ENGINEER.md` | Single-agent loop spec (8 hats, 15-item checklist) | **Har task ke andar** execution method. Ye doc uske *upar* coordination layer hai. |
| `progress.md` | Loop ledger (9-field + Date) | Append-only evidence ledger. Har DONE task ka entry yahan. |
| `_tasks_sync.json` | Legacy task board (`REV-xxx`) | **Read-only / superseded.** Naye tasks `T-WSxx-nnn`. Purane entries rewrite mat karo. |
| `docs/HANDOFF.md` | Cold-start infra map | Cold start pe sabse pehle. |
| `scripts/prod_check.py` | Gate | Har integration ke pehle aur baad. |

**Division of labour (important):**
- **Hermes bots = runtime plane** (app ke andar chalne wale scheduled staff). Ye workflow unhe *replace* nahi karta — unke output ko *consume* karta hai.
- **Workstream agents = engineering plane** (WorkBuddy subagents, is repo par code/config dok). Ye doc inhi ko govern karta hai.

---

## 1. Layer model

```
L0  OWNER (human)              — sirf gated decisions (§7). Kabhi auto-bypass nahi.
L1  PILOT (main agent)         — triage, routing, state transitions, integration. BUILD NAHI KARTA.
L2  WS LEAD  ×3 max            — ek workstream = ek lead subagent = ek branch. Execute karta hai.
L3  CROSS-CUT REVIEWERS        — QA / SEC / VERIFY. Short-lived spawn. Builder ≠ reviewer (hard rule).
L4  RUNTIME (Hermes bots)      — existing in-product staff. Is workflow ke spawn pool me NAHI.
```

**Concurrency cap = 3 active workstreams** (CLAUDE.md §3.2). Reviewers/verifiers is cap me count nahi hote — wo L3 hain aur serial chalate hain.

> PILOT ka execution work karna = oversight loss. Agar PILOT ko khud code karna pade, to pehle ek WS lead spawn karo.

---

## 2. Workstream roster (Hermes bots se derived)

| WS | Workstream | Lead persona | Hermes bot | Primary ownership (paths) | Reviewer |
|---|---|---|---|---|---|
| `WS-01` | **Engineering / Integrations** | vikram (Code Upgrader) | `engineering_sre` | `app/**` (non-voice), `scripts/**`, `alembic/**` | arjun + pranav |
| `WS-02` | **Voice / Swara** | tara (Voice Infra Ops) | `voice_swara` | `app/voice_agent/**`, `app/telephony/**` | arjun + arnav (compliance) |
| `WS-03` | **Funnel / Lead Intel** | rohan (Leads Manager) | `lead_intelligence` | `app/lead_scraper/**`, `app/prospecting/**`, `data/prospects/**` | diya (data integrity) |
| `WS-04` | **Outreach & Conversation** | anika (Cadence Mgr) | `outreach_conversation` | `app/automation/cadence/**`, `app/integrations/whatsapp|email_sender/**` | arnav (DPDP/opt-out) |
| `WS-05` | **Content / SEO** | ravi (SEO Scout) | `marketing_content` | `frontend/marketing/**`, `app/seo/**`, `frontend/**/*.html` (marketing tabs) | isha |
| `WS-06` | **Infra / SRE** | pranav (SRE) | `engineering_sre` | `docker-compose.vps.yml`, `deploy/**`, `infrastructure/**`, `.github/workflows/**` | aryan + arnav |
| `WS-07` | **Revenue Ops** | nikhil (Revenue Ops) | `revenue_cro` | `app/billing/**`, `app/crm/**`, `data/revenue/**` | vidya (FinOps) |
| `WS-08` | **QA / Verification** | arjun (QA Engineer) | `qa_analytics_finance` | `tests/**`, `evals/**`, `scripts/agent_tester.py` | lekha (analytics) |
| `WS-09` | **Security / Compliance** | arnav | *(cross-cutting)* | `scripts/check_secrets.py`, `.env*` (kabhi commit nahi) | pranav |

**Sirf 3 WS ek saath ACTIVE.** Baaki QUEUED.

---

## 3. Task lifecycle

```
INBOX → TRIAGED → SPEC'D → ASSIGNED → BUILDING → VERIFYING → REVIEW
                                                        ↓         ↓
                                                    INTEGRATE ← (pass)
                                                        ↓
                                                      DONE
   Side states (kisi bhi stage se): BLOCKED · FAILED
```

**Transition ownership: PILOT.** Agent khud status change nahi karta — wo handoff bhejta hai, PILOT transition karta hai.

| State | Meaning | Allowed to hold |
|---|---|---|
| `INBOX` | Signal aaya (owner request / watchdog / test fail), triage nahi hua | PILOT |
| `TRIAGED` | Priority P0–P5 + WS assigned + owner-impact likha gaya | PILOT |
| `SPEC'D` | Acceptance criteria + affected-surface list + rollback likha gaya | PILOT (+arch spawn) |
| `ASSIGNED` | WS lead spawn hua, branch/ownership locked | WS lead |
| `BUILDING` | Code change chal raha hai, periodic comments | WS lead |
| `VERIFYING` | Targeted pytest + `prod_check.py` + `check_secrets.py` chal rahe | WS lead → arjun |
| `REVIEW` | Cross-role review (builder se alag agent) | L3 reviewer |
| `INTEGRATE` | PILOT merge/integration karta hai, regression sweep | PILOT |
| `DONE` | Evidence ledger entry ho chuka | — |
| `BLOCKED` | Precise blocker + kya chahiye | koi bhi |
| `FAILED` | Approach galat nikla; reason capture; retry alag task | PILOT |

**Mandatory comments (agent ke liye):** start · blocker · handoff · completion. Chup agent = stuck agent — 1 follow-up ke baad PILOT usse shutdown karta hai aur task reassign karta hai.

**ID scheme:** workstream `WS-0n`, task `T-WS0n-nnn` (e.g. `T-WS02-014`). Legacy `REV-xxx` = read-only archive.

---

## 4. Artifact contract

Har task ka predictable output root — **spawn prompt me exact path dena zaroori hai**:

```
_work/<WS-ID>/<TASK-ID>/
    spec.md            # acceptance criteria + affected surfaces + rollback
    changed_files.txt  # exact paths, one per line
    tests.txt          # exact commands chalaye gaye
    evidence.md        # actual output (pass counts, health status, SHA)
    handoff.md         # 5-field handoff (§5)
```

Artifact root repo me committed hai (`_work/README.md`), par task dirs `.gitignore`d — evidence `progress.md` + `docs/` me rehta hai, scratch nahi.

---

## 5. Handoff protocol (5 fields — mandatory)

Har handoff me ye 5 cheezein honi chahiye. `handoff.md` + `SendMessage` dono me.

1. **What was done** — kya banaya/change kiya, ek paragraph.
2. **Where artifacts are** — exact file paths (`_work/...` + repo paths).
3. **How to verify** — exact commands + expected result.
4. **Known issues** — kya adhura/risky hai, chhupana mana.
5. **What's next** — receiving agent ke liye clear next action.

**Bad:** "Done, check the files."
**Good:** "Jio lane-filter `app/telephony/trunks.py` me add kiya (`Trunk.lanes`, promo fail-close). Verify: `.venv\Scripts\python.exe -m pytest tests/test_jio_sip_tenant.py -q` → 13 passed. Known issue: Jio DID non-140 hai, promo lane pe kabhi nahi chalega (TRAI). Next: arnav compliance sign-off."

---

## 6. Spawn contract (Agent tool prompt skeleton)

Har WS lead ko spawn karte waqt ye blocks **zaroori** hain:

```
CONTEXT      — repo root, current branch, task ID, kyun kar rahe hain
SCOPE        — exactly kaunse files; inke bahar mat jao
PERSONA      — agent-os/agents/<key>.md padho; uske KPI + gates follow karo
STANDARDS    — /inject-standards: <agent-os/standards/...> (task ke hisaab se)
OWNERSHIP    — sirf apne WS ke paths (§2 table). Doosre WS ke files = read-only.
DoD          — CLAUDE.md §6 + docs/LOOP_ENGINEER.md 15-item checklist
ARTIFACTS    — _work/<WS-ID>/<TASK-ID>/ (spec/changed_files/tests/evidence/handoff)
REPORTING    — comments at start · blocker · handoff · completion (SendMessage → PILOT)
FORBIDDEN    — commit/push/deploy · .env edit · compliance gate weaken ·
               duplicate route/page · cross-tenant data · fabricated evidence
STOP         — DoD prove ho jaye YA blocker clearly documented ho
```

---

## 7. Escalation — OWNER gate (kabhi auto nahi)

Sirf inme human authorization chahiye; baaki sab PILOT decide karta hai:

- OTP / CAPTCHA / KYC / banking / UPI credit confirmation
- Payment, invoice issuance, legally binding acceptance
- `git push`, deploy, production data mutation
- Naye paid provider/secret procurement (free-AI mandate hai)
- Production outbound calling enable karna (kill-switch / budget arming)
- Irreversible destructive action

**Fail-closed rule:** agar koi action is list me aata hai aur owner available nahi → task `BLOCKED` with precise ask. Skip nahi, guess nahi.

---

## 8. Conflict control

1. **File ownership map (§2)** — ek path ka ek hi writer. Doosre WS us path ko sirf padh sakte hain.
2. **Single-writer rule** — do agents kabhi ek hi file ko ek saath edit nahi karte. Overlap mile → PILOT ek ko BLOCKED karta hai.
3. **Pre-flight grep (mandatory before any build):**
   - duplicate route: `Grep` across all split routers (FastAPI first-route-wins silently shadows)
   - callers of the symbol you're changing
   - existing tests for that surface
4. **Branch discipline:** `ws/<id>-<slug>`. `main` par direct uncontrolled edit mana.
5. **Cross-system checklist** — har change ke baad check karo: callers · routes · tests · scheduler (`team_scheduler.py` + beat) · workers · Postgres/PgBouncer · Redis/DLQ · Qdrant · voice **dono** paths (`telecaller_brain` + `vobiz_stream`) · 3 customer dashboards · admin UI · billing (`packages.py` truth) · compliance gates.

---

## 9. Evidence standard (DONE ka matlab)

Task `DONE` tabhi jab:

1. Targeted pytest green (naya behaviour = RED-first test pehle).
2. `scripts/prod_check.py` = `[OK] ALL CHECKS PASSED`.
3. `scripts/check_secrets.py` clean on the diff.
4. Duplicate-route grep clean (route count unchanged unless intended).
5. Affected UI surface actually load karta hai (API-only = incomplete).
6. `progress.md` me 9-field entry (Date · Goal · Inspected · Problems Found · Changed · Tests Run · **Verification Evidence** · Risks · Remaining · Next Highest Priority).

**Forbidden phrases:** "should work" · "probably fixed" · "audit passed" (without proof) · fabricated test/deploy/payment/call/customer claims.

---

## 10. Cadence

| Cadence | Kya hota hai | Kaun |
|---|---|---|
| On signal | Triage + route + spawn | PILOT |
| Per task | build → verify → review → integrate | WS lead → L3 → PILOT |
| Daily 08:30 IST | Triage sweep: overnight watchdogs, DLQ depth, failed jobs, revenue ledger, top-3 reprioritization | PILOT (automation) |
| Daily 18:30 IST | Day digest: DONE/Blocked/Evidence/Next — owner visibility | PILOT (automation) |
| Hourly | Health/readiness watchdogs | **Hermes runtime (existing — duplicate mat karo)** |
| Weekly Fri | Hardening loop: deps (aryan), DR-restore drill (pranav), compliance posture (arnav) | PILOT routes |

---

## 11. Anti-patterns (inse bacho)

- **PILOT ka khud build karna** → oversight chala jaata hai.
- **Review skip** → 3–5 tasks ke andar quality drift pakka.
- **Bina artifact path ke spawn** → kaam milta hi nahi.
- **Silent agent** → coordination blind spot; assume stuck.
- **Capability mismatch** (e.g. browser test aise agent ko jiske paas browser nahi) → pehle capability verify karo.
- **Ek hi cheez do agents ko dena** → PILOT pehle existing task list scan karta hai.
- **Compliance gate ko "fix" ke naam pe weaken karna** → ABORT, fix nahi.

---

## 12. First-run activation sequence

```
A. Cold-start read      → CLAUDE.md · docs/HANDOFF.md · progress.md (tail) · _tasks_sync.json
B. True-state read      → prod_check.py + git status + /health check
C. Top-3 gaps           → P0→P5 ranking, evidence ke saath
D. Board                → docs/AGENT_BOARD.md me WS + tasks + owners
E. Spawn                → max 3 WS leads (§6 spawn contract)
F. Execute              → build → verify → review (builder ≠ reviewer)
G. Integrate            → PILOT merge + regression sweep + prod_check
H. Record               → progress.md 9-field entry
I. Re-prioritize        → agla highest-value task, loop continue
```

**Owner work preserve karo.** Kabhi `reset --hard`, force-push, ya environment destroy mat karo sirf clean state paane ke liye.

---

## 13. Relation to `docs/LOOP_ENGINEER.md`

- `LOOP_ENGINEER.md` = **ek task ke andar** kaise sochna hai (8 hats, 6-step loop anatomy, 15-item checklist).
- Ye doc = **ek se zyada tasks/agents** kaise coordinate hote hain (ownership, lifecycle, handoff, review, gates).
- Dono ek doosre ke superset nahi — dono lagu hote hain.
