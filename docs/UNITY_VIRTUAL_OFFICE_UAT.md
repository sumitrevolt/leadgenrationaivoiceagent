# UNITY VIRTUAL OFFICE — UAT SCRIPT (2026-07-12)

> Status: NOT YET EXECUTED — blocked on Unity build + flag flip + browser session.
> Fill the evidence column per run; screenshots to `docs/uat/office-YYYY-MM-DD/`.

## A. Admin UAT (Phase 29) — real browser, real admin login

| # | Route / action | Viewport | Expected | Evidence |
|---|---|---|---|---|
| A1 | `/app/office` (no params, flag ON) | desktop | EXISTING 2D Phaser office unchanged (default untouched) | |
| A2 | `/app/office?mode=map` | desktop | 2D map (explicit lightweight) | |
| A3 | `/app/office?mode=3d`, logged OUT | desktop | "Login required" state, no data, no blank canvas | |
| A4 | `/app/office?mode=3d`, admin session, NO build deployed | desktop | Shell: live KPIs/agents/pipeline/minimap from snapshot; "Unity build: NOT DEPLOYED"; fallback link | |
| A5 | same, build deployed | desktop | Unity loads with progress bar ≤20s; canvas visible; rooms match minimap 1:1 | |
| A6 | Click room in Unity | desktop | Minimap highlights same room; detail panel fills; no console errors | |
| A7 | Click room in minimap | desktop | Unity camera focuses same room (host→unity sync, no loop) | |
| A8 | Agent click → `open_agent_details` | desktop | Side panel shows agent status/task (REAL snapshot values) | |
| A9 | Alerts/NBAs panel | desktop | Matches `/api/platform/office/snapshot` next_best_actions | |
| A10 | Pipeline provenance | desktop | `partial`/`mock` stages visibly tagged (honesty check) | |
| A11 | Voice/compliance surfaces | desktop | platform_dial shown HARD OFF; promo window 09:00–19:00; DND fail-closed states truthful (vs `/api/activation/readiness`) | |
| A12 | Kill network 60s | desktop | "offline — retrying" chip → STALE badge; recovers on reconnect; no crash | |
| A13 | Expire session (clear token) → refresh action | desktop | Session-expired state; login link | |
| A14 | `/app/control-center`, `/app/admin`, `/app/explorer` | desktop | All unchanged and reachable (escape links work) | |
| A15 | Mobile ~390px `/app/office?mode=3d` | mobile | Inspector hidden, message + Lightweight link usable; no horizontal overflow | |
| A16 | Browser console (whole session) | both | Zero errors (warnings from Unity loader acceptable, listed) | |
| A17 | Network tab sweep | both | No secrets/tokens in any response body or URL; only allowlisted API paths | |

Screenshots required: command-center overview, blueprint minimap+panel, selected room,
selected agent, degraded/offline state, lightweight fallback.

## B. Customer UAT (Phase 30) — Milestone E (not built yet)

Blocked until `CustomerBlueprintOffice` exists. Script prepared:
real customer login (normal auth, tenant-scoped APIs — NEVER hard-coded jiya data),
verify: own tenant only, plan/deliverables from packages-truth endpoints, delivery shelf matches
`/api/customer/delivery-proof`, approvals count matches `/approvals/pending`, social states truthful
(manual mode shown as manual), reports/billing/support open existing HTML views authenticated,
mobile 360/390px usable, zero console errors, zero cross-tenant strings in network responses.

## C. Automated pre-UAT gate

`pytest tests/test_office_blueprint_shell.py -q` green + `prod_check.py` PASS + `check_secrets.py`
clean = precondition for starting manual UAT.
