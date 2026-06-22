---
name: team-access-ops
description: Team member add/remove/modules runbook — sub-admin banana, member ko modules dena, password reset, deactivate, audit dekhna, customer ko "login as" karke debug karna. Use jab "naya team member", "sub admin banao", "access do/hatao", "password reset", "kisne kya kiya (audit)", "login as customer / impersonate", ya /app/team-access ke baare me sawal ho.
---

# Team access ops — runbook (Sumit + agents)

## Naya sub-admin (sab handle kare, billing/critical chhod ke nahi — sab milta hai except super-only)
1. `/app/team-access` kholo (super_admin login) → "Add member" → role **admin** → temp password do.
2. Member `/app/admin-login` se login karega → pehli baar password change forced.
3. Super-only cheezein (user delete, code-patch approve, settings) uske liye 403 hi rahengi — by design.

## Module-limited member (e.g. sirf marketing)
1. Add member → role **manager** (ya agent/viewer) → modules tick karo (8 catalog: marketing/growth/leads/agents/clients/billing/telephony/analytics).
2. Wo sirf un modules ke API/pages use kar payega; baaki + unmapped surface = 403 (fail-closed).
3. Modules badalna: member row → "Modules" edit → save (audit me jata hai).

## API equivalents (UI na ho to) — sab super_admin
- Create: `POST /api/team-access/members` {email, first_name, last_name, role, modules[], temp_password(≥8)}
- Modules: `PATCH /api/team-access/members/{id}/modules` {modules[]}
- Reset: `POST /api/team-access/members/{id}/reset-password` {temp_password(≥8)} (failed-login counter + lock bhi clear)
- Self change-pass: `POST /api/team-access/auth/change-password` (koi bhi logged-in role; must_change flag clear)
- Catalog/my-access: `GET /api/team-access/modules` · `GET /api/team-access/me`
- Deactivate: `PATCH /api/admin/users/{id}` {status: "inactive"} · Delete (super): `DELETE /api/admin/users/{id}`
- Audit: `GET /api/admin/audit-logs` (kisne kya kiya, old/new values)

## Customer ko debug karna (impersonation — super_admin only)
Customer bole "mera dashboard tuta" → screenshots maangne ki zaroorat nahi. GATED `IMPERSONATION=1` (off = 404). `/app/impersonate` kholo → client choose → short-lived (30 min) portal-session mint hoti (`POST /api/impersonate/start` {client_id, reason}) → `/app/customer` me uske data me jaake debug. Password kabhi nahi maangte/dekhte. Start+stop dono `log_audit` (warning, IP+reason) me — tamper-record.

## Gotchas
- Khud ko delete/demote nahi kar sakte (guards). Super_admin hamesha kam se kam 1 active.
- Member login = wahi `/app/admin-login`; token `accessToken` localStorage me (admin pages pattern).
- Account suspend/inactive = login turant block (status check `get_current_user` me).
- Temp password chat/email me bhejna pade to rotate karwana yaad rakho; AGENTS.md/commit me KABHI nahi.
