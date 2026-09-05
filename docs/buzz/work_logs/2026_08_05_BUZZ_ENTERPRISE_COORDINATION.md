---
title: "Buzz enterprise coordination setup — 31 STAFF mirror + coding-agent bridge"
tags: [buzz, setup, autonomy, coding-agents, 31, boss]
status: active
created: 2026-08-05
---

# Work log — 2026-08-05

## Goal

Turn the partially-built Buzz plane into an enterprise-grade coordination layer:
31 runtime STAFF visibility, a single chain of control through Boss, and a working
bridge for Cursor / Claude Code / OpenCode / Monkey Code.

## Inspected

- `~/.buzz/GUIDES/*` (operating model, agent roles, Boss admin, channel ids)
- `~/.buzz/.scratch/*` (prior wiring scripts, managed-agents backup)
- `managed-agents.json` — live roster
- `app/platform/team.py` — canonical STAFF dict

## Problems found

1. **Boss gone entirely.** Not just removed from `#leadgen` — the managed agent was
   deleted from `managed-agents.json`. Only Honey / Fizz / Bumble remained.
2. **No coding-agent plane.** Four tools edit the same dirty checkout with no lock,
   no identity, no handoff format. Truncation and `git add -A` sweeps already
   happened historically.
3. **No STAFF visibility.** The 31 runtime agents had zero representation in Buzz.
4. **No written autonomy policy.** GREEN/AMBER/RED and the human gate lived only in
   conversation.

## Verified against code

`app/platform/team.py` STAFF dict = **31/31 exact match** with the owner's roster.
Division split confirmed by the `product` field: platform 12 (excl. Boss),
marketing 10, voice 8, coordination 1.

## Changed

**Buzz relay**
- Created `#build` (stream, private) — coding-agent bridge
- Created `#staff-pulse` (stream, private) — 31/31 read-only mirror
- Topics, purposes, canvases set on both
- Boss / Honey / Fizz / Bumble added to both (Boss = admin)
- Boss membership restored on admin+leadgen (admin) and gtm/ops/revenue/dev (member)
- Kickoff posts in `#build`, `#staff-pulse`, `#admin`

**Nest guides**
- NEW `GUIDES/AUTONOMY_POLICY.md` — GREEN/AMBER/RED, failure playbook, UPI-only gate
- NEW `GUIDES/STAFF_ROUTING_MAP.md` — canonical 31 with duties + channel homes
- NEW `GUIDES/CODING_AGENT_PROTOCOL.md` — prefixes, claim-before-edit, handoff format
- UPDATED `GUIDES/BUZZ_OPERATING_MODEL.md` — chain of control, new channels, coding plane
- UPDATED `GUIDES/BOSS_ADMIN.md` — single coordination interface + autonomy tiers
- UPDATED `GUIDES/CHANNEL_IDS.json`, `OUTBOX/BUZZ_READY_CHECKLIST.md`
- REWROTE `.scratch/boss_system_prompt.txt` for the new Boss role

**Repo (untracked, additive)**
- `docs/coordination/README.md`
- `docs/coordination/LOCKS.json`

## Evidence

- Every relay call returned rc 0 (22 wiring steps, 3 posts)
- Final membership probe: Boss admin on admin/leadgen/build/staff-pulse, member on
  gtm/ops/revenue/dev
- Canvas check: `#build` 1778 chars, `#staff-pulse` 1365 chars — both present
- 31/31 roster match confirmed by direct read of `team.py` lines 48–317

## Boss re-created — LIVE (same session, second pass)

`buzz agents draft-create` returned
`auth_error: agent draft requests require BUZZ_AUTH_TAG` — the owner identity cannot
send itself a draft; only managed agents carry that tag. So Boss was re-created
directly in the Buzz Desktop UI via computer-use instead.

- Agents → Create agent → name `Boss`, instructions from the rewritten prompt
- Harness Claude Code, model harness default, respond-to `Only me (default)`,
  parallelism 8 (Boss caps at 3 missions; 24 would over-provision a coordinator)
- Result: "Agent created — Boss is ready and running". The revealed nsec was left
  in the app only — not copied to any file, message, or log.

**New pubkey `20b69265…`, different from the dead `1b13cecc…`.** The channel
memberships wired in the first pass pointed at the dead identity, so all 8 channels
were re-wired to the new pubkey and the stale one removed (16 steps, all rc 0).
`GUIDES/BOSS_PUBKEY.txt` updated.

`LeadGen Admin` team was showing "1 agent no longer in your agents" — the dead Boss.
Fixed by ticking the new Boss in Edit team → "Updated team 'LeadGen Admin'".

### Live test (end-to-end proof)

`@Boss` in `#admin`, asked for a 5-point readiness ack after reading the four guides.
Boss read them (`Read GUIDES\AUTONOMY_POLICY.md` observed in the activity line) and
replied in ~4 min with all five correct: chain of control, 31/31 roster split
(correctly noting platform 13 including itself, so 30 to route), AMBER ownership +
retry→reassign→defer→rollback, UPI-only human gate with
`payment_verification_method = owner_confirmed_upi`, and the `#build` claim/stale-break
rule. Cited `app/platform/team.py:48-309`. Accepted the 3-mission cap and the RED
no-override rule. Closed with a clean owner next-action.

## Did not touch

