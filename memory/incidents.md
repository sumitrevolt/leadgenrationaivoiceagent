# Incidents — postmortems (append new at bottom)

Schema per entry: `[DATE] What broke | Root cause | Fix | Prevention rule added`

[2026-07-12] **Rohan prospecting returned irrelevant railway/helpline/infrastructure records and empty Google runs.** Root cause: a configured Google key forced Google-only mode even when Places returned empty/denied results; OSM fallback was only selected when no key existed, and sync Overpass urllib ran inside the async job. The pipeline also lacked Places business-status/type capture and historical quality re-check at listing/outreach. Fix: per-query OSM fallback off-loop, Places type/status fields, hard non-SMB/junk-title gate (IRCTC/railway/helpline/public-service), source lineage, and `is_quality_approved()` filtering before listing/email candidates. Prevention: every scraper source must preserve evidence/type/status and re-run the quality gate immediately before any outreach action; review capped samples before enabling send.

[2026-05/06] 3× production downs (site freeze/502) | KB/ML load (fastembed/torch) running ON the event loop inside public endpoints — one slow model load froze all requests | Off-loop `asyncio.to_thread` + hard deadline + disable-switch | RULE: har ML asset = image-bake + off-loop load + deadline + kill-switch; public endpoint me KB/ML = thread + hard timeout.

[2026-06-XX] Restart-storm prod-down | App restart during a heavy daily job's window → job re-fired every boot, stacking load | boot-grace: window active AT boot = skip this boot | RULE: every heavy scheduled job checks boot-grace.

[2026-06-XX] CLAUDE.md mid-file corruption | Sandbox bash append on a STALE mount | Rewrote from git; memory edits ab SIRF Windows file-tools (Edit/Write) | RULE: kabhi bash-append on memory files; Windows = source of truth.

[2026-06-XX] Windows dev: processes dying mysteriously | `os.kill(pid, 0)` on Windows sends CTRL_C (not a liveness probe) | `_pid_alive` via ctypes OpenProcess | RULE: POSIX idioms Windows pe verify karo.

[2026-06-2X] Admin dashboard all-zeros + latent breakage | Godfile split left 37 latent NameErrors (e.g. missing `timezone` import) — silent until route hit | ruff F821 sweep + fixes + test (db2b0a5) | RULE: refactor ke baad `ruff check` F821 mandatory; import-smoke != route-smoke.

[2026-06-2X] Customer Bill/Plan pages 500 | Status columns String-used-as-enum mismatch vs code enums | `Enum(native_enum=False)` columns | RULE: real-DB E2E test catches what mocked tests miss.

[2026-06-2X] Customer dashboard blank page | JS TDZ crash — `let` declared late while parallel Cursor edit moved usage earlier | Hoisted declarations | RULE: parallel edits on same file = git diff before commit; Playwright pageerror for blank-page debug.

[2026-06-2X] Concurrent Docker build race on VPS | Timed-out SSH ≠ killed remote build; retry started a 2nd build | setsid detached builds + check running builds first | RULE: before build, `ps aux | grep docker build`.

[2026-06-2X] Voice agent silent after 2-3 turns (dead-air) | Unbounded await inside `_on_utterance` (one slow provider = forever hang) | Bound EVERY await + THINK watchdog | RULE: voice path me koi unbounded await nahi (incl. EdgeTTS `_TTS_TIMEOUT_S`).

[2026-06-29] Web-call TTS crawling slow | Host had hardcoded +8% rate overriding config | Web TTS +18%→+26%, removed hardcode | RULE: prosody knobs env-driven only, no inline literals.

[2026-07-01] /app/office 90s timeout | Duplicate `_collect_live_stats` call, unbounded + serial | Timeout-bounded + parallelized (90s→8.3s) | RULE: dashboard aggregators = parallel + per-source timeout.

[2026-07-03] Phone agent "deaf" (user_turns=0) | `USE_SILERO_VAD=1` — 64ms rolling-window misclassified real caller speech as silence; Vobiz was WRONGLY suspected first | `.env USE_SILERO_VAD=0` + restart (user_turns 0→12) | RULE: don't re-suspect Vobiz delivery; Silero re-enable needs window-size fix + proof.

[2026-07-03] Close-signals never fired on live phone calls | Stream path (`reply_stream_sentences`) lacked the guards `reply()` had; also outbound calls had `caller_phone=None` so deal-writes silently no-op'd | Ported guards (2da6239) + threaded `lead_phone` (935c337) | RULE: every reply() guard mirrored in stream path; no silent no-op writes — log-and-alert.

[2026-07-03] Office map rendered 0x0 + approvals ✓/✗ silently failing | CSS collapse (container hidden at boot) + 18s snapshot-cache never invalidated after mutation | Pro-default restored + cache invalidation on mutate | RULE: cache TTL must EXCEED poll interval; mutations must bust caches.

