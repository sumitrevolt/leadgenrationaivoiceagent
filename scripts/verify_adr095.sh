#!/usr/bin/env bash
# verify_adr095.sh — read-only: prove the fix is live in the WORKER (where the alert fires)
set +e
cat > /tmp/verify095.py <<'PY'
from app.marketing import clients_store, customer_delivery as cd
from app.billing import gst_invoice

rows = gst_invoice._read()
inv = {str(r.get("client_id") or "").strip() for r in rows}
inv.discard("")
print("invoice_rows=%d ids=%s" % (len(rows), sorted(inv)))
print("has_paid_evidence exists:", hasattr(cd, "has_paid_evidence"))
print("-" * 82)
print("%-14s %-22s %-8s %-10s %-12s %-9s" % (
    "id", "business_name", "plan", "eligible", "paid_evidence", "delivered"))
for c in clients_store.list_clients(status="active") or []:
    print("%-14s %-22s %-8s %-10s %-12s %-9s" % (
        str(c.get("id"))[:14], str(c.get("business_name"))[:22], str(c.get("plan")),
        cd.is_paid_client(c), cd.has_paid_evidence(c), cd.is_delivered(c)))
print("-" * 82)
pending = cd.find_undelivered_paid_clients()
print("DEAD-MAN DETECTOR -> %d client(s): %s" % (
    len(pending), [str(c.get("business_name")) for c in pending]))
PY
echo "===VERIFY IN leadgen_worker (alert source)==="
docker cp /tmp/verify095.py leadgen_worker:/tmp/verify095.py >/dev/null 2>&1
docker exec leadgen_worker python3 /tmp/verify095.py 2>&1 | grep -v '"level"'
echo "===STUCK LOG (should get NO new Test Biz rows after 13:20 UTC)==="
docker exec leadgen_app sh -c 'tail -2 data/delivery_stuck.jsonl 2>/dev/null'
echo "===VERIFY_DONE==="
