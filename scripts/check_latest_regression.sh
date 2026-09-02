#!/usr/bin/env bash
# check_latest_regression.sh — READ-ONLY: is prod back on an unversioned image?
set +e
echo "===/health (source of truth)==="
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===PER-CONTAINER: Config.Image vs APP_VERSION vs started==="
for c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video leadgen_app_staging; do
  img=$(docker inspect --format '{{.Config.Image}}' "$c" 2>/dev/null | sed 's#.*:##')
  ver=$(docker exec "$c" printenv APP_VERSION 2>/dev/null)
  started=$(docker inspect --format '{{.State.StartedAt}}' "$c" 2>/dev/null | cut -c1-19)
  printf '%-24s image=%-10s APP_VERSION=%-10s started=%s\n' "$c" "$img" "${ver:-<unset>}" "$started"
done
echo "===IMAGE IDs — is :latest the SAME image as :2cda6d91?==="
docker image inspect ghcr.io/sumitrevolt/leadgenrationaivoiceagent:latest    --format 'latest   id={{.Id}} created={{.Created}}' 2>/dev/null
docker image inspect ghcr.io/sumitrevolt/leadgenrationaivoiceagent:2cda6d91  --format '2cda6d91 id={{.Id}} created={{.Created}}' 2>/dev/null
echo "===DID MY ADR-097 GUARD FIRE? (would prove an unversioned boot)==="
docker logs --since 3h leadgen_app 2>&1 | grep -i "provenance\|UNVERSIONED" | tail -5
echo "===REG_DONE==="
