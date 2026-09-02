# Prompt Library — Index & Usage

> **Full production prompts:** [`AGENT_SYSTEM_PROMPTS.md`](AGENT_SYSTEM_PROMPTS.md) (12 agents, inject-ready)
> **Voice runtime brain:** `app/voice_agent/telecaller_brain.py` · **Niche scripts:** `app/voice_agent/niche_scripts.py`
> **LLM chain:** `app/voice_agent/free_ai.py` · **Updated:** 2026-06-20

---

## 1. Library structure

| Category | Location | Use when |
|----------|----------|----------|
| **Staff system prompts** | `AGENT_SYSTEM_PROMPTS.md` | Boss, Swara, Rohan, Isha, Arjun, Meera, Kavya, … |
| **Voice call brain** | `telecaller_brain.py` | Live calls — KB-grounded, ≤2 sentences, 1 question |
| **Niche openers** | `niche_scripts.py` | Per-niche greeting + objection handlers |
| **Marketing content** | `post_generator.py`, `structured.py` | Social posts (`USE_STRUCTURED_CONTENT=1`) |
| **Sales / BANT** | `sales_qualify.py`, `sales_team.py` | Deep qualification |
| **Reply triage** | `reply_agent.py` | Inbound email intent + Hinglish draft |
| **Hinglish copy kits** | `Sales_Kit_Hinglish.md`, `Marketing_Kit_LeadGenAI.md` | Human sales/marketing copy |
| **241 skills** | `.claude/skills/` + `data/skills_extra/` | Agent runtime via `skill_pack.py` |
| **Council decision** | `.claude/skills/llm-council-decision/SKILL.md` + `llm_council.py` | Claude session + `POST /api/agents/council` — multi-opinion → peer rank → Chairman |

---

## 2. Prompt index (staff)

| Agent | Prompt section | Output shape |
|-------|----------------|--------------|
| Boss | AGENT_SYSTEM_PROMPTS §1 | JSON plan + teams + confidence |
| Swara | §2 | Qualification + next_action (voice) |
| Dev | §3 | KB seed summary |
| Rohan | §4 | Outreach angle + email draft |
| Isha | §5 | Caption + hashtags + CTA |
| Arjun | §6 | QA scorecard (double/repeat/slow) |
| Meera | §7 | Transcript analysis + fixes |
| Kavya | §8 | Health summary Hinglish |
| Tara | §9 | Telephony readiness report |
| Nikhil | §10 | Revenue/churn digest |
| … | See full file | … |

---

## 3. Voice agent rules (all calls)

From `telecaller_brain.py` + TRAI compliance:

- Open with **AI disclosure** ("main ek AI assistant hoon")
- Promotional: **10am–7pm IST**, DND scrub pass required
- Max **2 sentences**, **1 question** per turn (ACP pattern)
- KB retrieval timeout — never block call on RAG failure

Tuning order: **web-call first** (`/app/test-call`) → phone verify last.

---

## 4. Sales prompts (patterns)

| Stage | Template source |
|-------|-----------------|
| Cold email | `auto_outreach.py` + `cold-email-craft` skill |
| Follow-up D3/D7 | `auto_outreach` scheduler |
| Objection handle | `niche_scripts.py` + Swara prompt |
| Proposal | `sales_pipeline.py` auto-proposal |
| Review ask | `review_engine.py` (happy ≥4 → Google review) |

---

## 5. Support / ops prompts

| Use | Where |
|-----|-------|
| Daily digest Hinglish | `app/agents/staff.py` `run_digest` |
| Ops watchdog alert | `ops_watchdog.py` |
| Incident summary | `OPERATIONAL_RUNBOOKS.md` templates |

---

## 6. Injection pattern (code)

```python
from app.voice_agent import free_ai

text = await free_ai.chat(
    messages=[{"role": "user", "content": user_msg}],
    system=SYSTEM_PROMPT_FROM_AGENT_SYSTEM_PROMPTS,
    max_tokens=180,
)
```

Bulk content (posts): `free_ai.chat(..., profile="bulk")` → Cerebras-first when tokens ≥180.

---

## 7. Versioning & change control

1. Edit prompt in `AGENT_SYSTEM_PROMPTS.md` or module docstring
2. Run `scripts/agent_tester.py` after **any voice prompt** change
3. Log in [`CHANGELOG.md`](CHANGELOG.md)
4. Optional: `eval_gate` regression if `EVAL_GATE=1`

---

## 8. Do not commit

- API keys in prompts
- Client PII in example blocks
- Per-client secrets — use KB namespace `client:{id}` instead
