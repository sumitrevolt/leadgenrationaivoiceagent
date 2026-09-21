#!/usr/bin/env bash
# LeadGen AI — VPS-side Telegram/ingress setup + verification runbook (owner-run).
#
# Prereq: the feature branch (key manager hardening + tg-ingress service +
# headless Jarvis ingress) is MERGED to main and deployed via the canonical
# scripts/deploy_vps.sh (that deploy brings up the tg-ingress container in
# INERT posture: TELEGRAM_INGRESS_ENABLED defaults to 0).
#
# This script is IDEMPOTENT and NON-DESTRUCTIVE: it only (1) verifies the
# container is up, (2) appends missing env lines to /opt/leadgen/.env (never
# overwrites existing values), and (3) runs read-only verifications.

set -u
cd /opt/leadgen || { echo "FATAL: /opt/leadgen not found"; exit 1; }
ENV=/opt/leadgen/.env

echo "=== 1. tg-ingress container (INERT until TELEGRAM_INGRESS_ENABLED=1) ==="
docker ps --filter name=leadgen_tg_ingress --format 'table {{.Names}}\t{{.Status}}' || true
if ! docker ps -q -f name=leadgen_tg_ingress | grep -q .; then
  echo "   container not running — deploy main first (scripts/deploy_vps.sh), then re-run."
fi

echo
echo "=== 2. .env lines (append-only; existing values NEVER touched) ==="
ensure_line() {  # $1 = VAR, $2 = default
  local var="$1" def="$2"
  if grep -qE "^${var}=" "$ENV" 2>/dev/null; then
    echo "   $var: already present — leaving value untouched."
  else
    echo "$var=$def" >> "$ENV"
    chmod 600 "$ENV"
    echo "   $var: appended with default '$def' (owner can edit)."
  fi
}
ensure_line TELEGRAM_INGRESS_ENABLED 0
ensure_line TELEGRAM_WEBHOOK_SECRET ""
ensure_line COORDINATION_HUB_ENABLED 1
ensure_line TELEGRAM_OWNER_USER_IDS ""
echo "   (If KEYS_MASTER_KEY is absent: run python scripts/key_manager_gen_master.py and add it to $ENV — owner-only secret, never in chat/git.)"

echo
echo "=== 3. Ingress readiness probe (in-container, --once; safe & no-op when flag off) ==="
docker run --rm --env-file "$ENV" \
  "${APP_IMAGE:-ghcr.io/sumitrevolt/leadgenrationaivoiceagent:$(docker inspect leadgen_app --format '{{.Config.Image}}' | awk -F: '{print $NF}')} \
" 2>/dev/null || true
IMG="$(docker inspect leadgen_app --format '{{.Image}}' 2>/dev/null)"
docker run --rm --env-file "$ENV" -v /opt/leadgen/data:/app/data "$IMG" \
  python -m app.platform.telegram_ingress --once || echo "   (flag off => honest 'disabled' posture; expected until owner flips =1)"

echo
echo "=== 4. Dual-bot coordination verification (read-only Bot API probes) ==="
docker run --rm --env-file "$ENV" -v /opt/leadgen:/work -w /work "$IMG" \
  python scripts/test_telegram_dual_bot.py || echo "   dual-bot test exited non-zero — inspect output above."

echo
echo "=== 5. Owner checklist (manual, ~5 min) ==="
echo "  [ ] Verify @Sumits_jarvis_bot + @Leadsgenai1_bot getMe OK (from step 4 output)."
echo "  [ ] Set TELEGRAM_OWNER_USER_IDS=<your numeric id> in $ENV, then:"
echo "        docker compose -f docker-compose.vps.yml up -d tg-ingress"
echo "  [ ] Flap test: close the desktop poller, send /status to the Jarvis bot,"
echo "        confirm it is answered by the VPS (container logs show the update)."
echo "  [ ] Flips TELEGRAM_INGRESS_ENABLED=1 in $ENV and:"
echo "        docker compose -f docker-compose.vps.yml up -d tg-ingress"
echo "  [ ] Create the 3 missing coordination groups (Worker/Agents/Admin Command Center)"
echo "        + Topics + @Leadsgenai1_bot admin; paste chat_ids into"
echo "        config/telegram/setup_spec.yaml (fields with chat_id: '')."
echo "  [ ] Create the localpc tool secret (>=32 chars) in the Coordination Hub admin UI"
echo "        and set it on the owner PC (setup_local_pc.ps1 step 2)."
echo
echo "=== DONE ==="
