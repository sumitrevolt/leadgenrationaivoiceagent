# Research & Knowledge Docs Index (2026-06-19)

Active research docs (web-sourced, cross-check with `CLAUDE.md` + code before trusting):

| Doc | Use |
|-----|-----|
| `Competitor_Top20_Feature_Gap_2026.md` | Feature gaps vs 26 competitors |
| `COMPETITOR_INFRA_GROWTH_BLUEPRINT_2026.md` | Infra/voice moat vs Retell/Vapi |
| `Agentic_Customer_Acquisition_Playbook.md` | Channel cadence + DLT playbook |
| `Architecture_Research_RAG_Agents_MCP.md` | RAG/agents/MCP stack choices |
| `ADVANCEMENT_ROADMAP_2026.md` | Prioritized build backlog |
| `TRAI_CONSENT_CONFIRM_SPEC.md` | Voice compliance gate (build at DLT unlock) |
| `INFRA_HARDENING_GUIDE.md` | Cloudflare, R2/B2, HA options |
| `Marketing_Kit_LeadGenAI.md` / `Sales_Kit_Hinglish.md` | GTM copy (pricing → `packages.py` / `voice_packages.py`) |

**Archived / stale:** `legacy/THREE_BRAIN_ARCHITECTURE.md` (AuraLeads era — do not implement).

**2026-06-19 docs-audit + cleanup** (report consolidated into git history 2026-06-25):
- Removed 12 zero-reference scratch/one-time/superseded docs (5× `_route_*`, COORDINATOR_SKILL_BUILD_SUMMARY, SKILL_REVIEW_2026_06, GSC_SUBMIT_TODAY, FEATURE_TRIAGE_AUDIT, PROD_GAPS_2026_06_10_BATCH, Competitor_Infra_Research → folded into the infra blueprint, legacy/production_readiness_report).
- Fixed STALE pricing in `Marketing_Kit_LeadGenAI.md` (Starter/Growth/Advanced now 1199/2999/6999 = `packages.py` truth).
- Wired the dormant CRAG module into the public chatbot (`app/marketing/chatbot.py`, gated `USE_AGENTIC_RAG`) — it previously had zero call-sites.
- Key audit finding: most "gaps" in the competitor/infra docs are ALREADY BUILT — code is ahead of the docs. Remaining open items are DLT/telephony/paid/paperwork (external-blocked) or env-flag flips, not new builds.

**Audit script:** `python scripts/agents_skills_debug.py` (agents) · grep `docs/` refs in `.claude/skills/`.
