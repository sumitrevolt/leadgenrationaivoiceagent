# AgentVerse + Multi-Agent Automation — Research & Integration

**Date:** 2026-06-15 · **Scope:** Deep-dive AgentVerse (OpenBMB) + best-of automation repos; add the genuinely additive pattern to the backend.
**Outcome:** New coordinator capability `coordinate_agentverse` (dynamic expert recruitment + evaluate→re-compose loop) + API endpoint. Free-stack, gated-safe, prod_check green (route 650→651).

---

## 1. AgentVerse (OpenBMB) — kya hai, kya valuable

**Repo:** https://github.com/OpenBMB/AgentVerse · **Paper:** AgentVerse, ICLR 2024 — [arXiv:2308.10848](https://arxiv.org/abs/2308.10848). Apache-2.0.

Do framework: **simulation** (research/games — humare liye relevant nahi) aur **task-solving** (multi-agent system jo milke task solve kare — yahi valuable hai).

**Task-solving ka 4-stage CLOSED LOOP (paper ka core contribution):**

1. **Expert Recruitment** — ek "recruiter" agent (HR-manager jaisa) goal ke liye expert role-descriptions **dynamically generate** karta hai. Team fixed nahi — har task ke hisaab se TAILORED banti hai.
2. **Collaborative Decision-Making** — recruited experts milke decide karte: **horizontal** (peer refinement) ya **vertical** (solver + reviewers).
3. **Action Execution** — decided actions execute (tools ke saath).
4. **Evaluation** — ek verifier outcome ko score karta; agar weak ho to **feedback wapas** jaata aur **team ki composition + strategy ADJUST** hoti agle round me.

**Signature insight:** multi-agent group ki composition evaluator-feedback se **dynamically re-compose** hoti hai — "right team for the current state", har round behtar.

### Humare paas pehle se kya tha (duplicate avoid)
`app/agents/coordinator.py` me already: `coordinate` (planner+handoff), `fan_out` (parallel), `coordinate_advanced` (**Reflexion** — plan→execute→verify→reflect→retry), `debate` (pro/con consensus), `coordinate_hierarchical` (Boss→sub-teams). Plus `staff_supervisor.py` (LangGraph).

**Gap:** in sab me team/roster **FIXED** hai (8 STAFF). AgentVerse ka **dynamic expert recruitment** (goal-tailored team jo evaluator-feedback pe badalti) **missing tha** — yahi add kiya.

---

## 2. Best stack (2026) — kahaan khade hain

Industry survey (Firecrawl/Medium/AI-Magicx 2026): **LangGraph** ab production ka leader (graph-based, audit-trail, human-in-loop; early-2026 me CrewAI ko stars me overtake kiya). **CrewAI** quick role-playing setups. **AutoGen** (Microsoft) enterprise multi-agent. **MetaGPT** roles-as-software-company.

**Humara alignment:** project pehle se **LangGraph** use karta hai (`staff_supervisor.py`, `USE_LANGGRAPH_SUPERVISOR`). Isliye nayi capability **free-stack rakhi** (sirf `free_ai` chain — koi naya heavy dep nahi, lock-refresh nahi) aur LangGraph-compatible (chaaho to supervisor node ki tarah call kar sakte). Yeh "best stack" = jo already prod me proven hai usi pe build, naya bloat nahi.

---

## 3. Niche automation repos surveyed (sales / lead-gen / voice)

| Repo | Kya | Humare liye |
|---|---|---|
| **SalesGPT** (filip-michalsky) | Context/stage-aware AI sales agent (voice/email/SMS/WhatsApp), LLM | Stage-aware conversation pattern — humara `telecaller_brain` + `niche_scripts` already ismilta-julta |
| **Knotie-AI** (avijeett007) | Open-source inbound/outbound AI sales voice agent | Humara voice-agent + callback flow se overlap |
| **sales-outreach-automation-langgraph** (kaymen99) | LangGraph: lead research→qualify→outreach + CRM (HubSpot/Airtable/Sheets) | Humara prospector + reply_agent + crm_sync se overlap; LangGraph graph-shape reference |
| **OpenOutreach** | Self-hosted LinkedIn automation (Playwright stealth) | LinkedIn ToS-blocked (humara stance same — manual only) |

