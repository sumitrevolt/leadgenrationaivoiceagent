---
name: executive-council
description: LeadGen Executive Advancement Council — revenue/conversion/retention/moat analysis WITHOUT generic repo audit. Use when user asks advancement council, ROI roadmap, competitive gap, revenue friction, product moat, "council prompt", or strategic product review. Read docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md and run Phase 1–6.
---

# Executive Advancement Council

**Full protocol:** [`docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md`](docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md) — **Read entire doc first**, then execute phases.

## When to use (vs other council tools)

| Situation | Use |
|-----------|-----|
| Strategic advancement · ROI · competitive · revenue journey · moat roadmap | **This skill** (doc Phases 1–6) |
| Single ambiguous go/no-go · architecture fork | `llm-council-decision` skill |
| Multi-model runtime verdict | `POST /api/agents/council` (admin) |

## Invoke checklist (5 steps)

1. **Read** mandatory doc order in council prompt (handoff → SOP → CLAUDE → SESSION_LOG tail → Competitor doc).
2. **Assume GREEN** gates from prompt — do NOT re-audit explorer/cross-path/lifecycle unless regression proved.
3. **Grep `app/`** before claiming any gap — cite file paths in deliverables.
4. Run **Phases 1–6** — default = analysis only; **Phase 5 implement** only if user asks.
5. Output **7 deliverables** in Hinglish (see council doc) — max 5 ship-now recommendations.

## Product constraints (non-negotiable)

- DO alag products — no bundle USP (`product-split-adr`)
- Free stack only · compliance gates intact
- UPI LIVE — first customer = sales/ops
- Voice outbound = commercial blocked until Vobiz/DLT

## Live probes

```powershell
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

## Related

- `production-ready` — launch certification gates
- `advancement-roadmap` — shipped P0–P9 technical items
- `frontend/battlecard.html` — competitive intel UI
