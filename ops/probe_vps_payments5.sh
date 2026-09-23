#!/usr/bin/env bash
set -u
DB=leadgen
echo "=== payments schema ==="
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT column_name FROM information_schema.columns WHERE table_name='payments' ORDER BY ordinal_position;" 2>&1 | tr '\n' ' '
echo
echo "=== payments rows ==="
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT * FROM payments;" 2>&1
echo
echo "=== clients / subscriptions ==="
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE '%client%' OR table_name LIKE '%subscri%' OR table_name LIKE '%invoice%';" 2>&1
docker exec leadgen_db psql -U leadgen -d "$DB" -t -A -c "SELECT * FROM subscriptions LIMIT 5;" 2>&1
echo DONE
