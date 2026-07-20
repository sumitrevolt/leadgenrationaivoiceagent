# AI_OPERATING_PROTOCOL — Claude / Codex / Cursor

Mandatory for every coding agent on this repo.

## Governing system
**Universal Execution OS** = parent operating mode for all agents:

- Full text: `docs/context/UNIVERSAL_EXECUTION_OS.md`
- Cursor always-apply: `.cursor/rules/universal-execution-os.mdc`
- Claude always-apply: `.claude/rules/universal-execution-os.md`
- Decision: ADR-129

Default loop: **EXECUTE → TEST → FIX → RETEST → PROVE**.
Do not replace this system; you may advance practices inside it.

## Startup (every session)
1. Read `docs/context/CURRENT_STATE.md`
2. Read `docs/context/ACTIVE_WORK.md`
3. Read `docs/context/SESSION_HANDOFF.md`
4. Read / obey `docs/context/UNIVERSAL_EXECUTION_OS.md` (at least the hard rules if already loaded via always-apply rule)
5. Read only the relevant section of `docs/context/SYSTEM_MAP.md`
6. Verify git state (`HEAD`, dirty, worktrees)
7. Confirm the assigned workstream (max 3 total)
8. Modify only allowed files for that workstream
9. Execute **one** vertical slice to an observable outcome
10. Run targeted tests + relevant gates + real flow proof when UI/API involved
11. Update context files (CURRENT_STATE / ACTIVE_WORK / SESSION_HANDOFF minimum)
12. Produce a clean handoff in `SESSION_HANDOFF.md`

Also: reply Hinglish Roman; free-stack only; end canary line `🐦 pelican` per CLAUDE.md.

## Prohibitions
- Do not start with a full-project audit
- Do not create a new master plan when an active workstream exists
- Do not repeat already verified work
- Do not edit outside the active workstream without recording the dependency in ACTIVE_WORK
- Do not claim production completion from local tests
- Do not leave context only in chat
- Do not modify Swara or voice-related functionality (unless user explicitly lifts freeze)
- Do not create more than three concurrent workstreams
- Do not merge directly to main without gates (tests + prod_check as applicable)
- Do not commit/push/deploy without explicit user ask (except when user already ordered commit in the session mandate)
- Do not fake-complete (“code added”, “flag wired”, “looks correct”)
- Do not build admin UI without wired backend command + audit + runtime confirmation

## Evidence labels
PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN

## Completion statuses (only these)
COMPLETE · PARTIALLY COMPLETE · BLOCKED · NOT VERIFIED · ROLLED BACK

## Contradiction resolution order
1. Current production evidence (`/health`, live flags)
2. Current repository code
3. Current tests
4. Recent committed documentation (`docs/context` > CLAUDE Current State)
5. Historical chat summaries

## Required final report shape
Outcome · Work completed · Verification · Production state · Safety · Remaining risk · Exact next action
