# LeadGen AI — Telegram Dual-Bot + Coordination (SSOT)

**Status:** ACTIVE & CANONICAL · **Updated:** 2026-09-21 · **Owner:** Owner Ops / Admin Control Plane
**Code of record:** `app/platform/telegram_coordinator.py` · **Evidence tool:** `scripts/telegram_verify_setup.py`

> Coding truth lives in code + live probes, not in this file. If the doc and the
> verifier disagree, the verifier wins and this file gets fixed.

---

## 1. Where Telegram actually stands (live read-only probe, 2026-09-21)

Produced by `python scripts/telegram_verify_setup.py` — never trust the table
below after a token rotation; re-run the command.

| Surface | Env var | Live state |
|---|---|---|
| Jarvis bot `@Sumits_jarvis_bot` (interactive ingress) | `TELEGRAM_JARVIS_BOT_TOKEN` | **AUTHENTICATED** (getMe ok). No webhook set. |
| Notify bot `@Leadsgenai1_bot` (egress broadcast) | `TELEGRAM_NOTIFY_BOT_TOKEN` | **INVALID — 401 Unauthorized (ROTATION_REQUIRED)** |
| Legacy egress slot | `TELEGRAM_BOT_TOKEN` | Mixed: `.env` value is the same **dead** token; the machine env value is the live Jarvis token (drift) |
| Polling owner of the Jarvis token | — | **OTHER_CONSUMER**: HTTP 409 `Conflict: terminated by other getUpdates request` (the Hermes gateway, `hermes_cli.main --profile pilot gateway run`, PID 16064). Hermes' own log confirms it holds the token — see §3.5. |
| Groups in `config/telegram/setup_spec.yaml` | — | **0 / 13 reachable by the Jarvis bot** (`Bad Request: chat not found` → the bot was never added) |
| `workers_coordination` / `agents_coordination` / `admin_command_center` | — | **UNWIRED** (empty `chat_id` in the spec — the groups do not exist yet) |

Consequences, stated plainly:

* Owner commands sent to the Jarvis bot are answered by **Hermes**, not by this
  repo's runner, because Hermes owns the token's `getUpdates`.
* P0 owner alerts still leave the platform: `app/utils/telegram_egress.py` and
  `telegram_coordinator.dispatch_egress_alert()` blacklist the 401 token and fall
  back to the live slot — but they are delivered **as `@Sumits_jarvis_bot`**, not
  as the Notify bot, until the owner re-issues the Notify token.
* Anything written before 2026-09-21 claiming "dual-bot coordination is live" was
  describing code, not runtime. Use the status vocabulary in §8.

---

## 2. Two bots, two jobs

```
        inbound getUpdates                        outbound sendMessage
              │                                          ▲
              ▼                                          │
   ┌────────────────────────┐                 ┌────────────────────────┐
   │      JARVIS BOT        │                 │      NOTIFY BOT        │
   │ @Sumits_jarvis_bot     │                 │ @Leadsgenai1_bot       │
   │ TELEGRAM_JARVIS_...    │                 │ TELEGRAM_NOTIFY_...    │
   │ commands / intent /    │                 │ P0 alerts, deploy      │
   │ TypeSafe + skills      │                 │ notices, payment msgs  │
   │ ↓ one poller only      │                 │ ↓ NEVER polls (0 × 409)│
   └────────────────────────┘                 └────────────────────────┘
```

* **Jarvis** = interactive ingress. Long-polling (or webhook), owner-gated,
  answers `/status`, `/tasks`, `/agents`, `/pause`, `/resume`, `/keys`.
* **Notify** = egress only. It must never call `getUpdates`; two pollers on one
  token = HTTP 409 and both consumers silently lose half the updates.
* Egress has a **fallback chain** (`TELEGRAM_NOTIFY_BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`
  → `TELEGRAM_JARVIS_BOT_TOKEN`) with 401 blacklisting, so a revoked slot cannot
  swallow an alert. The `via` field of the result says which slot delivered.

---

## 3. Coordination: one token, one poller

Three real consumers exist on this project: the **local laptop runner**, the
**VPS systemd/Docker runner**, and the **Hermes desktop gateway**. Telegram
permits exactly one `getUpdates` consumer per token.

### 3.1 Ownership knob

