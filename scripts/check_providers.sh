#!/usr/bin/env bash
# check_providers.sh — READ-ONLY: would a real (non-dry) publish actually reach a provider?
set +e
cat > /tmp/prov.py <<'PY'
from app.social_engine import engine, store
import json

print("=== the 6 dry-run jobs: which platforms? ===")
try:
    jobs = store.list_jobs() or []
    for j in jobs[-8:]:
        print("  platform=%-10s status=%-10s post_id=%-22s client=%s" % (
            j.get("platform"), j.get("status"), str(j.get("post_id"))[:22], j.get("client_id")))
except Exception as e:
    print("  store err:", e)

print()
print("=== default platforms for self-brand ===")
try:
    print(" ", engine._default_platforms("leadgenai-self"))
except Exception as e:
    print("  err:", e)

print()
print("=== provider registry: configured? (this decides real vs __inert__) ===")
reg = engine.registry()
for name, prov in sorted(reg.items()):
    try:
        acct = engine._resolve_account("leadgenai-self", name, "")
        ok = prov.configured(acct)
        print("  %-12s configured=%-6s acct_keys=%s" % (name, ok, sorted(list(acct.keys()))[:5]))
    except Exception as e:
        print("  %-12s err=%s" % (name, str(e)[:60]))
PY
docker cp /tmp/prov.py leadgen_app:/tmp/prov.py >/dev/null 2>&1
docker exec leadgen_app python3 /tmp/prov.py 2>&1 | grep -v '"level"'
echo "===TELEGRAM / POSTIZ env==="
for v in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID POSTIZ_API_KEY; do
  val=$(docker exec leadgen_app printenv "$v" 2>/dev/null)
  [ -z "$val" ] && echo "  $v = <unset>" || echo "  $v = <set, ${#val} chars>"
done
echo "===PROV_DONE==="
