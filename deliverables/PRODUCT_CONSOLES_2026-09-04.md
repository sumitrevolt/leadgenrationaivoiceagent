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

## Making activation real (third pass)

The consoles originally **only saved configuration** — neither activation did
anything. That is inert-by-default, which this project classifies as a defect
rather than a working feature. Research established both execution paths already
existed, so nothing was rebuilt.

### Marketing launch now drives the real pipeline

A complete generate → approve → publish pipeline already exists in
`app/social_engine/`. The launch endpoint previously wrote only to its own
`console_configs.jsonl`, which **nothing downstream reads** — a tenant could be
shown "launched" while the engine generated nothing.

`marketing_launch` now writes through to `app/social_engine/client_config`,
because cadence and `approval_mode` there are what `auto_content._cadence_due`
and the hands-free publish path actually honour:

- **Start** → `channels`, `cadence`, `approval_mode="auto"`, then
  `auto_content.seed_client_content()` so the tenant sees a Day-1 packet now
  rather than at the 07:00 daily pass.
- **Stop** → `cadence="off"` (the engine's real stop signal) *and*
  `approval_mode="draft"` so nothing can publish even mid-batch.

Channel selection is filtered to what is **both** healthy here and a real
downstream content target. `x` is a connectable OAuth account but not a publish
target (`client_config._VALID_CHANNELS`), and `whatsapp` is 1-to-1 owner
delivery — accepting either would have been a silent no-op. Rejected channels
are returned in `channels_dropped` rather than discarded quietly.

Two platform-level master gates — `SOCIAL_ENGINE` and `SOCIAL_PREFS_HONOR` — are
both unset in this environment. Rather than imply a green switch that posts
nothing, the response reports `publishing_armed: false` with the specific
`owner_actions` needed. Configuration is genuinely saved; only the final
publishing step is gated.

Locked by `tests/test_console_marketing_launch.py` (11 checks), including that a
blocked launch writes nothing at all, and that re-activation does not re-seed.

### Voice automation: researched, deliberately not yet wired

Mapping the call path surfaced a trap worth recording. The canonical entry point
`start_stream_call` (`app/api/telephony_vobiz.py:275`) **bypasses
`app/telephony/voice_launch.py` entirely** — no daily cap, session cap,
concurrency limit, kill switch or circuit breaker. All four existing callers
share this gap. Wiring console automation straight to it would have shipped an
uncapped dialer with a `max_calls_per_day` field that decorates rather than
governs. Also missing: no `template_id` or `voice_role` reaches a live call, so
template selection cannot yet change call behaviour; and only 2 of the 8 event
slots have real hook points (`lead_created` live, `inbound_missed` flag-gated),
with 3 partial and 3 from scratch — `inbound_answered` among them, which needs
inbound-DID streaming that does not exist.

Left unimplemented rather than half-wired. See Known limitations.

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
- `prod_check.py` — **ALL CHECKS PASSED**, 1382 routes (1381 + the governed test-call route), 58 pages 0 gaps, `app.main` imports OK, no duplicate (method, path) collisions, 0 orphans in the explorer graph (362 nodes, 98/98 engine coverage).
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

## Checkpoint 4 — making the voice product demo-able

The marketing product could publish (behind two env gates). The voice product
could not dial at all: the console saved automation config, but nothing consumed
it, and the shared dial helper bypassed every safety gate. This checkpoint closes
that.

### The problem

`start_stream_call` (`app/api/telephony_vobiz.py:275`) is the canonical dial
helper used by the campaign loop and four internal callers. Those callers enforce
the launch gates themselves, so the helper enforces **none**: no daily cap, no
per-tenant cap, no kill switch, no circuit breaker, no lead eligibility. A console
button wired straight to it would have been a path around all of them — and the
tenant-facing `max_calls_per_day` (default 50) was stored and read by nothing.

### What was built

- **Per-tenant quota** in `app/telephony/voice_launch.py`: `tenant_cap()`,
  `reserve_tenant_slot()`, `release_tenant_slot()`. A separate counter from the
  campaign quota, so one tenant's console test calls cannot consume the shared
  allowance. `tenant_cap` clamps to the **same ceiling as the campaign cap** —
  deliberate, because a tenant-supplied `max_calls_per_day` (the console accepts
  up to 5000) must never raise a spend or compliance limit.
- **`release_tenant_slot` exists for a non-obvious reason.** The route reserves
  *before* dialling so the cap is always genuinely exercised — but a dry run dials
  nothing. Without the rollback, a tenant who pressed "test call" a few times with
  the default `dry_run=True` would exhaust their daily quota without a single call
  ever ringing.
- **A `template_id` / `voice_role` rail** threaded through `_answer_stream_qs`,
  `start_stream_call`, `_store_pending` and the signed answer-stream handler
  (`telephony_vobiz.py:469-486` — the path that recovers from a lost pending
  entry). `vobiz_stream.py` reads `template_id` into the session.
- **`POST /api/consoles/automation/test-call`** — gates run in a fixed order and
  stop at the first failure: phone → kill switch → circuit breaker → tenant cap →
  per-lead eligibility → dial.

### The honesty contract (the part that matters)

`dry_run` defaults to **True**. In that mode no call is placed, and the response
says so in plain words. `dialed` is the flag that means "we rang the phone";
`placed=True` alone means only "the governed chain completed and the answer_url
was built". Conflating the two would be exactly the green light that means
nothing, so they are separate fields and the UI keys off `dialed`.

Two further choices worth recording:

- **An invalid phone is a 400, not a silent 200.** Consistent with the rest of the
  file (`save_automation` raises 400 on an unknown template, `template_detail`
  raises 404). The project's never-500 rule is about *server* errors, not
  validation.
- **Having no template is a warning, not a blocker and not a silent fallback.**
  The call runs the generic telecaller and says so in `warnings[]`. Silently
  substituting `inbound_faq` would be the hidden-fallback pattern this codebase
  refuses.

### Defects found while reviewing this checkpoint

1. **A dry run that failed to build reported `reason: ""`.** With Vobiz
   unconfigured, `start_stream_call` returns `placed=False`, but the reason was
   blanked by `dry` alone — so the payload reported a clean run next to a cheerful
   DRY RUN note. Fixed: `"" if (dialed or (dry and placed)) else (...)`.
2. **Gate-blocked responses had a different shape than every other path.**
   `_fail()` omitted `dialed`, `voice_role`, `niche`, `knowledge_chunks` and
   `warnings` — so a consumer reading `r["dialed"]` got a `KeyError` precisely on
   the blocked paths, which are the ones a tenant hits most. Fixed.
3. **Three unclosed `<div>` inside `<header>`** across both consoles
   (`voice_console.html` 264, 333; `marketing_console.html` 341). Browsers
   auto-close these, so nothing looked wrong — found by walking a tag stack with
   `html.parser`, not by eye.

### A correction worth keeping on record

An earlier claim in this session that all 11 console mutation endpoints were
broken by a missing `Content-Type` was **wrong** and is withdrawn. It came from
reading `frontend/archify_console.js`, which is **not loaded by either console** —
both HTML files inline their own `api()` (which sets the header correctly). The
probe proved only that the *router* rejects `text/plain`, which is correct
behaviour, not a frontend defect. The related real finding stands: the shared
`archify_console.js` is orphaned, so the 401 redirect added to it is dead code.

### Verification

`79 passed` — 27 voice governance (every gate blocks without dialling; `dialed`
semantics; dry-run slot rollback; full response shape on blocked paths), 11
marketing launch, 35 impersonation portal target, 6 impersonation.
`prod_check.py` ALL CHECKS PASSED (1382 routes, 58 pages 0 gaps, 0 orphans).
`ruff check` clean on every touched file; the 28 remaining repo-wide ruff errors
are pre-existing in files this work never touched.

Not browser-tested: the console JS is verified by `node --check` and by code
inspection against the response contract, not by a real browser session.

### End-to-end proof against the real app

Unit tests with `require_customer` overridden prove the handlers, not the wiring.
`_scratch/e2e_consoles.py` closes that gap: it mints a **real customer JWT** for a
**real tenant** out of `clients_store` and drives every console route through the
full `app.main` stack (1382 routes, middleware and all) — **46/46 passing**.

With the kill switch disengaged, the governed chain completes all six steps in
order — `phone → admin_kill → circuit → tenant_cap → eligibility → dial` — with
`dialed=False`, the tenant slot reserved and then released, and the note reading
"DRY RUN — NO CALL WAS PLACED".

One trap worth recording: the in-memory Redis test double **must** implement
`exists()` and `pipeline()`. `require_customer` reads the logout blacklist with
`exists()` and is FAIL-CLOSED, so an incomplete fake makes every authenticated
route return 503. That 503 is the production gate doing its job — it cost an hour
to diagnose and is not a code defect.

## ⚠️ Go-live gate state — both products are currently inert

This is the most operationally important thing in this document.

| Gate | State | To activate |
|---|---|---|
| Voice admin kill switch | **ENGAGED** (`FILE/MISSING`) | `VOICE_LAUNCH_KILL=0`, or write `{"kill": false}` to `data/voice_launch_kill.json` |
| Voice campaign loop | **OFF** | `VOICE_LAUNCH_CAMPAIGN=1` (campaign dialling only — a single console test call does not need it) |
| Vobiz telephony provider | **Configured** | ready, no action |
| `SOCIAL_ENGINE` | **OFF** | `SOCIAL_ENGINE=1` |
| `SOCIAL_PREFS_HONOR` | **OFF** | `SOCIAL_PREFS_HONOR=1` |

**Vobiz is configured and the caps are sane** (`daily_cap=100`, `tenant_cap=25`) —
the only thing standing between the voice console and a real call is the kill
switch. That switch is fail-safe by design: a missing file, an unreadable file, a
malformed file, a wrong-typed value, a path inside the checkout — every one of
those **engages** the kill rather than permitting dialling. `{"kill": false}` is
checked with a strict `isinstance(..., bool)`, so `{"kill": 0}` and
`{"kill": "false"}` are rejected and engage.

The consequence is blunt: **until three environment variables are flipped, neither
product can do anything, and any demo will correctly show a blocked console.** The
console reports this as "Blocked at 'admin_kill'" rather than failing silently —
which is the whole point of building it this way.

## Known limitations

- **Voice automation still does not place calls.** It persists configuration and
  evaluates real gates, and nothing more. Wiring it requires, in order: routing
  through `voice_launch` governance so `max_calls_per_day` is enforced (currently
  unenforced — the field defaults to 50 and is read nowhere), then threading
  `template_id` / `voice_role` through `_answer_stream_qs` → WS query →
  `VobizStreamSession` so template selection affects a live call. Only then is an
  event dispatcher worth building. Of the 8 event slots, 2 have hook points, 3
  are partial, and 3 need from-scratch work (`inbound_answered` requires
  inbound-DID streaming that does not exist).
- **Marketing publishing is gated at platform level.** `SOCIAL_ENGINE` and
  `SOCIAL_PREFS_HONOR` are both unset, so generated content will not publish
  until the owner enables them. Reported honestly to the tenant rather than
  hidden. Content generation itself is unaffected.
- **No media hosting is wired.** Meta, GBP and LinkedIn publishing need a
  publicly reachable `media_url`, but `enqueue_publish` is called without one, so
  image and video posts will fail validation. Text posts, Postiz and WhatsApp
  work today.
- **The YouTube provider is a stub** (`providers.py:319` returns
  "activation pe wire hoga"), and **GBP and X OAuth are not implemented** — they
  surface as "not wired" with the specific owner action rather than as connectable.
- **`app/tasks/daily_social_post.py` is dead code** — it imports from
  `app.integrations.postiz`, which imports `app.integrations.base`, a module that
  does not exist. Three beat entries (`staff-daily-social-post-{morning,midday,evening}`)
  point at it and will fail on every tick. Pre-existing; not touched. Candidate
  for deletion or repointing at `social_engine.process_queue`.
- **`posting_days` and `posting_times` are persisted but read by nothing.** Cadence
  is approximated by two fixed daily passes (07:00, 15:00), not a per-tenant
  schedule.
- Channel availability depends on platform app review (Meta Advanced Access, LinkedIn partner access, GBP API). Slots that are not approved render as "Not available" with the specific owner action — this is honest, not broken.
- Consoles are desktop-first by design (matching Archify). Narrow screens receive safe containment and a bottom rail, not a separate mobile product.
- **A selected call template is carried but not yet consumed by the brain.** `template_id` rides the whole rail into `VobizStreamSession.template_id`, but `TelecallerBrain.__init__` has no template parameter, so it cannot be threaded further without raising `TypeError` on every live call. The session field is the honest ceiling today; wiring it into the brain is a separate, deliberate change. Reported as a gap rather than hidden behind a partial implementation.
- **`frontend/archify_console.js` is orphaned.** It is served at `/static/archify_console.js` but neither console loads it — only `archify_console.css` is linked. Both pages inline their own runtime. Consequence: the 401 session-loss redirect added to that file has never executed. Either the pages should load it and drop the inline duplicate, or the file should be deleted; leaving it invites exactly the wrong-file misread made during this session.
- **The voice console's automation is configured, not scheduled.** `test-call` is governed and real. The eight event bindings (lead created, missed call, appointment, …) and the per-tenant schedule are persisted and evaluated against real evidence, but no beat entry dispatches them yet — that is the next unit of work, and it needs the `staff-*` naming rule from `worker.py:877-880`.

## Checkpoint 5 — WhatsApp pending-drafts inbox (BLK-11), 2026-09-04

**Problem.** Every gate-denied WhatsApp send built a ban-safe `wa.me` link and
then threw it away: `_record_block()` counted reasons in an in-memory dict that
died on restart. ~1,829 blocked intents on 2026-09-04 produced a counter and
nothing a human could act on — including the ready ₹19,990 Jiya upsell ask.

**Fix.** The would-send is now persisted to a per-runtime jsonl store
(`whatsapp.pending_drafts`, resolved via `runtime_data_authority`, locked with
`file_lock` + atomic replace) and exposed as an admin inbox:

- `GET /api/wa/drafts` — pending drafts, newest first, with the gate `reason`
- `POST /api/wa/drafts/{id}/sent` — idempotent mark-sent (human tapped the link)
- `POST /api/wa/drafts/{id}/dismiss` — drop from the queue
- `GET /api/wa/status` — now carries `pending_drafts` + `pending_drafts_cap`

**Design guarantees (all test-proven):**

1. **The send path cannot break.** `auto_send_blocked` builds its return dict
   first and persists after, wrapped — a dead store leaves the payload
   byte-for-byte identical. The five-key caller contract (`error`, `status`,
   `mode`, `would_send`, `link`) is pinned by test.
2. **No gate was touched.** `send_permitted`, `auto_send_allowed`,
   `allowlist_permits`, `opt_out_permits` are unchanged (diff-verified hunk by
   hunk). This inbox transmits nothing; a human taps the link in their own
   WhatsApp.
3. **Dedupe by (to, sha256(message)[:16])** with reason-refresh — a repeat
   blocked as `opted_out` updates the row so the operator sees the LATEST
   reason, never a stale `auto_send_disabled` one.
4. **Cap-bounded** (`WHATSAPP_DRAFT_CAP`, default 500, max 5000) — the hourly
   onboarding job alone cannot grow the file unbounded.
5. **A draft blocked as `opted_out`/`suppressed` must not be sent by hand
   either** — surfaced in the route docstring; the `reason` field is the
   operator's safety check.

**Verification.** 22 new tests (corrupt store, unwritable store, idempotent
resolve, cap, dedupe, JWT-gated routes). Full re-run: **101/101 pass** (22
WhatsApp + 79 console regression). `prod_check.py` → **ALL CHECKS PASSED**,
1385 routes, API.md in sync (1406 ops). Ruff clean on all three in-scope files.

**Known limitation.** `dismiss` deletes the row rather than archiving it, so a
dismissed draft leaves no audit trail; and drafts persist only on the node that
wrote them (jsonl store, same as every other store in this repo — no cross-node
replication).
