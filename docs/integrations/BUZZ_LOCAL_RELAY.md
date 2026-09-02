# Buzz Local Relay — Runbook (Phase 0: local-first)

> Owner decision 2026-08-10: relay **local-first** (`ws://127.0.0.1:3100`), phir VPS.
> Hosted default (`leadsgenai.communities.buzz.xyz`) tab tak active hai jab tak local
> prove na ho. Buzz = **coordination plane only** — production authority NEVER.

## Why local-first

- Hosted relay = third party ke servers pe chit-chat history + agent state; local = data
  hamare paas (DPDP-lean), offline chalta hai, VPS outage se free.
- Prebuilt image (`ghcr.io/block/buzz:main`) — koi Rust build nahi, `just`/toolchain
  nahi chahiye; Docker Compose + Docker Desktop (29.x verified) bas.

## What runs

| Service | Role |
|---------|------|
| `relay` | Buzz relay (`ws://127.0.0.1:3100`, `/_liveness`) |
| `postgres`, `redis`, `minio` | DB / pubsub-cache / media (internal, localhost pe publish nahi) |
| `git` volume | workspace/repo mounts |

Compose file: `deploy/compose/compose.yml` (block/buzz repo) — same bundle jo VPS
migration me reuse hoga. `.env` wahi file; **`BUZZ_RELAY_PRIVATE_KEY` = relay identity —
backup zaroor** (`~/.buzz/` ya secrets backup; `.env` gitignored hai, commit kabhi nahi).

## One-shot setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\buzz_local_setup.ps1
```

Script kya karta hai (idempotent):
1. Docker running check
2. Shallow clone `block/buzz` → `%USERPROFILE%\Documents\buzz` (agar nahi hai)
3. `.env` ensure: copy from example + replace chain hamesha apply (sirf placeholder
   values touch; generated secrets kabhi nahi regenerate). **Open local mode**
   (`BUZZ_REQUIRE_AUTH_TOKEN=false`, `BUZZ_REQUIRE_RELAY_MEMBERSHIP=false`,
   `RELAY_URL=ws://127.0.0.1:3100` — same posture as `just dev`)
4. `docker compose up -d` (image pull + start)
5. `/_liveness` poll (≤120s) → "Buzz relay LIVE at ws://127.0.0.1:3100"

**Gotcha — stale data volumes:** agar kisi waqt `.env` placeholder (`CHANGE_ME_*`)
ke saath `up` hua (e.g. pichla partial run), to Postgres/Redis/MinIO volumes usi
placeholder password se init ho jaate hain aur relay "password authentication
failed for user buzz" pe crash-loop karta hai. Fix:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\buzz_local_setup.ps1 -ResetData
```
(`docker compose down -v` + fresh init naye secrets ke saath. SIRF tab jab koi
valuable data nahi hai — local Phase-0 me safe.)

## Post-setup

1. **Desktop:** Buzz Desktop → settings → relay `ws://127.0.0.1:3100` (identity wahi
   rahega — agents/channels chit-chat Desktop state me, relay sirf transport).
   Desktop ke saath local relay pe **workspace recreate karo** (channels `#admin`,
   `#leadgen`, `#ops`, `#dev` … + `~/.buzz/GUIDES/CHANNEL_IDS.json` refresh — `buzzlock.py`
   aur `buzz_staff_pulse.py` yehi ids use karte hain).
