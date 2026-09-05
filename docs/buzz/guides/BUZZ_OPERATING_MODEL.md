---
title: "Buzz Operating Model — LeadGen AI"
tags: [buzz, leadgen, admin, coordination]
status: active
created: 2026-08-03
---

# Buzz Operating Model (LeadGen AI)

Buzz = **human + coding-agent collaboration plane**. Yeh 31 runtime STAFF agents ko replace nahi karta.

## Three planes (do NOT mix)

| Plane | Where | Job |
|-------|--------|-----|
| **Buzz** (this) | `leadsgenai.communities.buzz.xyz` | Owner + Desktop agents coordinate, research, patch, report |
| **OpenClaw / Owner OS** | `/admin` + Owner OS | GREEN-only copilot over existing Boss → 31 STAFF |
| **Runtime STAFF** | VPS Celery / `team.py` | Real business work (Rohan, Isha, Swara, …) |

Rules:
- Buzz agents are **NOT** a 32nd STAFF persona.
- Do **not** invent new names in `app/platform/team.py` from Buzz.
- OpenClaw stays Stage A GREEN-only; Buzz Admin mirrors that discipline.
- Swara / voice calling path = **FROZEN** for Buzz code edits.

## Best-practice habits (from Block Buzz research)

1. **Narrow channels, one job** — never dump everything in `#general`.
2. **Act only on @mention** — no ambient spam; stopping instruction required for multi-agent threads.
3. **Chief-of-staff routes; workers execute** — Boss/Honey coordinate; Fizz builds; Bumble researches.
4. **Evidence before "done"** — paste exit codes / `/health` / pytest; prose ≠ proof.
5. **Earn write scope** — default read-only/forensic; commit/push/deploy only when owner explicitly asks.
6. **Identity-scoped access** — membership = permission; secrets never in channel text.

## Channel map

| Channel | Purpose | Primary agents |
|---------|---------|----------------|
| `#admin` | Owner decisions, launch readiness, routing | Boss (admin), Honey |
| `#leadgen` | Primary project home | All |
| `#gtm` | Hot Queue → 2nd paid customer | Honey, Fizz |
| `#ops` | Health, deploy, WAHA, queues | Honey, Bumble |
| `#revenue` | Billing / UPI / pay-truth | Honey, Bumble |
| `#dev` | Code / PRs / tests | Fizz, Bumble |
| `#build` | Coding-agent bridge: Cursor / Claude / OpenCode / Monkey Code. Claim-before-edit locks | Fizz, Bumble |
| `#staff-pulse` | Read-only mirror of the 31 runtime STAFF | Boss, Honey |
| `#general` | Announcements only | — |
| `#Welcome` | Onboarding / setup checks | Fizz |

Exact UUIDs: `GUIDES/CHANNEL_IDS.json`.

## Chain of control (2026-08-05, owner decision)

```
Buzz (#admin)  ->  Boss  ->  Owner OS / OpenClaw  ->  31 runtime STAFF  ->  Celery
```

- Buzz is an **interface**, never a second control plane.
- Commands enter through **Boss only**. No direct STAFF mutation hooks from Buzz.
- No duplicate Buzz bots for any of the 31 — `#staff-pulse` mirrors them read-only.
- Autonomy tiers: GREEN agent-executes · AMBER Boss-decides · RED system-refuses.
  Exactly **one** human gate: real UPI bank-credit confirmation + paid-ledger marking.
- Full policy: `GUIDES/AUTONOMY_POLICY.md` · roster: `GUIDES/STAFF_ROUTING_MAP.md`

## Coding-agent plane

Cursor, Claude Code, OpenCode and Monkey Code coordinate in `#build` with a
claim-before-edit file lock (`docs/coordination/LOCKS.json` in the repo). Every
message carries a tool prefix; every handoff carries evidence. A coding tool never
commands a runtime STAFF agent — it raises the need in `#dev` and Boss routes it.
Full protocol: `GUIDES/CODING_AGENT_PROTOCOL.md`.

## Hard LeadGen invariants (never break)

- Compliance gates never disabled (DND fail-closed, TRAI window, AI disclosure, DPDP).
- Secrets only in `.env` — never in Buzz messages, Nest notes, or commits.
- No commit / push / deploy without explicit owner ask.
- Free AI stack only — no paid STT/TTS/LLM add.
- Deploy only via `scripts/deploy_vps.sh` + `APP_VERSION=<sha>`.
- Cold WhatsApp blast (`SALES_AUTOPILOT_WHATSAPP_ENABLED`) stays OFF. Post-call Swara-interested WA is owner-gated separately — do not flip without explicit ask.
- Prod SHA truth = direct HTTPS `/health.version` only.

## Definition of Done (Buzz tasks)

1. Context: `docs/context/CURRENT_STATE.md` + `ACTIVE_WORK.md`
2. Targeted pytest green (if code changed)
3. `scripts/prod_check.py` PASS (if code/runtime touched)
4. Report evidence in the channel that owns the work
5. Update Nest `WORK_LOGS/` for non-trivial sessions

## Owner

Human: **sumit** (`@leadsgenai`) — sole authority for AMBER/RED, spend, secrets, deploy, paid-ledger writes.


## Mention mechanics (learned the hard way, 2026-08-03)

- **Agents wake only on `@mention`.** A message in a channel they belong to is otherwise invisible
  to them. Channel membership is permission, not attention.
- The `@` must **resolve to a chip** before you send. Plain text that merely looks like a mention
  does not trigger anything.
- **A thread reply without an `@mention` does not re-trigger the agent — even inside its own thread.**
  This silently cost one full round trip: a re-probe request sat unread in Honey's own thread until
  it was re-sent with the tag.
- A prod probe over SSH runs for several minutes and posts progress lines as it goes. Let it finish.
  Re-asking mid-flight starts a second run against the same box.

## Nest knowledge added 2026-08-03

- `GUIDES/PROD_PROBE_RUNBOOK.md` — the proven read-only prod probe: `/health`, SHA agreement,
  container skew, queues, named-flag reads without dumping `.env`, and asking the code rather than
  the filesystem for kill-switch state.
- `RESEARCH/SSH_ATTRIBUTION_GAP.md` — one shared root key across human and all agents means no
  change on the VPS is attributable. Includes an open action to rotate a `GEMINI_API_KEY` found in
  plaintext in root's `.bash_history`.
- `GUIDES/LEADGEN_PROJECT.md` — repo pointer, stack, hard rules, Definition of Done.
- Nest `AGENTS.md` now carries the operating rules inline so every agent inherits them.
