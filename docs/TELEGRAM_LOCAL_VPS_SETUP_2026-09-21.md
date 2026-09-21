# Telegram + Local/VPS Coordination Setup — Single Source of Truth (2026-09-21)

> **Supersedes:** `docs/TELEGRAM_SINGLE_SOURCE_OF_TRUTH_2026-09-20.md` §6 "Owner Action"
> workflow. Read that doc first for the 13-entity group grid; this doc is the
> **machine topology** truth (what runs where, single-consumer rules, setup steps).

## 1. Topology — one workforce, four surfaces (R4)

```
                       ┌────────────────────────────────────────────┐
 OWNER (sumitrevolt) ──┤  @Sumits_jarvis_bot   @Leadsgenai1_bot    │  ← 2 bots, 2 tokens
 (numeric id, allowlist)└──────────┬──────────────────┬──────────────┘
                                   │ getUpdates        │ egress send_message
                                   │ (single consumer) │ (no getUpdates ever)
                    ┌──────────────▼───────────────┐   │
                    │ VPS 72.61.245.204            │   │
                    │  • tg-ingress container      │   │  ← NEW (this change)
                    │    = headless Jarvis poller  │   │
                    │    (persistent Redis dedupe  │   │
                    │     + offset watermark)       │   │
                    │  • telegram_egress           │◄──┘
                    │    (P0/P1 alerts → groups)   │
                    │  • Coordination Hub          │
                    │    (HMAC tool heartbeats)    │◄──┐
                    │  • /api/admin/keys/*         │   │  ← P0-hardened key manager
                    │    (Fernet at rest, owner    │   │
                    │     JWT-gated)               │   │
                    └──────────┬───────────────────┘   │
                    Postgres/Redis/Qdrant (canonical)   │
                               │                        │
                               ▼                        │
                    ┌──────────────────────────────┐    │
                    │ OWNER PC (Windows)           │────┘
                    │  • local_telegram_coord.py  │  HMAC heartbeats (tool_id=localpc)
                    │    --loop --with-bot        │  /local /approve in own local bot
                    │  • OpenClaw/Hermes desktop  │  (own token — NEVER Jarvis's)
                    │                             │  (reads dashboards; no polling
                    │                             │   of shared tokens)
                    └─────────────────────────────┘
```

**Single-consumer rule (M7):** each bot token has EXACTLY one `getUpdates`
owner at any moment:

| Token | Owner consumer | When |
|---|---|---|
| `TELEGRAM_JARVIS_BOT_TOKEN` | VPS `tg-ingress` container | `TELEGRAM_INGRESS_ENABLED=1` |
| `TELEGRAM_JARVIS_BOT_TOKEN` | owner desktop poller (Hermes/OpenClaw) | flag `=0` (default today) |
| `TELEGRAM_NOTIFY_BOT_TOKEN` / `TELEGRAM_BOT_TOKEN` | never polls (egress only) | always |
| `TELEGRAM_LOCAL_BOT_TOKEN` (optional, PC) | PC `local_telegram_coord.py --with-bot` | when set |

If two consumers race on one token, Telegram answers 409; the VPS ingress
surfaces that as `conflict_another_consumer` + a one-shot owner-alerts-group
message (30-min cooldown) and backs off — it never force-takes the stream.

## 2. What this change ships (branch `feature/keymanager-telegram-coord`)

