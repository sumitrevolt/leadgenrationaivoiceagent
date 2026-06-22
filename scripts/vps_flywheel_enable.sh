#!/usr/bin/env bash
# Idempotent: append enterprise flywheel flags to /opt/leadgen/.env (no inline comments).
set -euo pipefail
ENV_FILE="${1:-/opt/leadgen/.env}"
FLAGS=(
  GROWTH_OPTIMIZER=1
  CHANNEL_EXPERIMENTS=1
  EVAL_GATE=1
  CAMPAIGN_OPTIMIZER=1
  PROCESS_ENGINE=1
  PROCESS_AUTOSTART=1
  OBJECTION_KB=1
  INTERACTION_LOG=1
  SELF_IMPROVE_LOOP=1
  OUTREACH_CAMPAIGN_VARIANTS=1
  VOICE_CAMPAIGN_VARIANTS=1
)
touch "$ENV_FILE"
for kv in "${FLAGS[@]}"; do
  key="${kv%%=*}"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s/^${key}=.*/${kv}/" "$ENV_FILE"
  else
    echo "$kv" >> "$ENV_FILE"
  fi
done
# Strip inline comments (pydantic gotcha)
sed -i 's/[[:space:]]\+#.*$//' "$ENV_FILE"
echo "Flywheel flags armed in $ENV_FILE"
