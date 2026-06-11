---
name: backend-rbac
description: LeadGen AI ka roles + module-grants access-control system — super_admin/sub-admin(ADMIN)/module-limited members. Use jab "sub admin", "team member access", "role", "permission", "module grant", "kaun kya access kar sakta", require_admin/require_super_admin, ya naya admin endpoint banate waqt access-level decide karna ho.
---

# Backend RBAC — roles + module grants

## Model (3 layers)
1. **SUPER_ADMIN** (Sumit) — sab kuch + user-management + critical ops (user delete, code-patch approve, settings). `require_super_admin`.
2. **ADMIN** = sub-admin — saare admin dashboards/API, par super-only ops blocked. `require_admin` pass karta.
3. **MANAGER / AGENT / VIEWER** = module-limited team members — `require_admin` inhe TABHI pass karta jab request path ka module unke grants me ho (`app/platform/rbac.py`).

## Storage (no-migration decision)
- Role = `users.role` enum column (pehle se).
- Module grants = `users.preferences` JSON me `{"modules": ["marketing", ...], "must_change_password": true}` — `rbac.get_user_modules(user)` / `set_user_modules`. Alembic migration NAHI chahiye (Text column reuse).

## Module map (rbac.MODULES)
`marketing`(/api/marketing,/api/creative,/api/contentauto) · `growth`(/api/growth,/api/seoops,/api/localseo) · `leads`(/api/leads,/api/data) · `agents`(/api/agents) · `clients`(/api/clientcrm,/api/conversion,/api/lifecycle) · `billing`(/api/billing) · `telephony`(/api/voiceai,/api/webhooks-admin) · `analytics`(/api/analytics). Naya router banao to `rbac._MODULE_PREFIXES` me prefix add karo, warna module-limited members ke liye 403.

## Enforcement (central, 588 routes untouched)
`auth_deps.require_admin(request, user)` — Request inject hota hai: super/admin → pass; warna `rbac.module_for_path(path)` grants me ho to pass. Sensitive endpoint = `require_super_admin` use karo (upgrader approve, user delete, settings).

## Onboarding flow (temp password)
`POST /api/team-access/members` (super_admin) → temp password + modules + `must_change_password=true` → member `/app/admin-login` se login → UI force change → `POST /api/team-access/auth/change-password`. Reset: `POST /members/{id}/reset-password`. Sab actions `log_audit` (AuditLog table) me.

## Rules
- Naya admin endpoint likhte waqt poochho: kya module-limited member ko ye milna chahiye? Default `require_admin` (modules respect karta). Critical/irreversible → `require_super_admin`.
- Member create/role-change UI: `/app/team-access`. API docs: `app/api/team_access.py`.
- Customer auth (`customer_auth.py`, lgai_token) ALAG system hai — kabhi mix mat karo.
