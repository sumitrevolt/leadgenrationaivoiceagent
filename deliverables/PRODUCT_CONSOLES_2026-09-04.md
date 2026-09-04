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
- `prod_check.py` — **ALL CHECKS PASSED**, 1380 routes, 58 pages 0 gaps, `app.main` imports OK.
- `scripts/sync_api_docs.py` re-run — `docs/API.md` in sync (1402 ops).
- JS: `node --check` clean on the shared runtime; both inline page scripts parse; all `getElementById` references resolve against DOM ids.

### Two real defects found and fixed during verification

1. **`PUT /api/consoles/business-config` with `{}` returned 200.** `model_dump()` always carried the `language` and `timezone` defaults, which made the "no fields to save" 400 unreachable and silently overwrote stored values on a partial save. Fixed with `model_dump(exclude_unset=True)`; a partial save now persists only the fields actually sent.
2. **The URL scheme check was unreachable.** `Field(min_length=8)` rejected the 7-character test input with 422 before the handler ran. This was a test defect, not a code defect — the test now uses `ftp://example.com/page` to exercise the handler's 400 path, and keeps a separate 422 length case.

## Known limitations

- Activation persists configuration and evaluates real gates; it does not itself enqueue calls. Wiring automation to the telephony worker is the natural next step.
- Channel availability depends on platform app review (Meta Advanced Access, LinkedIn partner access, GBP API). Slots that are not approved render as "Not available" with the specific owner action — this is honest, not broken.
- Consoles are desktop-first by design (matching Archify). Narrow screens receive safe containment and a bottom rail, not a separate mobile product.