| Area | Change | File |
|---|---|---|
| **P0 Key Manager** | Fernet encrypted-at-rest under `KEYS_MASTER_KEY` (env-only); owner-gated router (reads=`require_admin`, mutations=`require_super_admin`); **no prefix/suffix/value leakage** in status/audit/Telegram; atomic 0600 writes; legacy plaintext `keys.json` migrated once + securely deleted | `app/platform/key_manager.py`, `app/main.py`, `scripts/key_manager_gen_master.py` |
| **Headless Jarvis ingress** | real getUpdates long-poll loop, persistent Redis dedupe + offset watermark, 409 conflict detection + owner alert, `--once/--loop/--status` CLI; **inert by default** (`TELEGRAM_INGRESS_ENABLED=0`) | `app/platform/telegram_ingress.py`, `docker-compose.vps.yml` (`tg-ingress` service), `scripts/deploy_vps.sh` (rollout list) |
| **Numeric owner auth** | `TELEGRAM_OWNER_USER_IDS` = canonical immutable allowlist; when set, username matches are IGNORED (spoof-proof); unset = legacy behaviour (backward compatible) | `app/integrations/telegram_bot.py` |
| **Webhook hijack fix** | `/api/telegram/bot/set-webhook` was unauthenticated (anyone could point Jarvis's update stream at an attacker) → now admin-gated + HTTPS-only; optional `TELEGRAM_WEBHOOK_SECRET` (Telegram `secret_token`) on `/webhook` | `app/api/telegram_bot_api.py` |
| **Local PC runner** | stdlib-only `local_telegram_coord.py`: HMAC heartbeats to Coordination Hub (`tool_id=localpc`) + optional local coordination bot (`/local`, `/approve` → decisions ride heartbeat meta to VPS); `setup_local_pc.ps1` creates the scheduled task | `scripts/local_telegram_coord.py`, `scripts/setup_local_pc.ps1` |
| **VPS runbook** | idempotent, append-only `.env` + container checks + readiness probe + dual-bot verification | `scripts/setup_vps_ingress.sh` |
| **Tests** | storage/encryption + router auth (401/403/200) + real-auth enforcement | `tests/test_key_manager_storage.py`, `tests/security/test_key_manager_auth.py` |

**Deliberately NOT in this branch:** mounting the 4 TypeSafe slots into the
gateway consumer paths (follow-up: TypeSafe 4-slot gateway workstream), and
creating the 3 missing coordination groups (owner action below).

## 3. Setup — Local PC (owner, ~10 min)

```powershell
# from C:\Users\Ratanshila\leadgen-work (fresh main checkout):
git checkout main && git pull
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_local_pc.ps1
```
Env vars the script verifies (set them first, user level):
- `COORD_HUB_TOOL_LOCALPC_SECRET` (≥32 chars; issued via the owner dashboard's
  Coordination Hub tool secrets — HMAC, not an API key)
- optional: `TELEGRAM_LOCAL_BOT_TOKEN` (BotFather, "Local LeadGen Coord"),
  `TELEGRAM_LOCAL_OWNER_IDS=<your numeric user id>` (get it from @userinfobot)

## 4. Setup — VPS (owner, ~15 min, after branch merges + deploys)

```bash
ssh root@72.61.245.204
cd /opt/leadgen && bash scripts/setup_vps_ingress.sh   # steps 1-5 checklist
```
Sequence matters:
1. **Merge + deploy the branch first** (`deploy_vps.yml` gate → `deploy_vps.sh`);
   `tg-ingress` starts INERT (flag default 0) — zero behaviour change.
2. Set `TELEGRAM_OWNER_USER_IDS` + (later) `TELEGRAM_INGRESS_ENABLED=1` in `.env`.
3. **Flap test:** close the desktop poller, send `/status` to `@Sumits_jarvis_bot`;
   confirm the answer came from VPS (`docker logs leadgen_tg_ingress`).
4. Only then flip `TELEGRAM_INGRESS_ENABLED=1` and restart `tg-ingress`.
5. Create the 3 missing groups (SSOT doc §6 steps), add `@Leadsgenai1_bot` as
   admin, paste chat_ids into `config/telegram/setup_spec.yaml`.

## 5. Key Manager — provisioning the four TypeSafe slots

```bash
# VPS (owner):
python scripts/key_manager_gen_master.py     # prints KEYS_MASTER_KEY=***
# append that line to /opt/leadgen/.env (chmod 600), then:
docker compose -f docker-compose.vps.yml up -d app   # restarts with the router mounted
# 4 slots (logical, NON-secret names) provisioned via admin UI / API:
#   POST /api/admin/keys/set {"service":"typesafe_a","key":"***"}
#   ... typesafe_b / typesafe_c / typesafe_d
# then deploy each into runtime env:
#   POST /api/admin/keys/deploy/typesafe_a
# Owner-visible health (never the value/prefix):
#   GET /api/admin/keys/status  -> ABSENT|PRESENT|INVALID|ROTATION_REQUIRED
```
Work-class mapping (M3, pending measured provider limits): A = high-priority
prod sales/CRM/customer QA · B = email/WhatsApp/voice post-call validation ·
C = dev/QA/agent/task routing · D = research/content/background/burst reserve.
**Four keys are not 4× quota** — account-level limits still apply; the gateway
must measure per-key + shared throttles before spreading load (follow-up).

## 6. Coordination semantics (what "both bots coordinating" means)

- **VPS = authority.** All task ledger / agent / revenue state lives on the VPS
  (Postgres + Redis + canonical orchestrator).
- **Jarvis bot** = owner command surface (VPS ingress; desktop while flag off).
- **Egress bot** = alerts/broadcasts to the 13-group grid (severity routing in
  `config/telegram/owner_notify_routing.yaml`).
- **Local PC** never polls shared tokens. It (a) announces presence via HMAC
  heartbeats (Coordination Hub `tool_id=localpc`), (b) optionally runs its own
  small local bot for `/local` + `/approve` — decisions ride the next
  heartbeat's meta into the Hub event ledger, where the VPS-side orchestrator
  consumes them (same ledger; no 40 separate chatbots, no transcript copies).
- **Both machines offline-safe:** VPS down → PC heartbeats fail and queue the
  last state locally; PC down → VPS revenue/customer automations and owner
  alerts continue (verified by the PC-offline fault-injection test in R5).

## 7. Rollback

- Ingress: `TELEGRAM_INGRESS_ENABLED=0` + `docker stop leadgen_tg_ingress`
  (desktop poller resumes ownership; 409 cannot occur with the flag off).
- Key manager: revert the `main.py` mount (router simply unmounts; storage
  format is additive — `keys.enc.json` coexists with any legacy `keys.json`).
- Compose: remove the `tg-ingress` service block (state lives in Redis keys
  `tg:ingress:*` — safe to keep; TTL expires).
