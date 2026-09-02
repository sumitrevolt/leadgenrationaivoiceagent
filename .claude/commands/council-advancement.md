---
description: Run LeadGen Executive Advancement Council — revenue ROI, competitive gaps, moat roadmap (NOT generic repo audit). Reads executive-council skill + docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md.
---
# /council-advancement — Executive Product Council

Strategic advancement session for LeadGenAI. **Not** a bug hunt or full-repo audit.

## Steps

1. Read `.claude/skills/executive-council/SKILL.md`
2. Read **full** `docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md`
3. Follow mandatory read order (handoff → PRODUCT_SOP → PROJECT_SOP → CLAUDE → SESSION_LOG tail → Competitor doc)
4. Execute **Phases 1–6** from the council doc
5. Produce **7 deliverables** in Hinglish Roman

## Default mode

**Analysis + roadmap only.** Do NOT implement (Phase 5) unless `$ARGUMENTS` contains `implement` or user explicitly asks to ship code.

## Quick live check

```powershell
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

## Narrow decision alternative

Single go/no-go without full council → `llm-council-decision` skill or `POST /api/agents/council`.
