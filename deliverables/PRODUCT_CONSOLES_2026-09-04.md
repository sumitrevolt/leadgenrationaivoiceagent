# Product Consoles — Archify-styled customer dashboards

**Date:** 2026-09-04 · **Status:** built and verified locally · **Deployed:** no (deployment is owner-gated)

## What was built

Two enterprise consoles sharing one design system and one runtime, served at:

| Route | Product | Purpose |
|---|---|---|
| `/app/voice-console` | Product 1 | Customer Configuration & Knowledge Panel |
| `/app/marketing-console` | Product 2 | Marketing Product Launch Panel |

### Files

| File | Role |
|---|---|
| `app/api/product_consoles.py` | 17 routes: page serving, static assets, and all console APIs |
| `frontend/archify_console.css` | Design system — Archify tokens + Evidence Console components |
| `frontend/archify_console.js` | Shared runtime: nav, system map, all section renderers, drawer |
| `frontend/voice_console.html` | Product 1 page (nav + topology + automation logic) |
| `frontend/marketing_console.html` | Product 2 page (nav + topology + launch logic) |

Mounted in `app/main.py` inside a guarded `try`, immediately before the `customer_onboard` block.

## Discovery: the consoles were orphans

Building the pages was not sufficient — nothing linked to them, so a logged-in
customer could never find them. Wiring was added in a second pass (2026-09-04):

| Surface | File | Behaviour |
|---|---|---|
| Customer sidebar (combo/marketing/voice) | `frontend/customer_dashboard.html:564-565` | Voice link carries `voice-only`, marketing link carries `marketing-only`. The existing body-class CSS (`.prod-marketing .voice-only` / `.prod-voice .marketing-only`) gives per-product visibility for free — no new gating logic. |
| Customer mobile "More" sheet | `frontend/customer_dashboard.html:1466-1471` | Same classes, so the existing mobile gating keeps working. The 6-slot bottom bar was left alone; it was full. |
| Customer dashboard v2 | `frontend/customer_dashboard_v2.html:249-250` + gate IIFE | v2 has **no** product gating of its own — it shows every nav item to every customer. Pasting the links in would have shown unentitled entries, so a small token-based gate was added: it reads `/api/customer/auth/me`, and **fails closed** (hides both) on missing token, bad response, or unknown product. |
| Admin / operator reach | `app/api/impersonation.py`, `frontend/impersonate.html` | See below. |

Resulting visibility:

| Route / product | Voice Console | Marketing Console |
|---|---|---|
| `/app/customer` (combo) | visible | visible |
| `/app/customer/marketing` | hidden | visible |
| `/app/customer/voice` | visible | hidden |

**Admin reach — why no plain admin nav link was added.** An admin JWT carries no
`client_id`, so `/api/consoles/bootstrap` rejects it and a naive sidebar link
would have been broken on arrival. The correct path is impersonation, and it was
already 90% built: the frontend honoured `portal_url`
(`frontend/impersonate.html:77`) but the backend hard-coded it to `/app/customer`
(`impersonation.py:205`). The minimal fix was entirely server-side:

- `ImpersonateIn` gained an optional `to` field, validated against
  `PORTAL_ALLOWLIST` by `_safe_portal_url()`. **Exact-match only** — anything with
  a scheme, host, query or trailing path is not a member and falls back to
  `/app/customer`. This closes an open redirect, since the value is echoed to the
  browser and then followed.
- `GET /api/impersonate/targets` now returns each client's `product`, so the
  operator is shown the console that client is actually entitled to.
- `/app/impersonate` renders one action per entitled console (two for combo
  clients) and displays the product as a chip.

Locked down by `tests/test_impersonation_portal_target.py` (35 checks), including
13 hostile-input cases — absolute URLs, protocol-relative `//host`, `javascript:`,
query smuggling, path traversal, trailing slash, and case variation.

### One deliberate non-fix

The entitlement signal is the `marketing` / `voice` / `combo` product enum, which
is **not** price-tier aware. A `marketing` customer on the ₹5,999 Advanced plan
therefore does not see the Voice Console, even though voice callback is a feature
of that tier per the charter. Correcting this needs a `plan`-aware signal on the
server; the existing `product`-only model cannot express it. Flagged rather than
guessed — inventing gating here would have been worse than the gap.

## Design language

Derived from `tt-a1i/archify` `DESIGN.md` — north star **"The Evidence Console"**.

