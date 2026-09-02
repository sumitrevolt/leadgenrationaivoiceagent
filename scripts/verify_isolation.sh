#!/usr/bin/env bash
# verify_isolation.sh — read-only: tenant isolation + public journey HTTP probes (live domain)
set +e
B=https://leadsgenai.in
probe () { printf '%-52s -> %s\n' "$2 $1" "$(curl -s -o /dev/null -w '%{http_code}' -m 15 "$B$1")"; }

echo "===PUBLIC (expect 200)==="
probe "/"                     "GET "
probe "/pricing"              "GET "
probe "/start"                "GET "
probe "/health"               "GET "
probe "/app/login"            "GET "

echo "===UNAUTHENTICATED TENANT/ADMIN APIS (expect 401/403 - NOT 200)==="
probe "/api/admin/dashboard"          "GET "
probe "/api/customer/office"          "GET "
probe "/api/platform/office/snapshot" "GET "
probe "/api/customer/dashboard"       "GET "
probe "/api/customer/deliverables"    "GET "

echo "===CROSS-TENANT PROBE (unauth must NOT read jiya data)==="
probe "/api/customer/dashboard?client_id=jiya-makeover" "GET "
probe "/api/marketing/client/jiya-makeover"             "GET "

echo "===AUTHENTICATED PAGES (200 = shell renders, gate is API-side)==="
probe "/app/customer" "GET "
probe "/app/admin"    "GET "
probe "/app/office"   "GET "
echo "===ISO_DONE==="
