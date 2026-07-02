#!/bin/sh
# =============================================================================
# migration_preflight.sh — Alembic DB-revision guard for the manual VPS deploy.
#
# WHY: deploying new app code whose SQLAlchemy models expect migration N WITHOUT
# first running `alembic upgrade head` causes Postgres enum write errors on the
# 8 tables touched by 010_enum_columns_to_varchar (the enum-model / migration-010
# coupling). This guard REFUSES to bless an app recreate until the DB is at the
# code's head revision(s).
#
# FAIL-CLOSED: agar alembic khud chal hi na paaye (DB unreachable, compose gadbad)
# to exit 1 — kabhi bhi aisa deploy bless mat karo jo verify nahi hua.
#
# Usage (VPS pe, /opt/leadgen se, `up -d --no-deps app` se PEHLE):
#   bash scripts/migration_preflight.sh \
#     && docker compose -f docker-compose.vps.yml up -d --no-deps app
#
# Exit: 0 = DB current == code head(s)  (safe to recreate)
#       1 = mismatch (pehle `alembic upgrade head` chalao)  OR  alembic error
#
# Dependency-free: sh + docker compose + awk/grep/sort/sed.
# =============================================================================
set -u

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.vps.yml}"
ALEMBIC_SERVICE="${ALEMBIC_SERVICE:-app}"

ERR_H="/tmp/mig_pf_heads.$$.err"
ERR_C="/tmp/mig_pf_cur.$$.err"
trap 'rm -f "$ERR_H" "$ERR_C"' EXIT

# alembic.ini apne INFO logs stderr pe bhejti hai, isliye stdout sirf revision
# lines hoti hain ("<rev> (head)" / "<rev>"). stdout se ids padho, stderr me error.
heads_raw="$(docker compose -f "${COMPOSE_FILE}" run --rm "${ALEMBIC_SERVICE}" alembic heads 2>"$ERR_H")"
if [ $? -ne 0 ]; then
  echo "❌ migration_preflight: 'alembic heads' fail (fail-closed):"
  sed 's/^/    /' "$ERR_H" 2>/dev/null
  exit 1
fi

cur_raw="$(docker compose -f "${COMPOSE_FILE}" run --rm "${ALEMBIC_SERVICE}" alembic current 2>"$ERR_C")"
if [ $? -ne 0 ]; then
  echo "❌ migration_preflight: 'alembic current' fail — DB unreachable? (fail-closed):"
  sed 's/^/    /' "$ERR_C" 2>/dev/null
  exit 1
fi

# Normalize: har non-empty line ka pehla token = revision id; sort -u = set.
HEADS="$(printf '%s\n' "${heads_raw}" | awk 'NF {print $1}' | sort -u)"
CUR="$(printf '%s\n' "${cur_raw}" | awk 'NF {print $1}' | sort -u)"

if [ -z "${HEADS}" ]; then
  echo "❌ migration_preflight: koi Alembic head nahi mila (unexpected) — fail-closed."
  exit 1
fi

# Mismatch agar KOI bhi head current me present nahi (multiple-heads bhi handle).
missing=""
for h in ${HEADS}; do
  if ! printf '%s\n' "${CUR}" | grep -qx "${h}"; then
    missing="${missing} ${h}"
  fi
done

if [ -n "${missing}" ]; then
  echo "=================================================================="
  echo "❌ MIGRATION MISMATCH — app container ABHI recreate MAT karo!"
  echo "   DB current : ${CUR:-<none / not stamped>}"
  echo "   code head(s): ${HEADS}"
  echo "   missing    :${missing}"
  echo ""
  echo "   Pehle migration chalao (enum/migration-010 coupling — warna Postgres"
  echo "   enum write errors 8 tables pe):"
  echo ""
  echo "     docker compose -f ${COMPOSE_FILE} run --rm ${ALEMBIC_SERVICE} alembic upgrade head"
  echo ""
  echo "   Phir yeh preflight dobara chalao, tab 'up -d --no-deps app'."
  echo "=================================================================="
  exit 1
fi

echo "✅ migration_preflight OK — DB code head(s) pe hai: ${HEADS} (app recreate safe)."
exit 0
