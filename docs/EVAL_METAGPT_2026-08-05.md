# MetaGPT Evaluation — for LeadGen AI Platform

**Date:** 2026-08-05 · **Repo:** https://github.com/FoundationAgents/MetaGPT · **Licence:** MIT (Copyright 2024 Chenglin Wu)
**Evaluated commit:** `11cdf46` (2026-01-21) · 509 py files / ~61.7k LOC
**Scope:** assessment only — no code changed, no dependency added.

---

## TL;DR (verdict)

**Do NOT adopt MetaGPT as a dependency. DO steal 4 patterns.**

Dependency adoption is blocked on hard, verifiable grounds (python ceiling + 8 exact-pin conflicts against `requirements.lock.txt`), and the flagship use case (one-line requirement → software repo) is not our business. But MetaGPT solves 4 problems we currently solve worse, and MIT licence means we can lift the *patterns* freely with attribution.

---

## 1. What MetaGPT actually is

Core philosophy: `Code = SOP(Team)`. A fixed waterfall of LLM roles (TeamLeader → ProductManager → Architect → Engineer2 → DataAnalyst) collaborating in a message-passing `Environment` to turn one requirement into a repo.

Primitives worth naming:

| Primitive | File | What it gives |
|---|---|---|
| `Role` | `metagpt/roles/role.py:125` | Declarative agent: `profile`/`goal`/`constraints`/`actions[]`/`watch`. Loop = `_observe → _think → _act → _react`, with 3 react modes: `REACT`, `BY_ORDER`, `PLAN_AND_ACT` (`RoleReactMode`, L82). |
| `ActionNode` | `metagpt/actions/action_node.py:135` | **The crown jewel.** A tree of typed output fields that *generates a pydantic model at runtime* (`create_model_class` L248), compiles instruction+example into the prompt (`compile` L382), fills it (`fill` L597 / `xml_fill` L553 / `code_fill` L533), then `review()` L729 → `revise()` L816 the model's own output against the schema. |
| `Environment` | `metagpt/environment/` | Pub/sub message routing; roles subscribe to Action *types* via `_watch` (role.py L284), messages carry `cause_by`. |
| `Planner` + `Plan`/`Task` | `metagpt/strategy/planner.py`, `schema.py:457,496` | Goal → ≤N tasks with `task_type`; `precheck_update_plan_from_rsp` validates the plan and **retries generation on invalid** before adopting it; optional `AskReview` human gate. |
| `exp_pool` | `metagpt/exp_pool/` | Productised Reflexion: `@exp_cache` decorator (decorator.py L30) does semantic retrieval of past experiences, a `scorer`, a `perfect_judge` (skip the LLM call entirely if a perfect prior exists), and **separate `enable_read` / `enable_write` config flags**. |
| `ToolRecommender` | `metagpt/tools/tool_recommend.py:54` | Two-stage tool selection: `recall_tools` (BM25 L195 / embedding L231 / type-match L173) → LLM `rank_tools` L129. Only the top-k reach the prompt. |
| `Team` | `metagpt/team.py:32` | `hire(roles)`, `invest(budget)` → `NoMoneyException` hard stop, `run(n_round)`, serialize/deserialize for recovery. |

---

## 2. Blockers — why we can't just `pip install metagpt`

### 2.1 Python ceiling (hard)
`setup.py:110` → `python_requires=">=3.9, <3.12"`. Our dev/prod stack is py3.12 (`CLAUDE.md §3`; `pyproject.toml` declares `>=3.10`, mypy target 3.11). MetaGPT would refuse to install.

### 2.2 Dependency conflicts (hard) — 8 exact-pin collisions with `requirements.lock.txt`

