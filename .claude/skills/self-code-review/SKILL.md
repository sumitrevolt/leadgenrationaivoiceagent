---
name: self-code-review
description: Ship se pehle solo-dev multi-pass review — bug-hunt, security, signature-drift, hot-path, test-gap — 5 alag "reviewer hats" ek hi session me. Use when user says "review karo", "ship se pehle check", "commit kar du?", "/ship se pehle", ya koi bhi batch deploy hone wala ho. Diff pe chalao: `git diff main` ya uncommitted changes.
---

# Self Code Review (5 passes, ship se pehle)

Solo dev = koi PR reviewer nahi → khud ke code ko 5 ALAG perspectives se padho, har pass me SIRF us lens se. Diff lo (`git diff` / changed files list) aur har pass ka output: file:line + issue + fix. Critical/High pehle fix, fir ship.

## Pass 1: Bug Hunter 🐛
- **Fail-open vs fail-closed DELIBERATE hai?** Project contract: compliance/DND/TRAI = fail-CLOSED (block on doubt); rate-limit/billing-gate/tenant = fail-OPEN (never block business). Naya code kis side hai — soch ke likha ya accident?
- Never-raise contract: integration/scheduler/hook code me top-level try/except + safe default? (har engine ka pattern)
- Async bugs: `async for` vs `async with get_async_session` (lead_scoring bug) · SQLAlchemy `not Column` vs `.is_(False)` (scraping bug) · `os.kill(pid,0)` Windows pe CTRL_C (scheduler lesson).
- Edge: empty list, None phone/email, LLM garbage-JSON parse-fail path, dedupe keys.

## Pass 2: Security Auditor 🔒
- **Public endpoint = `rate_limit(...)` dependency hai?** (ratelimit.py pattern, ai/command lesson — open LLM endpoint = abuse surface).
- Admin action = `require_admin` / customer = `require_customer`? Anonymous fallback to nahi (data.py "demo-client" hole lesson — prod me 401).
- File serve = **regex-lock** path (`/ai-img-file/{name}` pattern) — kabhi raw user path join nahi (traversal).
- Secrets sirf `.env` — code/commit/log/CLAUDE.md me kabhi nahi. Webhook = signature-verify (Twilio/Exotel/HMAC pattern).

## Pass 3: Contracts/Signature-drift 📜
- `free_ai.chat(system, messages)` REAL signature — tuple/str drift = silent static-fallback (growth_optimizer bug). Har LLM call-site check.
- Sync fn ko await / async ko sync call? Response shape change = `/api/public/*` backward-compat toot raha? Page-route naya = deploy note "HARD RELOAD".
- packages.py / niches.py = single source of truth — koi naya hardcoded price/plan/niche list to nahi?

## Pass 4: Hot-path 🔥
- **Endpoint/voice-path me sync ML/KB/SDK?** = event-loop starve, site down (widget-chat lesson). Fix: `asyncio.wait_for(asyncio.to_thread(fn), 10-25s)`.
- Scheduler me naya job heavy hai? = gated + worker me (boot pe fire = prod-down qa lesson). Unbounded loop/store? (jsonl auto-trim pattern).

## Pass 5: Test-coverage gap 🧪
- Har naya module ka test file hai? Flag-OFF=zero-change test? Contract assert (price/shape)? Parse-fail/fallback path tested? Network test me timeout marker?
- Final: `python scripts/prod_check.py` + `scripts\run_tests.bat` (pytest_run.log Read) + frontend touch hua to `python scripts/check_html_js.py`.

Output format: `## Critical (must fix)` / `## High` / `## Consider` — fir Critical+High fix karke dobara sirf failed passes re-run. Ship = `leadgen-ops`.

Adapted from NeoLabHQ/context-engineering-kit `review` plugin (multi-agent review → solo-dev passes) (via VoltAgent/awesome-agent-skills).