| Env | Values | Meaning |
|---|---|---|
| `TELEGRAM_INGRESS_OWNER` | `auto` (default), `local`, `vps`, `hermes`, `off` | When set to a role, **only** that role may poll. Other roles refuse — fail-closed, no 409 spam. `off` disables repo-side polling entirely (Hermes keeps it). |
| `TELEGRAM_INSTANCE_ROLE` | `local`, `vps`, `hermes` | What *this* process is. Default `local`. |
| `TELEGRAM_INSTANCE_ID` | any string | Stable identity (default `host:pid`). |
| `TELEGRAM_POLL_LEASE_TTL` | seconds (floor 30) | Lease/heartbeat TTL. Default 120. |
| `TELEGRAM_POLL_SCOPE` | string | Lease namespace, one per bot token. Default `jarvis`. |

### 3.2 Lease decision order (`should_poll`)

1. `TELEGRAM_INGRESS_OWNER` = `off` → **no poll**.
2. `TELEGRAM_INGRESS_OWNER` = a role ≠ our role → **no poll** (`ingress_owner_is_<role>`), and we do **not** even claim the lease.
3. A recent real 409 cooldown is active → **no poll** (`external_consumer_conflict`).
4. Otherwise acquire the **polling lease**: Redis (`leadgen:telegram:poll_lease:<scope>`, cross-host) when reachable, else a file lease at `data/telegram_poll_lease.json` (cross-process on one host). Held by another live instance → **standby**. Expired holder → stale takeover.

### 3.3 Behaviour under conflict (honest, no fighting)

* A real HTTP 409 logs `HTTP 409 conflict #n`, **releases our own lease** (we must
  not advertise ourselves as owner while not polling), then stands by with
  backoff 10s → 20s → 40s → 60s.
* The runner never fakes ingestion: an **invalid token refuses to start at all**
  (no 401 loop), and standby is logged, not hidden.
* Exit is clean: the lease is released in a `finally`. The runner handles
  `SIGTERM` (what Docker sends on stop) by converting it to the same path as
  `SIGINT`, so a restart or redeploy releases the token immediately instead of
  leaving the lease to expire on its TTL.

### 3.4 Liveness heartbeat (a dead poller must not look healthy)

The runner has no port and no HTTP surface, so a silently dead loop is
indistinguishable from a healthy one from the outside. Every round therefore
writes `data/telegram_jarvis_state.json`:

```json
{ "at": 1789…, "at_iso": "2026-09-21T02:23:22Z", "state": "polling",
  "instance_id": "leadgen-vps", "role": "vps", "pid": 42,
  "ingress_owner": "vps", "polls": 137, "updates_total": 4, "conflicts": 0 }
```

`state` is `starting` · `polling` · `standby` · `external_conflict` · `stopped`.
The compose healthcheck reads this file and requires `instance_id == leadgen-vps`
and a heartbeat younger than 240s — `instance_id` matters because `./data` is a
shared bind mount, so a stale **local** heartbeat must not satisfy the **container's**
check. Read it from the runner too: `--status-only` prints state/age/polls/updates.

### 3.5 Making Hermes Desktop non-polling (owner cockpit ≠ ingress)

The Hermes pilot-profile gateway is the real holder of the Jarvis token, and Hermes
enforces its own single-consumer lock — its own log says so verbatim:

```
[Telegram] Telegram bot token already in use by the 'pilot' profile gateway
(PID 16064). Stop that gateway first (hermes --profile pilot gateway stop).
```

Take the Telegram platform away from Hermes **without stopping its gateway** (the
gateway also runs the owner-brief cron and the other platforms):

```yaml
# <HERMES_HOME>/profiles/pilot/config.yaml — TOP LEVEL
platforms:
  telegram:
    enabled: false
```

Use the vendor's own write path rather than hand-editing:
`write_platform_config_field("telegram", "enabled", False)`
(`hermes_cli/web_server_messaging.py` → `hermes_cli/config.py`). The gateway's
`gateway/config_loader.py` consumes it as `_enabled_explicit` — precisely the
"`enabled: false` for a migrated plugin platform" case — and `enabled` is only
honoured from a **top-level** `platforms.<name>` block, not from
`gateway.platforms.<name>`. Then restart so it applies:

```bash
hermes --profile pilot gateway stop
hermes --profile pilot gateway start     # or: hermes gateway restart
```

Verify with the probe, never with the config file alone:
`python scripts/telegram_verify_setup.py` must stop reporting `OTHER_CONSUMER`.
Remember the probe displaces the holder's in-flight call, so give it a moment
between attempts (the script already retries — see §7).

Hermes keeps: Desktop cockpit, MCP tools, egress sends, cron owner briefs.
Hermes loses: Telegram **ingress** — that is the point. To hand ingress back, set
`enabled: true` and restart.

