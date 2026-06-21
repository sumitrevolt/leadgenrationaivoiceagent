---
name: llm-council-decision
description: Claude (session agent) ko Council-style faisla lene ka protocol — multi-agent opinions → peer review → Chairman decision. Use jab user strategy/go-no-go/architecture/priority maange, "decision lo", "council jaisa", ya ambiguous high-stakes sawal ho. LIVE engine bhi hai POST /api/agents/council.
---

# LLM Council Decision — Claude ka kaam ka tareeka

> **Core idea (Karpathy):** ek LLM se seedha jawab mat do jab faisla ambiguous/high-stakes ho. Pehle **alag-alag perspectives** (multi-agent / multi-model), phir **peer rank** (bias kam), phir **Chairman ek clear decision**.

Yeh skill **Claude Code / Cursor session** ke liye hai — tum (Claude) user ke liye council jaisa kaam karoge. Runtime engine: `app/agents/llm_council.py` + `POST /api/agents/council` (LIVE `/app/agents`).

---

## Kab Council mode ON karo (mandatory)

In triggers pe **single-shot answer band** — council protocol chalao:

| Trigger | Example |
|---------|---------|
| Strategy / priority | "Pehle email ya WhatsApp?", "Kaunsa niche?" |
| Go / no-go | "Deploy ab?", "DLT wait ya marketing launch?" |
| Architecture fork | "Redis queue ya Celery?", "Naya module ya extend?" |
| Product trade-off | "Pricing tier change?", "Feature cut karein?" |
| User explicitly | "council jaisa", "multi-agent se decide", "sab agents se pucho" |

**Council OFF (seedha kaam karo):** clear bug fix, user ne exact file/bata diya, trivial one-liner, ya user ne "seedha batao" kaha.

---

## Claude session — 4-step protocol (tum Chairman ho)

```text
[1 RECRUIT]  →  [2 OPINIONS]  →  [3 PEER REVIEW]  →  [4 CHAIRMAN DECISION]
 2-4 experts      parallel takes     rank anonymized      ONE verdict + why
```

### Step 1 — RECRUIT (agents banao)

Question ke hisaab se **2–4 tailored experts** — fixed roster blind mat lagao.

| Domain | Example personas |
|--------|------------------|
| Growth | Rohan (outreach), Isha (marketing) |
| Ops | Kavya (infra), Arjun (QA/risk) |
| Product | Boss (business), Dev (data/research) |
| Code | Architect, Security, FinOps |

**Subagent use:** disjoint files / deep research → `Task` tool se parallel subagents (explore / generalPurpose). **Token discipline:** sirf high-stakes pe; chhote sawal pe mat phodo.

**Runtime use:** `POST /api/agents/coordinate-agentverse` — dynamic expert recruit + rounds.

### Step 2 — OPINIONS (parallel, alag lens)

Har expert ko **same question**, alag system prompt. Output chhota rakho (5–8 line each).

- **Claude session:** parallel Task subagents YA ek message me alag sections ("Mistral lens", "Ops lens"…) jab subagents overkill hon
- **LIVE product:** `POST /api/agents/council` — Stage 1 multi-model (Mistral/Groq/Cerebras/Gemini)
- **Staff fanout:** `POST /api/agents/fanout` — same goal, alag STAFF personas

### Step 3 — PEER REVIEW (bias kam)

Har opinion ko **Response A / B / C** label do — reviewer ko pata na chale kaun likha.

Reviewer se maango:
1. Har response ke pros/cons (1 line each)
2. `FINAL RANKING:` numbered list (best → worst)

**Claude session:** khud alag "Reviewer" persona se rank karwao — apna Step-2 output mat prefer karo.

**LIVE:** Council Stage 2 automatic (`llm_council.py`).

### Step 4 — CHAIRMAN DECISION (tum)

Sab opinions + rankings dekh ke **ek clear output**:

```markdown
## Decision
<GO / NO-GO / Option X>

## Kyon (3 bullets)
- …

## Risks (1-2)
- …

## Next action (1 concrete step)
- …
```

User ko pehle individual opinions dikha sakte ho (tabs/sections), phir final — `/app/agents` UI jaisa.

---

## Kaunsa engine kab (Claude choose kare)

| Situation | Engine |
|-----------|--------|
| Full advancement · ROI Top 20 · competitive · moat roadmap · revenue journey | **`executive-council` skill** + `docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md` (Phases 1–6) |
| Ambiguous strategy, user admin hai | **`POST /api/agents/council`** (best — real multi-model) |
| Pro vs con binary | `POST /api/agents/debate` |
| Goal → subtasks → drafts | `POST /api/agents/coordinate` or `-advanced` |
| Dynamic experts + retry | `POST /api/agents/coordinate-agentverse` |
| Code design + tests plan | `POST /api/agents/coordinate-engineering` |
| Compliance / send / pay | **process engine** — council opinion sirf input, gate code pe |

Rule: **Council = opinion quality** · **Process engine = side-effect execute**.

---

## Claude ke liye hard rules

1. **High-stakes = council mandatory** — ek model se turant verdict mat do.
2. **Recruit tailored** — har sawal pe same 4 agents mat lagao.
3. **Peer review anonymized** — apna pehla draft rank me top mat rakho bina reason.
4. **Chairman concise** — user ko 10-page essay nahi; Decision + Why + Next.
5. **Ban-risk** — council "send karo / call karo" decide kar sakta hai as DRAFT; auto-send/call kabhi nahi.
6. **Heavy subagents kam** — 2 parallel Task max unless user ne broad audit maanga; VPS API prefer jab admin token available.
7. **Free stack** — council members = Mistral/Groq/Cerebras/Gemini (`chat_provider`); paid OpenRouter mat assume karo.

---

## Quick API (admin token)

```bash
# Members check
GET /api/agents/council/members

# Full council (~1-3 min)
POST /api/agents/council
{"question": "Pune solar — email outreach ya WhatsApp links pehle?"}
```

Response: `stage1[]` opinions · `stage2[]` rankings · `stage3.response` final · `metadata.aggregate_rankings`.

---

## Anti-patterns

- User ne "decide karo" kaha → tumne bina kisi aur lens ke seedha answer de diya
- Debate (pro/con) use kiya jab 3+ options the (council better)
- Council verdict ko auto-deploy/send maan liya (human + process gate)
- Har chhoti cheez pe 4 subagents — token jalana

---

## Related skills

- `multi-agent-coordination` — primitive matrix
- `coordinator-orchestration` — goal execute abhi
- `agent-loop-design` — daily loops vs one-shot council
