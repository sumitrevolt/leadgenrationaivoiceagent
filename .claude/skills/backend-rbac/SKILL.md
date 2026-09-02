---
name: backend-rbac
description: LeadGen AI ka roles + module-grants access-control + admin-side auth features. Use jab "sub admin", "team member access", "role", "permission", "module grant", "kaun kya access kar sakta", require_admin/require_super_admin, 2FA/TOTP, magic-link login, ya "login as customer"/impersonation, ya naya admin endpoint banate waqt access-level decide karna ho.
---

# Backend RBAC — roles + module grants

## Model (3 layers)
1. **SUPER_ADMIN** (Sumit) — sab kuch + user-management + critical ops (user delete, code-patch approve, settings). `require_super_admin`.
2. **ADMIN** = sub-admin — saare admin dashboards/API, par super-only ops blocked. `require_admin` pass karta.
3. **MANAGER / AGENT / VIEWER** = module-limited team members — `require_admin` inhe TABHI pass karta jab request path ka module unke grants me ho (`app/platform/rbac.py`).

## Storage (no-migration decision)
- Role = `users.role` enum column (pehle se).
- Module grants = `users.preferences` JSON me `{"modules": ["marketing", ...], "must_change_password": true}` — `rbac.get_user_modules(user)` / `set_user_modules`. Alembic migration NAHI chahiye (Text column reuse).

## Module map (`rbac.MODULES`, 8 modules → path-prefixes)
`marketing`(/api/marketing,/creative,/contentauto,/widgets) · `growth`(/api/growth,/seoops,/localseo,/brand) · `leads`(/api/leads,/data) · `agents`(/api/agents,/ai) · `clients`(/api/clientcrm,/conversion,/lifecycle,/minisite,/journeys,/clientops) · `billing`(/api/billing) · `telephony`(/api/voiceai,/calls,/booking) · `analytics`(/api/analytics,/memory). Naya admin router banao to `rbac.MODULES` me prefix add karo, warna module-limited members ke liye wo 403 (fail-closed by design — unmapped surface bhi deny).

## Enforcement (central; ~1030 routes untouched)
`auth_deps.require_admin(request, user)` — Request inject hota hai: super/admin → pass; warna `rbac.module_for_path(path)` (longest-prefix match) grants me ho to pass (`rbac.member_can_access`). Sensitive endpoint = `require_super_admin` use karo (upgrader approve, user delete, settings).

## Onboarding flow (temp password)
`POST /api/team-access/members` (**super_admin only**) → temp password + modules + `must_change_password=true` → member `/app/admin-login` se login → UI force change → `POST /api/team-access/auth/change-password`. Reset: `POST /api/team-access/members/{id}/reset-password`. Modules edit: `PATCH /api/team-access/members/{id}/modules` (super_admin). Sab writes `log_audit` (AuditLog table) me.

## Extra admin-auth features (flag-gated, INERT default)
- **Customer TOTP 2FA** (`app/platform/customer_totp.py`, mounted `/api/customer/2fa/*`): customer opt-in, authenticator QR, login pe email+pass → challenge token → `/api/customer/2fa/verify` → JWT. Challenge HMAC `TOTP_CHALLENGE_KEY` (random/restart if unset), 5-min expiry. 8 single-use recovery codes (SHA-256). **Admin TOTP** = `app/utils/totp.py` + `ADMIN_TOTP_SECRET`.
- **Magic-link passwordless** (`customer_auth.py`, `/api/customer/magic-link/*`): GATED `MAGIC_LINK=1` (TTL `MAGIC_LINK_TTL_S`, default 900s). Off = config endpoint says disabled, UI hides.
- **Impersonation / "login as customer"** (`app/api/impersonation.py`, `/api/impersonate/*`, page `/app/impersonate`): super_admin ONLY + GATED `IMPERSONATION=1` (off = 404, inert). Short-lived customer-role JWT (`imp=true`+`imp_by` markers, TTL `IMPERSONATION_TTL_MIN`=30). HAR start/stop `log_audit` (severity=warning, IP+reason). Password kabhi read/return nahi.

## Rules
- Naya admin endpoint likhte waqt poochho: kya module-limited member ko ye milna chahiye? Default `require_admin` (modules respect karta). Critical/irreversible → `require_super_admin`.
- Member create/role-change UI: `/app/team-access` (frontend `team_access.html`). API docs: `app/api/team_access.py`.
- Customer auth (`customer_auth.py`, lgai_token, role=="customer") ALAG system hai — kabhi admin auth ke saath mix mat karo. Impersonation is dono ke beech ka audited bridge hai.

## Enterprise gate (access-control = fail-CLOSED)

- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover me: naya router/path ka module-mapping + jo dep lagana hai woh confirm karo (unmapped surface = silent 403, design hai par intentional hona chahiye).
- **Change-risk tier: High-risk** (secrets/auth domain). Auth dep, `rbac.MODULES` map, role-enum, ya impersonation/2FA touch = §9 ka full bar + named rollback + `security-review` SAATH.
- **Fail-CLOSED gates (bypass = privilege escalation, reject):**
  - **Default-deny RBAC** — `require_admin` module-limited member ko TABHI pass kare jab path ka module grants me ho; **unmapped path = deny**. Naya admin router add kiya to `rbac.MODULES` me prefix add karo, warna woh members ke liye toота-403 dikhega.
  - **IDOR** — member/user mutations server-derived identity pe; cross-user delete/demote/grant guarded (super_admin self-demote/self-delete block, ≥1 active super hamesha).
  - **Least-privilege** — sensitive/irreversible (user delete, code-patch approve, settings, modules-edit) = `require_super_admin`, never plain `require_admin`. Naye endpoint ka default `require_admin`; upgrade sirf jab justify ho.
  - **Secrets** — `TOTP_CHALLENGE_KEY`/`ADMIN_TOTP_SECRET`/JWT signing keys sirf `.env`; temp passwords commit/CLAUDE.md me KABHI nahi (`scripts/check_secrets.py`).
  - **Audit-mandatory** — har grant/role/reset/impersonation write `log_audit` (AuditLog: actor, old→new, IP, reason). Bina audit-trail wali privileged write = incomplete.
- **Flag-gated inert:** Impersonation (`IMPERSONATION=1`, off=404) · Magic-link (`MAGIC_LINK=1`, off=disabled). Default-OFF = zero attack surface jab tak explicitly on na ho.
- **Rollback (NAMED):** offending endpoint dep tighten / flag OFF → container recreate (`up -d --no-deps app`); galat grant = `PATCH .../modules` se revert + audit-log se blast-radius dekho. No-migration design (preferences JSON) = schema rollback nahi chahiye.
- **Evidence to close:** unauth + wrong-role + cross-module request → 401/403 ka test/log; super-only endpoint pe plain-admin token → 403; `.venv\Scripts\python.exe scripts\prod_check.py` PASS + `scripts\check_secrets.py` clean + audit-log entry visible (`GET /api/admin/audit-logs`).