### 3.6 Cross-process update dedupe

Local polling, the VPS runner and the webhook can all observe the same update.
`is_duplicate_update()` keeps an in-process cache **and** a best-effort Redis key
(`leadgen:telegram:dedupe:<scope>:<update_id>`, TTL 1h) so the same command is not
executed twice across processes. Redis down = fail-open to the in-process cache.

---

## 4. Group topology + coordination runbook

`config/telegram/setup_spec.yaml` is the single source of truth (13 entries).
Product groups are addressed as `<product>.<key>` (both products define
`announcements`/`community`/`support`/`feedback`, so a bare key is ambiguous and
the tooling refuses to guess).

Required coordination groups (ship with an empty `chat_id` because the Bot API
cannot create a group for the owner):

| Ref | Purpose | Topics |
|---|---|---|
| `workers_coordination` | 9 worker CLI bots: status, handoffs, urgent | `worker-status`, `task-handoffs`, `urgent` |
| `agents_coordination` | 31 agents: status, assignments, verdicts, skill share | `agent-status`, `assignments`, `verdicts`, `skill-share` |
| `admin_command_center` | owner ops: deploys, revenue, kill switch, metrics, health | `deploys`, `revenue`, `kill-switch`, `metrics`, `system-health` |

**Owner runbook (≈2 min per group):**

1. Create the group in Telegram, enable **Topics**, keep it private.
2. Add **@Sumits_jarvis_bot** and **@Leadsgenai1_bot**.
3. Promote the Jarvis bot to admin with **Manage Topics** (needed for topic creation).
4. Get the chat id (forward any group message to `@userinfobot`, or copy the `-100…` id), then:

```bash
python scripts/telegram_wire_coordination_groups.py --set workers_coordination=-100XXXXXXXXXX
python scripts/telegram_wire_coordination_groups.py --create-topics workers_coordination
python scripts/telegram_wire_coordination_groups.py --verify
```

5. Repeat for `agents_coordination` and `admin_command_center`. `--verify` exits
   non-zero until all three are wired.

Safety of the write path: every write keeps a timestamped `setup_spec.yaml.bak-*`,
re-parses the rendered YAML and refuses to write unless the document round-trips
identically, and `--set` refuses to silently replace an existing `chat_id`
(use `--force`). Ambiguous keys are rejected with the candidate list.
`--discover` prints chat ids seen in recent updates and is **read-only**: it omits
`offset` on purpose (Telegram only confirms — i.e. deletes — an update when
`getUpdates` is called with `offset`), so it cannot eat an owner command. It still
needs a token that is not being long-polled, because Telegram answers 409 while the
real consumer's call is in flight.

---

## 5. Local setup (laptop)

```bat
scripts\run_telegram_local.bat                  :: truth table, then poll as role=local
scripts\run_telegram_local.bat --status-only    :: status only
scripts\run_telegram_local.bat --probe          :: live token validation first
```

Requires, in `.env` (or the machine env): `TELEGRAM_JARVIS_BOT_TOKEN`,
`TELEGRAM_OWNER_CHAT_IDS`, `TELEGRAM_OWNER_USERNAMES`.

Before starting the local runner while Hermes or the VPS is polling, choose the
single owner:

```bat
set TELEGRAM_INGRESS_OWNER=local
```

Otherwise the runner will (correctly) stand by and log 409s instead of stealing
updates from the owner-configured consumer.

---

## 6. VPS setup (Hostinger Mumbai) — a Docker service, NOT systemd

The poller is a first-class compose service (`telegram-jarvis`) running the same
app image as `app`/`worker`. A host systemd unit would need `/opt/leadgen/.venv`,
which **does not exist** on this VPS (the app tier is Docker, `WEB_CONCURRENCY=2`
inside the container), so it could only crash-loop on `203/EXEC`. That broken unit
was deleted — do not reintroduce a host-venv runner.

Why a dedicated single-replica service at all: Telegram allows one `getUpdates`
consumer per token, and `app` itself runs two uvicorn workers — a poller inside
`app` would conflict with **itself**.

### 6.1 Bootstrap (first time only)

The service is deliberately **not** in `deploy_vps.sh`'s `SERVICES` list yet: that
script fail-closed-captures the previously running tag of every service it rolls
and exits 2 when a container does not exist, so a brand-new service would abort the
release. Create it once, at the tag the running workers already use (never
`:latest` — that is the unknown-provenance trap):