- Palette: canvas `#020617`, mask `#0F172A`, semantic cyan `#22D3EE` (active), green `#34D399` (verified), violet `#A78BFA` (stored state), amber `#FBBF24` (needs action), rose `#FB7185` (blocked), orange `#FB923C` (transit), slate (external).
- JetBrains Mono throughout; hierarchy from weight/scale/spacing, never a display face.
- 140–200 ms transitions, `prefers-reduced-motion` honoured, 2 px cyan focus rings, non-colour state cues.
- **Deliberately excluded** because Archify names them as anti-patterns: dense dashboard shells, grids of identical cards, glassmorphism, gradient text, decorative motion.
- **Used instead:** a live SVG system map (the console's primary spatial narrative) plus progressive disclosure into exactly one focused drawer.

## Reused infrastructure (nothing rebuilt)

| Capability | Module |
|---|---|
| Per-tenant knowledge base | `app/voice_agent/knowledge_base.py`, namespace `client:<id>` |
| Web-page ingestion | `app/voice_agent/kb_loader.py` |
| Encrypted credential vault | `app/social_engine/vault.py` (Fernet at rest) |
| Social OAuth start/callback | `app/api/social_oauth.py` |
| Connection health classifier | `app/platform/integration_status.py` |
| Client record | `app/marketing/clients_store.py` |
| Tenant auth | `require_customer` (JWT + Redis revocation) |

Per-tenant config persists to `data/console_configs.jsonl` (jsonl-first, append-only, latest-wins) via `platform.runtime_data_authority.resolve_store_path(store_id="consoles.config")`.

## Notable design decisions

**Event → asset binding.** Call automation is expressed as 8 lifecycle event slots bound to templates (pattern borrowed from Tata Tele Business Services Smartflo), not as one opaque settings blob. Each row shows the bound template, channel, DLT requirement, and an `ARMED` / `INERT` state. `_normalize_bindings()` discards unknown slots and template ids, so a stale record can never reference a deleted template.

**Commitment-free test before credentials.** The Grounding Probe answers a question from the tenant's own knowledge and returns the exact source chunks with scores — before anything is switched on.

**Honesty contract.** No surface reports a state it cannot evidence:
- Marketing launch returns `blocked: true` when zero channels are healthy, rather than showing a green switch that publishes nothing.
- Automation reports `live: false` with the specific failing gates until knowledge, template, binding and channel are all real.
- Unbound events are labelled `INERT`, not silently given fallback behaviour.
- Missing data renders as honest zeros and explicit "unknown" — never as a hopeful green.

## Verification

79 checks passing, 0 failing (re-run 2026-09-04 after the duplicate-mount fix — no regression).

- `\_scratch/smoke_consoles.py` — 69 checks against the real app via `TestClient` with `require_customer` overridden: pages, static assets, bootstrap for both products, business config, full knowledge lifecycle (ingest → probe → evidence → delete), template gallery and detail, event-binding normalisation, blocked-launch path, readiness computed from real state, and 401 on every route without auth.
- `\_scratch/smoke_consoles_fast.py` — 10 targeted regression checks for the two failures found below.
- `ruff check app/api/product_consoles.py --select E,F,W --line-length 110` — clean.
- `prod_check.py` — **ALL CHECKS PASSED**, 1381 routes, 58 pages 0 gaps, `app.main` imports OK, no duplicate (method, path) collisions, 0 orphans in the explorer graph (362 nodes, 98/98 engine coverage).
- `scripts/sync_api_docs.py` re-run — `docs/API.md` in sync (1402 ops).
- JS: `node --check` clean on the shared runtime; both inline page scripts and the edited `impersonate.html` script parse.
- `tests/test_impersonation_portal_target.py` — 35 checks (portal-target allowlist, hostile-input rejection, product normalisation, targets payload).
- `tests/test_impersonation.py` — 6 checks, no regression from the `to` field addition.

A note on the route count: `prod_check` reports 1381 while an earlier run this
session reported 1380. The delta is **not** attributable to this work — `git diff`
confirms no route decorator was added by any console or impersonation change, and
the count is stable at 1381 across three separate processes with byte-identical
path lists. It comes from unrelated in-flight work in the same working tree
(`video_pipeline.py`, `render_engine.py`). `prod_check`'s own guards — expected-route
presence and duplicate-collision detection — both pass.

### Defects found and fixed during verification

1. **`PUT /api/consoles/business-config` with `{}` returned 200.** `model_dump()` always carried the `language` and `timezone` defaults, which made the "no fields to save" 400 unreachable and silently overwrote stored values on a partial save. Fixed with `model_dump(exclude_unset=True)`; a partial save now persists only the fields actually sent.
2. **The URL scheme check was unreachable.** `Field(min_length=8)` rejected the 7-character test input with 422 before the handler ran. This was a test defect, not a code defect — the test now uses `ftp://example.com/page` to exercise the handler's 400 path, and keeps a separate 422 length case.
3. **Duplicate router mount in `app/main.py`.** The `product_consoles` router was mounted twice, producing five FastAPI duplicate-operation-id warnings. Removed the earlier, less-documented block; every route now carries an explicit `operation_id`.
4. **A dead-end on session loss.** The boot-time no-token guard existed, but a 401 *mid-session* (expired token) only produced an error toast, leaving a half-rendered shell with no way forward. `archify_console.js` now redirects to `/app/login` on 401. No return-path parameter is passed — `/app/login` does not honour one (verified), so passing `next=` would have been dead code. A one-shot flag stops several concurrent in-flight calls from racing the redirect.

## Known limitations

- Activation persists configuration and evaluates real gates; it does not itself enqueue calls. Wiring automation to the telephony worker is the natural next step.
- Channel availability depends on platform app review (Meta Advanced Access, LinkedIn partner access, GBP API). Slots that are not approved render as "Not available" with the specific owner action — this is honest, not broken.
- Consoles are desktop-first by design (matching Archify). Narrow screens receive safe containment and a bottom rail, not a separate mobile product.