| Package | Ours (lock) | MetaGPT pin | Verdict |
|---|---|---|---|
| `openai` | 2.41.0 | `~=1.64.0` | **major conflict** |
| `aiohttp` | 3.14.3 | `==3.8.6` | **conflict** |
| `qdrant-client` | 1.18.0 | `==1.7.0` | **conflict** (and we run Qdrant live) |
| `pandas` | 2.2.0 | `==2.1.1` | conflict |
| `tiktoken` | 0.13.0 | `==0.7.0` | conflict |
| `tenacity` | 9.1.4 | `==8.2.3` | conflict |
| `websockets` | 15.0.1 | `>=10.0,<12.0` | **conflict** (voice WS path) |
| `numpy` | 1.26.3 | `~=1.26.4` | minor conflict |

Plus ~90 transitive deps we do not want on a single Hostinger VPS: `faiss-cpu`, `playwright`, `semantic-kernel==0.4.3.dev0` (a dev release), `gymnasium`, `boto3`, `volcengine-python-sdk`, `dashscope`, `qianfan`, `zhipuai`, `tree-sitter`, `ipykernel`/`nbclient`/`ipywidgets`. `requirements.lock.txt` is our single source of truth — this is unacceptable lock churn for a navigation-layer benefit.

### 2.3 Free-provider mandate — partial coverage only
`LLMType` (`configs/llm_config.py:20`) covers Gemini, Ollama, OpenRouter, Mistral (routed through the OpenAI-compatible client, `provider/openai_api.py:49`). **There is no Groq provider** — only one comment mention (`software_company.py:131`). Groq is our realtime-chain primary and our STT primary. Our 9-key Gemini rotation, per-provider circuit breaker, and egress guard have no equivalent: MetaGPT has **one** LLM config with no fallback chain.

### 2.4 Purpose mismatch
MetaGPT's roles are PM/Architect/Engineer/QA producing code. Our 31 agents do marketing, voice, sales-ops and compliance work. Almost zero role overlap. The reusable asset is the **framework primitives**, not the SOP.

### 2.5 Maintenance signal
Last commit on `main` is 2026-01-21 — roughly 6 months quiet as of today. The team's energy has visibly moved to the commercial product (MGX). Not disqualifying by itself, but it argues against taking a runtime dependency.

---

## 3. Where we are already ahead

Being honest about this matters — it stops us from cargo-culting.

- **Governance.** `app/platform/agent_registry.py:125` `AgentContract` carries 30+ fields — `autonomy`, `lane`, `prohibited`, `max_concurrency`, `cost_budget_inr_day`, `customer_contact_cap_day`, `kill_switches`, `escalation`, `idempotency`. MetaGPT has essentially none of this; `Team.invest()` is its entire budget story, and ours is *per-agent* not per-run.
- **Harness invariants.** Our `.claude/skills/agent-harness-standard` mandates harness-owned termination — stopping is never inferred from the model's prose. MetaGPT terminates on an `n_round` counter plus role-idle. Ours is the stronger contract.
- **Durable replay.** `process_engine.replay()` / `dag_engine` reconstruct state from an append-only journal with fail-closed edge conditions. MetaGPT serialises the whole `Team` to JSON for recovery — coarser, no per-step frontier.
- **Compliance spine.** DND fail-closed, TRAI window, consent ledger, AI-disclosure. No analogue exists in MetaGPT and none is expected.
- **Provider resilience.** `app/voice_agent/free_ai.py` — dual profile chain (`_build_llm_chain` L578), per-provider circuit breaker (L248/L269), semantic cache, egress guard (L677). MetaGPT: single provider, no breaker.

---

## 4. The steal-list (ranked, with the concrete gap each closes)

### #1 — ActionNode-style structured fill + self-review + revise
**Our gap:** `coordinator._extract_list()` (`app/agents/coordinator.py:218`) scrapes freeform JSON out of LLM prose, and is called at L276 (plan parsing) and L865 (agentverse expert recruitment). When the model returns junk, `plan()` silently drops to a hardcoded chain — dev → rohan → isha.
**What to lift:** the `compile → fill → review → revise` cycle over a runtime-generated pydantic model (`action_node.py:248,382,597,729,816`). Not the class — the *cycle*.
**Where it goes:** `app/agents/harness/contracts.py` — that module's own docstring says it exists precisely to replace `coordinator._extract_list`. This is the missing implementation, not a new idea.
**Value:** highest. Kills the single most fragile link in our planning path.