```bash
cd /opt/leadgen
TAG=$(docker inspect -f '{{.Config.Image}}' leadgen_worker | awk -F: '{print $NF}')
APP_VERSION="$TAG" docker compose -f docker-compose.vps.yml up -d --no-deps telegram-jarvis
```

### 6.2 Then, permanently

Add `telegram-jarvis` to `SERVICES=` in `scripts/deploy_vps.sh`. Until that is
done, every later deploy moves the workers and leaves this container behind —
silent image drift, which is how untracked `:latest` containers happen.

### 6.3 ⚠️ Never run `docker compose config` without `--quiet`

`docker compose -f docker-compose.vps.yml config` **renders every resolved
`env_file` value inline**, so it prints live API keys and bot tokens into your
shell history and the agent transcript. Use `config --quiet` (schema validation
only) or pipe through a filter. Anything you have already run this way should be
assumed exposed and rotated through the normal owner secret path.

### 6.4 Operating it

```bash
cd /opt/leadgen
docker compose -f docker-compose.vps.yml ps telegram-jarvis
docker logs -f --tail=100 leadgen_telegram_jarvis
docker inspect -f '{{.State.Health.Status}}' leadgen_telegram_jarvis
```

Flags baked into the service: `TELEGRAM_INSTANCE_ROLE=vps`,
`TELEGRAM_INSTANCE_ID=leadgen-vps`, `TELEGRAM_INGRESS_OWNER=${TELEGRAM_INGRESS_OWNER:-vps}`,
`restart: unless-stopped`, single replica, no published port.

One token = one poller. Do not run the local runner and the VPS service against the
same token "to be safe" — that is exactly the failure mode this doc exists to
prevent. If you must run locally, set `TELEGRAM_INGRESS_OWNER=local` here **and**
`=vps` back on the VPS, or the two will trade the token.

---

## 7. Verification

```bash
python scripts/telegram_verify_setup.py            # human truth table
python scripts/telegram_verify_setup.py --json      # machine readable
python scripts/telegram_verify_setup.py --no-groups # credential-only, fast
```

Exit codes: `0` green · `1` critical (no usable ingress token / required group
unwired) · `2` degraded (warnings such as a dead egress slot). Read-only: it never
sends a message, never sets a webhook, and its 409 probe uses
`getUpdates(allowed_updates=[])` with **no `offset`**, so it returns instantly and
never confirms (deletes) a pending update.

The probe repeats a few times on purpose. HTTP 409 only appears while the other
consumer's call is in flight, so **one clean probe is a false negative** — observed
live: `probes=['clean','409','clean']`. Therefore:

* any 409 in any attempt → `OTHER_CONSUMER`, conclusive;
* zero 409s → `NO_CONFLICT_OBSERVED`, which is explicitly **not** "nobody is
  polling" (long-poll holders leave gaps, and the probe itself displaces the
  holder's in-flight call, because Telegram allows one `getUpdates` at a time);
* network failure → `UNKNOWN`, never "free".

Tests:

```bash
.venv\Scripts\python.exe -m pytest tests/test_telegram_dual_bot.py -q      # lease, owner gate, 409 standby, egress fallback
.venv\Scripts\python.exe -m pytest tests/test_telegram_wiring_tool.py -q   # SSOT write guards, ambiguous-key refusal
.venv\Scripts\python.exe -m pytest tests/test_telegram_integration_2026.py -q
```

---

## 8. Status vocabulary + invariants

Use these labels; never promote one without the matching evidence:
`UNKNOWN` · `CODE-PRESENT` · `CONFIGURED` · `AUTHENTICATED` · `LIVE-VERIFIED` ·
`PRODUCTION-PROVEN` · `PARTIAL` · `GATED-INERT` · `BLOCKED` · `ROTATION_REQUIRED`.

Invariants:

1. **One token, one `getUpdates` consumer.** Enforced by owner role + lease; a 409
   is treated as evidence, not as noise.
2. **Notify bot never polls.** Egress only.
3. **Fail-closed credentials.** Present ≠ valid. An invalid token refuses to poll and
   is blacklisted for egress; the fallback chain reports which slot delivered.
4. **Never print, log, commit or prompt a token.** Only SHA-256 fingerprints appear in
   diagnostics.
5. **Owner commands only from `TELEGRAM_OWNER_CHAT_IDS` / `TELEGRAM_OWNER_USERNAMES`.**
6. **Compliance gates unchanged.** DND/TRAI/consent/opt-out behaviour is out of scope
   for this architecture and is never weakened by a notification change.
