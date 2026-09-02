#!/usr/bin/env bash
# verify_jiya.sh — read-only: is the real customer's data REAL (not demo fallback)?
set +e
cat > /tmp/vjiya.py <<'PY'
import json, os
from app.marketing import clients_store, customer_delivery as cd

c = None
for x in clients_store.list_clients(status="active") or []:
    if str(x.get("id")) == "jiya-makeover":
        c = x
        break
if not c:
    print("JIYA NOT FOUND"); raise SystemExit(0)

print("=== IDENTITY ===")
for k in ("id", "business_name", "plan", "status", "slug", "niche",
          "delivery_state", "delivered_at", "setup_done"):
    print("  %-16s %s" % (k, c.get(k)))
print("  billing_client_ids  %s" % (c.get("billing_client_ids"),))
print("  mini_site_url       %s" % cd.mini_site_url(c))
print("  is_paid_client=%s  has_paid_evidence=%s  is_delivered=%s" % (
    cd.is_paid_client(c), cd.has_paid_evidence(c), cd.is_delivered(c)))

def count(path, label):
    n = 0
    try:
        if os.path.exists(path):
            n = sum(1 for l in open(path, encoding="utf-8") if l.strip())
    except Exception as e:
        print("  %s ERR %s" % (label, e)); return
    print("  %-22s %d rows" % (label, n))

print("=== REAL DELIVERY DATA ===")
count("data/delivery_ledger/jiya-makeover.jsonl", "delivery_ledger")
count("data/content_queue/jiya-makeover.jsonl", "content_queue")

print("=== LAST 3 LEDGER EVENTS ===")
try:
    rows = [json.loads(l) for l in open("data/delivery_ledger/jiya-makeover.jsonl", encoding="utf-8") if l.strip()]
    for r in rows[-3:]:
        print("  %s | %s | %s" % (r.get("at"), r.get("event"), str(r.get("detail"))[:44]))
except Exception as e:
    print("  ERR", e)

print("=== INVOICE (immutable payment evidence) ===")
try:
    from app.billing import gst_invoice
    for r in gst_invoice._read():
        print("  %s | client_id=%s | %s" % (r.get("invoice_no"), r.get("client_id"), r.get("total")))
except Exception as e:
    print("  ERR", e)
PY
docker cp /tmp/vjiya.py leadgen_app:/tmp/vjiya.py >/dev/null 2>&1
docker exec leadgen_app python3 /tmp/vjiya.py 2>&1 | grep -v '"level"'
echo "===JIYA_DONE==="
