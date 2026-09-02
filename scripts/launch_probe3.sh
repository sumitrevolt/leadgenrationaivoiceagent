#!/usr/bin/env bash
# launch_probe3.sh — read-only: paid-truth table (plan-based vs invoice-evidence)
set +e
echo "===PAID_TRUTH_TABLE==="
cat > /tmp/truth.py <<'PY'
from app.marketing import clients_store, customer_delivery as cd
from app.billing import gst_invoice

rows = gst_invoice._read()
inv_ids = {str(r.get("client_id") or "").strip() for r in rows}
inv_ids.discard("")
print("invoice_rows=%d invoice_client_ids=%s" % (len(rows), sorted(inv_ids)))
print("-" * 78)
print("%-14s %-24s %-9s %-10s %-8s" % ("id", "business_name", "plan", "plan_paid", "has_inv"))
for c in clients_store.list_clients(status="active") or []:
    cid = str(c.get("id") or "")
    ids = {cid} | {str(x or "") for x in (c.get("billing_client_ids") or [])}
    ids.discard("")
    has_inv = bool(ids & inv_ids)
    print("%-14s %-24s %-9s %-10s %-8s" % (
        cid[:14], str(c.get("business_name"))[:24], str(c.get("plan")),
        cd.is_paid_client(c), has_inv))
PY
docker cp /tmp/truth.py leadgen_app:/tmp/truth.py >/dev/null 2>&1
docker exec leadgen_app python3 /tmp/truth.py
echo "===PROBE3_DONE==="
