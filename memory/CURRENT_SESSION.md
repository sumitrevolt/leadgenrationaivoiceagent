# CURRENT_SESSION.md — OmniRoute audit session (2026-07-12→13, updated 2026-07-13)

_Note: this repo's own memory protocol (CLAUDE.md §9) routes decisions to
`memory/decisions.md` (see ADR-081 through ADR-084, full detail) — this file is a
lightweight pointer kept because it was explicitly requested. Update `decisions.md`
for anything durable._

## UPDATE (2026-07-13): first real Claude completion through OmniRoute — VERIFIED, with one caveat
Sumit connected the "Antigravity" OAuth provider himself (browser-flow OAuth, not the
broken PKCE path below) — exposes real Claude models (`claude-sonnet-5`,
`claude-opus-4-6-thinking`, `claude-sonnet-4-6`). Ran the Windows bridge script for
real: Windows Claude Code -> OmniRoute -> Antigravity -> `claude-sonnet-4-6` -> back to
Windows, exit code 0, confirmed via real Request Logs entries (200 status, real token
counts) and live Provider Topology status — genuine E2E round trip proven for the
first time. **Caveat found and documented, not glossed over:** the response contains
one invisible `U+200D ZERO WIDTH JOINER` character not present in the requested echo
string — ruled out a local encoding bug as the cause (fixed a real one first, then
re-verified at the byte level). Likely an output watermark/fingerprint from the
Antigravity relay; flagged to Sumit as directly relevant to the same account-risk
category the Claude Code/Codex OAuth ban-risk dialog warned about. Full evidence:
`uat_evidence/omniroute_setup/e2e/ANTIGRAVITY_CLAUDE_E2E_PROOF.md`, ADR-084.

## UPDATE (evening): both blockers below RESOLVED by Sumit
Sumit installed + signed into the Claude in Chrome extension, then logged into
OmniRoute's dashboard himself using the page's own displayed default password
(`CHANGEME` — Claude never touched the password field). Real browser proof (screenshot
+ URL + page text at `/dashboard/api-manager`) and a full real MCP JSON-RPC round trip
(`initialize` + `tools/list` [91 tools] + 3 `tools/call` invocations, all succeeded)
are now recorded — see ADR-082 for full detail. `.mcp.json`'s `omniroute` entry is
`ACTIVE`. **Newly found open item:** `omniroute oauth start --provider claude-code
--no-browser` returns an empty/malformed device-code response (`Visit: undefined`) —
looks like an OmniRoute-side OAuth-app config gap, not fixable by retrying. Provider
connections still show 0, so Phase 5 (routing) and Phase 8 (Claude launch profiles)
remain open pending that fix or Sumit adding a raw provider key himself.

## Paths / version / ports
- OmniRoute binary: WSL-only, `/usr/bin/omniroute`, **v3.8.46** (upgraded from 3.6.5
  this session). No working Windows-native `omniroute` command.
- Gateway: `http://127.0.0.1:20128` (HTTP) · WS `127.0.0.1:20129` (loopback).
- Data dir: `/root/.omniroute/` (WSL) — `.env`, `storage.sqlite` (encrypted).
- Windows Claude Code: `C:\Users\Ratanshila\.local\bin\claude.exe` v2.1.207.0 — separate
  filesystem from WSL's `/root/.claude/`; `setup-claude`/`launch` run from WSL will NOT
  be visible to it without an explicit copy step (unresolved, next-session item).
- tmux: session `leadgen-omni`, window `gateway` (1 pane, the server) + window `leadgen`
  (3 panes = coding lanes: implement/research/…).

## Decisions this session
- Upgrade OmniRoute 3.6.5→3.8.46 (backup + rollback proven, near-zero downtime).
- Do NOT set OmniRoute's admin password myself (credential-creation is outside
  Claude's operating rules even under "don't pause" instruction) — documented the
  exact one-line fix for Sumit instead.
- Wire `block_if_sensitive` (existed, untested-in-integration) into all 4 provider
  dispatch points in `free_ai.py` as defense-in-depth PII/secret hard-block.
- Add `app/platform/omniroute_client.py` + `OMNIROUTE_ENABLED` flag as an explicitly
  INERT, unwired integration point — not claimed as "done" since it can't be verified
  end-to-end yet.

## Blockers — history + current state
1. ~~OmniRoute admin auth never set up~~ — **RESOLVED** (Sumit logged in himself, see
   UPDATE above).
2. ~~Claude in Chrome extension not connected~~ — **RESOLVED** (Sumit installed +
   signed in).
3. **OAuth device-flow broken for claude-code/codex direct** —
   `omniroute oauth start --provider claude-code/codex --no-browser` returns
   `Device code: ` (empty) / `Visit: undefined`. Root cause confirmed (PKCE-vs-device
   mislabel, see OAUTH_ROOT_CAUSE.md) — still open, but **sidestepped, not fixed**: a
   real Claude completion now routes through OmniRoute via the Antigravity provider
   instead (see UPDATE above). Direct Anthropic/OpenAI key or fixed OAuth still not
   done; Claude cannot enter credentials per the credential-entry boundary — this
   remains Sumit's call if he wants direct-provider access too.
4. **Still open:** WSL (`/root/.claude/`) vs Windows-native Claude Code
   (`C:\Users\Ratanshila\.claude\`) profile-writing gap for `omniroute
   setup-claude`/`launch` — flagged, not yet solved.

## Rollback
`uat_evidence/omniroute_setup/ROLLBACK.md` — downgrade command, config restore, gateway
restart, confirms LeadGen app/Redis/Celery/FastAPI are unaffected either way (OmniRoute
is not in the customer request path).

## Full audit trail
`uat_evidence/omniroute_setup/` (discovery scripts + raw output incl.
`PHASE9_STATUS.md` real MCP proof, `phase9_mcp_http4_output.txt` raw JSON-RPC), `docs/
OMNIROUTE_ENGINEERING_RUNBOOK.md`, `docs/OMNIROUTE_ADMIN_GUIDE_HINGLISH.md`,
`memory/decisions.md` ADR-081 (upgrade + PII gate) + ADR-082 (login + MCP verified,
canonical for this update).
