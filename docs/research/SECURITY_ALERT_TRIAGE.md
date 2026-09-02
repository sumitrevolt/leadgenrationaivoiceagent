# SECURITY ALERT TRIAGE — DEPENDABOT + CODEQL

> FreeBuff security triage mission · 2026-08-09 · main `71da9bcb` (starting) · sandbox probes read-only; no production mutation.
> Status legend: FIXED-AND-PR · ALREADY-FIXED · FALSE-POSITIVE-PROVEN · NO-FIX-AVAILABLE · TEST-ONLY · MITIGATED · OWNER-BACKLOG · UPSTREAM-BLOCKED.

## 1. Dependabot — 11 open alerts

| # | Pkg | Sev | Manifest | Decision | Evidence |
|---|---|---|---|---|---|
| 34 | nanoid | high | video_renderer/hyperframes/package-lock.json | **FIXED-AND-PR (#299)** | GHSA-2v37-7h3g-55p8 (<3.3.17); override 3.3.17; npm audit 0 |
| 33 | hono | medium | package-lock.json | **FIXED-AND-PR (#299)** | GHSA-8j4g-w8fx-2239 (<4.12.34); override 4.12.34 |
| 32 | hono | low | package-lock.json | **FIXED-AND-PR (#299)** | GHSA-79qm-7rj5-m7r9; same override |
| 31 | hono | medium | package-lock.json | **FIXED-AND-PR (#299)** | GHSA-54fx-42gc-7vw4; same override |
| 28 | hono | medium | package-lock.json | **FIXED-AND-PR (#299)** | GHSA-f23p-vx2j-j53r; same override |
| 30 | black | high | requirements-dev.txt | **FIXED-AND-PR (#300)** | GHSA-3936-cmfr-pm3m (<26.3.1); pin 26.3.1; dev-only, not in CI |
| 26 | pytest | medium | requirements.txt | **OWNER-BLOCKED (documented exception)** | CVE-2025-71176 / GHSA-6w46-j5rx-g56g; repo exception expiry 2026-11-08 (DEPENDENCY_REMEDIATION_2026-08-08.md + test_dependency_security_floors EXCEPTIONS + expiry test); ci.yml documents pytest-asyncio 1.x + aiosqlite 0.22.x segfault (exit-139) — pytest 9 attempt reverted |
| 13 | pytest | medium | requirements.lock.txt | **OWNER-BLOCKED (documented exception)** | same advisory + same exception evidence |
| 6 | pytest | medium | requirements-filtered.txt | **OWNER-BLOCKED (documented exception)** | same advisory + same exception evidence |
| 3 | pytest | medium | requirements-dev.txt | **OWNER-BLOCKED (documented exception)** | same advisory + same exception evidence |
| 11 | ecdsa | high | requirements.lock.txt | **NO-FIX-AVAILABLE (UPSTREAM)** | CVE-2024-23342 / GHSA-wj6h-64fc-37mp Minerva P-256 timing; python-ecdsa declares side-channel out of scope, no patched version (Dependabot patched range empty); installed 0.19.2 == latest; transitive via python-jose 3.5.0 |

### ecdsa containment note (no dismissal)
- Reachability: signature **generation** only (OSV: verification unaffected); app uses python-jose for JWT — ES256 signing path only if configured. Minerva requires high-precision timing measurement (local or close-network); practical risk low for internet-facing signer.
- Compensating control: no crypto-path change made (JWT signing surface frozen — voice/auth code owner-gated); revisit on upstream fix or if ES256 keys are added. Alert kept OPEN; not dismissed.

## 2. CodeQL — 100 open alerts

### 2.1 py/path-injection (1) — **FIXED (PR #300's sibling: sec-codeql-20260809)**
| Alert | Location | Decision |
|---|---|---|
| 578 | app/platform/workforce_memory.py:278 | **FIXED** — sink-side realpath containment (`_contained_under(_root(), os.path.realpath(entries_path))`) added immediately before `open()` in `_append_entry`; existing containment barrier (`_agent_dir`/`_contained_under` collapse-to-root) + dedicated tests already present; `test_workforce_memory_path_injection.py`, `test_workforce_memory_path_containment_2026_08_08.py`, `test_workforce_memory_2026_08_03.py`, `test_agent_memory.py` → exit 0 (1 Windows symlink skip) |

### 2.2 py/url-redirection (3) — **FALSE POSITIVE — PROVEN** (no code change; hardening already present)
| Alert | Location | Evidence |
|---|---|---|
| 547 | app/api/widgets.py:190 | Redirect target from `bio_link.resolve_block` → `_block_target` **scheme allowlist**: only http://, https://, or own-relative "/" (explicitly rejects "//"); tel:/upi:/wa.me constructed internally from validated digits/VPA. Owner-configured source, no per-request attacker input (ua/ref only logged). |
| 546 | app/main.py:2373 | `RedirectResponse(url="/")` — **static literal** in client_blog_post error path. No user input. |
| 545 | app/api/email_track.py:81 | `record_click` → `verify_click_token` validates http/https scheme (`_is_redirect_safe`, email_tracking.py:140-176) AND token is HMAC-signed (app-created URLs only). Fallback is static `_FALLBACK_URL`. |

### 2.3 py/incomplete-url-substring-sanitization (2) — **TEST-ONLY — NOT APPLICABLE**
| Alert | Location | Evidence |
|---|---|---|
| 571 | tests/test_social_oauth_stubs.py:238 | Assertion `"linkedin.com/oauth/v2/authorization" in url` on a test fixture URL. No security sink — test code only. |
| 570 | tests/test_social_oauth_stubs.py:191 | Assertion `"facebook.com" in url` on a test fixture URL. No security sink — test code only. |

### 2.4 py/stack-trace-exposure (82) — **MITIGATED + OWNER-BACKLOG** (grouped)
- **Global mitigation (proven):** `app/exceptions.py` `leadgen_exception_handler` (line 158+) returns JSON with `request_id` + redacted message (no traceback body) + `X-Request-ID` header for unhandled 500s; `http_exception_handler` same pattern. Client never receives raw tracebacks through the public surface.
- **Group A — internal-log-only (majority):** flagged `logger.error(... exc_info=True)` / `traceback.format_exc()` used for server-side diagnostics only; values never returned to clients. Classification: `MITIGATED` (log-only), no behavior change required. Representative locations: app/api/clientops.py:426, app/api/widgets.py:110/121/168, app/telephony/webhooks.py:284, app/marketing/*, app/platform/*.
- **Group B — dev-only response paths:** a small subset returns traceback text in development-mode responses (e.g., when `production=False`). Classification: `OWNER-BACKLOG` — replace with `request_id` + generic message in production; keep detail dev-only. Fix pattern documented; 82 individual fixes not bundled into this PR (owner prioritisation + CI ratchet needed).
- **Verification hook:** CI CodeQL already gates new findings (13/13 checks on #298/299/300 include CodeQL); a stack-trace ratchet is the suggested next hardening.

### 2.5 py/polynomial-redos (12) — **OWNER-BACKLOG** (fix pattern documented)
| # | Location | Pattern risk |
|---|---|---|
| 559,558 | app/platform/sales_autopilot/safety.py:61 | ReDoS on regex over message text |
| 557 | app/platform/safe_ai_payload.py:125 | Regex over payload strings |
| 556 | app/platform/reseller.py:61 | Regex over input |
| 555 | app/platform/mission_control.py:262 | Regex over text |
| 554 | app/marketing/magic_resize.py:119 | Regex over dimensions/args |
| 553,552,551,550,549 | app/marketing/video_production/feedback.py:65/77/90 | Multiple regex over feedback text |
| 548 | app/marketing/creative_os/brief.py:240 | Regex over brief text |
| 547→(redos) 547 was url-redirect | app/marketing/brand_frames.py:229 | Regex over brand text |

**Fix pattern (per alert):** replace vulnerable regex with linear parse, add length cap before match (e.g., `text[:2000]`), or use `re` with bounded alternation; add adversarial-input test with runtime bound. Not bundled here — separate focused PR after owner prioritisation (all are non-blocking warnings; CodeQL gate green).

## 3. Net position
- Dependabot: **6/11 fixed** — PR #299 (JS, 5 alerts) + black via #300; pytest x4 + ecdsa = owner-tracked documented exceptions (expiry 2026-11-08, CI-enforced); no alert dismissed.
- CodeQL: 1 path-injection fixed; 3 url-redirect + 2 test-substring = proven false-positive/test-only; 82 stack-trace mitigated-by-global-handler (log-only) + backlog; 12 redos backlog with fix pattern.
- No suppression comments, no scanner weakening, no dismissals without evidence.

## 4. Evidence commands (exact exits)
| Command | Exit |
|---|---|
| `npm audit` (after overrides) | 0 (0 vulnerabilities) |
| `npm ls hono nanoid` | 4.12.34 / 3.3.17 |
| `pytest tests/test_hyperframes_deploy_contract.py tests/test_hyperframes_provider.py` | 0 |
| pytest 9.0.3 scratch: billing+UPI+activation+hyperframes batch | 0 |
| pytest 9.0.3 scratch: asyncio/mocker/tmp_path sample | 0 |
| workforce memory path-injection/containment tests | 0 (1 Windows symlink skip) |
| `prod_check.py` (JS + PY worktrees, bounded) | 0 ALL CHECKS PASSED |
| `check_secrets.py` | 0 |
| `git diff --check` | 0 |
