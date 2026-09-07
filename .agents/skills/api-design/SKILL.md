---
name: api-design
description: FastAPI route/endpoint design discipline for the LeadGen AI platform — grep-first (no duplicate routes), additive + flag-gated + defensive handlers, contract-first. Use when adding/changing ANY API endpoint or router, designing a module boundary, or wiring a new feature into app/api or app/main.py.
---

# API & Interface Design (LeadGen AI)

Contract-first FastAPI discipline. Encodes the #1 lesson from this project: **never create a route that already exists.**

## When to Use
Adding/changing any `@router`/`@app.get/post`, mounting a router in `main.py`, or designing a feature's endpoints.

## Process

1. **GREP FIRST (mandatory, non-negotiable).** Before adding ANY route/module, search for an existing one:
   `grep -rn "@router\|@app.get\|@app.post" app/api/<area>.py` and `grep -rn "def <likely_name>" app/`. FastAPI is first-route-wins → a duplicate path silently SHADOWS prod. With ~1030 routes (2026-07-05) the odds an endpoint already exists are high; this project has lost hours to duplicate festival/review/route modules. If it exists, EXTEND it — don't rebuild.
2. **Additive + gated.** New behavior defaults to today's behavior. Risky/new = behind an env flag (default OFF, register in `app/api/growth.py` `AUTOMATION_FLAGS`) or `Depends(require_admin)`. Zero behaviour change unless explicitly enabled.
3. **Defensive handlers.** Reuse the project pattern: lazy imports inside handlers, `try/except` → graceful result (never 500 except validation), `*.get()` fallbacks. Modules import-safe (never raise on import).
4. **Contract-first.** Pydantic models for in/out. Clear error semantics (422 validation, 401/403 auth, 409 conflict). Validate at the boundary (length caps, types).
5. **Mount safely.** Router include in `main.py` inside `try/except` with a warning log (optional-mount pattern), prefix `/api`.
6. **Page routes need HARD RELOAD.** New `@app.get` page-routes don't show after a normal restart (stale `.pyc`) — see ship-checklist.

## Red Flags
- Adding a route without grepping for an existing one. · A new module that duplicates an existing capability (review/festival/etc.). · A handler that can raise an unhandled 500. · New endpoint changes default behaviour without a flag. · Route added but not verified in `prod_check` route count.

## Verification
- Show the grep proving no existing route/module before building.
- `python scripts/prod_check.py` → route count increased by exactly the number you added, ALL CHECKS PASSED.
- `import app.main` clean. New endpoint returns expected codes (200 / 401 unauth / 422 bad input).

## Enterprise gate
Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`).

**Change-risk tier:** an endpoint **inherits the tier of what it touches**. Plain read/generation route = **Standard** (dup-route grep + flag-gate + changed-file tests + `prod_check`). But the moment the path touches **billing/pricing, a public unauthed surface, auth/secrets, or telephony/outbound → High-risk** — lock the per-domain gate below and add `self-code-review` + `security-review`.

**Gates (relevant to endpoint work):**
- **Safety:** new behaviour defaults to today's behaviour — risky/new behind `Depends(require_admin)` or an env flag registered in `app/api/growth.py AUTOMATION_FLAGS` (else invisible in `/api/growth/infra/flags`). Mount routers in `main.py` inside `try/except` (optional-mount), prefix `/api`.
- **Contract + defensive:** Pydantic in/out, boundary validation (length caps, types); clear codes (422 validation · 401/403 auth · 409 conflict). Handlers never raise an unhandled 500 — lazy imports inside the handler, `try/except` → graceful result, `*.get()` fallbacks.
- **Per-domain escalation:** *public route* → SSRF/auth/rate-limit (`app/api/ratelimit.py` `rate_limit(...)` Depends), public endpoint heavy/ML work = `asyncio.to_thread` + hard timeout (widget-chat prod-down lesson). *Billing* → `app/marketing/packages.py` single source + `test_billing_truth_2026` SAATH green. *Auth/IDOR* → resource scoped to `_authed_client_id` dep. *Telephony/outbound* → TRAI 9am–7pm + DND fail-CLOSED + AI-disclosure (never bypass).
- **Rollback (named):** flag OFF reverts behaviour; container recreate (`up -d --no-deps app`) clears the stale-`.pyc` 404 for new `@app.get` page-routes.

**Evidence (done):** `.venv\Scripts\python.exe scripts\prod_check.py` (route count += exactly N, ALL PASS) + `import app.main` clean + new endpoint returns 200 / 401 unauth / 422 bad-input + `.venv\Scripts\python.exe -m pytest tests\test_<area>.py -q`. Billing-touching → add `test_billing_truth_2026`; secrets-touching → `scripts\check_secrets.py`.