### #2 — Two-stage tool/roster recommendation (BM25 recall → LLM rank)
**Our gap:** `coordinator.plan()` injects the **whole 31-agent roster** into every planning prompt (L235). `docs/context/SYSTEM_MAP.md:51` already flags "429 storms if coordinator uncapped" as a known risk.
**What to lift:** `BM25ToolRecommender.recall_tools` → `rank_tools` (`tool_recommend.py:195,129`).
**Zero new deps needed:** the `rank-bm25` package is *not* in our lock, but we already have a hand-rolled BM25-style lexical scorer (`app/ml/reranker.py:42`, "no ML deps") plus RRF dense+sparse fusion (`app/ml/hybrid_search.py`) and a BM25 mirror in the KB (`app/voice_agent/knowledge_base.py:817`). Recall stage can reuse those or `agent_recall._keyword_recall`.
**Value:** direct token reduction on the hottest prompt, and it attacks a risk we have already written down.

### #3 — Plan precheck + repair-retry
**Our gap:** invalid plan → deterministic hardcoded fallback. We never ask the model to fix its own plan.
**What to lift:** `precheck_update_plan_from_rsp` + the bounded `max_retries` regeneration loop (`strategy/planner.py:83+`), keeping our deterministic chain as the *final* fallback rather than the first.
**Value:** better plans at roughly one extra cheap call, and only on the failure path.

### #4 — `exp_cache` semantics for `agent_recall.py`
**Our gap:** two uncoordinated memory tiers — `coordinator._MEMORY` (jsonl, hard cap `_MAX_MEM = 3`, L498-561) and `agent_recall.py` (hybrid keyword+vector). Neither scores an experience, neither can skip an LLM call outright, and read/write are not independently controllable.
**What to lift:** three ideas from `exp_pool/decorator.py:30` — a `scorer`, a `perfect_judge` (perfect prior ⇒ return it, no LLM call at all), and **separate `enable_read` / `enable_write` flags** so we can canary reads before arming writes.
**Value:** turns a log into a cache. The read/write split fits our INERT-by-default convention exactly.

### Explicitly SKIP
- `Role` / `Environment` pub-sub rewrite — our blackboard + JSONL journal is adequate at 31 agents, and a message-bus migration would touch every orchestrator. Not worth it.
- `Team` / `invest()` — our per-agent `cost_budget_inr_day` is strictly better.
- The software-company SOP roles (PM/Architect/Engineer/QA) — no business fit.
- Data Interpreter / notebook execution — sandbox surface we do not want on the VPS.

---

## 5. Recommended next step (not yet done)

Steal-item **#1 only**, as a contained loop: implement the fill/review/revise cycle inside `app/agents/harness/contracts.py`, flag-gated and INERT by default, with `coordinator.plan()` as the single canary caller and `_extract_list` retained as fallback. Contract test first (`docs/AGENT_WORK_RULES.md` R8 — this touches a governed surface, so it needs an explicit human yes, not just green tests).

Items #2–#4 stay parked in `memory/backlog.md` until #1 has proven itself in prod.

---

## Verification notes

- All MetaGPT line numbers read from a fresh `git clone --depth 1` at commit `11cdf46`.
- All LeadGen line numbers verified against working-tree source, not from memory.
- Dependency conflicts computed by diffing MetaGPT `requirements.txt` against our `requirements.lock.txt` pins directly.
- Steal #2 dep question resolved: `rank-bm25` absent from lock/pyproject, but `app/ml/reranker.py:42` already implements a dep-free BM25-style scorer — no new dependency required.
- **Not claimed:** that any steal-item improves a measured metric. No benchmark was run. Adoption of #1 should carry its own before/after evidence.
