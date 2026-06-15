# Backend Reliability + Engineer Agents — Research & Integration

**Date:** 2026-06-15 · **Scope:** Deep-dive SOTA agent/reliability repos; add genuinely additive backend + automation items (+ an engineer-agent crew).
**Outcome:** (1) Webhook **idempotency** layer (real double-credit bug fix) + (2) MetaGPT-style **engineering crew** agent. Free-stack, never-raise, prod_check green (route 651→652, 549→550 files).

---

## 1. Repos researched (what + why)

| Repo / pattern | Core idea | Humare liye verdict |
|---|---|---|
| **OpenHands** | CodeAct: agent code likhta/test/run karta via executable actions, controller-agent-runtime sandbox | Full autonomous-coding sandbox = humari draft-only/ban-safe philosophy ke against → NAHI liya |
| **SWE-agent** (Princeton) | Agent-Computer Interface (ACI) for GitHub-issue resolution | Same: autonomous code-apply → NAHI |
| **MetaGPT** | "AI software company": PM/Architect/Engineer/QA roles, SOP pipeline → design+code+tests | **Roles pattern LIYA** (draft-only crew — niche) |
| **Webhook idempotency / outbox** (Stripe/GitHub/Shopify consumer guides) | At-least-once delivery → exactly-once *processing* consumer ki job; event-id dedup | **LIYA** — real gap tha |
| AG2/AutoGen, DSPy, Letta/MemGPT | group-chat, prompt-opt, agent memory | Coordinator + free_ai chain + episodic memory already cover → abhi skip |

**Best-stack note:** LangGraph already tere stack me (production leader 2026). Naya kuch free-stack + no-new-dep rakha (lock-refresh nahi).

---

## 2. ADD #1 — Webhook idempotency (BACKEND reliability, real bug fix)

**Gap (proven):** `app/api/billing.py` ka Razorpay + Stripe webhook signature to verify karta, par **event-id dedup nahi** tha. Invoices `payment_ref` se dedupe hoti thi, par **usage-credit nahi**:
- Razorpay `payment.captured` redeliver ho (at-least-once retry) → `add_topup_leads` / `add_topup_minutes` (billing.py:1463/1440) **DOUBLE credit** (customer ko +20 leads instead of +10), ya subscription double-activate.

**Fix:** `app/billing/idempotency.py` — generic `seen_before(key)`:
- Atomic **Redis `SET key val NX EX ttl`** (ek command: "naya?" + claim). MAIN redis = **noeviction** (audit P0-1) → idem keys TTL-window (14 din) me kabhi evict nahi.
- **FAIL-OPEN**: Redis down = per-process memory fallback, warna event process (legit payment lose karna double se bura). Never raises.
- Wired BOTH webhooks (top pe, side-effect se PEHLE): Razorpay `X-Razorpay-Event-Id` header (fallback `event_type:payment_id`); Stripe `event.id`. Duplicate = `{"received": true, "duplicate": true}` early-return.

**Asar:** payment webhook redelivery ab **exactly-once process** hoti — double-credit / double-activate khatam. `IDEMPOTENCY_TTL_S` env tunable. Manual replay: `idempotency.forget(key)`.

---

## 3. ADD #2 — Engineering crew agent (AUTOMATION / "engineer agents")

**`app/agents/coordinator.py` → `coordinate_engineering(goal, context)`** + `POST /agents/coordinate-engineering`.

MetaGPT/OpenHands-inspired 4-role crew (free-LLM): **Architect** (design: components/data-flow/API/trade-offs) → **Engineer** (step-by-step implementation PLAN, pseudo-code level) → **Reviewer** (security/reliability/idempotency risks + fixes) → **QA** (unit+integration+failure-mode test plan). Output = design + plan + review + test_plan.

**DRAFT-ONLY** — code KABHI auto-apply nahi (tere `code_upgrader` ki "core code admin-approve pe hi" philosophy ke saath consistent). Yeh `code_upgrader` (signal→patch) ka **complement**: goal→design+plan+tests. Naya feature plan karne / design review ke liye on-demand aid. Free-stack, never-raise.

(Pichhli baar `coordinate_agentverse` add hua tha — ab agent-coordinator ke modes: plan/fanout/reflexion/debate/hierarchical/**agentverse**/**engineering**.)

---

## 4. Why NOT more (discipline)

OpenHands/SWE-agent jaise full autonomous code-apply agents jaan-bujhke NAHI liye — tera system ban-safe + draft-only + human-approve design ka hai (WhatsApp/calls/code sab gated). Auto-applying code-agent us safety ke against jaata. Engineering crew isliye **draft-only** rakha. AutoGen/DSPy/MemGPT ke patterns (group-chat, prompt-opt, memory) tere coordinator + free_ai breaker + episodic memory (`_recall`/`_remember`) me already cover.

---

## 5. Verification

`python scripts/prod_check.py` → **ALL CHECKS PASSED**: 549→**550** files (idempotency.py), `app.main` imports OK, routes 651→**652** (engineering endpoint), env OK. Free-stack + never-raise + fail-open → zero-key/Redis-down par bhi safe. Deploy-pending (same pipeline).

### Files
- `app/billing/idempotency.py` (new) · `app/api/billing.py` (Razorpay + Stripe guards)
- `app/agents/coordinator.py` (`coordinate_engineering`) · `app/api/agents.py` (endpoint)

## Sources
- OpenHands SDK — https://arxiv.org/pdf/2511.03690 · https://github.com/All-Hands-AI/OpenHands
- SWE-agent — https://github.com/SWE-agent/SWE-agent
- MetaGPT — https://github.com/FoundationAgents/MetaGPT
- Webhook idempotency (2026) — https://www.hooklistener.com/learn/webhook-idempotency-and-deduplication · https://www.digitalapplied.com/blog/webhook-reliability-idempotency-retries-engineering-reference-2026
- Agent frameworks 2026 — https://www.firecrawl.dev/blog/best-open-source-agent-frameworks
