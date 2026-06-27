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

## Enterprise gate

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`).

**Change-risk tier:** Readiness gate run + approvals clear (UI) = **Standard**. God Mode se koi automation/flag flip ya outbound trigger karna = **High-risk** (production runtime, ban/cost). "PRODUCTION READY" declare karna evidence-backed ho, vibe-backed nahi.

- **Approvals (fail-CLOSED, human-in-loop):** Content/Self-improve/Process runs UI se ✓/✕ — auto-approve KABHI default mat karo. Core code/patch (code_upgrader) auto-apply nahi. Self-improve `SELFIMPROVE_COST_CAP=50` + optional `SELF_IMPROVE_APPROVAL=1` honor karo.
- **Safety / flags:** har automation gated default-OFF + inert-without-creds; God Mode se flag flip karne se pehle `automation-flags` skill ka ban/cost-risk dekho. Flags registry = `/api/growth/infra/flags` (live on/off). Secrets sirf `.env`.
- **Compliance (fail-CLOSED):** "production ready" ≠ telephony bypass — phone campaigns Vobiz+DLT pe blocked (TRAI/DND/9am–7pm/AI-disclosure intact). Payments = manual UPI (`UPI_VPA`); GST GST_GSTIN-gated. Razorpay removed — re-add mat suggest karo.
- **Observability:** `/api/activation/summary` `production_ready` (public) + `/api/activation/readiness` (13 probes) + `final_integration_check.py` (prod_check + wiring audit + smoke + tests) + `/app/automation` Mission Control liveness. Approvals backlog visible.
- **Rollback (NAMED):** misbehaving automation → flag OFF (`/api/growth/infra/flags`) → inert. Bad deploy → container recreate / `RUN_IN_PROCESS_SCHEDULER=1`+stop worker/scheduler (scheduler rollback path). Incident → `prod-incident-triage` skill.

**Evidence (done):** `python scripts/final_integration_check.py` PASS + `/api/activation/summary` `production_ready: true` + approvals pending = 0 + 1 marketing tab live smoke. Bina final_integration_check PASS "launch ready" KABHI mat bolo.
