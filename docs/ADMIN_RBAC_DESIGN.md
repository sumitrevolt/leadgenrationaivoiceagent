# Admin RBAC Design — super admin → sub-admins → module-limited team (2026-06-11)

## Brief (user)
Ek super admin (Sumit) jo sab handle kare, sub-admins assign kar sake, team members ko specific
modules de sake. Feature-change ka documented flow. Production-ready. Skills pehle, phir build.

## Already-true (audit finding — REBUILD NAHI)
`app/api/admin.py` me poora user-management backend MAUJOOD tha: login/logout/me, user CRUD
(create/list/get/patch/delete), role guards (super-only delete, super-only super-promote),
**AuditLog DB table + log_audit() har action pe**, sessions/lockout/2FA fields. `auth_deps.py` me
`require_admin/require_super_admin/require_manager` ready. Gap sirf: (1) module-level grants +
enforcement, (2) temp-password first-login flow, (3) management UI, (4) chand critical endpoints
ka super-gating.

## New design

### Roles (existing enum reuse)
SUPER_ADMIN=Sumit (sab) · ADMIN=sub-admin (sab admin surface, super-only ops 403) ·
MANAGER/AGENT/VIEWER=module-limited members.

### Module grants — storage trade-off
`users.preferences` (Text/JSON, existing column) me `{"modules": [...], "must_change_password": bool}`.
**Chosen**: zero Alembic migration, zero model change, User row ke saath atomic.
**Rejected**: nayi grants table (migration + join, abhi overkill — revisit jab >25 team members
ya per-client scoping chahiye).

### Enforcement — central dependency (588 routes untouched)
`require_admin(request: Request, user)` upgrade: super/admin → pass; member-roles →
`rbac.module_for_path(request.url.path)` user ke grants me ho to pass, warna 403.
**Chosen**: ek jagah change, har route apne-aap covered, FastAPI Request injection se.
**Rejected**: (a) har route pe `require_module(x)` lagana — 588 edits, drift-prone;
(b) pure middleware — kaunse route admin-gated hain middleware nahi jaanta, public routes pe
false-positive risk.

### Module catalog (`app/platform/rbac.py`)
marketing · growth · leads · agents · clients · billing · telephony · analytics — path-prefix map.
Unmapped admin path (e.g. /api/admin, infra) = sirf ADMIN+; member ke liye 403 (fail-closed).

### Temp-password onboarding
Create member (super) → temp password + `must_change_password=true` → login response me flag →
UI force-change → `POST /api/team-access/auth/change-password` (self) flag clear. Reset-password
bhi yahi flag set karta. Email invite NAHI (user decision — baad me add ho sakta, SMTP ready hai).

### API (naya router `app/api/team_access.py`, prefix /api/team-access)
`GET /modules` (catalog) · `GET /members` (users + modules merged) · `POST /members` (super; temp
password) · `PATCH /members/{id}/modules` (super) · `POST /members/{id}/reset-password` (super) ·
`POST /auth/change-password` (self, koi bhi role). User CRUD/status = EXISTING /api/admin/users/*.
Sab writes → existing `log_audit`.

### Critical-ops super-gating (is pass me)
`POST /api/growth/upgrader/patches/{id}/status` (code-patch approve) require_admin →
**require_super_admin**. (User delete + super-promote pehle se super-only.)

### UI — `/app/team-access` (admin accessToken pattern)
Members table (role/modules/status/last-login) + add-member form + modules editor + reset/deactivate
+ recent audit feed (existing /api/admin/audit-logs). Member ke liye read-only self view.

## Production readiness notes
Login lockout (failed_login_attempts/locked_until) + status suspend = pehle se model me; rate-limit
login pe lagana ho to `rate_limit` dependency ready. 2FA TOTP super_admin ke liye gated env pehle se.
Audit DB-backed (Postgres) — backup nightly pg_dump me covered.

## Revisit when
>25 members ya per-client tenant teams → grants table + Alembic; SSO/Google login demand →
authlib add; per-route fine-grained perms → `require_permission` (already stubbed in auth_deps) ko
modules se merge karna.
