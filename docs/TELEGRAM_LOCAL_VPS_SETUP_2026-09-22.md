# Telegram Dual-Bot Coordination — Local + VPS Setup Runbook (2026-09-22)
Status: SETUP DONE (local side), VPS ingestion live; 2 open items for owner.

## What exists (verified today)
- **VPS ingress owner (canonical):** `leadgen_telegram_jarvis` container
  (`run_telegram_jarvis.py --role vps`, `TELEGRAM_INGRESS_OWNER=vps`) — healthy,
  polling @Sumits_jarvis_bot; 409-containment + Redis lease in place.
- **Local instance:** `run_telegram_jarvis.py` with `--role local` refuses to
  poll (owner gate = vps). `--status` on this PC works, reads shared Redis lease.
  => Local and VPS are already in coordinated dual-instance mode; no 2nd
  getUpdates consumer on the local side (OpenClaw gateway uses a different
  bot token and is not a leadgen consumer).
- **Notify/egress bot** (@Leadsgenai1_bot): token now resolves from the
  encrypted Key Manager vault (`telegram_notify_bot_token`) when env is absent,
  so a rotated token survives restarts without .env mutation (commit c224a7e0).
- **Owner allow-list:** `TELEGRAM_OWNER_CHAT_IDS` default = 1621120182.
  8687893086 (company admin) is intentionally NOT allowed; /status attempts
  are audited as unauthorized_access_attempt (fail-closed, correct).

## Local setup (this PC)
1. No code change needed to *coordinate* with VPS: local runner is gate-off.
2. To TEST a local ingestion instance (e.g. when VPS is down):
   - `TELEGRAM_INGRESS_OWNER=local .venv\Scripts\python.exe scripts\run_telegram_jarvis.py --role local`
   - NEVER run it while VPS owns the ingress (409 + standby churn).
   - VPS recovery: restart container `leadgen_telegram_jarvis`.
3. Local bot-to-bot / group messaging (both bots) works from any instance via
   `app/utils/telegram_egress.py` (notify token vault-first, 401-blacklist).

## VPS setup (72.61.245.204, /opt/leadgen)
- Canonical jarvis container is up; do not add a 2nd consumer.
- `leadgen.service` systemd unit is BROKEN-LEGACY (points at
  /opt/leadgen/.venv/bin/python which does not exist; crash-loops ~15k times).
  Prod :8000 is served by the `leadgen_app` container (Caddy -> 127.0.0.1:8000
  -> container). The deploy script's `systemctl restart leadgen` step is
  therefore a P0 deploy risk — see docs/TELEGRAM_DUAL_BOT_SETUP.md §VPS note.

## Open items (owner-only, exact actions)
1. **Telethon api_hash ROTATION_REQUIRED:** api_id 30160587 + api_hash
   (5a6af325…) were committed in git history (public repo). Re-issue at
   my.telegram.org -> API development, re-export TELEGRAM_API_ID/HASH into
   .env only (never commit). The local 30160587 session may be flagged.
2. **Owner path proof:** send `/status` from allow-listed account 1621120182
   to @Sumits_jarvis_bot to close the last unverified command-path segment.
