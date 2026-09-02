# awesome-llm-apps → LeadGen platform mining report

**Date:** 2026-08-05
**Source:** https://github.com/Shubhamsaboo/awesome-llm-apps (Apache-2.0, shallow clone inspected at HEAD)
**Scope:** 100+ templates across 12 top-level categories. This doc keeps only what survives our constraints.
**Status:** research / decision input. Nothing here is wired. New file, additive — no existing file touched.

---

## 0. Filter applied (why most of the repo is discarded)

| Constraint (from CLAUDE.md) | Effect on this repo |
|---|---|
| **Free providers only** — no paid STT/TTS/LLM | Kills ~70% of templates: they default to `openai:gpt-5.2`, `anthropic:claude-sonnet-4-6`, Tavily, Firecrawl, Cohere, Gemini Live, OpenAI Realtime. Value = **pattern**, not code. |
| **Server-rendered HTML frontend** (28-tab marketing.html, 4 dashboards) | Kills every Streamlit / Next.js shell. Extract the Python core, drop the UI layer. |
| **ToS-blocked auto-scrape REFUSED** | Kills browser-use / web-scraping agents outright. |
| **Compliance gates never weakened** (§5) | Nothing here touches DND / TRAI window / consent / DLT. Safe by construction — none of these are telephony. |
| **`requirements.lock.txt` = single source; no casual deps** | Anything pulling `langchain`+`langgraph`+`langchain-community` (corrective_rag) is a big dep surface for a pattern we can hand-write. |
| **Additive, flag-gated, INERT default** | Every adoption below is a new module behind a new `AUTOMATION_FLAGS` entry. |

**Bottom line:** ~4 items are worth real engineering time, 2 are free drop-ins, the rest is reading material.

---

## 1. TIER A — highest ROI, adopt

### A1. Typed RAG with refusal + validated citations ⭐ top pick
`rag_tutorials/agentic_typed_rag_pydanticai/agent.py`

**What it actually is:** a Pydantic contract that makes hallucination a *validation error* instead of a bad answer.

```python
DEFAULT_MIN_RELEVANCE = 0.2
REFUSAL_TEXT = "I do not have enough evidence in the indexed sources to answer that question."

class Answer(BaseModel):
    text: str; citations: list[Citation]; confidence: float; answered: bool

    @model_validator(mode="after")
    def answer_and_citations_must_agree(self):
        if self.answered and not self.citations:
            raise ValueError("answered responses require at least one citation")
        if not self.answered and self.citations:
            raise ValueError("refused responses must not contain citations")
```

Plus: retrieval runs **first**, scores are thresholded, and if `top_score < MIN_RELEVANCE` the LLM is never asked — `Answer.insufficient_evidence()` short-circuits. `Citation.quoted_span` must be a verbatim span from a stored chunk, `chunk_id` must be a real returned id.

**Why it matters here:** our Qdrant `kb_main` (namespaces `niche:` / `client:<id>` / `skills`) feeds a **voice agent talking to real customers**. A confidently wrong price, policy, or timing claim on a live call is a customer-facing and arguably a compliance problem, and it is currently guarded by prompt text, not by a type.

**Adoption shape:**
- New `app/voice_agent/kb_answer.py` — Pydantic `KBAnswer` with the two-way `answered ⟷ citations` validator, `min_relevance` gate before any LLM call.
- Model-agnostic: drop `pydantic_ai`, keep plain `pydantic` (already in lock) + our existing `free_ai.py` chain.
- Flag `VOICE_KB_STRICT_GROUNDING`, INERT default. Canary = one niche namespace.
- **Latency note:** the threshold gate makes the *cheap* path cheaper (no LLM call on weak retrieval) — this is a win on the voice path, not a tax.
- Test: `tests/test_voice_kb_grounding.py` — weak-retrieval fixture MUST produce `answered=False, citations=[]`. Precondition set by the test itself (rule R4).

**Reference test already provided upstream:** `rag_tutorials/agentic_typed_rag_pydanticai/test_typed_rag.py`.

---

### A2. Zero-token skill CI gates (stdlib only) ⭐ free drop-in
`agent_skills/evals/tools/{skill_lint.py, skill_scanner.py, run_trigger_evals.py}`

Three deterministic, **stdlib-only, no-network, non-executing** scripts:

| Tier | Script | Catches |
|---|---|---|
| 1 Structural | `skill_lint.py --strict` | bad frontmatter, `name != dir`, unfilled placeholders, prompt-dump-only skills |
| 1b Security | `skill_scanner.py` | install lures, undeclared network calls, credential access, obfuscated payloads — mapped to OWASP Agentic Skills Top 10 (AST01–AST10), modelled on the ClawHavoc Jan-2026 supply-chain campaign |
| 2 Routing | `run_trigger_evals.py` | positive prompts must rank their own skill first; **flags near-colliding descriptions between two skills** |

