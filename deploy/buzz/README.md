# Buzz — Local-first coordination kit

Self-hosted [Block Buzz](https://github.com/block/buzz) relay on the dev machine:
a private Nostr relay where the Boss + staff agents share channels and run YAML
workflows. **Coordination/visibility only** — production commands always route
through Owner OS/OpenClaw → the 31 runtime STAFF. Buzz is never a control plane.

## What this kit contains (local scope)

| Path | Purpose |
|------|---------|
| `scripts/buzz-local-up.sh` | Idempotent bootstrap + start: clones `block/buzz`, generates `.env` + owner keypair, starts Docker stack (project `buzz-local`, port pinned to loopback), adds owner member, provisions channels/workflows |
| `scripts/buzz-local-down.sh` | Stop the stack (volumes + data kept) |
| `scripts/buzz-local-cli.sh` | Run `buzz` CLI against the local relay (Docker, Linux binary) |
| `scripts/buzz-local-configure.sh` | Idempotent channels + workflow install via CLI |
| `scripts/buzz-keys.sh` | Generate a Nostr keypair (hex/nsec/npub) via the relay image |
| `scripts/buzz-cli-build.sh` | Build the `buzz` CLI binary in a throwaway Rust container |
| `scripts/nostr_bech32.py` | nsec/npub bech32 encoding (stdlib) |
| `env/.env.local.template` | Local relay env template — `CHANGE_ME` placeholders only |
| `workflows/*.yml` | Local workflows: daily standup, deploy-approval gate, incident echo |

## Quick start

```bash
bash deploy/buzz/scripts/buzz-local-up.sh
```

- Relay + web UI: `http://127.0.0.1:3000` (loopback only; `RELAY_URL=ws://127.0.0.1:3000`)
- Compose project is pinned to the deterministic `buzz-local` — it never manages
  or collides with another stack (`buzz-prod` is upstream's name, untouched).
- If port 3000 is already held by a non-Buzz process the script aborts with a
  clear error — pick a free port with `BUZZ_HTTP_PORT=<port>`.
- Owner keypair (nsec) lands in `deploy/buzz/env/.env.local.owner` — gitignored.
  Import the nsec into the Buzz desktop app and point it at `ws://127.0.0.1:3000`.
- Channels (`#general #engineering #office #agents #incidents`) + the 3 local
  workflows are provisioned automatically.

CLI against the local relay:

```bash
BUZZ_PRIVATE_KEY=<nsec> bash deploy/buzz/scripts/buzz-local-cli.sh channels list
```

## Rules (owner mandate 2026-08-10)

- Loopback only — the relay's published port is pinned to `127.0.0.1` at setup;
  never exposed beyond the dev machine.
- No automatic send/call/payment/provider action from workflows; no external
  webhooks; no GitHub bridge (disabled, parked).
- Generated files (`env/.env.local.owner`, `env/channels.local`, `env/gh-events.response`,
  `bin/`) are gitignored — never commit keys or generated IDs.
- VPS deployment and the GitHub bridge are **NOT** production-approved and are
  intentionally not part of this kit.
