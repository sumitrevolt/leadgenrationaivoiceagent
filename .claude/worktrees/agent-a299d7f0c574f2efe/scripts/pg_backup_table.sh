#!/usr/bin/env bash
# Granular Postgres backup/restore (R4#8) — per-table ya per-client data dump.
# Full nightly backup `pg_backup.sh` karta hai; yeh selective restore/export ke liye.
#
# Usage (VPS pe):
#   bash scripts/pg_backup_table.sh dump <table>                  # ek table dump
#   bash scripts/pg_backup_table.sh dump <table> "client_id='abc'" # WHERE filter (data-only)
#   bash scripts/pg_backup_table.sh restore <dumpfile.sql>        # restore ek dump
#
# Output: backups/granular/<table>_<ts>.sql.gz
set -uo pipefail

DB_NAME="${POSTGRES_DB:-leadgen}"
DB_USER="${POSTGRES_USER:-leadgen}"
DB_CONT="${PG_CONTAINER:-leadgen_db}"
OUT_DIR="/opt/leadgen/backups/granular"
TS="$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"

cmd="${1:-}"; arg="${2:-}"; where="${3:-}"

case "$cmd" in
  dump)
    [ -z "$arg" ] && { echo "usage: dump <table> [where]"; exit 1; }
    out="$OUT_DIR/${arg}_${TS}.sql.gz"
    if [ -n "$where" ]; then
      echo "[granular] data-only dump of $arg WHERE $where"
      docker exec "$DB_CONT" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "\\copy (SELECT * FROM ${arg} WHERE ${where}) TO STDOUT WITH CSV HEADER" \
        | gzip > "${out%.sql.gz}.csv.gz"
      echo "[granular] wrote ${out%.sql.gz}.csv.gz"
    else
      echo "[granular] full table dump of $arg"
      docker exec "$DB_CONT" pg_dump -U "$DB_USER" -d "$DB_NAME" -t "$arg" | gzip > "$out"
      echo "[granular] wrote $out"
    fi
    ;;
  restore)
    [ -z "$arg" ] || [ ! -f "$arg" ] && { echo "usage: restore <dumpfile.sql(.gz)>"; exit 1; }
    echo "[granular] restoring $arg into $DB_NAME (⚠️ overwrites matching rows)"
    if [[ "$arg" == *.gz ]]; then
      gunzip -c "$arg" | docker exec -i "$DB_CONT" psql -U "$DB_USER" -d "$DB_NAME"
    else
      docker exec -i "$DB_CONT" psql -U "$DB_USER" -d "$DB_NAME" < "$arg"
    fi
    echo "[granular] restore done"
    ;;
  *)
    echo "usage: $0 {dump <table> [where] | restore <file>}"; exit 1;;
esac