**Why it matters here:** ADR-131 made `.claude/skills` the canonical tracked skill root, and this box now loads a very large skill surface (plugin skills + user skills). Two things are unguarded today: (a) nothing statically vets a skill we install from outside, (b) nothing detects two skills whose `description` fields collide, which is exactly how a skill silently stops triggering.

**Adoption shape:** vendor the three files into `scripts/skill_evals/` (upstream file header already says "[vendored] repo-side CI copy" — they expect this), wire into the existing CI gate next to `prod_check.py`. Exit codes are CI-friendly (`0` clean / `1` CRITICAL / `2` usage). Cost: **0 tokens, ~seconds**. Risk: near-zero, it never executes what it scans.

Their own note: tier 1 caught a real symlink bug that silently disabled a feature on macOS. This is not theatre.

---

### A3. RAG failure taxonomy P01–P12 — steal the table, skip the app
`rag_tutorials/rag_failure_diagnostics_clinic/README.md`

Ignore the LLM script (it calls an OpenAI-compatible endpoint to classify bugs). **The 12-pattern table is the asset** — and four of them are verbatim our own §7 landmines:

| ID | Pattern | Our matching incident class |
|---|---|---|
| P04 | Index skew / staleness | `:latest` unknown-provenance prod, per-container skew (ADR-097) |
| P10 | Startup ordering / dependency not ready | scheduler boot-grace restart-storm prod-down |
| P11 | Config / secrets drift across environments | `.env.example` drift; `REPLY_AUTO_SEND` env-vs-Redis divergence; `UPI_AUTO_ACTIVATE` doc drift |
| P12 | Multi-tenant / multi-agent interference | customer-isolation invariant; parallel-coding-tool truncation (buzzlock) |
| P01 | Retrieval hallucination / grounding drift | exactly what A1 fixes |
| P09 | Evaluation blind spots | "passes tests, fails on real incidents" — our function-level-import 7-day 500 |

**Adoption shape:** append the table to `memory/incidents.md` as a **triage index** (pattern → past postmortems), so debugging starts from a named pattern instead of a blank page. Pairs with `docs/AGENT_WORK_RULES.md` R1/R2. Cost: one doc edit, no code.

---

## 2. TIER B — worth building, but scoped

### B1. Corrective RAG (CRAG) — for async paths only, with SearXNG as the fallback
`rag_tutorials/corrective_rag/`

Loop: retrieve → **grade the retrieved docs** → if graded insufficient, rewrite the query → fall back to web search → answer.

- **Swap the paid part:** upstream uses Tavily. We already self-host **SearXNG**. Free substitute, no new vendor.
- **Do NOT put this on the voice path.** A retrieve→grade→rewrite→search→answer loop is multiple sequential LLM round-trips; on a live call that is dead air, and our Groq/Cerebras chain is already 429-prone.
- **Do put it on async surfaces:** `/audit` + `/site-audit` lead magnets, and email reply-triage — both already run in Celery where a 20s loop is free.
- **Skip their dep tree.** `langchain` + `langgraph` + `langchain-community` + `langchain-core` + `tenacity` + `nest-asyncio` for one grading loop is a bad trade against `requirements.lock.txt` discipline. The grader is one prompt + one Pydantic enum; hand-write it against `free_ai.py`.

Flag `RAG_CORRECTIVE_ENABLED`, INERT default, Celery-only guard.

### B2. Tool-output compression — steal SmartCrusher's idea, not the dependency
`advanced_llm_apps/llm_optimization_tools/headroom_context_optimization/`

Claim: 47–92% token reduction on tool-heavy agent loops via statistical compression of JSON tool outputs — **keep first N items, last N items, anomalies, and query-relevant matches; compress the redundant middle.** Also prefix-stabilisation for provider cache hits, and reversible retrieval (ask for the original when needed).

**Why it matters here:** our binding constraint is not cost, it is **free-tier quota** — Groq TPD exhausting on content-heavy days, Cerebras 429s, the escalating 60s→30min circuit breaker in `free_ai.py`. Fewer tokens per call = more calls survive the day.

**Recommendation: do NOT add `headroom-ai`.** It is a transparent proxy plus a new external dependency in front of the one code path (`free_ai.py` ~line 420) that must never wobble. The SmartCrusher heuristic itself is ~30 lines we can write and test ourselves, applied to the fattest tool outputs (prospecting payloads, CRM blobs, audit JSON) before they enter the prompt. Measure before/after token counts — no claim without evidence.

