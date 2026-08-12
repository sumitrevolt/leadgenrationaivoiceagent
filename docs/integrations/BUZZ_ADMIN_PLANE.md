# Buzz Admin Plane — LeadGen AI

> Collaboration workspace for humans + Desktop coding agents.
> Relay: `leadsgenai.communities.buzz.xyz` (hosted default) — **migrating local-first**
> `ws://127.0.0.1:3100` (owner decision 2026-08-10) · Desktop: Block Buzz
> Updated: 2026-08-10 (local-first decision)

## Relay migration (2026-08-10)

Local-first: relay hamare machine pe (`scripts\buzz_local_setup.ps1`), VPS relay sirf
production-proof ke baad. Buzz = **coordination plane only** — koi production authority
nahi. Full runbook + hardening + VPS migration path: `docs/integrations/BUZZ_LOCAL_RELAY.md`.
Tooling reads `BUZZ_RELAY` env (`buzzlock.py` / `buzz_staff_pulse.py` / `buzz_mcp.py`).

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
