---
name: leadgen-security-rbac
description: Security + auth + RBAC + tenant-isolation + secrets + admin-permissions + API-keys + webhooks + PII handling audit. Use jab customer-facing ya admin route ka auth/authorization check karna ho — missing auth = release blocker.
---

# LeadGen Security RBAC

> Enterprise audit skill. `backend-rbac` = roles/grants MODEL; **yeh = security audit lens** (IDOR, tenant-scope, secrets, webhook-sig, PII). Customer/admin route pe missing auth = RELEASE BLOCKER. Pehle `context-first`.

## Mission
Customer accounts, admin actions, lead data, payments, voice-compliance-state protect karo.

## Repo truth
- **RBAC**: `require_admin` / `require_super_admin`; 3-layer roles + module-grants (`backend-rbac`). Customer auth `_authed_client_id` dep.
- **IDOR closed (C1)**: har billing mutation pe `_authed_client_id` — wrong-tenant access blocked.
- **Webhook sigs FAIL-CLOSED in prod**: Twilio/Vobiz/WhatsApp → 503 jab secret unset (C2/C3 idempotent).
- **2FA**: customer TOTP (H.2). Admin login `/app/admin-login`.
- **SSRF (C4)**: `/site-audit` private-IP block.
- **Secrets**: sirf `.env` (gitignored); `scripts/check_secrets.py` (`/verify` step-4 wired; false-positive = line `nosecret`). CLAUDE.md/scripts/committed-file me KABHI nahi.
- **MCP**: `/mcp` gated (`FASTAPI_MCP_TOKEN` OR `MCP_IP_ALLOWLIST`; prod me bina ek ke mount REFUSED).
- **Tenant**: `middleware/tenant.py` FAIL-OPEN (subdomain + custom_domain).

## Workflow
1. Auth/session mechanisms, roles, permissions, tenant-ownership, API-keys, admin-routes, webhook-endpoints inventory.
2. Critical routes: authentication + authorization + tenant-scope + CSRF + rate-limit review.
3. Hardcoded secrets, exposed env, debug endpoints, public admin pages, PII-in-logs search.
4. Admin actions ke audit logs verify.
5. Tests: unauthorized / wrong-tenant / wrong-plan / wrong-role access.

## Enterprise checks
- Public routes sirf public data expose karein.
- Customer portal sirf current-customer ke resources read/write.
- Admin approval/payment/plan-change → admin role required.
- Webhooks signature/shared-secret verify.
- Secrets env/secret-manager se, committed nahi.
- PII + recordings minimized/masked/permission-gated (90-din retention).

## Output
Security/RBAC gap report · critical-route risk table · access-control test cases · secret+PII remediation · readiness /100.

## Related repo skills (duplicate mat banao)
`backend-rbac` (roles/grants model) · `team-access-ops` (RBAC ops) · `llm-security` (prompt/LLM security) · `security-review` + `self-code-review` (code-level) · `leadgen-billing-upi` (entitlement) · `leadgen-voice-compliance` (consent/PII) · `tenant-isolation-audit` (tenant-boundary deep-dive) · `secrets-rotation` (key inventory/rotation) · `data-retention-dpdp` (PII retention/delete).