`toonify_token_optimization` (TOON serialisation format, claims 30–60%) is the same idea at the serialisation layer — read it, cheaper to evaluate, same "measure it" caveat.

---

## 3. TIER C — read, don't build (yet)

| Template | Idea worth knowing | Why parked |
|---|---|---|
`agent_skills/self-improving-agent-skills/backend/adk_optimizer.py` | Run a skill against its evals → LLM rewrites the skill → re-score → keep if better. Loop shape maps onto our `self_improve` agent + agent-harness-standard. | Google-ADK + Gemini-shaped; Next.js frontend irrelevant. Read the optimizer loop, ignore the rest. Also: an agent that rewrites its own instructions must never be able to touch a §5 compliance gate — that containment design is the real work, not the loop. |
| `always_on_agents/*/scheduler_api.py` | FastAPI HTTP **+** Pub/Sub dual trigger for a scheduled agent, with unit tests for the trigger hook itself and an `eval_config.yaml` per agent. | We already have Celery beat + boot-grace. Modest value as a reference for the dormant `LEADGEN_SCHEDULER_SECRET` recovery endpoint shape (idempotency + bounded params — note their `_as_top_n` clamps to 1..25). |
| `rag_tutorials/knowledge_graph_rag_citations/` | Multi-hop answers with verifiable source attribution. | Needs a graph store; we already spent that budget on Graphify (code nav, DEV-only). Revisit only if KB multi-hop becomes a real complaint. |
| `mcp_ai_agents/multi_mcp_agent_router/` | Specialist agents each bound to their own MCP server, with a router in front. | Conceptually close to Boss → Owner OS → 31 STAFF. Compare designs; don't port. |
| `advanced_ai_agents/.../ai_sales_intelligence_agent_team`, `ai_competitor_intelligence_agent_team`, `product_launch_intelligence_agent` | GTM battle-cards / competitor teardowns / launch intel — adjacent to our Hot Queue and 2nd-paying-customer goal. | README-level: these lean on Firecrawl / paid search and Streamlit. Pattern only. Our `sales:*` and `marketing:*` plugin skills already cover most of this surface. |
| `generative_ui_agents/ai-dashboard-canvas-agent` | Chat → charts assemble on a live canvas. | Next.js; we are server-rendered HTML. Interesting for `/app/automation` Mission Control someday, not now. |

---

## 4. Explicitly rejected

- **All Gemini-Live / OpenAI-Realtime voice templates** (`insurance_claim_live_agent_team`, `voice_rag_openaisdk`, `customer_support_voice_agent`) — paid realtime APIs. Our voice path is FreeSWITCH + Vobiz + EdgeTTS + Groq-whisper and is **FROZEN** (edit prohibited). Do not touch.
- **Browser-use / web-scraping agents** — collide with the ToS-blocked-scrape refusal (§5).
- **Every Streamlit demo app** (travel, chess, memes, fitness, movies, tic-tac-toe) — no transferable engineering.
- **`llm_finetuning_tutorials/`** — we buy zero GPU and run free inference only.
- **`headroom-ai` as a dependency** — see B2. Idea yes, package no.

---

## 5. Recommended sequencing

1. **A2 skill CI gates** — free, zero-token, no product risk, hardens ADR-131. Do first because it costs nothing.
2. **A3 P01–P12 taxonomy → `memory/incidents.md`** — one doc edit, immediate debugging leverage.
3. **A1 typed grounding + refusal** — real engineering, real customer-facing win, needs its own contract test and a single-niche canary. Do NOT bundle with anything else.
4. **B2 measure token fat** on the 3 fattest tool outputs before writing any compressor. Evidence first.
5. **B1 CRAG on `/audit` + reply-triage** — only after A1 lands, since A1's grounding contract is what CRAG's grader would return.

Everything above stays inside §5 (no compliance gate touched), §6 DoD (targeted pytest + `prod_check.py` + secrets scan), and §8 (no commit/push/deploy without your go-ahead).

---

## 6. Provenance

- Apache-2.0 (`LICENSE`), explicitly "fork it, ship it, sell it" — vendoring A2 is licence-clean. Keep upstream attribution headers; `skill_scanner.py` already carries one.
- Inspected via `--filter=blob:none --sparse` shallow clone; 241 directories enumerated, README (23.5 KB) read in full, and the following read as source: `agentic_typed_rag_pydanticai/agent.py`, both `requirements.txt` files above, `rag_failure_diagnostics_clinic/README.md`, `agent_skills/evals/README.md`, `evals/tools/skill_scanner.py`, `headroom_context_optimization/README.md`, `release_radar_agent/scheduler_api.py`.
- Everything in Tier C marked "README-level" was **not** read as source — claims there are upstream marketing, not verified.
