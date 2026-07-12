# UNITY VIRTUAL OFFICE — SECURITY (2026-07-12)

> Threat model: Unity WebGL is UNTRUSTED CLIENT CODE, same as any browser JS. All authorization is
> server-side. Nothing in this program may weaken existing gates (CLAUDE.md §5).

## 1. Identity & tenancy (reused, unchanged)

- Admin: `Depends(require_admin)` (`app/api/auth_deps.py:94`) — fail-CLOSED 403 for unmapped members
  (RBAC). All office/control-center/system-health/activation admin feeds already carry it.
- Customer: `Depends(require_customer)` (`app/api/customer_auth.py:193`) — JWT role must equal
  `customer`; tenant = `payload["sub"]`. Signature-locked (existing test
  `tests/test_customer_tenant_isolation_authenticated.py`): the dependency takes ONLY `creds` —
  no request-controlled tenant hint can become an argument. Forged `client_id` in query/body/header
  is unparsed/ignored by construction (no `Query()` binding on any customer route).
- Unity receives ONLY presentation state pushed by the shell. The shell holds the bearer token
  (localStorage, same as every existing dashboard); the token is never passed into the Unity heap,
  never in URL params.

## 2. Hard prohibitions (inherited + program-specific)

Unity/shell must never: connect to PostgreSQL/Redis/Qdrant directly; receive social tokens, SIP
creds, webhook secrets, DB URLs, `.env` values; render other tenants' data in customer mode;
display fake system activity (source/note provenance must be surfaced); show platform_dial as
anything but HARD OFF while the 3-layer kill is active; bypass DND fail-CLOSED, TRAI window
(09:00–19:00 code-conservative), DPDP retention, packages.py entitlement truth, WhatsApp 1-click
manual-only truth.

## 3. Bridge hardening

Allowlist table in UNITY_OFFICE_API_CONTRACT.md §4 is the ONLY navigation surface. Rules:
fixed route map (Unity supplies action name + sanitized id, never URLs/JS), id regex
`^[a-zA-Z0-9_\-\.]{1,64}$`, unknown action → reject+console.warn, permission pre-check (customer
shell never registers admin actions; server re-checks anyway), no `eval`/`Function`/dynamic script
injection, postMessage (if ever used cross-frame) pinned to same-origin — never `'*'`.

## 4. Feature flags & rollout

`UNITY_VIRTUAL_OFFICE_ENABLED` / `UNITY_CUSTOMER_OFFICE_ENABLED` — env flags in
`AUTOMATION_FLAGS` registry, default OFF/INERT (flag off → `/app/office?mode=3d` serves the
existing map; zero new attack surface). Progressive per-tenant rollout later via the existing
Redis feature-flag service (`app/infrastructure/feature_flags.py`). Rollback = unset flag
(no redeploy of old builds needed for the shell; Unity static builds are versioned dirs).

## 5. Test matrix (Phase 25 → concrete)

Backend guarantees 1–7, 15, 19–22, 24–25 are ALREADY covered by existing suites
(`test_customer_tenant_isolation_authenticated.py` 19 tests — AST + primitive proof;
billing-truth suite; office/admin routes behind require_admin). NEW tests this program adds
(`tests/test_office_blueprint_shell.py`):

| # | Assertion | Type |
|---|---|---|
| S1 | `/app/office` default serves existing map when flag unset (INERT proof) | TestClient |
| S2 | `?mode=3d` with flag OFF serves existing map (no shell leak) | TestClient |
| S3 | `?mode=3d` with flag ON serves blueprint shell | TestClient (monkeypatch env) |
| S4 | Shell HTML contains NO secret-shaped literals (sk_, Bearer <tok>, redis://, postgres://, AKIA…) | static |
| S5 | Shell bridge allowlist == documented action set (drift lock, parsed from HTML) | static |
| S6 | Shell contains no hard-coded customer names (jiya etc.) / counts / plan prices | static |
| S7 | Shell fetches ONLY allowlisted API paths (`/api/platform/office/`, `/api/events/stream`, documented set) | static |
| S8 | Unity static mount absent when build dir missing (no 500 at boot) + guarded registration | TestClient/import |
| S9 | postMessage targets are same-origin pinned (no `'*'` in shell) | static |
| S10 | Customer shell variant (when built) registers zero admin actions | static (deferred to Milestone E) |

Runtime cross-tenant/event-isolation tests for a future tenant-SSE remain REQUIRED-BEFORE-CUSTOMER-
PREVIEW (Phase 25 #6/#17/#24) — tracked in backlog; the vertical slice avoids them by using
polling of already-proven tenant-scoped endpoints.

## 6. Ops/log hygiene

Shell logs to console only (no payload bodies in error paths); server logging unchanged; no new
log sinks. Known open P0 from self-improve audit (query-string credential redaction in INFO HTTP
logs) is OUTSIDE this program but relevant: the shell deliberately keeps tokens out of URLs so that
existing exposure class doesn't grow.