**Takeaway:** humara lead-gen/voice/outreach stack already in repos jaisa (ya aage). Inse naya feature copy karne ki zarurat nahi thi — **asli gap orchestration intelligence me tha**, isliye AgentVerse pattern chuna.

---

## 4. Kya add kiya (implementation)

**`app/agents/coordinator.py`** — naya `coordinate_agentverse()` + 3 helpers:
- `_recruit_experts(goal, feedback, team_size)` — **Stage 1**: recruiter free-LLM se 2-4 goal-tailored expert roles (`{role, expertise, staff?}`); feedback pe team RE-COMPOSE. Fallback trio agar LLM down.
- `_expert_contribution(expert, goal, board, execute)` — **Stage 2/3**: har expert apna perspective; `execute=True` + STAFF-bound + real tool ho to ACTUAL artifact (safe capability reuse), warna draft.
- `_solver_synthesize(goal, contributions, feedback)` — **Stage 2 (vertical solver)**: contributions → ek coherent solution.
- `coordinate_agentverse(goal, execute=False, max_rounds=2, quality_bar=0.75, team_size=3)` — poora loop: recruit → collaborate → solve → **`_verify` (reused evaluator)** → feedback se re-compose + refine (best-of kept). Episodic memory `_recall`/`_remember` se cross-run learning.

**`app/api/agents.py`** — `POST /agents/coordinate-agentverse` (admin + rate-limited, `AgentVerseRequest`). Mirrors existing `coordinate-*` routes.

**Design discipline (project conventions honored):**
- Free-stack only (`free_ai` chain), **no new deps**, lock-refresh nahi.
- **NEVER raises** (har LLM/parse fail pe graceful fallback).
- **SAFE default** `execute=False` (sirf drafts; side-effect agents draft-only).
- Reuses `_verify`/`_recall`/`_remember`/`_persist`/`_TOOLS`/`_log` — koi rebuild nahi.
- Runs `data/coordination_runs.jsonl` me persist; steps `agent_events` (→ /app/team dashboard) me log.

### Kaise alag hai `coordinate-advanced` (Reflexion) se
| | coordinate-advanced (Reflexion) | coordinate-agentverse (NEW) |
|---|---|---|
| Team | FIXED 8-STAFF roster | **Dynamically recruited, goal-tailored** |
| Loop driver | critic score → reflect → retry (same team) | evaluator feedback → **RE-COMPOSE team** → refine |
| Best for | known workflows, self-correction | novel/ambiguous goals jahan right team pehle se pata nahi |

---

## 5. Usage

```bash
# Drafts only (safe):
curl -X POST https://leadsgenai.in/agents/coordinate-agentverse \
  -H "X-API-Key: <admin>" -H "Content-Type: application/json" \
  -d '{"goal":"Solar niche ke liye Q3 lead-gen + content strategy banao","max_rounds":2,"quality_bar":0.75}'
# execute=true → recruited experts ki SAFE staff-tools bhi chalengi (post/research/ops/qa).
```
Response: `{experts[], rounds[], solution, final_score, critique, summary, ...}`.

---

## 6. Verification

- `python scripts/prod_check.py` → **ALL CHECKS PASSED**, `app.main` imports OK, routes **650→651** (naya endpoint registered), env OK.
- Free-stack + never-raise → zero-key par bhi boot/skip-safe (fallback trio + draft).
- Deploy-pending (same pipeline as audit). On-demand API hai (koi auto-loop nahi) → kisi flag ki zarurat nahi; chaaho to team_scheduler se periodically call kar sakte.

## Sources
- AgentVerse repo — https://github.com/OpenBMB/AgentVerse
- AgentVerse paper (ICLR 2024) — https://arxiv.org/abs/2308.10848
- Multi-agent framework survey 2026 — https://www.firecrawl.dev/blog/best-open-source-agent-frameworks
- Open-source AI sales agents — https://github.com/Salesably/awesome-ai-agents-for-sales · https://github.com/kaymen99/sales-outreach-automation-langgraph · https://github.com/avijeett007/Knotie-AI
