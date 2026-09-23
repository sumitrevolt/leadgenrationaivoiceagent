#!/usr/bin/env bash
set -u
echo "=== try psql directly on leadgen_db ==="
docker exec leadgen_db psql -U leadgen -d leadgen_db -t -A -c "SELECT COUNT(*) FROM payments;" 2>&1
docker exec leadgen_db psql -U leadgen -d leadgen_db -t -A -c "SELECT COALESCE(SUM(amount_inr),0) FROM payments WHERE status='paid';" 2>&1
docker exec leadgen_db psql -U leadgen -d leadgen_db -t -A -c "SELECT id, client_id, amount_inr, status FROM payments ORDER BY id DESC LIMIT 4;" 2>&1
docker exec leadgen_db psql -U leadgen -d leadgen_db -t -A -c "SELECT name FROM clients LIMIT 6;" 2>&1
docker exec leadgen_db psql -U leadgen -d leadgen_db -t -A -c "SELECT c.name, s.status FROM clients c JOIN subscriptions s ON s.client_id=c.id LIMIT 6;" 2>&1
echo DONE