[2026-07-05] platform_dial marked IVR/bots as "interested" (7 fake leads) + real call-money burn | No bot/IVR detection — any completed call with keywords counted; agent talked to answering machines | HARD OFF 3-layer kill (see ADR-019) | RULE: outbound autonomy needs min-user-turns gate + allowlist testing before ramp; human-verify recordings before trusting agent-labeled outcomes.

[2026-07-05] Prospect store "ready" pool polluted with SERP junk | Lead-harvester websearch path stored search-result PAGE TITLES as businesses ("Contact Us | HDFC...", bank helplines as phones) — ~94 junk records, whole home_loans niche garbage; explains WHY platform_dial dialed IVRs and marked them "interested" | Sprint extraction filtered by GMB-discriminator (rating/reviews_count present + valid 6-9 mobile) → 354 real SMBs; purge + harvester gating parked in backlog | RULE: prospect ingest must validate (GMB fields OR valid mobile) + brand/junk-title filter; dial lists ONLY from validated records.

[2026-07-05] Mobile customers COULD NOT LOGIN — Login link invisible on phone | index.html ≤720px media query had `.nav-cta .login{display:none}` + hamburger menu me Login item tha hi nahi; demo.html me Login link kahin nahi (header/footer dono) — mobile journey me login entry-point ZERO | Fix: mobile header me Login = bordered chip (header CTA hidden, hero me same CTA hai) + hamburger menu me Login item + demo.html header/footer me Login link; pricing.html already OK | RULE: har public page ke mobile viewport me Login reachable hona chahiye — naya responsive hide rule likhte waqt check karo ki wo cheez menu me available hai ya nahi.

[2026-06-2X] Security tests gave false confidence | Batch-1 security tests ran against mocked-OPEN auth | Fixed `tests/security/conftest.py` to exercise real auth (a2d2464) | RULE: security tests must run against real auth wiring, never mocks.

[2026-07-06] Full-suite me 8 stale tests deployed behaviour ke against assert kar rahe the (W1.5 fail-closed slot, W1.6 lazy URL-accessors, W2.1 caption validator, SSRF guard, CATCH-ALL cooldown, CLOSE_DETECT short-circuit) | Behaviour-change ship karte waqt sirf CHANGED-file tests chale the; full pytest CI non-blocking hai isliye drift silently jama hota gaya | Sab 8 test-side fix (code sahi tha) — dono full-suite drift-sweeps 2026-07-06 | RULE: koi bhi behaviour-change ship karo to grep -r "<old-symbol/assumption>" tests/ chala ke us behaviour ke SAB asserting tests update karo; full-suite sweep har wave ke end pe.

[2026-07-10] Live `/api/upi/submit` returned 404 while `/health` stayed production-healthy | Commit `2f5c40e` hardened UPI submit auth but accidentally deleted adjacent `from pydantic import BaseModel`; `UpiSubmitIn(BaseModel)` then raised during guarded router import, so the app booted without UPI submission routes | Restored the single import locally; one-off import RED→GREEN and `prod_check.py` now sees all routes. NOT DEPLOYED in this session; live GET remains 404 until an explicitly authorized deploy | RULE: guarded revenue-router imports need effective post-startup route checks, and import edits must preserve adjacent model dependencies.

[2026-07-10] `prod_check.py` reported 632 false missing-route/wiring errors under locked FastAPI 0.139 | FastAPI now stores included routers lazily as `_IncludedRouter`; startup/prod/deep-wiring checks inspected only direct `.path` attributes. A previous crash-suppression commit skipped lazy objects instead of expanding them; included WebSockets also surfaced an empty `RouteContext.path` edge | Added `iter_effective_routes()` using FastAPI's public `iter_route_contexts`, with WebSocket normalization to its resolved Starlette route and eager-version fallback; wired startup sweep, prod gate, and deep wiring audit. Gate moved 85→1064 routes and 628→0 wiring gaps | RULE: route truth must inspect effective route contexts, not raw `app.routes`, on lazy-router FastAPI versions.
[2026-07-11] **Self-improve requeue chain died on sub-second ETA skew.** Production evidence: a successful tick enqueued its successor for 180s and then recorded `tick_next_allowed`; because the Redis timestamp was written milliseconds after Celery calculated ETA, the successor arrived ~20ms before `next_allowed`, `acquire_tick_slot()` returned empty, and the `tick_slot` skip path correctly did not requeue duplicates—accidentally killing the only chain until the 10/20-minute reviver. Fix: allow a bounded 2s ETA skew before the far-future guard, while the existing Redis NX running-lock remains the duplicate-execution authority. TDD reproduced 0.5s early arrival RED then GREEN; far-future and duplicate guards remain green. Production deploy must verify successive natural ticks rather than only one manual tick.
