# Buzz Local Relay — Runbook (local-first)

> Owner decision 2026-08-10: relay **local-first** on the dev machine
> (`ws://127.0.0.1:3100`, loopback only). Buzz = **coordination plane only** —
> never production authority. Production commands route via Owner OS/OpenClaw →
> 31 runtime STAFF.

## Why local-first

- Hosted relay = third party servers hold chit-chat history + agent state; local =
  data stays on the dev machine, works offline, independent of any VPS.
- Prebuilt image (`ghcr.io/block/buzz:main`) — no Rust build, no `just`/toolchain
  needed; Docker Compose + Docker Desktop (29.x verified) only.
- **VPS deployment is NOT production-approved** and is parked — this runbook
  covers the local plane only.

## What runs

| Service | Role |
|---------|------|
| `relay` | Buzz relay (`ws://127.0.0.1:3100`, `/_liveness`) |
| `postgres`, `redis`, `minio` | DB / pubsub-cache / media (internal; not published to the network) |

The compose bundle is the upstream `block/buzz` `deploy/compose` (shallow-cloned
to `%USERPROFILE%\buzz-local` by the setup script). The setup scripts pin the relay's published port to
`127.0.0.1` (the upstream compose publishes on `0.0.0.0`) so the relay is
loopback-only. The relay `.env` is generated
from `deploy/buzz/env/.env.local.template` with random secrets; it lives outside
the repo and is never committed.

## One-shot setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\buzz_local_setup.ps1
```

or, from a bash shell:

```bash
bash deploy/buzz/scripts/buzz-local-up.sh
```

Both are idempotent: re-running keeps the existing clone + `.env` and just
ensures the stack is up. `buzz-local-up.sh` additionally generates the owner
keypair, adds the owner member, and provisions channels + the 3 local workflows.

Post-start:

1. Import the owner nsec (from `deploy/buzz/env/.env.local.owner`) into the Buzz
   desktop app; add relay `ws://127.0.0.1:3100`.
2. Point local tooling at the local relay (user env var, read by `buzzlock.py` /
   `buzz_staff_pulse.py` / `buzz_mcp.py`):
   ```powershell
   setx BUZZ_RELAY ws://127.0.0.1:3100
   ```
3. Stop (data stays in volumes):
   ```powershell
   docker compose -f %USERPROFILE%\buzz-local\deploy\compose\compose.yml down
   ```

**Gotcha — stale data volumes:** if the relay ever starts against a placeholder
(`CHANGE_ME_*`) `.env`, Postgres/Redis/MinIO volumes initialize with the
placeholder password and the relay crash-loops with "password authentication
failed for user buzz". Fix (only when no valuable data exists — safe in Phase 0):
`docker compose down -v` then re-run the setup.

## MCP

`.mcp.json` exposes a `buzz` MCP server (stdio, stdlib-only) backed by
`scripts/buzz_mcp.py` — tools `buzz_channels` / `buzz_send` / `buzz_lock_status`.
Read-mostly surface; no VPS access, no deploy, no DB writes. The relay is taken
from `BUZZ_RELAY` env (default `ws://127.0.0.1:3100`).

## Security posture

- Loopback only; `BUZZ_REQUIRE_AUTH_TOKEN=true` + `BUZZ_REQUIRE_RELAY_MEMBERSHIP=true`
  in the generated `.env` (closed relay — owner pubkey is injected at bootstrap).
- Generated artifacts (key files, channel IDs, CLI binary) are gitignored.
- No GitHub webhook bridge, no external webhooks, no automatic outbound actions.
