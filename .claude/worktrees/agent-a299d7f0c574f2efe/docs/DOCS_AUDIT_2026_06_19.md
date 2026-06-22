# Docs Audit + Knowledge→Code Enhancement (2026-06-19)

> Scope: har web-sourced research `.md` doc ko ACTUAL code se cross-check kiya (4 parallel
> read-only audits: competitor/GTM · RAG/agents/repos · infra/reliability/roadmap · doc-dedup).
> Goal: doc knowledge se project enhance + duplicate docs merge + unnecessary remove.

## Headline finding
**Code docs se AAGE hai.** Competitor/infra research docs me jo "gaps/TO-BUILD" likhe the un me se
**~sab already BUILT + routed + mounted** hain (modules doc-date ke baad likhe gaye, doc update nahi hua).
Isliye "enhance" ka asli kaam = (1) docs ko reality se match karao, (2) duplicate/scratch docs hatao,
(3) jo chand genuinely DORMANT code items the unhe wire karo. Naya free-stack feature banana **almost
kuch nahi** bacha — baaki sab DLT/telephony/paid/paperwork (external-blocked) ya sirf `.env` flag-flip.

---

## SHIPPED is session me (additive, verified — prod_check green, 8/8 chatbot tests pass)

### 1. Dormant CRAG module wired (real code win)
- `app/agents/agentic_rag.py` (`get_agentic_rag()`) ke **zero call-sites the** — flag `USE_AGENTIC_RAG`
  set karne pe bhi kuch nahi hota tha (inert). `docs/RAG_KnowledgeGraph_Agentic.md §2` ne kaha tha
  "wire where `kb.retrieve` used" — kabhi hua nahi.
- **Wired into `app/marketing/chatbot.py`** (public widget/FAQ bot — TEXT path, latency-tolerant).
  Corrective loop (grade→query-rewrite→retry→grounded answer) **sirf empty-KB path pe** chalta hai:
  common path (context mil gaya) bilkul unchanged, zero extra latency. Gated `USE_AGENTIC_RAG=1`
  (default OFF = byte-identical), bounded (20s), never-raise, output-guardrail respected.
- **Voice path me JAAN-BUJH ke NAHI** daala — `telecaller_brain._kb_facts` live call turn pe hai
  (executor + hard timeout by design); 1-2 extra LLM round-trips wahan latency todte. Text path = sahi ghar.
- Tests: `tests/test_chatbot_guardrails.py` me 3 naye (gated-off byte-identical · grounded short-circuit · not-grounded fall-through). **Enable karne ke liye:** prod `.env` me `USE_AGENTIC_RAG=1`.

### 2. Stale pricing fix (GTM copy bug)
- `docs/Marketing_Kit_LeadGenAI.md` §7 + funnel-range purane daam dikhata tha
  (Starter ₹2,999 / Growth ₹5,999 / Advanced ₹11,999). **Theek kiya → 1199 / 2999 / 6999**
  (`app/marketing/packages.py` = source-of-truth). Live website pehle se sahi tha (API se fetch),
  bug sirf is copy-doc me tha.

### 3. Doc cleanup — 20 zero-reference docs removed (git rm; har ek ref-checked)
Round 1 (12): `_route_candidates_all/growth`, `_route_inventory`, `_route_safe_to_delete`,
`_route_usage_method` (5× route-reduction scratch) · `COORDINATOR_SKILL_BUILD_SUMMARY` ·
`SKILL_REVIEW_2026_06` · `GSC_SUBMIT_TODAY` · `FEATURE_TRIAGE_AUDIT` · `PROD_GAPS_2026_06_10_BATCH` ·
`Competitor_Infra_Research` · `legacy/production_readiness_report`.
Round 2 (8 more, superseded + zero-ref via `git grep`): `Infra_BestStack_GapAnalysis`,
`SAAS_INFRA_GAP_ADDITIVE`, `Infra_Upgrade_Activation_Runbook`, `AgentVerse_MultiAgent_Research`,
`Backend_Reliability_EngineerAgents`, `PHASE7_QUICK_START`, `PRODUCTION_HARDENING_GAP`, `COPY_PASTE_LAUNCH`.
KEPT (referenced, churn not worth it): `PHASE6_DEPLOYMENT_GUIDE` (verify script), `Automation_Marketing_Repos`
+ `LeadGen_Competitor_Repos` + `ROADMAP_2026...` (CLAUDE.md/AGENTS.md), launch checklists (EXECUTE_LAUNCH_NOW.sh).

