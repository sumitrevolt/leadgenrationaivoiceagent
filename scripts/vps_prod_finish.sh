#!/usr/bin/env bash
# VPS one-shot: RAG A/B gate -> enable flags -> catch up overdue staff jobs -> verify.
set -euo pipefail
cd /opt/leadgen

echo "=== RAG A/B gate ==="
if docker exec leadgen_app python scripts/rag_retrieval_ab.py; then
  python3 scripts/vps_enable_deferred_backlog.py --rag-gate || python3 scripts/vps_activate_rag_flags.py
  docker compose -f docker-compose.vps.yml up -d --no-deps app worker worker-heavy scheduler
else
  echo "RAG gate FAIL — flags not flipped"
fi

echo "=== Catch-up overdue staff jobs ==="
for j in qa trainer pipeline; do
  echo "Trigger $j ..."
  docker exec leadgen_worker celery -A app.worker call app.tasks.staff_jobs.run_staff_job --args='["'"$j"'"]' || true
done

sleep 12
echo "=== Post-deploy verify ==="
python3 scripts/vps_post_deploy_verify.py

echo "=== Activation summary ==="
curl -sf http://127.0.0.1:8000/api/activation/summary | head -c 350
echo
