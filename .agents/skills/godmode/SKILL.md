---
name: godmode
description: Production readiness + automation ops via Admin God Mode and Mission Control. Use when user says "god mode", "production ready", "launch", "automation approvals clear", or "final integration".
---

# God Mode — Production Ready (Marketing First)

**Goal:** Confirm platform **PRODUCTION READY** (marketing + ops) and run automations from UI.

**NOT gated:** payments (manual UPI), Vobiz telephony, DLT — optional later. (Razorpay gateway removed.)

## One command gate
```bash
python scripts/final_integration_check.py
```
PASS = prod_check + 33-page wiring audit + live smoke + tests + production_ready.

## UI checklist (5 min)
1. `/app/admin-login` → **God Mode** → **🟢 PRODUCTION READY**
2. **Automation Hub** → run any workflow (21 buttons)
3. `/app/automation` → **Approvals** → pending clear
4. `/app/marketing` → 1 tab smoke (post generate)
5. `/api/activation/summary` → `production_ready: true` (public)

## Approvals
- Content: Admin Hub or `/app/automation` → Approvals / ClientOps → ✓/✕
- Self-improve: Automation Hub pending or Mission Control Approvals
- Process: Mission Control → Processes → WAITING runs

## Automations (Admin Hub)
Self-Improve · Optimizer · Scrape · Email · Dunning · Digest · Health · Harvest · Cadence · Lifecycle · Followups · Reply · Content · Blog · Growth · Reviews · Journeys · Sales · Upgrader · QA · Prospects

## Optional (ignore for launch)
- Phone campaigns (`/app/test-call`, Launch Campaign) — Vobiz telephony creds baad me
- Paid payments — manual UPI (`UPI_VPA`) baad me

## If FAIL
- `final_integration_check.py` output dekho — handler/API gap ya live 404
- Admin token expired → re-login `/app/admin-login`