### 4. Orphan modules wired (additive + defensive, inert-without-dep, tested)
- `seo_tools` (advertools SEM matrix) → `ads_copy.campaign_plan` (new `keyword_matrix` field; `[]` without
  advertools, active on VPS where it's opt-in-installed). `to_markdown` (MarkItDown) → `onboarding`
  KB-seed fallback (jab deep_extract <150 chars de — PDF brochure/JS-thin page). Dono never-raise.

### 5. External-service circuit breaker (net-new, gated OFF, 6 unit tests)
- `app/infrastructure/circuit_breaker.py` — reusable async breaker (CLOSED→OPEN→HALF_OPEN). Wired into
  Pollinations image fetch (`ai_image.fetch_image_bytes`): outage pe har call 45s wait na kare. Gated
  `CIRCUIT_BREAKER=1` (default OFF = pass-through, byte-identical). Registered in `AUTOMATION_FLAGS`.
  GAP_ANALYSIS §3.3 ka reliability gap (free_ai ke alawa baaki externals) ab addressable.

### 6. prod_check GREEN restored
- `CONSENT_CONFIRM` dead-flag (deferred TRAI feature) ko `automation_wiring_audit.RESERVED_FUTURE` me daala
  (`HERMES_HANDOFF` ka same idiom) — koi compliance gate nahi chhua. `prod_check` ab **[OK] ALL CHECKS PASSED**
  (pehle `[FAIL] 1 problem`), automation **0 gaps**.

### 7. More stale-doc fixes
- `Competitor_Top20 §4` "GENUINE GAPS" pe banner (sab free-stack items built — dobara mat banao).
- `INFRA_UPGRADE_2026`: OTel "`ENABLE_OTEL=1` bas set karo" GALAT tha (exporter deps baked nahi) → corrected;
  Part-4 Razorpay setup-steps → **UPI_VPA** reality (Razorpay 2026-06-18 removed); activation-checklist #1 fix.

> **⚠️ Concurrent git activity dekha:** is session ke dauraan dusra process/automation ne mere staged doc
> deletions ko apne commit (`a16cb56` webhook/roadmap) ke saath commit kar diya. Saare 20 deletions ab
> COMMITTED hain. Mere code/test/doc edits abhi working-tree me uncommitted — commit se pehle diff review karo
> (concurrent session same file na chhoo raha ho).

**Verify (sab green):** `prod_check` [OK] ALL PASSED (737 routes, 0 gaps) · tests 30/30 (chatbot 8 + circuit
breaker 6 + orphan-wiring 3 + engineer-agents 13) · har edited file compile+import OK.

---

## ENABLE-READY: dormant code, sirf `.env` flag chahiye (free-stack, safe, koi paid/cred nahi)
> Yeh code WIRED hai par default OFF. Main tumhari prod `.env` set nahi kar sakta — yeh tum flip karo.
> Sab fail-open / never-raise, rollback = `=0`.

| Flag | File | Kya karta hai | Risk |
|------|------|---------------|------|
| `USE_AGENTIC_RAG=1` | chatbot.py (ab wired) | Public bot pe CRAG corrective answer (empty-KB path) | Nil — gated, never-raise |
| `USE_STRUCTURED_CONTENT=1` | `app/llm/structured.py` (gate `post_generator.py`) | Typed/validated marketing JSON, fragile parse khatam | Nil — template fallback |
| `REQUEST_GUARD=1` | `app/middleware/__init__.py` | Per-req 504 timeout + load-shed; voice/WS/stream skip-listed | Nil — fail-open |
| `PLAN_RATE_LIMIT=1` | `app/middleware/__init__.py` | Tier RPM (Starter60/Growth200/Adv500) | Nil — fail-open |
| `SEMANTIC_CACHE=1` | `app/cache/semantic_cache.py` | Qdrant+Redis LLM cache → Groq/Cerebras TPD bachao | Nil — off-loop deadline, fail-open |
| `PUBLIC_GUARDRAILS=1` | chatbot.py | Public bot pe PII-redact + injection-block | Nil — fail-open |
| `OPS_ALERTS=1` | `app/platform/ops_alerts.py` | ntfy alerts (ntfy already live) | Nil — outbound push |

**Voice turn-taking** (`USE_SILERO_VAD=1`): torch-CPU image me already BAKED (CLAUDE.md) → free win,
par voice path pe hai isliye enable ke baad `scripts/agent_tester.py` se verify karna.

---

## NEXT (recommended, additive — is session me skip kiya kyunki ref-updates/verify chahiye)
- **Orphan wiring** (free, no dep): `app/marketing/seo_tools.py` (`generate_keywords`/`split_ad`, pandas-only)
  → ads/SEO copy generators me wire karo. `app/lead_scraper/to_markdown.py` (MarkItDown) → client-doc
  ingest me (dep `markitdown` present ho to).
- **Doc merges (ref-update zaroori, isiliye abhi nahi kiye):** infra cluster → 2 canonical
  (`SAAS_INFRA_TRUTH_AND_GAPS` + `INFRA_DEEP_AUDIT_BILLIONAIRE_SCALE`); `Infra_BestStack_GapAnalysis` +
  `SAAS_INFRA_GAP_ADDITIVE` fold (GAP_ANALYSIS ko code cite karta — pehle wo ref update karo). PHASE6/7
  docs → 1-1 canonical (PHASE7_DETERMINISTIC_LOOPS ko `self_improve.py` cite karta — rakho). Launch
  checklists (DEPLOY_VERIFICATION/GO_LIVE/COPY_PASTE_LAUNCH) → OPERATIONAL_RUNBOOKS (pehle
  `EXECUTE_LAUNCH_NOW.sh` update karo).
- **Stale-claim doc fixes (accuracy):** `Competitor_Top20_Feature_Gap_2026.md §4` ("GENUINE GAPS") —
  saare 20 items ab BUILT, §3 parity me move karo (sirf transfer/SMS/RCS = DLT-blocked open). Infra
  docs me **Razorpay/Exotel references stale** hain (dono 2026-06-18 ko REMOVED) — INFRA_UPGRADE_2026,
  PRODUCTION_HARDENING_GAP, dono roadmaps me. `INFRA_UPGRADE_2026` ka "`ENABLE_OTEL=1` bas set karo"
  GALAT — otel exporter deps lock me baked NAHI (`requirements-otel.txt` alag); image-rebuild chahiye.

## Real gaps still open (free but net-new build — prioritize alag)
Postgres RLS (DB-enforced tenant isolation) · system-wide circuit-breaker (Vobiz/SMTP/Maps) ·
load+chaos testing (k6+Pumba, baselines voice-scale se pehle) · agent-memory (Mem0 on Qdrant,
cross-session recall) · per-tenant health metrics.

## External-blocked (token mat jalao jab tak unlock na ho)
DLT/Vobiz recharge → cold-calling + live transfer + SMS-DLT · Meta/FB-IG/GBP auto-post (app-review) ·
Cloudflare WAF/CDN + HA 2nd-node (account/spend) · R2/B2 offsite (creds) · 2nd sending-domain (buy).
**P0 revenue: `UPI_VPA` set karo** (Razorpay removed = manual UPI ab primary path).

## Compliance (REPORT only — sab INTACT, kuch nahi chheda)
TRAI 10am-7pm + 140-series + AI-disclosure + DND fail-closed + consent-ledger sab active.
`TRAI_CONSENT_CONFIRM_SPEC` correctly **spec-only / deferred** (DLT unlock pe build). `CONSENT_CONFIRM`
flag AUTOMATION_FLAGS me declared par read nahi (prod_check "dead flag" warn deta — yeh intentional-deferred,
non-blocking, isliye chhoda).

---
*Method note: file-content truth = Windows venv (`prod_check.py` + pytest Desktop Commander se chalaye);
sandbox sirf read-exploration. Subagent audits read-only the. Sab change additive + gated + never-raise.*
