# RISKS_AND_BLOCKERS

## B1 — Jiya proof deliverable incomplete
- **Severity:** HIGH
- **Observed evidence:** ADR-125 left proof HONEST-blocked; assurance at_risk=1 for sole paid client
- **Business impact:** Delivery matrix stuck ~90%
- **Root cause status:** EXTERNAL + pending approvals
- **Owner:** WS-2 / human
- **Required resolution:** Meta customer-page access or manual publish proof + approvals

## B2 — Command Center authenticated UI KPI not browser-proven
- **Severity:** LOW
- **Observed evidence:** code+assurance data PRODUCTION-PROVEN; no admin-token browser click this session
- **Business impact:** residual operator-trust gap
- **Root cause status:** evidence gap (not a known code defect)
- **Owner:** ops smoke
- **Required resolution:** one admin login to Delivery Command Center

## B3 — deploy_vps.sh skew check vs hashed container names
- **Severity:** LOW (tooling)
- **Observed evidence:** script FATAL skew while `/health`+image tags matched `d32a4934`
- **Business impact:** false deploy failure noise
- **Root cause status:** Confirmed tooling defect
- **Owner:** infra follow-up (not WS-2)
- **Required resolution:** skew check via compose service / image tag not static container name

## B4 — CI pytest job pre-existing failures
- **Severity:** MEDIUM (signal quality)
- **Observed evidence:** PR #59 merge allowed; remote `prod_check + pytest` failed many unrelated tests; local `prod_check` PASS; delivery_assurance 12+ passed
- **Business impact:** CI less trustworthy as merge gate
- **Root cause status:** PRE-EXISTING (e.g. admin_clients_delivery_panel also fails on origin/main)
- **Owner:** test hygiene backlog
- **Required resolution:** quarantine/fix pre-existing failures separately
