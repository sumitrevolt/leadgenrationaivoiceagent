# AI_OPERATING_PROTOCOL — Claude / Codex / Cursor

Mandatory for every coding agent on this repo.

## Startup (every session)
1. Read `docs/context/CURRENT_STATE.md`
2. Read `docs/context/ACTIVE_WORK.md`
3. Read `docs/context/SESSION_HANDOFF.md`
4. Read only the relevant section of `docs/context/SYSTEM_MAP.md`
5. Verify git state (`HEAD`, dirty, worktrees)
6. Confirm the assigned workstream (max 3 total)
7. Modify only allowed files for that workstream
8. Execute **one** vertical slice
9. Run targeted tests + relevant gates
10. Update context files (CURRENT_STATE / ACTIVE_WORK / SESSION_HANDOFF minimum)
11. Produce a clean handoff in `SESSION_HANDOFF.md`

Also: reply Hinglish Roman; free-stack only; end canary line `🐦 pelican` per CLAUDE.md.

## Prohibitions
- Do not start with a full-project audit
- Do not create a new master plan when an active workstream exists
- Do not repeat already verified work
- Do not edit outside the active workstream without recording the dependency in ACTIVE_WORK
- Do not claim production completion from local tests
- Do not leave context only in chat
- Do not modify Swara or voice-related functionality
- Do not create more than three concurrent workstreams
- Do not merge directly to main without gates (tests + prod_check as applicable)
- Do not commit/push/deploy without explicit user ask (except when user already ordered commit in the session mandate)

## Evidence labels
PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN

## Contradiction resolution order
1. Current production evidence (`/health`, live flags)
2. Current repository code
3. Current tests
4. Recent committed documentation (`docs/context` > CLAUDE Current State)
5. Historical chat summaries
