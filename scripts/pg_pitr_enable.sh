#!/usr/bin/env bash
# =============================================================================
# pg_pitr_enable.sh — Point-In-Time Recovery (PITR) setup for the dockerised
# Postgres (leadgen_db). pg_dump nightly = 24h RPO; WAL archiving se RPO minutes
# me aa jata (kisi bhi second tak restore).
#
# DRY-RUN by default — sirf plan print karta, kuch change NAHI karta.
# Apply karne ke liye:  bash scripts/pg_pitr_enable.sh --apply
#
# ⚠️  --apply ALTER SYSTEM se archive_mode ON karta — ek baar `docker restart
#    leadgen_db` chahiye (archive_mode restart-only param). Maintenance window
#    me karo. WAL ko container ke bahar persist karne ke liye compose me ek
#    volume mount (neeche dikhaya) chahiye — woh manual + restart ke saath.
#
# Reference: WAL-G / Barman bhi consider karo (docs/ROADMAP — pgBackRest Apr2026
# se unmaintained). Yeh script native archive_command use karta (zero new dep).
# =============================================================================
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-leadgen_db}"
PG_USER="${POSTGRES_USER:-leadgen}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/var/lib/postgresql/wal_archive}"   # inside container (mount this!)
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

cat <<PLAN
[$(date -Is)] PITR plan for container=${DB_CONTAINER}
  1) compose me leadgen_db pe ek persistent volume mount karo (WAL bahar rahe):
       volumes:
         - walarchive:/var/lib/postgresql/wal_archive
     (aur top-level 'volumes:' me 'walarchive:' add karo)
  2) Postgres settings (ye script --apply pe lagayega):
       ALTER SYSTEM SET wal_level = 'replica';
       ALTER SYSTEM SET archive_mode = 'on';
       ALTER SYSTEM SET archive_command = 'test ! -f ${WAL_ARCHIVE_DIR}/%f && cp %p ${WAL_ARCHIVE_DIR}/%f';
       ALTER SYSTEM SET archive_timeout = '300';     # force WAL switch every 5 min
  3) docker restart ${DB_CONTAINER}   # archive_mode restart-only
  4) WAL archive ko offsite bhejo (cron): rclone copy ${WAL_ARCHIVE_DIR} <remote>/wal
  5) Restore (PITR): base backup + WAL replay tak 'recovery_target_time'.

  RPO after this: ~5 min (archive_timeout). RTO: base-restore + WAL replay.
PLAN

if [[ "${APPLY}" != "1" ]]; then
  echo "[$(date -Is)] DRY-RUN — kuch change nahi kiya. Apply: bash $0 --apply (maintenance window me)"
  exit 0
fi

echo "[$(date -Is)] --apply: archive dir + ALTER SYSTEM…"
docker exec "${DB_CONTAINER}" mkdir -p "${WAL_ARCHIVE_DIR}" || true
docker exec "${DB_CONTAINER}" chown postgres:postgres "${WAL_ARCHIVE_DIR}" || true
# BUGFIX (2026-06-10): heredoc ke liye `docker exec -i` ZAROORI hai (warna stdin
# pass nahi hota — psql kuch run hi nahi karta, "staged" jhooth bolta tha).
# ALTER SYSTEM ko -c multi-statement me bhi mat dalna (transaction-block error).
docker exec -i "${DB_CONTAINER}" psql -U "${PG_USER}" -v ON_ERROR_STOP=1 <<SQL
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET archive_mode = 'on';
ALTER SYSTEM SET archive_command = 'test ! -f ${WAL_ARCHIVE_DIR}/%f && cp %p ${WAL_ARCHIVE_DIR}/%f';
ALTER SYSTEM SET archive_timeout = '300';
SELECT pg_reload_conf();
SQL
# verify staged (auto.conf me dikhna chahiye)
docker exec "${DB_CONTAINER}" grep -E 'archive_mode|wal_level' /var/lib/postgresql/data/postgresql.auto.conf || {
  echo "[$(date -Is)] ❌ ALTER SYSTEM stage nahi hua — abort"; exit 1; }

echo "[$(date -Is)] settings staged. ⚠️ ab 'docker restart ${DB_CONTAINER}' karo (archive_mode restart-only)."
echo "[$(date -Is)] restart ke baad verify: docker exec ${DB_CONTAINER} psql -U ${PG_USER} -c 'show archive_mode;'"
