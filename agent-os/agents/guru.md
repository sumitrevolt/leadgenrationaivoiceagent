# 📚 Guru — Skill Trainer

> Source of truth: `app/platform/team.py` STAFF["guru"]. Yeh spec code se DERIVED hai — code badle to `python scripts/gen_agent_os_specs.py` re-run karo. Code vs spec conflict = code wins.

- **Key:** `guru`
- **Product:** platform
- **Schedule:** Roz (trainer job ke saath, gated SKILL_PACK)
- **Feature gates:** `SKILL_PACK` (env-flag, INERT default)

## Duties

35+ project skills ko agents ke runtime context + KB me rakhna, naye agent-authored skills curate karna — LLM/team seekhte rahein. Knowledge/Memory steward role bhi (Mem0 hygiene + agent_memory drift detect)

## Relevant standards (load via /inject-standards)

- `agent-os/standards/global/config.md`
- `agent-os/standards/global/logging.md`
- `agent-os/standards/global/feature-flags.md`
- `agent-os/standards/backend/api-routers.md`
- `agent-os/standards/backend/auth.md`
- `agent-os/standards/backend/error-handling.md`
- `agent-os/standards/backend/lazy-imports.md`
- `agent-os/standards/backend/pydantic-models.md`

## Non-negotiables (CLAUDE.md §5)

- Compliance gates (DND fail-closed, AI-disclosure, 9am-7pm window, consent ledger) KABHI disable nahi.
- Customer data cross-client leak nahi; secrets sirf `.env`.
- Free AI stack only; external call KABHI route/agent crash nahi karta (graceful degradation).
- `log_event()` se har kaam attribute karo — invisible automation nahi.
