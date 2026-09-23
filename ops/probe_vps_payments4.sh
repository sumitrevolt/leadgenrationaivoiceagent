#!/usr/bin/env bash
set -u
DBNAME=$(docker exec leadgen_db psql -U leadgen -d postgres -t -A -c "SELECT datname FROM pg_database WHERE NOT is_template;" 2>/dev/null | tr '\n' ' ')
echo "databases: $DBNAME"
DB=$(docker exec leadgen_db psql -U leadgen -d postgres -t -A -c "SELECT datname FROM pg_database WHERE datname LIKE 'leadgen%' OR datname LIKE 'app%' LIMIT 1;" 2>/dev/null)
echo "using db=$DB"
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT COUNT(*) FROM payments;" 2>&1
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT COALESCE(SUM(amount_inr),0) FROM payments WHERE status='paid';" 2>&1
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT id, amount_inr, status FROM payments ORDER BY id DESC LIMIT 4;" 2>&1
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT name, status FROM subscriptions LIMIT 6;" 2>&1
echo DONE