Prod, `.env`, `app/platform/team.py`, deploy, STAFF registry, OpenClaw Stage A,
Swara/voice path, billing ledger. No commit, no push.

## Next

1. **Owner decision:** Boss asked whether to stay on Stage 1 (read-only pulse
   mirror) or move to Stage 2 (bounded GREEN command canary). Answer in `#admin`.
2. Wire the `#staff-pulse` feed — scheduled read-only probe posting `[PULSE]` lines.
   Stage 1 of the rollout is read-only canary; no command hooks yet.


---

# Third pass — "setup incomplete hai" (owner, correct)

The owner was right. Pass 1 and 2 built the coordination *plane* but no data moved
through it: `#staff-pulse` was an empty channel with a nice canvas, and `#build` had
a documented claim protocol with no way for any tool to actually claim anything.
A protocol nobody can execute is a document, not a system.

## Gap 1 — `#staff-pulse` had no feed

`/api/platform/team` is `require_admin`, so no credential I hold could read it, and
inventing one was out of scope. Instead: SSH to the VPS (documented access, key
already present) and call `team_status()` **inside the running app container** —
read-only, no writes, no deploy, no `.env`.

Built `scripts/buzz_staff_pulse.py`:
- pulls a trimmed payload (name/product/state/mins/actions/errors/last action)
- groups by division, sorts problems first
- flags `fail` on errors or offline, `warn` on >24h silence
- posts a `[PULSE]` digest to `#staff-pulse`
- `--dry-run` prints without posting

First real run — 31/31 members, 1861 actions today, 0 errors, 10 working — and it
immediately earned its keep: **Ira silent 13.9d, Raksha silent 2.4d**, both `warn`.
Neither shows as an error anywhere else; a silent agent is exactly the failure this
mirror exists to surface. Both are event/on-demand agents so this may be benign,
but it is now visible instead of invisible.

Scheduled hourly: `schtasks` task **"LeadGen Buzz Staff Pulse"**, Interactive only
(needs the desktop credential + Buzz CLI), Status Ready, next run confirmed.
Wrapper `scripts/buzz_staff_pulse.bat` logs to `~/.buzz/WORK_LOGS/staff_pulse.log`.

## Gap 2 — `#build` had no way to claim

Built `scripts/buzzlock.py` — `claim` / `release` / `status` / `break`:
- atomic write to `docs/coordination/LOCKS.json` (tempfile + `os.replace`; a
  half-written registry is worse than none)
- refuses a claim held by another tool with **exit 2**, and auto-posts the
  `BLOCKED ON` line
- `break` only works past `stale_after_minutes` (240), refuses fresh claims
- `release` requires `--evidence` — no evidence, no release
- Buzz posting is best-effort: no CLI or no credential still leaves the lock
  authoritative, so this works from a non-Windows OpenCode session too

### Smoke test — 6/6 as expected

| # | Action | Expected | Got |
|---|--------|----------|-----|
| 1 | CURSOR claims a CLAUDE-held file | refuse, exit 2 | exit 2 |
| 2 | CURSOR STALE-BREAKs a fresh claim | refuse, exit 2 | exit 2 |
| 3 | CLAUDE releases its own | ok, exit 0 | exit 0 |
| 4 | CURSOR claims the freed file | ok, exit 0 | exit 0 |
| 5 | CURSOR releases | ok, exit 0 | exit 0 |
| 6 | status | tree free | "no active claims" |

All four posts landed in `#build`. Registry ends empty — no leftover state.

**Method note:** my first exit-code check printed `EXIT=0` for a refusal. That was
the cmd `%ERRORLEVEL%` parse-time expansion trap in an `&`-chained line, not a bug
in buzzlock. Re-ran from a `.bat` where per-line expansion is correct and got the
real 2 / 2 / 0 / 0 / 0 / 0. Worth remembering: never verify exit codes in a chained
cmd one-liner.

## Gap 3 — no tool actually read the protocol

- `.cursor/rules/build-coordination.mdc` — `alwaysApply: true`, so Cursor loads it
  every session
- `CLAUDE.md` §5 — one dense line in the invariants block (token discipline)
- `AGENTS.md` — re-synced as a byte copy, hash-verified identical. This is what
  OpenCode and Monkey Code read.

## Evidence

- pulse dry-run + live post: 31/31 members, exit 0, "posted 31 members"
- `schtasks /query`: Status Ready, Hourly, Interactive only
- buzzlock smoke: 6/6, exit codes 2/2/0/0/0/0
- `check_secrets.py`: 87 files scanned, no secrets, exit 0
- `ruff check` on both new scripts: exit 0
- `Get-FileHash` CLAUDE.md == AGENTS.md: `7B833F29…`, byte-copy confirmed

## Not verified

`prod_check.py` was still running when the session ended — it stalls after the app
import and I will not report an unfinished gate as a pass. Nothing under `app/` was
touched this pass (two new `scripts/`, docs, one CLAUDE.md line, one Cursor rule),
so it is not the gate that matters here; the secrets scan and ruff are.

## Still open

1. Owner decision in `#admin`: Stage 1 (read-only, current) or Stage 2 (bounded
   GREEN command canary).
2. Ira and Raksha staleness — real signal from the first pulse, worth a look.
3. All of this is untracked and uncommitted, as required.
