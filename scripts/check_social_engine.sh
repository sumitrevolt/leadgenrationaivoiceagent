#!/usr/bin/env bash
# check_social_engine.sh — READ-ONLY: is the social publish engine on, and is anything queued?
set +e
echo "===FLAGS (app + worker — worker is what runs jobs)==="
for c in leadgen_app leadgen_worker; do
  echo "--- $c ---"
  for v in SOCIAL_ENGINE SOCIAL_DRY_RUN SOCIAL_ENGINE_CONFIG SOCIAL_PREFS_HONOR AFTERNOON_CONTENT; do
    val=$(docker exec "$c" printenv "$v" 2>/dev/null)
    echo "  $v = ${val:-<unset>}"
  done
done
echo "===data/social_engine.json (env-unset fallback)==="
docker exec leadgen_app sh -c 'cat data/social_engine.json 2>/dev/null || echo "(file missing)"'
echo "===engine.enabled() / dry_run live==="
docker exec leadgen_app python3 -c "
from app.social_engine import engine
print('enabled =', engine.enabled())
try:
    print('dry_run =', engine._dry_run_enabled())
except Exception as e:
    print('dry_run err', e)
" 2>&1 | grep -v '"level"'
echo "===SOCIAL ENGINE QUEUE (anything waiting?)==="
docker exec leadgen_app sh -c 'ls -la data/social_engine* 2>/dev/null; wc -l data/social_engine/*.jsonl 2>/dev/null | tail -3'
docker exec leadgen_app python3 -c "
from app.social_engine import store
try:
    q = store.list_jobs() if hasattr(store,'list_jobs') else None
    print('jobs:', len(q) if q is not None else 'n/a')
    if q:
        from collections import Counter
        print(Counter([str(j.get('status')) for j in q]))
except Exception as e:
    print('store err:', e)
" 2>&1 | grep -v '"level"'
echo "===APPROVAL QUEUE for self-brand (approved but never published?)==="
docker exec leadgen_app python3 -c "
from app.marketing import content_approval as ca
rows = ca.list_all('leadgenai-self', limit=200) or []
from collections import Counter
print('total approvals:', len(rows))
print(Counter([str(r.get('status')) for r in rows]))
" 2>&1 | grep -v '"level"'
echo "===SOCIAL_DONE==="
