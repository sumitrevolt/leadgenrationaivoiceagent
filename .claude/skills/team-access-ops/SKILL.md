---
name: team-access-ops
description: Team member add/remove/modules runbook — sub-admin banana, member ko modules dena, password reset, deactivate, audit dekhna. Use jab "naya team member", "sub admin banao", "access do/hatao", "password reset", "kisne kya kiya (audit)", ya /app/team-access ke baare me sawal ho.
---

# Team access ops — runbook (Sumit + agents)

## Naya sub-admin (sab handle kare, billing/critical chhod ke nahi — sab milta hai except super-only)
1. `/app/team-access` kholo (super_admin login) → "Add member" → role **admin** → temp password do.
2. Member `/app/admin-login` se login karega → pehli baar password change forced.
3. Super-only cheezein (user delete, code-patch approve, settings) uske liye 403 hi rahengi — by design.

## Module-limited member (e.g. sirf marketing)
1. Add member → role **manager** (ya agent/viewer) → modules tick karo (marketing/growth/leads/agents/clients/billing/telephony/analytics).
2. Wo sirf un modules ke API/pages use kar payega; baaki 403.
3. Modules badalna: member row → "Modules" edit → save (audit me jata hai).

## API equivalents (UI na ho to)
- Create: `POST /api/team-access/members` {email, first_name, last_name, role, modules[], temp_password}
- Modules: `PATCH /api/team-access/members/{id}/modules` {modules[]}
- Reset: `POST /api/team-access/members/{id}/reset-password` {temp_password}
- Deactivate: `PATCH /api/admin/users/{id}` {status: "inactive"} · Delete (super): `DELETE /api/admin/users/{id}`
- Audit: `GET /api/admin/audit-logs` (kisne kya kiya, old/new values)

## Gotchas
- Khud ko delete/demote nahi kar sakte (guards). Super_admin hamesha kam se kam 1 active.
- Member login = wahi `/app/admin-login`; token `accessToken` localStorage me (admin pages pattern).
- Account suspend/inactive = login turant block (status check `get_current_user` me).
- Temp password chat/email me bhejna pade to rotate karwana yaad rakho; CLAUDE.md/commit me KABHI nahi.
