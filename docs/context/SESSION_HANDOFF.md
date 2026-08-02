# SESSION_HANDOFF - overwrite every session end

## Session objective
Stop Warp Claude Code `PostToolUse` (`on-post-tool-use.sh`) from repeatedly reopening Cursor panels — project ke liye disable.

## Outcome — DONE (CODE-PRESENT, needs Claude Code restart on Windows)
- **Verdict:** glitch / plugin side-effect — LeadGen requirement NAHI.
- Tracked `.claude/settings.json` ab `"enabledPlugins": {"warp@claude-code-warp": false}` set karta hai.
- `.gitignore` me `!.claude/settings.json` exception (hooks/local secrets abhi bhi `settings.local.json` pe).
- ADR: `memory/decisions.md` → ADR-WARP-PLUGIN-OFF · `docs/AI_WORKFORCE.md` Tier-3 line updated.
- No app/runtime/deploy/voice change.

## Owner action (Windows)
1. Pull/merge this branch (or cherry-pick the settings commit).
2. Agar pehle se local `.claude/settings.json` hai → usme `enabledPlugins.warp@claude-code-warp: false` merge karo; local guard hooks mat mitao.
3. Claude Code / Cursor agent session restart.
4. Confirm: tool call ke baad `on-post-tool-use.sh` panel wapas nahi khulta.

## Safety
Warp = optional Warp-terminal UX only. Product flags, dial, WA auto-send, billing untouched.
