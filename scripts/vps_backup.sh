#!/usr/bin/env bash
# LeadGen AI — daily VPS backup (data/ + sqlite DBs + .env) — keep 7 days.
# Installed by scripts/backup_setup.bat → cron @ 04:00 IST daily.
set -u
APP=/opt/leadgen
DEST=/root/backups
STAMP=$(date +%F)
mkdir -p "$DEST"
cd "$APP" || exit 1
tar -czf "$DEST/leadgen_data_$STAMP.tgz" \
    --exclude='data/vectorstore' \
    data/ .env *.db 2>/dev/null
# Checksum (integrity verify on restore) — pehle koi backup artifact pe checksum nahi tha.
sha256sum "$DEST/leadgen_data_$STAMP.tgz" > "$DEST/leadgen_data_$STAMP.tgz.sha256" 2>/dev/null || true

# --- Qdrant: CONSISTENT snapshot via API (live-dir tar = torn/inconsistent risk) ---
# Qdrant /collections snapshot API point-in-time consistent deta. API reachable +
# python3 ho to har collection ka .snapshot + .sha256; warna raw-tar fallback (kabhi
# backup miss na ho). RAG/KB core hai — corrupt-on-restore = silent SPOF.
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
QSNAP_OK=0
if command -v python3 >/dev/null 2>&1 && curl -fsS --max-time 10 "$QDRANT_URL/collections" >/dev/null 2>&1; then
  COLS=$(curl -fsS --max-time 10 "$QDRANT_URL/collections" \
    | python3 -c 'import sys,json; print(" ".join(c["name"] for c in json.load(sys.stdin)["result"]["collections"]))' 2>/dev/null || echo "")
  for col in $COLS; do
    snap=$(curl -fsS --max-time 120 -X POST "$QDRANT_URL/collections/$col/snapshots" \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["name"])' 2>/dev/null || echo "")
    if [ -n "$snap" ]; then
      out="$DEST/qdrant_${col}_$STAMP.snapshot"
      if curl -fsS --max-time 300 -o "$out" "$QDRANT_URL/collections/$col/snapshots/$snap" 2>/dev/null; then
        sha256sum "$out" > "$out.sha256" 2>/dev/null || true
        curl -fsS --max-time 30 -X DELETE "$QDRANT_URL/collections/$col/snapshots/$snap" >/dev/null 2>&1 || true
        QSNAP_OK=1
      fi
    fi
  done
fi
if [ "$QSNAP_OK" != "1" ] && [ -d /opt/qdrant_storage ]; then
  # Fallback: raw tar (API unreachable) — better than nothing.
  tar -czf "$DEST/qdrant_$STAMP.tgz" -C /opt qdrant_storage 2>/dev/null
  sha256sum "$DEST/qdrant_$STAMP.tgz" > "$DEST/qdrant_$STAMP.tgz.sha256" 2>/dev/null || true
fi

# Retention: keep last 7 of each (+ their .sha256)
ls -1t "$DEST"/leadgen_data_*.tgz 2>/dev/null | tail -n +8 | xargs -r rm -f
ls -1t "$DEST"/leadgen_data_*.tgz.sha256 2>/dev/null | tail -n +8 | xargs -r rm -f
ls -1t "$DEST"/qdrant_*.tgz 2>/dev/null | tail -n +8 | xargs -r rm -f
ls -1t "$DEST"/qdrant_*.snapshot 2>/dev/null | tail -n +8 | xargs -r rm -f
ls -1t "$DEST"/qdrant_*.snapshot.sha256 2>/dev/null | tail -n +8 | xargs -r rm -f
ls -1t "$DEST"/qdrant_*.tgz.sha256 2>/dev/null | tail -n +8 | xargs -r rm -f
echo "backup done $STAMP (qdrant_snapshot_api=$QSNAP_OK): $(ls -lh $DEST | tail -3 | awk '{print $9, $5}' | tr '\n' ' ')"
