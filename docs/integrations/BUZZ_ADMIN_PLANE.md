# Buzz Admin Plane — LeadGen AI

> Collaboration workspace for humans + Desktop coding agents.
> Relay: `leadsgenai.communities.buzz.xyz` · Desktop: Block Buzz
> Updated: 2026-08-03 (completion pass)

## What Buzz is (and is not)

| Is | Is not |
|----|--------|
| Owner + agent home base (channels, mentions, canvases, drafts) | Replacement for 31 runtime STAFF in `team.py` |
| Coordination / research / patch discussion plane | OpenClaw / Owner OS prod GREEN-only copilot |
| Identity-scoped membership (Nostr keys) | Authority to deploy or weaken compliance |

OpenClaw Stage A + Boss → 31 STAFF remain the production control path. Buzz agents are a **separate plane** — do not invent a 32nd STAFF persona from Buzz setup.

### Coordination Hub (ADR-150)

If `COORDINATION_HUB_ENABLED=1`, Buzz can send **presence/events only** to
`POST /api/admin/owner-os/coordination-hub/webhooks/buzz` using
`COORD_HUB_BUZZ_SECRET` HMAC (`X-CoordHub-*` headers: timestamp, nonce, signature).
This is **not** the human admin bearer / `ADMIN_API_KEY`. Hub is a thin Owner OS
projection — not a second control plane or STAFF registry. Flag default OFF.

## Live workspace layout

| Channel | Job | Agents |
|---------|-----|--------|
| `#admin` | Owner decisions, launch readiness, routing | Boss+Honey **admin**; Fizz/Bumble member |
| `#leadgen` | Primary project home | Boss+Honey **admin**; Fizz/Bumble member |
| `#gtm` | Hot Queue → 2nd paid Marketing customer | all 4 members |
| `#ops` | Health, deploy, WAHA, queues/DLQ | all 4 members |
| `#revenue` | Billing / UPI / pay-truth (no fake PAID) | all 4 members |
| `#dev` | Code / tests / PRs | all 4 members |
| `#general` / `#Welcome` | Announcements / onboarding | Welcome defaults |

Nest (machine-local) guides: `~/.buzz/GUIDES/`. Checkout junction: `~/.buzz/REPOS/leadgenrationaiagent` → this repo.

## Agents (team: LeadGen Admin)

| Agent | Role | Status |
|-------|------|--------|
| **Boss** | Admin / Chief of Staff | LIVE — NIP-OA, `#admin`/`#leadgen` admin, buzz-acp, owner-only |
| **Honey** | Forensics + ops truth | LIVE — LeadGen prompt, `#admin`/`#leadgen` admin, owner-only |
| **Fizz** | Maker / implementer | LIVE — LeadGen prompt, owner-only |
| **Bumble** | Researcher | LIVE — LeadGen prompt, owner-only |

Harness: `claude-agent-acp` via `buzz-acp`. Respond policy: **owner-only** (no agent cross-allowlist loops).

## Completion checklist (2026-08-03)

- [x] Private channels created + topics/purposes set
- [x] All 4 agents members of admin/leadgen/gtm/ops/revenue/dev
- [x] Boss+Honey admin on `#admin` + `#leadgen`
- [x] Team `LeadGen Admin` includes Boss + Honey/Fizz/Bumble
- [x] Canvases on admin/gtm/ops/revenue/dev
- [x] Nest guides + repo doc + WORK_LOG
- [x] `@Boss` reply smoke in `#admin`
- [x] No Desktop Save left for Boss create (programmatic NIP-OA)

## Owner how-to

1. Open Buzz Desktop → `#admin`
2. `@Boss ab launch ke liye kya bacha?` (max 3)
3. Route build work with `@Fizz`, forensics `@Honey`, research `@Bumble`

## Research basis

Block Buzz (Apache-2.0, Nostr): agents as channel members with own keys; ACP harness; narrow one-job channels; @mention-only activation; chief-of-staff stopping rule to avoid agent ping-pong.

## Multi-harness + OmniRoute lane (2026-08-09, ADR-167)

