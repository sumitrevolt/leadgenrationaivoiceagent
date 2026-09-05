# Channel-ID maps (split - never one global map)

- `CHANNEL_IDS.json`        = LOCAL relay community (`leadgen-local`) channel UUIDs.
- `CHANNEL_IDS.hosted.json` = HOSTED canonical community (`leadsgenai.communities.buzz.xyz`) channel UUIDs.

## Verified endpoints (2026-08-11 closeout)
- Hosted canonical relay: `wss://leadsgenai.communities.buzz.xyz` (v0.2.0, auth_required).
- Local dev relay: container `buzz-prod-relay-1` (compose project `buzz-prod` at
  `C:/Users/Ratanshila/buzz-local/deploy/compose/compose.yml`).
  - Published: `0.0.0.0:3000` and `127.0.0.1:3100` -> container 3000.
  - **Community host is bound to `RELAY_URL=ws://127.0.0.1:3100` (Host-header routing).
    `127.0.0.1:3000` returns "no community is configured for this host" (404).**
  - The intended `127.0.0.1:3000` unification requires `.env RELAY_URL=ws://127.0.0.1:3000`
    + a local-stack relay recreate + Desktop relay setting change - NOT done (owner next step).
- User env `BUZZ_RELAY` currently = `ws://localhost:3000`; for local CLI use against the
  running relay the consistent value is `ws://127.0.0.1:3100` (setx, new terminal).

## Do not
- Do not let tooling auto-flip the IDs: pick the map matching the target relay explicitly.