2. **Tabhi `BUZZ_RELAY` flip karo** jab local workspace ready ho (pehle nahi —
   `buzz_staff_pulse.py` #staff-pulse channel lookup fail karega):
   ```powershell
   setx BUZZ_RELAY ws://127.0.0.1:3100
   ```
   (naya terminal kholo — current shell me yeh nahi dikhega)
3. **Verify Boss read-only pulse** (VPS→Buzz = read-only only):
   ```powershell
   .venv\Scripts\python.exe scripts\buzz_staff_pulse.py
   ```
   → `#ops` me heartbeat aana chahiye (hosted relay pe ja raha tha — ab local pe).
4. **Lock status:** `scripts\buzzlock.py status`

## Everyday ops

```powershell
# start / stop / logs
docker compose -f "$env:USERPROFILE\Documents\buzz\deploy\compose\compose.yml" up -d
docker compose -f "$env:USERPROFILE\Documents\buzz\deploy\compose\compose.yml" down   # data volumes me bacha rehta hai
docker compose -f "$env:USERPROFILE\Documents\buzz\deploy\compose\compose.yml" logs -f relay
```

Update (image pin):
```powershell
docker compose -f "$env:USERPROFILE\Documents\buzz\deploy\compose\compose.yml" pull
docker compose -f "$env:USERPROFILE\Documents\buzz\deploy\compose\compose.yml" up -d
```

## Hardening (later — don't do at first boot)

1. `BUZZ_REQUIRE_AUTH_TOKEN=true` + `BUZZ_REQUIRE_RELAY_MEMBERSHIP=true` (closed relay)
2. `RELAY_OWNER_PUBKEY` = owner ke Buzz Desktop identity ka 64-hex Nostr pubkey
3. `BUZZ_IMAGE=ghcr.io/block/buzz:sha-<7>` pin (main ke jagah)
4. Public exposure = sirf VPS migration stage pe (Caddy + TLS via `compose.caddy.yml`)

## Migration path (Phase 1 — VPS)

1. Local prove (channels/agents/pulse daily ~1 week)
2. `deploy/compose` bundle VPS pe (image pin + closed relay + `RELAY_OWNER_PUBKEY`)
3. DNS/port: `buzz.leadsgenai.in` ya subpath — Caddy host config; `BUZZ_COMPOSE_TLS=true`
4. Desktop + `BUZZ_RELAY=wss://buzz.leadsgenai.in` re-point; hosted relay decommission
5. Rollback = Desktop relay wapas hosted; data-loss nahi (channels Desktop me synced)

## Sharp edges

- **Relay URL = `ws://127.0.0.1:3100` (2026-08-11 postmortem):** community relay ke
  `RELAY_URL` host-port se bind hota hai (compose `.env`: `RELAY_URL=ws://127.0.0.1:3100`,
  media/CORS bhi 3100). Sends tab tak 404 (`no community is configured for this host`)
  dete hain jab tak compose relay service `127.0.0.1:3100->3000` publish na kare
  (compose.yml ports me second mapping; `BUZZ_HTTP_PORT` sirf 3000 publish karta hai).
  CLI send ke 3 aur gates: (1) `RELAY_OWNER_PUBKEY` = tooling identity ka 64-hex pubkey
  hona chahiye — CLI `secrets.buzz-desktop` cred se nsec use karta hai, relay owner usi
  se derive hona chahiye warna `403 relay_membership_required`; (2) `BUZZ_REQUIRE_RELAY_MEMBERSHIP=true`
  = sender channel member hona chahiye (`400 restricted: not a channel member`) —
  `scripts/buzz_local_workspace.py` se members ensure karo; (3) CHANNEL_IDS.json fresh
  local ids hold karta hai. Desktop NIP-OA se chalta hai (membership bypass), CLI
  strict hai. `buzz_channels`/`buzz_lock_status` local reads hain isliye relay down pe
  bhi chalte hain — sirf `buzz_send` relay pe depend karta hai.

- Port 3000 conflict (kuch aur us pe chal raha ho) → `.env` me `BUZZ_HTTP_PORT` badlo,
  script wahi port liveness ke liye padhta hai.
- `Invoke-WebRequest` TLS hiccups Windows pe — local is HTTP (ws://) isliye koi issue nahi.
- First `up` image pull ~GB-class ho sakta hai (relay + db images) — do not Ctrl-C.
- Relay signing key rotation = sabhi channels/identities re-sign — **.env kabhi delete mat
  karo**, backup me rakho.
- **Workspace recreate CLI:** `buzz channels search` takes `--query` / `--exact`
  (NOT `--name`). Channel JSON uses `channel_id`. Wrong search flag = silent miss →
  duplicate `#admin`/`#build`/… on every re-run. Fix path =
  `scripts/buzz_local_workspace.py` (list-first + `--archive-dupes`).
- **CHANNEL_IDS vs BUZZ_RELAY mismatch:** local IDs + hosted default relay = dead
  posts. After liveness OK, `setx BUZZ_RELAY ws://127.0.0.1:3100` BEFORE tooling
  (buzzlock / staff_pulse / buzz_mcp). New terminals pick it up.
- **Duplicate Desktop agents:** `managed-agents.json` may hold hosted stubs
  (empty pubkey) + local copies of Boss/Honey/Fizz/Bumble. Workspace script skips
  empty pubkeys and keeps last active per name — Desktop me stale stubs archive/
  delete manually.


## Security & containment (2026-08-10)

- **GitHub bridge is disabled, not deleted.** The public `/gh-hook` route on the VPS
  host Caddy is fail-closed `403` and the GitHub webhook is deactivated. Do NOT
  re-enable either without a signed verifier bridge and explicit owner authorization.
- **Upstream-HMAC-before-downstream-authority invariant.** Any public webhook path
  must verify the upstream signature over the exact raw body (constant-time) BEFORE
  injecting any downstream credential. Caddy-style header injection alone is
  forbidden — it is a confused-deputy defect.
- **VPS relay is preserved but NOT production-approved.** The remote relay exists in
  a read-only state. The canonical setup is the local-first relay
  (`ws://127.0.0.1:3000`, loopback-only, deterministic compose project `buzz-local`).
- **Signed bridge = separate review.** Reintroducing GitHub events requires a
  dedicated verifier: raw-body HMAC with constant-time compare, body-size cap,
  event allowlist, delivery-ID replay dedupe, rate limiting, secret redaction,
  negative tests, and a named rollback — then explicit owner authorization.