The 2026-08-03 checklist above is unchanged and still accurate. This section is
additive: it covers the second harness and the free-provider lane.

**Measured constraint.** `scripts/buzz_agent_cost.py --days 7` (2026-08-09):
Claude Code 591M tokens / 2,020 calls, Codex 266M / 1,810, **Codex subscription
peaked at 100% used**. Counterfactual at API list price ≈ $483; actual marginal
cost ₹0. Quota, not money, is what takes an agent offline here.

**Participant classes.** ACP agents need a headless ACP binary; keyboard tools do
not and never join a channel.

| Participant | Harness / binary | Status |
|---|---|---|
| Boss · Honey · Fizz · Bumble | `claude-agent-acp` | LIVE (unchanged) |
| **Comb** — independent reviewer | `codex-acp` (bundled with Buzz Desktop) | **CODE-READY**, LIVE only after owner Saves the draft |
| Goose | `goose` 1.45.0 | installed, no agent created |
| Cursor · OpenCode · Freebuff · Monkey | n/a | keyboard-side only — lock prefix + `#build` handoff is the whole integration |

Freebuff is an Electron app and OpenCode has no binary on PATH, so neither can be
a Buzz agent. `scripts/buzzlock.py` now registers all seven tools; it also
self-initialises `LOCKS.json` (a fresh worktree used to crash on `status`).

**Cross-check is owner-routed.** Respond-policy stays owner-only per
`AGENT_ROLES.md` — agents do not @-loop each other. The owner routes
`@Fizz` (Claude) → `@Comb` (Codex) and decides. Different harness is the point;
two Claude agents reviewing each other correlate their mistakes.

**OmniRoute lanes.** OmniRoute is a local gateway (`127.0.0.1:20128/v1`, WSL tmux
`leadgen-omni`) fanning out to free providers via the `leadgen-project-best`
combo. Three lanes, labelled by evidence:

- **A — subscription:** Buzz agents on their native harnesses. PROVEN, live.
- **B — keyboard via OmniRoute:** `scripts/start-claude-omniroute.ps1`. PROVEN.
- **C — Buzz agents via OmniRoute:** `scripts/start-buzz-omniroute.ps1`.
  **UNVERIFIED.** `claude-agent-acp` reads `ANTHROPIC_BASE_URL`/`AUTH_TOKEN`/
  `MODEL`, but whether Buzz Desktop forwards a process env block to the harness it
  spawns is not established. The wrapper is preview-by-default, refuses to launch
  against a dead gateway (exit 2), sets env process-scoped only, and requires
  OmniRoute call-log traffic as proof. This reverses the 2026-08-03 note "keep
  Buzz on native buzz-acp" — the cost evidence above is the reason, and Lane A
  remains the default.

**Verified live 2026-08-09.** Gateway brought up (Redis PONG, tmux `leadgen-omni`,
`:20128` UP); `/v1/models` = 200; `leadgen-project-best` **is addressable as a
model id** — load-bearing, since Lane C sets `ANTHROPIC_MODEL` to the combo name.
A synthetic completion through the combo returned `COMBO_SMOKE_OK` served by
`llama-3.3-70b-versatile` (Groq = priority-1 target, so the chain resolves as
configured). Auth re-tested both ways: **authenticated 200 with a real completion**
(key accepted) and **anonymous 200** (loopback does not enforce auth) — the key
works but is not load-bearing, so `:20128` must stay loopback-only. Repo gates
`OMNIROUTE_ENABLED` / `OMNIROUTE_AGENTS` remain unset (double gate closed);
nothing here opens them.

**Multi-machine stays read-only.** No write-capable agent on the VPS — it holds
the prod SSH key, `.env` and the live customer DB. `scripts/buzz_staff_pulse.py`
(Windows → SSH read-only → `#staff-pulse`) is the pattern.

**Hermes not adopted.** OmniRoute already fills the non-subscription-harness role,
and `Hermes 🛰️` is an existing runtime STAFF name — a Buzz agent by that name
would collide and trip the RED-tier "no 32nd STAFF persona" refusal.

Full procedure: `~/.buzz/GUIDES/BUZZ_END_TO_END_RUNBOOK.md`.
