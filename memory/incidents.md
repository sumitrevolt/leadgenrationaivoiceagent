# Incidents — postmortems (append new at bottom)

Schema per entry: `[DATE] What broke | Root cause | Fix | Prevention rule added`

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

[2026-06-2X] Security tests gave false confidence | Batch-1 security tests ran against mocked-OPEN auth | Fixed `tests/security/conftest.py` to exercise real auth (a2d2464) | RULE: security tests must run against real auth wiring, never mocks.
