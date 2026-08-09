#!/usr/bin/env bash
# disk_reclaim.sh — reclaim docker disk SAFELY. Disk was at 92% (16G free) and
# every deploy adds a ~7GB app image with no retention.
#
# SAFETY:
#  - `docker rmi` WITHOUT -f: docker itself refuses to delete an image that any
#    container references, so an in-use image cannot be removed by accident.
#  - dynamic KEEP tag: the image used by leadgen_app is never listed.
#  - `docker builder prune -f` only removes UNUSED build cache.
#  - nothing here touches volumes, containers, or data. No `-a`, no `system prune`.
set -uo pipefail

IMG=ghcr.io/sumitrevolt/leadgenrationaivoiceagent
KEEP_TAG="$(docker inspect --format '{{.Config.Image}}' leadgen_app 2>/dev/null | sed 's#.*:##')"
case "$KEEP_TAG" in
  ""|latest|dev|"<none>")
    echo "FATAL: cannot establish an immutable current production tag; refusing cleanup"
    exit 2
    ;;
esac

echo "===BEFORE==="
df -h / | tail -1
docker system df

echo
echo "===1. BUILD CACHE (unused only)==="
docker builder prune -f 2>&1 | tail -3

echo
echo "===2. OLD APP IMAGE TAGS (keeping current production: $KEEP_TAG)==="
for t in $(docker images "$IMG" --format '{{.Tag}}'); do
  if [ "$t" = "$KEEP_TAG" ]; then
    echo "  KEEP   $t"
    continue
  fi
  # no -f: docker will refuse if a container still references it
  out=$(docker rmi "$IMG:$t" 2>&1)
  if [ $? -eq 0 ]; then
    echo "  REMOVED $t"
  else
    echo "  SKIPPED $t -> $(echo "$out" | head -1)"
  fi
done

echo
echo "===3. DANGLING IMAGES (untagged leftovers)==="
docker image prune -f 2>&1 | tail -2

echo
echo "===AFTER==="
df -h / | tail -1
docker system df

echo
echo "===SANITY: prod still healthy + images still present==="
curl -s -m 10 127.0.0.1:8000/health; echo
docker images "$IMG" --format '{{.Tag}}|{{.Size}}'
docker ps --filter name=leadgen_app --filter name=leadgen_worker --format '{{.Names}}|{{.Status}}'
echo "===RECLAIM_DONE==="
