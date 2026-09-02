#!/usr/bin/env bash
# disk_plan.sh — READ-ONLY. Work out exactly what is safe to reclaim. Deletes NOTHING.
set +e
KEEP_CURRENT=$(docker inspect --format '{{.Config.Image}}' leadgen_app 2>/dev/null | sed 's#.*:##')
echo "CURRENT_PROD_TAG=$KEEP_CURRENT"
echo
echo "===ALL app-image tags (newest first)==="
docker images ghcr.io/sumitrevolt/leadgenrationaivoiceagent --format '{{.Tag}}|{{.ID}}|{{.Size}}|{{.CreatedSince}}'
echo
echo "===TAGS IN USE BY A RUNNING CONTAINER (never delete these)==="
docker ps -a --format '{{.Image}}' | sort -u
echo
echo "===CANDIDATE DELETIONS (app-image tags that are NOT current and NOT container-referenced)==="
INUSE=$(docker ps -a --format '{{.Image}}' | sed 's#.*:##' | sort -u)
for t in $(docker images ghcr.io/sumitrevolt/leadgenrationaivoiceagent --format '{{.Tag}}'); do
  case "$t" in
    "$KEEP_CURRENT") echo "  KEEP   $t (current production)"; continue ;;
  esac
  if echo "$INUSE" | grep -qx "$t"; then echo "  KEEP   $t (running container)"; else echo "  DELETE $t"; fi
done
echo
echo "===RECLAIMABLE SUMMARY==="
docker system df
echo
echo "===BUILD CACHE (unused is safe to prune)==="
docker system df -v 2>/dev/null | grep -A2 "Build cache usage" | head -3
echo "===PLAN_DONE (nothing was deleted)==="
