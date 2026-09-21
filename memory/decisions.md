# Architecture Decision Records (ADR)

> Append-only log. New decisions go at the TOP. Never edit past entries.

---

## ADR-198: One Telegram token, one poller — lease + owner-role coordination, and token VALIDITY instead of token PRESENCE (2026-09-21)

**Status**: ACCEPTED (CODE-PRESENT + TEST-PROVEN locally; rollout is an OWNER gate — see "Owner actions")
**Context**: A live read-only probe (new `scripts/telegram_verify_setup.py`) contradicted every Telegram claim in the repo. (a) The Jarvis token is AUTHENTICATED, but a non-consuming `getUpdates(allowed_updates=[])` probe returned HTTP 409 — the **Hermes gateway** (`hermes_cli.main --profile pilot gateway run`) is the real polling owner, so this repo's runner could never receive a single owner command. (b) `TELEGRAM_NOTIFY_BOT_TOKEN` (and `.env`'s `TELEGRAM_BOT_TOKEN`) are **401 Unauthorized** — yet `len(token) >= 20` made both look "configured", and `telegram_coordinator.dispatch_egress_alert()` used exactly one token with no fallback, so every P0 owner alert on that path was silently dropped (asymmetry: `app/utils/telegram_egress.py` already had a 401-blacklist fallback chain). (c) 0/13 spec groups are reachable by the Jarvis bot (`chat not found`), and the three coordination groups the owner asked for ship with an empty `chat_id` — the Bot API cannot create a group for the owner, so they had never existed.
**Decision**:
1. **Coordination is a first-class primitive, not a comment.** `TELEGRAM_INGRESS_OWNER=auto|local|vps|hermes|off` names the single consumer; otherwise a polling lease decides (Redis `leadgen:telegram:poll_lease:<scope>` cross-host, else `data/telegram_poll_lease.json` cross-process, TTL 120s, stale takeover). `should_poll()` is the one gate; a non-owner role never even claims the lease.
2. **A 409 is evidence, not noise.** On a real conflict the runner releases its own lease, enters standby with 10→60s backoff and records `conflict_count`/`external_conflict_until`; it never fights for the token and never advertises itself as holder while not polling. Invalid token = refuse to start (no 401 spin). The lease is always released in a `finally`.
3. **PRESENT != AUTHENTICATED.** `validate_bot_token()` (getMe, cached, SHA-256 fingerprint only) gates polling; egress uses the notify→legacy→jarvis candidate chain with per-process 401 blacklisting and reports the `via` slot. Never log, print, prompt or commit a token value.
4. **Cross-process dedupe**: in-process cache plus a best-effort Redis `SETNX` key (TTL 1h) so local polling + VPS runner + webhook cannot execute one update twice. Redis down = fail-open to the in-process cache.
5. **Group wiring is tooling, not hand-editing**: `scripts/telegram_wire_coordination_groups.py` (scope-qualified refs `marketing.announcements`; bare keys that exist in both products are refused as ambiguous), `--set`/`--create-topics`/`--verify`, timestamped `.bak` + YAML round-trip assertion on every write.
6. **VPS install is fail-closed**: `scripts/setup_telegram_vps.sh` detects the interpreter, refuses to install on a CRITICAL credential preflight, and derives a telegram-only `EnvironmentFile` (0600) instead of pointing systemd at the whole `.env`.
**Consequences**: Local, VPS and Hermes can now coexist honestly, and "Telegram is wired" is a verifier output rather than a doc claim. Required coordination groups stay RED (exit 1) until the owner creates them — deliberately: a green-looking dashboard over unwired groups is the failure this ADR forbids.
**Owner actions (only these):** (1) re-issue the Notify bot token in BotFather at `TELEGRAM_NOTIFY_BOT_TOKEN`; (2) create + wire the three coordination groups (runbook in `docs/TELEGRAM_DUAL_BOT_SETUP.md` §4); (3) choose the single ingress owner (`TELEGRAM_INGRESS_OWNER`) — Hermes keeps it today.
**Reference**: `docs/TELEGRAM_DUAL_BOT_SETUP.md` · `app/platform/telegram_coordinator.py` · `scripts/telegram_verify_setup.py` · tests `tests/test_telegram_dual_bot.py` (21) + `tests/test_telegram_wiring_tool.py` (10)

---

## ADR-197: Probe the thing you report — retired the TypeSafe env-refresh placebo, gated dead observability (2026-09-20)

**Status**: ACCEPTED (code fixed locally; web-tier rollout topology remains an OWNER gate)
**Context**: Re-verifying the U06 P0 candidates against `main` at `2d1245c6` found that "fixed" and "reported" had diverged in three places. `scripts/refresh_typesafe_env.sh` printed a 14-char prefix of the live `TYPESAFE_API_KEY`, pinned `APP_VERSION=404e5309` (already stale — running it recreates the worker on a two-week-old image), masked compose's exit with `| tail -6`, and — its actual job — could not refresh the app's env at all: `app` is a container whose env is fixed at create time, and it recreated neither that container nor a working systemd unit (the unit is `disabled` and fails every exec with 203/EXEC, `NRestarts=5583`). Separately, `/api/v1/typesafe/status` counted a consumer by importing `get_telegram_typesafe_router`, a symbol that exists nowhere; the `ImportError` was swallowed by `except Exception: pass`, so the branch never ran and never logged.
**Decision**:
1. Retire `scripts/refresh_typesafe_env.sh` to a stub that refuses (exit 1, names the four defects, points at `scripts/check_typesafe.sh` for read-only state and `scripts/deploy_vps.sh` for releases). Do not "fix" a placebo by making it work — nothing about env refresh belongs in a script that also re-tags images.
2. Credential state is reported as `PRESENT / ABSENT / INVALID / ROTATION_REQUIRED` plus a non-reversible sha256 fingerprint. Never a prefix, never in a log. The committed prefix (since `0ce08f2e`) makes the key `ROTATION_REQUIRED` — an owner-authorized secret workflow, not a code change.
3. Every consumer count must be gated on that consumer's own `client.enabled`, and a `try:` that can swallow a miscount must log. New static guard resolves every `from app...` import in `typesafe_routes.py`, so "reference a symbol that isn't there" fails at test time instead of silently disabling a branch (the AGENTS.md §7 function-level-import landmine class).
4. Probe an **invocation**, never an import: `python3 -c "import alembic"` is true on the VPS with no working alembic, because `cd /opt/leadgen` puts the repo's own `alembic/` migrations dir on `sys.path` as a PEP-420 namespace package. `python3 -m alembic --help` is the honest probe, and a running container (`/opt/venv/bin/alembic`) is the first candidate.
5. A workflow installer may not be able to silently no-op. `curl … | sh` under GitHub's `bash -e` (no pipefail) exits 0 on an empty stdin; the failure then surfaces as exit 127 one line later. Download, `test -s`, execute, then prove the binary.
**Consequences**: `active_consumers_count` now under-reports nothing and over-promises nothing — but it is still only a CONFIGURED-state number, and its docstring says so; invoked/consumed/side-effect-verified states need real counters, which do not exist yet. The retired stub breaks any operator runbook that called it (none tracked remains; `progress.md` history keeps the record). `deploy_vps.sh` is untouched: rolling `app` through compose would pre-empt an owner decision that `test_no_app_container_drift.py` and `deploy_preflight.sh:56-58` both currently encode.
**Reference**: `memory/incidents.md` "2026-09-20: The web tier flipped back to Docker…", ADR-194 (single source of truth), `tests/test_vps_migrate_probe.py`, `tests/test_workflow_installer_integrity.py`, `tests/test_typesafe_status_consumer_probe.py`, `tests/test_no_app_container_drift.py`, `tests/test_deploy_guard_ordering.py`.

---

## ADR-192: TypeSafe Gateway Integration for Workers (2026-09-19)

**Status**: ACCEPTED
**Context**: TypeSafe API was only used by `scripts/typesafe_admin_triage.py` (offline script). Workers (email, voice, revenue) were making ad-hoc decisions without TypeSafe judgment. This created inconsistency and missed revenue opportunities.
**Decision**: Create canonical `app/platform/typesafe_gateway.py` as single entry point for all TypeSafe calls. Wire email and voice workers to use it for:
- Lead qualification (`qualify_lead()`)
- Call risk assessment (`assess_call_risk()`)
- Next-action selection (`select_next_action()`)
**Consequences**: 
- +10% decision quality (expected)
- Full trace logging for audit
- Fallback to heuristics on API failure
- Reference: `app/platform/typesafe_gateway.py`, `app/tasks/email_automation.py`, `app/tasks/voice_automation.py`

---

## ADR-191: OmniRoute Gateway Health vs Desktop-Auth Readiness (2026-09-06)

**Status**: ACTIVE
**Context**: OmniRoute was reporting healthy but desktop auth wasn't ready for production traffic.
**Decision**: Separate health checks — API health vs auth readiness.
**Consequences**: Prevents routing traffic to unauthenticated endpoints.
**Reference**: `app/platform/omniroute_gateway.py`

---

## ADR-190: DSH Runtime Hardened Path (2026-08-16)

**Status**: SHIPPED
**Context**: DeepSeek Harness needed governed boundary for production.
**Decision**: Pin source-built Linux runtime in hardened container. Allowlist-based activation.
**Consequences**: DSH can run but requires owner gate for each canary promotion.
**Reference**: `memory/playbooks.md` DSH rollout section

---

## ADR-189: SmartFlo Calling Window Enforcement (2026-09-19)

**Status**: ACCEPTED
**Context**: Calls were being blocked by TRAI compliance (DND lookup failed).
**Decision**: Configure `COMPLIANCE_ALLOWLIST` with test numbers. Keep `DND_FAIL_OPEN=0` (fail-closed).
**Consequences**: Test numbers can call; real numbers require DND database.
**Reference**: `app/telephony/compliance.py`

---

## ADR-188: Hermes Desktop Cockpit with Super Admin JWT (2026-09-14)

**Status**: LIVE
**Context**: Owner needed desktop GUI for admin tasks.
**Decision**: `FASTAPI_MCP_TOKEN` set to super_admin service-JWT (1825d expiry).
**Consequences**: Hermes Desktop GUI/Telegram has 54 MCP tools available.
**Reference**: `docs/integrations/HERMES_DESKTOP.md`

---

## ADR-187: TypeSafe Credential State Tracking (2026-09-19)

**Status**: ACCEPTED
**Context**: TypeSafe key was present but not being used consistently.
**Decision**: Track credential state as `PRESENT`, `ABSENT`, `INVALID`, `ROTATION_REQUIRED`.
**Consequences**: Clear visibility into TypeSafe integration health.
**Reference**: `app/platform/typesafe_gateway.py` `get_credential_state()`

---

## ADR-186: Worker Coordination Ledger (2026-09-19)

**Status**: ACCEPTED
**Context**: 9 workers running independently with no shared state.
**Decision**: Create SQLite-backed task ledger with A2A handoff support.
**Consequences**: Cross-worker visibility, no duplicate work, audit trail.
**Reference**: `app/tasks/worker_coordination.py`

---

## ADR-185: DND Compliance Fail-Closed (2026-09-19)

**Status**: SHIPPED
**Context**: TRAI mandate requires DND check before promotional calls.
**Decision**: `DND_FAIL_OPEN=0` in production (hard-coded in code, cannot be overridden).
**Consequences**: All calls blocked without DND database; allowlist bypass for test numbers.
**Reference**: `app/telephony/compliance.py`

---

## ADR-184: Auto-Outreach Restoration (2026-09-19)

**Status**: SHIPPED
**Context**: `auto_outreach.py` was 0 bytes in production (revenue outage).
**Decision**: Cherry-pick commit 97a6a3f4 to restore 1,982 lines.
**Consequences**: Cold email engine operational again.
**Reference**: Git commit 97a6a3f4

---

## ADR-183: DSH Owner Authority Arm (2026-08-14)

**Status**: LIVE-INERT
**Context**: DeepSeek Harness needed owner-authorized activation.
**Decision**: `DSH_RUNTIME_ENABLED=1`, CSV allowlist 29 identities.
**Consequences**: DSH runtime available but shadow mode only (legacy executor still primary).
**Reference**: `memory/playbooks.md` DSH section

---

## ADR-182: Legacy DSH Retirement Gates (2026-08-14)

**Status**: PENDING
**Context**: DSH migration requires phased rollout.
**Decision**: Soak gates before legacy deletion: 72h shadow comparison, 99.9% parity.
**Consequences**: Legacy executor remains until DSH proven.
**Reference**: `memory/decisions.md`

---

## ADR-181: DSH Hardened Path (2026-08-14)

**Status**: SHIPPED
**Context**: DeepSeek Harness needed governed boundary.
**Decision**: Pinned source-built Linux runtime in hardened container.
**Consequences**: DSH can run but requires owner gate for each canary promotion.
**Reference**: `memory/playbooks.md`

---

## ADR-180: SessionEvent Steal (2026-08-14)

**Status**: SHIPPED
**Context**: Need typed session events for harness audit trail.
**Decision**: Add `SessionEvent` + per-run `seq`/`prev_hash`/`event_hash` on `audit.record`.
**Consequences**: Hash-chain traces available; `HARNESS_SESSION_EVENTS` flag controls activation.
**Reference**: `app/agents/harness/session.py`

---

## ADR-179: DSH NO-GO + SessionEvent (2026-08-14)

**Status**: SHIPPED
**Context**: DeepSeek Harness as full dep rejected (model only, no runtime).
**Decision**: Steal #1 only: SessionEvent pattern. DSH deployment deferred.
**Consequences**: No new dep added; audit trail improved.
**Reference**: Git commit history

---

## ADR-178: GSC Rank Tracking (2026-08-14)

**Status**: INERT
**Context**: Need SEO observability for pSEO.
**Decision**: FREE Search Console daily snapshot (clicks/impressions/avg-position).
**Consequences**: `GSC_ENABLED=0` until creds available.
**Reference**: `app/integrations/gsc.py`

---

## ADR-177: GSC + Funnel + Referral + Triage (2026-08-14)

**Status**: SHIPPED
**Context**: Multiple small improvements needed.
**Decision**: GSC rank tracking, PostHog funnel gap events, referral kit, reply-triage noise filter.
**Consequences**: 212 tests green, prod_check PASS.
**Reference**: PR #356 ancestry

---

## ADR-176: Relay Fix (2026-08-11)

**Status**: SHIPPED
**Context**: Local relay sends failing (wrong port, pubkey mismatch, empty memberships).
**Decision**: Fix compose port (3100), .env owner pubkey, re-run `buzz_local_workspace.py`.
**Consequences**: `buzz_send` MCP-path verified `accepted:true`.
**Reference**: `docs/integrations/BUZZ_LOCAL_RELAY.md`

---

## ADR-175: Boss Silent Fix (2026-08-11)

**Status**: SHIPPED
**Context**: Boss not responding to mentions.
**Decision**: Canonical Boss = `1b13cecc` (only operable identity). Membership actuated.
**Consequences**: Boss can now respond; Harness NOT started (sandbox classifier gated).
**Reference**: `docs/coordination/BUZZ_MEMBERSHIP_SNAPSHOT.json`

---

## ADR-174: Buzz Grid + Canonical Boss (2026-08-09)

**Status**: SHIPPED
**Context**: Need multi-harness + OmniRoute lane.
**Decision**: Buzz plane ab 2 harness: 4 Claude-ACP agents LIVE + Comb (Codex-harness reviewer) CODE-READY.
**Consequences**: Agent turnaround ~7-8 min; repo bug fixed (buzzlock exit codes).
**Reference**: Git commit history

---

## ADR-173: OmniRoute Lane A/B Proven (2026-08-09)

**Status**: LIVE-VERIFIED
**Context**: Need multi-model routing.
**Decision**: Lane A/B PROVEN, Lane C UNVERIFIED. `:20128` loopback-only.
**Consequences**: Groq llama-3.3-70b smoke `COMBO_SMOKE_OK`; auth loopback enforced.
**Reference**: `scripts/buzz_agent_cost.py`

---

## ADR-172: Agent-Create Script Impossibility (2026-08-09)

**Status**: ACCEPTED
**Context**: Need programmatic agent creation.
**Decision**: `BUZZ_AUTH_TAG` (NIP-OA) only minted by Desktop in-process.
**Consequences**: Owner must click once per agent; cannot be fully automated.
**Reference**: `~/.buzz/GUIDES/BUZZ_END_TO_END_RUNBOOK.md`

---

## ADR-171: Workspace Self-Documenting (2026-08-09)

**Status**: SHIPPED
**Context**: Need runnable documentation.
**Decision**: `#build`/`#dev` canvases + runbook note + `#ops` cost + `#admin` brief LIVE post.
**Consequences**: `scripts/buzz_admin_setup.py` superset-guard = 0 lines lost.
**Reference**: Git commit history

---

## ADR-170: MetaGPT Evaluation (2026-08-05)

**Status**: REJECTED
**Context**: Consider adopting MetaGPT as dep.
**Decision**: DON'T adopt (py-ceiling + 8 pin conflicts). Steal #1 only: ActionNode-style fill/review/revise.
**Consequences**: `app/agents/harness/plan_node.py` = INERT default; legacy fallback retained.
**Reference**: `memory/backlog.md` ADR-160

---

## ADR-169: Enterprise Profiles (2026-08-06)

**Status**: SETUP-READY
**Context**: Need multi-agent enterprise support.
**Decision**: One shared Agent-OS; each STAFF gets agent+tenant-isolated memory/KB namespaces.
**Consequences**: `enterprise_profile_ready` = setup truth, NOT rollout-live. Runtime remains 12/17/2.
**Reference**: `memory/decisions.md`

---

## ADR-168: Boss Coordination Coverage (2026-08-06)

**Status**: SHIPPED
**Context**: Need hierarchical coordination.
**Decision**: Canonical Office map now gives Boss → 7 domain teams → 30 workers = 31/31 coordination-ready.
**Consequences**: Rollout remains 12/17/2; Hub flags unchanged/OFF.
**Reference**: `memory/decisions.md`

---

## ADR-167: Buzz Multi-Harness + OmniRoute (2026-08-09)

**Status**: SHIPPED
**Context**: Need multi-harness + model routing.
**Decision**: Buzz plane ab 2 harness; OmniRoute combo LIVE-VERIFIED.
**Consequences**: Lane A/B PROVEN; Lane C UNVERIFIED; Hermes REJECTED (name collision).
**Reference**: Git commit history

---

## ADR-166: DLT Cold-Outbound Approved (2026-07-14)

**Status**: SHIPPED
**Context**: Need legal basis for cold calls.
**Decision**: DLT APPROVED (user-confirmed 2026-07-14).
**Consequences**: Cold outbound ab FULL CAMPAIGN LIVE (2026-08-02, cap 100/day, niche=all).
**Reference**: `CLAUDE.md` §5

---

## ADR-165: Boss Decision Governance (2026-08-06)

**Status**: LIVE
**Context**: Need governance on Boss autonomy.
**Decision**: `BOSS_FULL_AUTONOMY=1` + `BOSS_DECISION_GOVERNANCE=1`.
**Consequences**: Governance sweep LIVE; agents UNARMED 30/30 (rollout held).
**Reference**: `memory/decisions.md`

---

## ADR-164: 31-Agent Enterprise Profiles (2026-08-06)

**Status**: SETUP-READY
**Context**: Need enterprise-grade agent isolation.
**Decision**: One shared Agent-OS; each STAFF gets agent+tenant-isolated memory/KB namespaces.
**Consequences**: `enterprise_profile_ready` = setup truth, NOT rollout-live.
**Reference**: `memory/decisions.md`

---

## ADR-163: Video Decisions (2026-07-23)

**Status**: SHIPPED
**Context**: Need video pipeline governance.
**Decision**: Reject = terminal/no-regeneration; Changes = revises; exact-version approval refuses stale terminal ledgers.
**Consequences**: Design-system assets bypass stale SW cache.
**Reference**: Git commit `510ed7bc`

---

## ADR-162: Skill Registry (2026-07-23)

**Status**: SHIPPED
**Context**: Need canonical skill location.
**Decision**: `.claude/skills` = canonical tracked root; `.agents/skills` removed.
**Consequences**: CODE-PRESENT on `origin/main` via PR #106.
**Reference**: `CLAUDE.md` §0

---

## ADR-161: OpenClaw Admin Stage A (2026-07-23)

**Status**: LIVE
**Context**: Need admin stage for OpenClaw.
**Decision**: PR #105 LIVE at prod `7cab5f60`; Owner OS sole OpenClaw authority; GREEN-only.
**Consequences**: Calling HARD OFF; workforce stays 31 agents.
**Reference**: Git commit history

---

## ADR-160: Parked Ideas (2026-08-05)

**Status**: PARKED
**Context**: MetaGPT #2-4, other experiments.
**Decision**: Park in backlog with why.
**Consequences**: Available for later evaluation.
**Reference**: `memory/backlog.md`

---

## ADR-159: MetaGPT Eval → Steal #1 Only (2026-08-05)

**Status**: SHIPPED
**Context**: Consider adopting MetaGPT.
**Decision**: DON'T adopt (py-ceiling + 8 pin conflicts). Steal #1 only: ActionNode-style fill/review/revise.
**Consequences**: `app/agents/harness/plan_node.py` = INERT default; legacy `_extract_list`+hardcoded fallback retained.
**Reference**: `memory/backlog.md` ADR-160

---

## ADR-158: UPI Manual Payment (2026-08-05)

**Status**: SHIPPED
**Context**: Payment rail decision.
**Decision**: Manual UPI = CANONICAL (owner decision 2026-08-05, ADR/issue #243 closed not_planned).
**Consequences**: Stripe REMOVED 2026-07-10; Razorpay REMOVED 2026-06-18; `PROVIDER_VERIFIED` unreachable BY DESIGN.
**Reference**: `CLAUDE.md` §1

---

## ADR-157: Free Stack Only (2026-07-05)

**Status**: SHIPPED
**Context**: Cost constraint.
**Decision**: Entire AI stack = FREE providers only (user mandate — koi paid STT/TTS/LLM nahi).
**Consequences**: Mistral/Groq/Cerebras/Gemini/NVIDIA/SambaNova/OpenRouter all free tiers only.
**Reference**: `CLAUDE.md` §1

---

## ADR-156: Platform Dial Full Campaign (2026-08-02)

**Status**: LIVE
**Context**: Calling campaign status.
**Decision**: ORIGINAL USER-MANDATE "HARD OFF" → test-mode (2026-07-31) → FULL unblock 2026-08-02.
**Consequences**: `VOICE_LAUNCH_KILL=0`; `DIAL_TEST_MODE=0`; `VOICE_DAILY_CALL_CAP=100`; `PLATFORM_DIAL_DAILY=1`; `PLATFORM_DIAL_LIMIT=100`.
**Reference**: `CLAUDE.md` §5

---

## ADR-155: Ban Safety (2026-07-14)

**Status**: SHIPPED
**Context**: WhatsApp ban risk.
**Decision**: WhatsApp cold/bulk auto-send = number ban (`SALES_AUTOPILOT_WHATSAPP_ENABLED` OFF; campaign 1-click human default).
**Consequences**: Post-call Swara-interested WA separate path (`WHATSAPP_AUTO_SEND` + `POST_CALL_WHATSAPP` / `VOICE_CLOSE_WHATSAPP`).
**Reference**: `CLAUDE.md` §5

---

## ADR-154: ToS-Blocked Auto-Scrape (2026-07-14)

**Status**: SHIPPED
**Context**: Legal risk from scraping.
**Decision**: ToS-blocked auto-scrape (justdial/indiamart/sulekha/linkedin/fb/insta) REFUSED — manual CSV hi path.
**Consequences**: No legal exposure from scraping.
**Reference**: `CLAUDE.md` §5

---

## ADR-153: Ban-Safety Implementation (2026-07-14)

**Status**: SHIPPED
**Context**: WhatsApp safety.
**Decision**: Implement ban-safety gates in code.
**Consequences**: `SALES_AUTOPILOT_WHATSAPP_ENABLED` OFF by default.
**Reference**: `CLAUDE.md` §5

---

## ADR-152: DND Scrub Fail-Closed (2026-07-14)

**Status**: SHIPPED
**Context**: TRAI compliance.
**Decision**: DND scrub fail-CLOSED (lookup fail = promotional BLOCK).
**Consequences**: No illegal calls; compliance safe.
**Reference**: `CLAUDE.md` §5

---

## ADR-151: AI Disclosure at Call Start (2026-07-14)

**Status**: SHIPPED
**Context**: TRAI requirement.
**Decision**: AI-disclosure at call start ("ek AI assistant").
**Consequences**: Compliance with TRAI AI-calling rules.
**Reference**: `CLAUDE.md` §5

---

## ADR-150: Promo Calling Window (2026-07-14)

**Status**: SHIPPED
**Context**: TRAI time restrictions.
**Decision**: Promo calling-window 9am–7pm (code-conservative; TRAI actual 9–9).
**Consequences**: Legal compliance; conservative window.
**Reference**: `CLAUDE.md` §5

---

## ADR-149: Consent Ledger Opt-Out (2026-07-14)

**Status**: SHIPPED
**Context**: DPDP Act compliance.
**Decision**: Consent ledger opt-out = INSTANT cross-channel suppression.
**Consequences**: Opt-out honored immediately across all channels.
**Reference**: `CLAUDE.md` §5

---

## ADR-148: Foreign Trunks Illegal (2026-07-14)

**Status**: SHIPPED
**Context**: Telegraph Act compliance.
**Decision**: Foreign trunks (Twilio etc.) India-domestic = ILLEGAL.
**Consequences**: Only Indian trunks (SmartFlo, Vobiz) for domestic calls.
**Reference**: `CLAUDE.md` §5

---

## ADR-147: DLT Gated Cold Outbound (2026-07-14)

**Status**: SHIPPED
**Context**: DLT compliance.
**Decision**: Cold auto-calls bina DLT = nahi (sirf inbound auto-callback).
**Consequences**: DLT_APPROVED=1 required for cold outbound.
**Reference**: `CLAUDE.md` §5

---

## ADR-146: Pure Minutes-Resale Illegal (2026-07-14)

**Status**: SHIPPED
**Context**: Telegraph Act compliance.
**Decision**: Pure minutes-resale = Telegraph Act violation; legal = SaaS bundle, DLT/140 CLIENT ke naam.
**Consequences**: Position as SaaS bundle, not telephony resale.
**Reference**: `CLAUDE.md` §5

---

## ADR-145: DPDP Act 2023 (2026-07-14)

**Status**: SHIPPED
**Context**: Data protection compliance.
**Decision**: Purpose limitation + data minimisation + consent basis for first contact.
**Consequences**: 90-din recording retention; purge API + Grievance Officer in /privacy.
**Reference**: `CLAUDE.md` §5

---

## ADR-144: Lead Data Cross-Client Leak (2026-07-14)

**Status**: SHIPPED
**Context**: Tenant isolation.
**Decision**: Lead data cross-client leak KABHI nahi (customer-isolation).
**Consequences**: Strict tenant isolation in code.
**Reference**: `CLAUDE.md` §5

---

## ADR-143: Billing Truth (2026-07-18)

**Status**: SHIPPED
**Context**: Pricing integrity.
**Decision**: `packages.py` = single source (sync via `subscription._sync_plans_from_packages`).
**Consequences**: Pricing change = packages.py + test_billing_truth_2026.py SAATH.
**Reference**: `CLAUDE.md` §5

---

## ADR-142: Growth ₹2,999 Legacy Hidden (2026-07-18)

**Status**: SHIPPED
**Context**: Legacy pricing.
**Decision**: Growth ₹2,999 = LEGACY hidden (`get_public_packages()` use karo).
**Consequences**: Old price not exposed to new customers.
**Reference**: `CLAUDE.md` §5

---

## ADR-141: GST Only with GSTIN (2026-07-18)

**Status**: SHIPPED
**Context**: Tax compliance.
**Decision**: GST sirf `GST_GSTIN` set pe.
**Consequences**: No GST without GSTIN configured.
**Reference**: `CLAUDE.md` §5

---

## ADR-140: Invoice Sequential (2026-07-18)

**Status**: SHIPPED
**Context**: Rule-46 compliance.
**Decision**: Invoice Rule-46 sequential `INV/2026-27/0001`.
**Consequences**: First invoice INV/2026-27/0001 (Jiya makeover).
**Reference**: `CLAUDE.md` §5

---

## ADR-139: Secrets in .env Only (2026-07-14)

**Status**: SHIPPED
**Context**: Security.
**Decision**: Secrets sirf `.env` (gitignored) — kabhi committed file/CLAUDE.md/scripts me nahi.
**Consequences**: API keys env se only; `sk_` Pollinations key KABHI URL me nahi.
**Reference**: `CLAUDE.md` §5

---

## ADR-138: FastAPI First-Route-Wins (2026-07-14)

**Status**: SHIPPED
**Context**: Route registration.
**Decision**: FastAPI first-route-wins — naya route add karne se pehle duplicate grep (saare split routers me).
**Consequences**: No route conflicts.
**Reference**: `CLAUDE.md` §4

---

## ADR-137: Web Process KABHI Heavy Job (2026-07-14)

**Status**: SHIPPED
**Context**: Performance.
**Decision**: Web process KABHI heavy job na chalaye (Celery only).
**Consequences**: HTTP requests stay fast.
**Reference**: `CLAUDE.md` §4

---

## ADR-136: Never Write Prod DB from Local (2026-07-14)

**Status**: SHIPPED
**Context**: Data safety.
**Decision**: Never write prod DB from local.
**Consequences**: Local dev isolated from prod data.
**Reference**: `CLAUDE.md` §4

---

## ADR-135: USE_SILERO_VAD=0 (2026-07-03)

**Status**: SHIPPED
**Context**: Voice processing.
**Decision**: `USE_SILERO_VAD=0` rakhna (2026-07-03: =1 ne har phone call "deaf" bana diya).
**Consequences**: Voice processing works correctly.
**Reference**: `CLAUDE.md` §7

---

## ADR-134: EdgeTTS >=7.2.0 (2026-07-14)

**Status**: SHIPPED
**Context**: TTS compatibility.
**Decision**: EdgeTTS `>=7.2.0` warna 403.
**Consequences**: TTS works without 403 errors.
**Reference**: `CLAUDE.md` §7

---

## ADR-133: Reply() Guard Mirror (2026-07-03)

**Status**: SHIPPED
**Context**: Voice processing.
**Decision**: Har `reply()` guard `reply_stream_sentences()` me bhi mirror karo.
**Consequences**: Close-signals work in stream path.
**Reference**: `CLAUDE.md` §7

---

## ADR-132: Rate Limits (2026-07-14)

**Status**: SHIPPED
**Context**: Provider quotas.
**Decision**: Groq TPD content-heavy days pe khatam · Cerebras 429-prone · NVIDIA 40 RPM + ~5k LIFETIME credits · Gemini free quota → 9-key rotation · email outreach cap 25/day + warmup · `PROSPECT_MAX_LOOKUPS=60`/run.
**Consequences**: Provider quotas respected.
**Reference**: `CLAUDE.md` §7

---

## ADR-131: Skill Registry Canonical (2026-07-23)

**Status**: SHIPPED
**Context**: Skill location.
**Decision**: `.claude/skills` = canonical tracked root; `.agents/skills` removed.
**Consequences**: Single source of truth for skills.
**Reference**: `CLAUDE.md` §0, Git PR #106

---

## ADR-130: :latest = UNKNOWN-provenance (2026-07-14)

**Status**: SHIPPED
**Context**: Deployment provenance.
**Decision**: `:latest` = UNKNOWN-provenance prod (2026-07-14, ADR-097). Deploy pe `APP_VERSION=<sha>` set karna OPTIONAL nahi.
**Consequences**: `/health` version field = drift detector.
**Reference**: `CLAUDE.md` §7

---

## ADR-129: Causal-Claim Discipline (2026-07-14)

**Status**: SHIPPED
**Context**: Debugging methodology.
**Decision**: "Errors the → maine deploy kiya → errors gaye" = causation nahi. Check error series END timestamp.
**Consequences**: Avoid false attribution of fixes.
**Reference**: `CLAUDE.md` §7

---

## ADR-128: Function-Level Import Startup Gates (2026-07-14)

**Status**: SHIPPED
**Context**: Import safety.
**Decision**: Function-level import startup gates ko DHOKA deta hai. Koi bhi pricing/shared helper retire karo to uske SAARE callers grep karo.
**Consequences**: No silent import failures.
**Reference**: `CLAUDE.md` §7

---

## ADR-127: App Port 8080 Inside, 8000 Host (2026-07-14)

**Status**: SHIPPED
**Context**: Docker networking.
**Decision**: App ka port DO hai — 8080 andar, 8000 host pe (`--port ${PORT:-8080}`, publish `8080/tcp -> 127.0.0.1:8000`).
**Consequences**: Container-to-container URL = `http://app:8080/...`; HOST/curl = `127.0.0.1:8000`.
**Reference**: `CLAUDE.md` §7

---

## ADR-126: .env.example Drift FIX (2026-09-05)

**Status**: SHIPPED
**Context**: Config documentation.
**Decision**: `.env.example` drift FIX hua (STT/TTS/Stripe sections ab real stack se aligned).
**Consequences**: Docs match reality.
**Reference**: Git commit history

---

## ADR-125: Pyproject.toml Reference-Only (2026-07-14)

**Status**: SHIPPED
**Context**: Dependency management.
**Decision**: `pyproject.toml` = reference-only (koi pip-install isse nahi karta); edge-tts floor `>=7.2.0`.
**Consequences**: `requirements.lock.txt` hi truth.
**Reference**: `CLAUDE.md` §7

---

## ADR-124: Compose Service Worker-Heavy (2026-07-14)

**Status**: SHIPPED
**Context**: Docker naming.
**Decision**: Compose service `worker-heavy` (hyphen) — galat naam = poora `up` ABORT.
**Consequences**: Correct service names prevent deploy failures.
**Reference**: `CLAUDE.md` §7

---

## ADR-123: VPS docker compose -f (2026-07-18)

**Status**: SHIPPED
**Context**: VPS deployment.
**Decision**: VPS pe `docker compose` bina `-f docker-compose.vps.yml` = LEGACY stack.
**Consequences**: Always use `-f docker-compose.vps.yml` for VPS.
**Reference**: `CLAUDE.md` §7, `memory/incidents.md`

---

## ADR-122: Windows OpenSSH Broken (2026-07-14)

**Status**: SHIPPED
**Context**: Windows dev environment.
**Decision**: Windows: OpenSSH broken → Git ka ssh.exe; `.bat` me `call` npm/git.
**Consequences**: Use Git's SSH, not system SSH.
**Reference**: `CLAUDE.md` §7, `windows-dev-gotchas` skill

---

## ADR-121: Sandbox Mount STALE (2026-07-14)

**Status**: SHIPPED
**Context**: Windows file tools.
**Decision**: Sandbox mount STALE ho jata → Windows file-tools = source of truth.
**Consequences**: Never trust mounted state; use Windows tools directly.
**Reference**: `CLAUDE.md` §7

---

## ADR-120: Large Multi-File Edits (2026-07-14)

**Status**: SHIPPED
**Context**: Edit safety.
**Decision**: Bade multi-file edits same file pe parallel = truncation.
**Consequences**: Edit one file at a time.
**Reference**: `CLAUDE.md` §7

---

## ADR-119: OKF Curated Bundle (2026-09-02)

**Status**: SHIPPED
**Context**: Knowledge management.
**Decision**: Repo-root `knowledge/` = Open Knowledge Format v0.1 draft bundle.
**Consequences**: Not a RAG replacement; large-scale retrieval stays Qdrant.
**Reference**: `memory/INDEX.md`

---

## ADR-118: Memory System Rules (2026-09-02)

**Status**: SHIPPED
**Context**: Knowledge base discipline.
**Decision**: Read INDEX.md first; write-back same session; no secrets; monthly pruning.
**Consequences**: Knowledge base stays current and secure.
**Reference**: `memory/INDEX.md`

---

## ADR-117: Tier 1 vs Tier 2 Working Memory (2026-09-02)

**Status**: SHIPPED
**Context**: Memory organization.
**Decision**: Tier 1 (hot cache) = `CLAUDE.md ## Current State` (≤40 lines). Tier 2 = `memory/` directory.
**Consequences**: Fast access to current state; deep knowledge in memory.
**Reference**: `memory/INDEX.md`

---

## ADR-116: Session Log Archive (2026-09-02)

**Status**: SHIPPED
**Context**: History tracking.
**Decision**: Dated history archive = `docs/SESSION_LOG.md` (auto-load NAHI).
**Consequences**: Full history available but not loaded by default (token discipline).
**Reference**: `memory/INDEX.md`

---

## ADR-115: Canonical Shared Context (2026-07-05)

**Status**: SHIPPED
**Context**: Session startup.
**Decision**: pehle `docs/context/CURRENT_STATE.md` + `ACTIVE_WORK.md` + `SESSION_HANDOFF.md` padho.
**Consequences**: Consistent context across sessions.
**Reference**: `CLAUDE.md` §8

---

## ADR-114: Hinglish Reply (2026-07-05)

**Status**: SHIPPED
**Context**: Communication style.
**Decision**: Hinglish (Roman) me HI reply — concise, kam formatting.
**Consequences**: Canarian check: HAR reply ke END me akeli line `🐦 pelican`.
**Reference**: `CLAUDE.md` §8

---

## ADR-113: Anti-Mistake Rules (2026-07-05)

**Status**: SHIPPED
**Context**: Debugging discipline.
**Decision**: `docs/AGENT_WORK_RULES.md` — 10 rules from real postmortems.
**Consequences**: Avoid common debugging mistakes.
**Reference**: `CLAUDE.md` §8

---

## ADR-112: Work Quality Gate (2026-07-05)

**Status**: SHIPPED
**Context**: Code quality.
**Decision**: (1) context-first — edit se PEHLE parallel Grep/Glob se saare touch-points PURA padho (2) Edit se theek pehle Read.
**Consequences**: No stale edits; context-aware changes.
**Reference**: `CLAUDE.md` §8

---

## ADR-111: Never /env Touch (2026-07-05)

**Status**: SHIPPED
**Context**: Secret safety.
**Decision**: Never: `.env` values touch/overwrite · destructive migration/`DROP`/`reset --hard` bina explicit user confirm · `git add -A` (parallel Cursor edits — shared files diff karo).
**Consequences**: Secrets safe; no accidental data loss.
**Reference**: `CLAUDE.md` §8

---

## ADR-110: Plan Before Multi-File Edits (2026-07-05)

**Status**: SHIPPED
**Context**: Change management.
**Decision**: Plan before multi-file edits (`plan-then-build`); small reviewable diffs.
**Consequences**: Changes are reviewable and reversible.
**Reference**: `CLAUDE.md` §8

---

## ADR-109: Architecture Change = Memory Write-Back (2026-07-05)

**Status**: SHIPPED
**Context**: Knowledge preservation.
**Decision**: Naya decision → `decisions.md` (append-only ADR), incident → `incidents.md`, procedure → `playbooks.md`, parked idea → `backlog.md`.
**Consequences**: Knowledge survives session boundaries.
**Reference**: `CLAUDE.md` §9

---

## ADR-108: AGENTS.md = CLAUDE.md Byte-Copy (2026-07-05)

**Status**: SHIPPED
**Context**: Agent configuration.
**Decision**: AGENTS.md = CLAUDE.md ki byte-copy rakho (Copy-Item se re-sync).
**Consequences**: Agents see same context as Claude.
**Reference**: `CLAUDE.md` §8

---

## ADR-107: DLT/Udyam Paperwork Recurring (2026-07-14)

**Status**: SHIPPED
**Context**: Compliance reminders.
**Decision**: DLT/Udyam paperwork ko recurring talking-point mat banao (user ko pata hai) — par compliance GATES kabhi disable nahi.
**Consequences**: Compliance always enforced; paperwork tracked separately.
**Reference**: `CLAUDE.md` §8

---

## ADR-106: Free Stack Only (2026-07-05)

**Status**: SHIPPED
**Context**: Cost constraint.
**Decision**: Free stack only — koi paid AI service add nahi.
**Consequences**: All AI providers free tiers only.
**Reference**: `CLAUDE.md` §1

---

## ADR-105: Repository Context Retrieval Protocol (2026-07-05)

**Status**: SHIPPED
**Context**: Token discipline.
**Decision**: Poora repo har session dobara mat padho — ek Graphify knowledge-graph already bana hai.
**Consequences**: Fast navigation without loading full repo.
**Reference**: `CLAUDE.md` §9.5

---

## ADR-104: Graphify Navigation Layer (2026-07-05)

**Status**: SHIPPED
**Context**: Codebase navigation.
**Decision**: `app/graphify-out/graph.json` = DEV-only navigation layer, MCP-wired via `.mcp.json` → `graphify-mcp`.
**Consequences**: Fast call-graph exploration without loading source.
**Reference**: `docs/GRAPHIFY.md`

---

## ADR-103: Skill Registry Paths (2026-07-23)

**Status**: SHIPPED
**Context**: Skill location.
**Decision**: Canonical registry from CURRENT repository truth — do not trust old `.agents/skills`, `.claude/skills`, `skills/`, `.Codex/skills`.
**Consequences**: Single authoritative skill location.
**Reference**: `CLAUDE.md` §0, ADR-131

---

## ADR-102: TypeSafe Model Contract (2026-09-19)

**Status**: SHIPPED
**Context**: TypeSafe integration.
**Decision**: For new LeadsGen AI TypeSafe decisions, use current canonical JEv alias: `jev-latest`.
**Consequences**: Consistent model usage across sessions.
**Reference**: `app/platform/typesafe_gateway.py`

---

## ADR-101: TypeSafe as Decision Engine (2026-09-19)

**Status**: SHIPPED
**Context**: TypeSafe usage.
**Decision**: Use TypeSafe where semantic judgment materially improves execution (lead qualification, next-action, risk triage).
**Consequences**: Better decisions on revenue-critical paths.
**Reference**: `CLAUDE.md` §0

---

## ADR-100: TypeSafe Traceability (2026-09-19)

**Status**: SHIPPED
**Context**: Audit requirements.
**Decision**: Every TypeSafe invocation must provide traceability: task_id, question_id, state/evidence hash, requested_model, resolved_model, primitive, input evidence references, latency, success/failure, result, probability/confidence, downstream action, eventual observed outcome.
**Consequences**: Full audit trail for compliance.
**Reference**: `app/platform/typesafe_gateway.py`

---

## ADR-99: Meta-Brand Post Blocked (2026-07-14)

**Status**: SHIPPED
**Context**: Meta API restrictions.
**Decision**: Meta app-review for CUSTOMER pages only (Advanced Access chahiye).
**Consequences**: Own-brand social poora wired (Postiz live 2026-08-01).
**Reference**: `CLAUDE.md` §Current State

---

## ADR-98: Postiz Restore (2026-08-01)

**Status**: SHIPPED
**Context**: Social media integration.
**Decision**: Postiz live 2026-08-01 restore — temporal + nginx fixes, 6 connected channels verified.
**Consequences**: Social media automation operational.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-97: WAHA Session Flapping Fix (2026-08-23)

**Status**: SHIPPED
**Context**: WhatsApp automation.
**Decision**: WAHA LIVE-VERIFIED 2026-08-23 — session flapping root-caused, QR re-scan (***2607), sweep sent:2/2 Jiya+Kamal.
**Consequences**: WhatsApp automation stable.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-96: Harness OBS — SessionEvents (2026-08-23)

**Status**: SHIPPED
**Context**: Agent observability.
**Decision**: `HARNESS_SESSION_EVENTS=1` ARMED (2026-08-23 owner-approved; hash-chain traces; `AGENT_HARNESS` still OFF).
**Consequences**: Session traces available for debugging.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-95: Wiring Gaps LIVE (2026-08-14)

**Status**: SHIPPED
**Context**: Integration completeness.
**Decision**: wiring_gaps LIVE (PR #421, in ancestry): `automation_health.health().wiring_gaps` ab daily owner brief + Mission Control me "flag ON but backend/creds missing" report karta hai.
**Consequences**: Missing integrations visible in dashboard.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-94: DSH Runtime Enabled (2026-09-10)

**Status**: SHIPPED
**Context**: DeepSeek Harness.
**Decision**: DSH `DSH_RUNTIME_ENABLED=1` (runtime + shadow ON, allowlist `["jiya_makeover"]` — ⚠️ CORRECTED 2026-09-10 from live `/health`; the old "0 / allowlist empty" note was STALE).
**Consequences**: DSH available for Jiya makeover only.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-93: GSC INERT (2026-09-10)

**Status**: SHIPPED
**Context**: SEO tracking.
**Decision**: GSC INERT: `GSC_ENABLED` UNSET par CREDOS PRESENT (`GSC_SERVICE_ACCOUNT_JSON`+`google_sheets_credentials` SET — sirf flag flip baaki).
**Consequences**: Ready to enable when flag flipped.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-92: CRM LIVE (2026-09-10)

**Status**: SHIPPED
**Context**: Customer relationship management.
**Decision**: CRM LIVE: provider=`hubspot`, `auto_sync`, recent_pushes=5.
**Consequences**: HubSpot integration operational.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-91: Boss Autonomy ON (2026-09-10)

**Status**: SHIPPED
**Context**: Agent autonomy.
**Decision**: BOSS AUTONOMY ON: `BOSS_FULL_AUTONOMY=1` + `BOSS_DECISION_GOVERNANCE=1` (governance sweep LIVE; agents UNARMED 30/30 — rollout held).
**Consequences**: Boss can decide but agents not yet activated.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-90: UPI Allowlist Containment (2026-09-10)

**Status**: SHIPPED
**Context**: Payment security.
**Decision**: UPI allowlist containment intact · cold WA OFF · calling LIVE under compliance gates (`PLATFORM_DIAL_DAILY=1`, `VOICE_LAUNCH_KILL=0`).
**Consequences**: Payment path secure; calling operational.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-89: Trainer Fix LIVE (2026-09-10)

**Status**: SHIPPED
**Context**: Voice training.
**Decision**: trainer fix LIVE: `ingest_to_kb` bounded 200s.
**Consequences**: KB ingestion won't hang.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-88: Deployment = scripts/deploy_vps.sh ONLY (2026-09-10)

**Status**: SHIPPED
**Context**: Deployment discipline.
**Decision**: Deployment = `scripts/deploy_vps.sh` ONLY (fail-closed gates: runtime-data guard · `.env` guard · environment=production · `/health/ready`=200 · route count · per-service skew · systemd app rollout).
**Consequences**: Consistent deployments.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-87: VOICE_LAUNCH_KILL Deleted (2026-09-15)

**Status**: SHIPPED
**Context**: Kill switch cleanup.
**Decision**: ⚠️ CORRECTED 2026-09-15: the old `VOICE_LAUNCH_KILL` TRUE_TOKEN preflight was DELETED — it was dead code (invocation lost in `db5b1ceb`, 2 test files still asserting it was MANDATORY, 4 RED tests) AND self-blocking (it passed only when the kill switch was ENGAGED, while `VOICE_LAUNCH_KILL=0` is the normal state of the live campaign).
**Consequences**: Kill switch now works correctly.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-86: GitHub Branch Protection (2026-09-14)

**Status**: SHIPPED
**Context**: Git discipline.
**Decision**: GitHub main = PR-only by convention + local `no-commit-to-branch` hook (direct push refused locally) — ⚠️ CORRECTED 2026-09-14: platform-level branch protection is NOT configured (`GET branches/main/protection` → HTTP 404 "Branch not protected"; `rulesets` → []), so all CI checks are advisory until an admin adds a required check/ruleset.
**Consequences**: CI non-blocking; manual review recommended.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-85: SHA Discipline (2026-07-25)

**Status**: SHIPPED
**Context**: Git tracking.
**Decision**: a stale local `origin/main` ref on 2026-07-25 made an agent report merged-and-deployed PR #125 as "not merged". `git fetch` + re-probe `/health` before asserting any SHA.
**Consequences**: Always fetch before checking SHA.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-84: Lineage Warning (2026-09-14)

**Status**: SHIPPED
**Context**: Deployment tracking.
**Decision**: ⚠️ LINEAGE WARNING (2026-09-14, git-verified — supersedes the 2026-09-10 version): PROD and local HEAD have DIVERGED. Deployed = `95245ce8` (= `origin/main` tip) · local HEAD = `20e4180b` · merge-base `071dc31b` · prod-only commits = 2 · local-only = 1.
**Consequences**: Base every migration/deploy branch on `95245ce8` (= `origin/main`), NOT `20e4180b`.
**Reference**: `docs/context/PHASE0_BASELINE.md`

---

## ADR-83: Truth Gate (2026-09-10)

**Status**: SHIPPED
**Context**: Data integrity.
**Decision**: ⚠️ TRUTH GATE (2026-09-10): `data/workforce_live_status.json` must NEVER be rendered as live worker activity. It reports `RUNNING_24_7_PARALLEL` + `actions_today=592` while `active_workers=0`, `task_execution_verified=false`, `evidence_kind=inference_probe_only`, and 6/6 desktop apps UNVERIFIED.
**Consequences**: Label it probe-only inference or omit it. Enforced in code by `app/utils/owner_feed.py` (`FORCE_UNVERIFIED_SOURCES`).
**Reference**: `CLAUDE.md` §Current State

---

## ADR-82: Platform Dial Full Campaign (2026-08-02)

**Status**: SHIPPED
**Context**: Calling campaign.
**Decision**: platform_dial = FULL CAMPAIGN LIVE (owner go-ahead 2026-08-02) — original USER-MANDATE (2026-07-05) "HARD OFF" → test-mode (2026-07-31) → FULL unblock 2026-08-02.
**Consequences**: `VOICE_LAUNCH_KILL=0` · `DIAL_TEST_MODE=0` · `VOICE_DAILY_CALL_CAP=100` · `PLATFORM_DIAL_DAILY=1` (boolean ON/OFF — not a count) · `PLATFORM_DIAL_LIMIT=100` (per-run cap).
**Reference**: `CLAUDE.md` §5

---

## ADR-81: Live Proof Platform Dial (2026-08-02)

**Status**: SHIPPED
**Context**: Calling verification.
**Decision**: LIVE proof: 3 real Vobiz calls placed 2026-08-02 (call_attempts+1, session `S20260802-a280d841`, state `running`).
**Consequences**: Calling pipeline verified.
**Reference**: `CLAUDE.md` §5

---

## ADR-80: Daily Scheduler Auto-Dial (2026-08-02)

**Status**: SHIPPED
**Context**: Scheduling.
**Decision**: Daily 11:30 IST scheduler auto-dials up to `PLATFORM_DIAL_LIMIT`/run (niche=all).
**Consequences**: Automated dialing during business hours.
**Reference**: `CLAUDE.md` §5

---

## ADR-79: Compliance Spine UNTOUCHED (2026-08-02)

**Status**: SHIPPED
**Context**: Legal compliance.
**Decision**: Compliance spine UNTOUCHED: DND fail-closed · TRAI window 10–19 IST · AI-disclosure · consent · DLT_APPROVED=1 · phone-type gate · learned IVR blocklist · circuit breaker · 30-call training pause · recording gate · concurrency=1.
**Consequences**: All TRAI requirements met.
**Reference**: `CLAUDE.md` §5

---

## ADR-78: Rollback Available (2026-08-02)

**Status**: SHIPPED
**Context**: Deployment safety.
**Decision**: Rollback = `.env.bak-fullcampaign-20260802075851` (restore + recreate).
**Consequences**: Can revert if issues arise.
**Reference**: `CLAUDE.md` §5

---

## ADR-77: Calling Window + DND Gates ACTIVE (2026-08-02)

**Status**: SHIPPED
**Context**: Runtime compliance.
**Decision**: Calling window + DND gates call path me ACTIVE.
**Consequences**: Compliance enforced at runtime.
**Reference**: `CLAUDE.md` §5

---

## ADR-76: Unity WebGL Build (ADR-076)

**Status**: SHIPPED
**Context**: 3D office visualization.
**Decision**: Unity WebGL build (ADR-076): ✅ LIVE on prod `041501c2` (2026-08-04) — `/app/office?mode=3d` 3D Blueprint office; `UNITY_VIRTUAL_OFFICE_ENABLED=1` · `UNITY_CUSTOMER_OFFICE_ENABLED=0`; artifacts versioned in `frontend/office_unity/` (rollback = restore dir).
**Consequences**: 3D office available for owner.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-75: Admin UAT Pending (2026-08-04)

**Status**: PENDING
**Context**: Unity build verification.
**Decision**: Admin UAT pending.
**Consequences**: Owner to verify 3D office.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-74: EXTERNAL-Blocked Items (2026-07-14)

**Status**: BLOCKED
**Context**: External dependencies.
**Decision**: EXTERNAL-blocked (token mat jalao): missed-call DID webhook, GBP API approval, HA 2nd server, Meta app-review for CUSTOMER pages only (Advanced Access chahiye).
**Consequences**: These require external action.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-73: Own-Brand Meta NOT Blocked (2026-07-14)

**Status**: SHIPPED
**Context**: Meta API access.
**Decision**: ⚠️ OWN-brand ke liye Meta blocked NAHI hai (2026-07-14 console-verified, ADR-099): app `LeadsGenAI` (1278868110768460) dev-mode me hai aur `pages_manage_posts` + `instagram_content_publish` dono "Ready for testing" hain — apne hi Pages pe review ke bina post hota hai.
**Consequences**: Own-brand social fully operational.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-72: Postiz Live (2026-08-01)

**Status**: SHIPPED
**Context**: Social media.
**Decision**: Own-brand social poora wired hai (Postiz live 2026-08-01 restore — temporal + nginx fixes, 6 connected channels verified via public API, `POSTIZ_INTEGRATIONS` env me 5 ids).
**Consequences**: Social media automation working.
**Reference**: `CLAUDE.md` §Current State

---

## ADR-71: Free Providers Stack (2026-07-05)

**Status**: SHIPPED
**Context**: AI stack.
**Decision**: Entire AI stack = FREE providers only (user mandate — koi paid STT/TTS/LLM nahi).
**Consequences**: No AI costs.
**Reference**: `CLAUDE.md` §1

---

## ADR-70: Mistral Primary (2026-07-05)

**Status**: SHIPPED
**Context**: LLM routing.
**Decision**: Mistral mistral-small-latest → LLM primary · Groq → LLM fallback + STT whisper-large-v3 primary · Cerebras → free 120B fallback (429-prone) · Gemini → VOICE-scoped primary (`VOICE_GEMINI_PRIMARY=1`, 9-key rotation pool `data/voice_gemini_keys.json`) + audio STT fallback.
**Consequences**: Multi-provider fallback chain.
**Reference**: `CLAUDE.md` §2

---

## ADR-69: NVIDIA/SambaNova/OpenRouter Deep-Tail (2026-07-05)

**Status**: SHIPPED
**Context**: LLM routing.
**Decision**: NVIDIA NIM / SambaNova / OpenRouter → deep-tail LLM.
**Consequences**: Extra providers for edge cases.
**Reference**: `CLAUDE.md` §2

---

## ADR-68: EdgeTTS TTS (2026-07-05)

**Status**: SHIPPED
**Context**: Text-to-speech.
**Decision**: EdgeTTS hi-IN-SwaraNeural → TTS (free).
**Consequences**: Hindi TTS working.
**Reference**: `CLAUDE.md` §2

---

## ADR-67: Pollinations AI Images/Video (2026-07-05)

**Status**: SHIPPED
**Context**: Media generation.
**Decision**: Pollinations → AI images/video.
**Consequences**: Free media generation.
**Reference**: `CLAUDE.md` §2

---

## ADR-66: Vobiz Telephony (2026-07-05)

**Status**: SHIPPED
**Context**: Telephony provider.
**Decision**: Vobiz → telephony provider (India SIP; Twilio = international-only fallback; Exotel DELETED).
**Consequences**: Indian telephony working.
**Reference**: `CLAUDE.md` §2

---

## ADR-65: Hostinger SMTP/IMAP (2026-07-05)

**Status**: SHIPPED
**Context**: Email infrastructure.
**Decision**: Hostinger SMTP/IMAP admin@leadsgenai.in → outreach + reply-triage.
**Consequences**: Email sending working.
**Reference**: `CLAUDE.md` §2

---

## ADR-64: Google Places (2026-07-05)

**Status**: SHIPPED
**Context**: Lead sourcing.
**Decision**: Google Maps Places (New) → prospecting.
**Consequences**: Lead discovery working.
**Reference**: `CLAUDE.md` §2

---

## ADR-63: SearXNG Self-Host (2026-07-05)

**Status**: SHIPPED
**Context**: Web search.
**Decision**: SearXNG (self-host) → websearch.
**Consequences**: Self-hosted search.
**Reference**: `CLAUDE.md` §2

---

## ADR-62: ntfy Self-Host (2026-07-05)

**Status**: SHIPPED
**Context**: Push notifications.
**Decision**: ntfy (self-host) → phone push.
**Consequences**: Phone notifications working.
**Reference**: `CLAUDE.md` §2

---

## ADR-61: WhatsApp Meta Cloud + WAHA (2026-07-05)

**Status**: SHIPPED
**Context**: WhatsApp integration.
**Decision**: WhatsApp Meta Cloud + own WAHA :3111 → 1-click human send.
**Consequences**: WhatsApp automation working.
**Reference**: `CLAUDE.md` §2

---

## ADR-60: UPI Manual Payment (2026-08-05)

**Status**: SHIPPED
**Context**: Payment processing.
**Decision**: UPI manual (`UPI_VPA`) → the only payment rail; owner confirms bank credit (`payment_verification_method = owner_confirmed_upi`, never `PROVIDER_VERIFIED`).
**Consequences**: Manual payment verification.
**Reference**: `CLAUDE.md` §1

---

## ADR-59: Stripe REMOVED (2026-07-10)

**Status**: SHIPPED
**Context**: Payment processing.
**Decision**: Stripe REMOVED 2026-07-10.
**Consequences**: No Stripe dependency.
**Reference**: `CLAUDE.md` §1

---

## ADR-58: Razorpay REMOVED (2026-06-18)

**Status**: SHIPPED
**Context**: Payment processing.
**Decision**: Razorpay REMOVED 2026-06-18, so `PROVIDER_VERIFIED` is unreachable BY DESIGN.
**Consequences**: Only UPI manual path exists.
**Reference**: `CLAUDE.md` §1

---

## ADR-57: Sentry Errors (2026-07-05)

**Status**: SHIPPED
**Context**: Error tracking.
**Decision**: Sentry → errors (ARMED).
**Consequences**: Errors tracked.
**Reference**: `CLAUDE.md` §2

---

## ADR-56: rclone Google Drive Backup (2026-07-05)

**Status**: SHIPPED
**Context**: Disaster recovery.
**Decision**: rclone → Google Drive → offsite backup (LIVE, restore PROVEN).
**Consequences**: Backups working and restore verified.
**Reference**: `CLAUDE.md` §2

---

## ADR-55: GHCR Images (2026-07-05)

**Status**: SHIPPED
**Context**: Container registry.
**Decision**: GHCR → images.
**Consequences**: Container images stored.
**Reference**: `CLAUDE.md` §2

---

## ADR-54: LLM Chain in free_ai.py (2026-07-05)

**Status**: SHIPPED
**Context**: Voice agent LLM routing.
**Decision**: LLM chain lives in `app/voice_agent/free_ai.py` (~line 420) with escalating 429 circuit-breaker (60s→30min).
**Consequences**: Graceful degradation on rate limits.
**Reference**: `CLAUDE.md` §2

---

## ADR-53: Main Product ₹1,999/mo (2026-07-05)

**Status**: SHIPPED
**Context**: Pricing.
**Decision**: AI Automated Marketing = MAIN product — Main ₹1,999/mo + Combo/Advanced ₹5,999/mo (voice callback sirf ek FEATURE, 500 min).
**Consequences**: Marketing product primary revenue.
**Reference**: `CLAUDE.md` §1

---

## ADR-52: Voice Product Standalone (2026-07-05)

**Status**: SHIPPED
**Context**: Pricing.
**Decision**: AI Voice Calling Agent = standalone full AI telecaller, flat per niche-band ₹4,999/₹9,999/₹19,999/mo (DLT-gated for cold outbound).
**Consequences**: Voice product tiered pricing.
**Reference**: `CLAUDE.md` §1

---

## ADR-51: Money Path (2026-07-05)

**Status**: SHIPPED
**Context**: Acquisition funnel.
**Decision**: Money path: free lead magnets (`/audit`, `/site-audit`, `/demo`) + programmatic SEO + auto email-outreach → inquiry → `/pricing` → `/start` → manual UPI → subscription + top-up minute packs.
**Consequences**: Complete revenue path defined.
**Reference**: `CLAUDE.md` §1

---

## ADR-50: Marketing + Voice Bundle USP GALAT (2026-07-05)

**Status**: SHIPPED
**Context**: Marketing positioning.
**Decision**: "Marketing + voice bundle" USP framing GALAT hai — use mat karo.
**Consequences**: Don't use incorrect USP.
**Reference**: `CLAUDE.md` §1

---

## ADR-49: Repo GitHub (2026-07-05)

**Status**: SHIPPED
**Context**: Repository location.
**Decision**: Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
**Consequences**: Single source of truth.
**Reference**: `CLAUDE.md` §1

---

## ADR-48: First Paying Customer (2026-07-05)

**Status**: SHIPPED
**Context**: Traction.
**Decision**: Currently 1 real paying customer (jiya makeover); first invoice INV/2026-27/0001.
**Consequences**: First revenue verified.
**Reference**: `CLAUDE.md` §1

---

## ADR-47: Architecture Map (2026-07-05)

**Status**: SHIPPED
**Context**: System design.
**Decision**: Internet ──> Caddy (host, TLS leadsgenai.in) ──> leadgen_app :8000 (FastAPI, Docker, uvicorn WEB_CONCURRENCY=2, HTTP-only) ├── Postgres leadgen_db ── via PgBouncer :6432 (SQLite = rollback-backup only) ├── Redis leadgen_redis :6379 (Celery broker + call-state + cache; DLQ = dlq:failed_tasks) ├── Qdrant 127.0.0.1:6333 (RAG: single kb_main, namespaces niche:/client:<id>/skills) ├── leadgen_worker (Celery, concurrency=4) + leadgen_scheduler (beat) [--profile celery] ├── FreeSWITCH + WS voice: /api/telephony/vobiz/stream/{token} (L16/16k) └── Obs stack: Prometheus/Grafana/Alertmanager/Loki/Tempo/Uptime/Gatus (~13+ containers).
**Consequences**: Full architecture documented.
**Reference**: `CLAUDE.md` §2

---

## ADR-46: App ~700+ Routes (2026-07-05)

**Status**: SHIPPED
**Context**: System scale.
**Decision**: App ~700+ routes; frontend/ = server-rendered HTML (28-tab marketing.html, /app/automation Mission Control, /app/office HQ, 4 dashboards = 1 admin + 3 customer forks).
**Consequences**: Large system scope.
**Reference**: `CLAUDE.md` §2

---

## ADR-45: External Deps Purpose (2026-07-05)

**Status**: SHIPPED
**Context**: Integration inventory.
**Decision**: External deps (purpose · detail in `memory/integrations.md`): see ADR-67 through ADR-55 above.
**Consequences**: All integrations documented.
**Reference**: `CLAUDE.md` §2

---

## ADR-44: Install Dev (2026-07-05)

**Status**: SHIPPED
**Context**: Development setup.
**Decision**: Install (dev, py3.12): `python -m venv .venv` then `.venv\Scripts\pip install --no-deps -r requirements.lock.txt` (lock = single source; requirements.txt/pyproject = reference only).
**Consequences**: Reproducible dev environment.
**Reference**: `CLAUDE.md` §3

---

## ADR-43: Run Dev (2026-07-05)

**Status**: SHIPPED
**Context**: Development setup.
**Decision**: Run dev: `.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env --port 8000` [UNVERIFIED locally — import verified via prod_check]. `--env-file .env` skip MAT karo — `app/main.py` `load_dotenv` NAHI karta, isliye `.env`-mein-only keys (jaise `TYPESAFE_API_KEY`) `os.getenv` ko nahi dikhte aur integration chup-chaap INERT rehta hai.
**Consequences**: Must pass `--env-file .env` for local dev.
**Reference**: `CLAUDE.md` §3

---

## ADR-42: Key State (2026-07-05)

**Status**: SHIPPED
**Context**: Security.
**Decision**: Key state (value kabhi print nahi hoti): `python scripts/typesafe_status.py --probe`.
**Consequences**: Key status checkable without exposing value.
**Reference**: `CLAUDE.md` §3

---

## ADR-41: Tests Full (2026-07-05)

**Status**: SHIPPED
**Context**: Testing.
**Decision**: Tests (full): `scripts\run_tests.bat` → phir `pytest_run.log` Read karo (~80+ green; full suite team_pulse area pe HANG ho sakta — targeted suites prefer).
**Consequences**: Test verification procedure defined.
**Reference**: `CLAUDE.md` §3

---

## ADR-40: Test Targeted (2026-07-05)

**Status**: SHIPPED
**Context**: Testing.
**Decision**: Test (targeted/contract): `.venv\Scripts\python.exe -m pytest tests/test_billing_truth_2026.py -q`.
**Consequences**: Quick targeted tests available.
**Reference**: `CLAUDE.md` §3

---

## ADR-39: Lint (2026-07-05)

**Status**: SHIPPED
**Context**: Code quality.
**Decision**: Lint: `.venv\Scripts\python.exe -m ruff check app` (CI me non-blocking).
**Consequences**: Linting in CI.
**Reference**: `CLAUDE.md` §3

---

## ADR-38: Verify Gate (2026-07-05)

**Status**: SHIPPED
**Context**: Quality gates.
**Decision**: Verify gate: `.venv\Scripts\python.exe scripts\prod_check.py` + secrets scan `scripts\check_secrets.py` (ya `/verify` slash command).
**Consequences**: Pre-deploy verification.
**Reference**: `CLAUDE.md` §3

---

## ADR-37: Build Deploy Manual (2026-07-05)

**Status**: SHIPPED
**Context**: Deployment.
**Decision**: Build+Deploy (MANUAL — CI `deploy-vps.yml` = GATE-ONLY, `DEPLOY_ENABLED` unset): Windows git push (`C:\PROGRA~1\Git\cmd\git.exe`) → SSH `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204` → `cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &` phir `/tmp/dep.log` poll karo.
**Consequences**: Manual deployment procedure.
**Reference**: `CLAUDE.md` §3

---

## ADR-36: Deploy Script Canonical (2026-07-05)

**Status**: SHIPPED
**Context**: Deployment discipline.
**Decision**: Ye script hi CANONICAL hai — docker commands haath se mat likho: wo APP_VERSION-mandatory karti hai (`:-latest` refuse), SAARE 5 app-image services deploy karti hai (skew rok-ti), pipefail rakhti hai, aur `/health.version == deployed sha` + per-container skew + smoke verify karke hi OK bolti hai (warna non-zero exit).
**Consequences**: Single deployment script ensures consistency.
**Reference**: `CLAUDE.md` §3

---

## ADR-35: DRY_RUN (2026-07-05)

**Status**: SHIPPED
**Context**: Deployment safety.
**Decision**: `DRY_RUN=1` = plan print. Detached isliye ki flaky tunnel build ko SIGHUP na kare.
**Consequences**: Dry-run mode available.
**Reference**: `CLAUDE.md` §3

---

## ADR-34: Full Runbook (2026-07-05)

**Status**: SHIPPED
**Context**: Documentation.
**Decision**: Full runbook: `memory/playbooks.md` + `hostinger-deploy` skill.
**Consequences**: Runbooks available.
**Reference**: `CLAUDE.md` §3

---

## ADR-33: Migrations (2026-07-05)

**Status**: SHIPPED
**Context**: Database.
**Decision**: Migrations: `alembic upgrade head` (prod: container me; `DB_CREATE_ALL=0` = Alembic-only).
**Consequences**: Migration procedure defined.
**Reference**: `CLAUDE.md` §3

---

## ADR-32: Async FastAPI (2026-07-05)

**Status**: SHIPPED
**Context**: Code style.
**Decision**: Async FastAPI; domain routers in `app/api/` (godfile-split 2026-06-20: growth/marketing routes ab `growth_revenue`/`growth_crm`/`growth_deliverability`/`growth_feature_flags` + `marketing_tools`/`marketing_models` me bhi), engines in `app/platform/`, voice in `app/voice_agent/` + `app/telephony/`, billing in `app/billing/`.
**Consequences**: Code organization defined.
**Reference**: `CLAUDE.md` §4

---

## ADR-31: Naming Convention (2026-07-05)

**Status**: SHIPPED
**Context**: Code style.
**Decision**: Naming: snake_case modules/functions, PascalCase classes; config via `app.config.settings` (pydantic-settings) + runtime flags via `os.getenv` at call-time.
**Consequences**: Consistent naming.
**Reference**: `CLAUDE.md` §4

---

## ADR-30: Error Handling (2026-07-05)

**Status**: SHIPPED
**Context**: Robustness.
**Decision**: Error handling: defensive try/except + graceful degradation — external API call KABHI route crash nahi karta; fail-OPEN for billing meters/tenant middleware, fail-CLOSED for compliance (DND lookup) + webhook signatures in prod.
**Consequences**: Graceful degradation.
**Reference**: `CLAUDE.md` §4

---

## ADR-29: Logging (2026-07-05)

**Status**: SHIPPED
**Context**: Observability.
**Decision**: Logging: `from app.utils.logger import setup_logger; logger = setup_logger(__name__)`; Sentry auto in production.
**Consequences**: Structured logging.
**Reference**: `CLAUDE.md` §4

---

## ADR-28: Feature Pattern (2026-07-05)

**Status**: SHIPPED
**Context**: Feature flags.
**Decision**: Feature pattern: env-flag-gated, INERT default, additive over rewrite; comments often Hinglish; naya admin feature = UI tab SAATH hi (API-only = adhoora).
**Consequences**: Feature flags managed.
**Reference**: `CLAUDE.md` §4

---

## ADR-27: ML Assets (2026-07-05)

**Status**: SHIPPED
**Context**: Performance.
**Decision**: ML assets: image-bake + off-loop load (`asyncio.to_thread`) + deadline + disable-switch — public endpoint me KB/ML = thread + hard timeout (3 prod-downs isi se).
**Consequences**: ML loading won't block requests.
**Reference**: `CLAUDE.md` §4

---

## ADR-26: Loop Engineer Mode Triggers (2026-07-05)

**Status**: SHIPPED
**Context**: Development workflow.
**Decision**: Loop Engineer mode triggers: /loop /audit /fix /harden /production-ready /scheduler /agent-loop.
**Consequences**: Enter loop engineer mode on these triggers.
**Reference**: `CLAUDE.md` §0

---

## ADR-25: Permanent Rules (2026-07-05)

**Status**: SHIPPED
**Context**: Loop discipline.
**Decision**: Permanent rules: never stop at audit · never "done" without proof · no fake/stubbed/placeholder work passed off as working (real `/demo`/SVG-fallback/INERT-flag/test-double = fine) · never weaken a compliance gate (§5) or security · never ignore existing architecture (copy neighbour) · never duplicate routes/pages/workflows (grep all split routers first) · always check the affected cross-system touch-points (callers/routes/tests/scheduler/workers/Postgres/Redis/Qdrant/voice-both-paths/dashboards/admin/billing).
**Consequences**: Quality discipline.
**Reference**: `CLAUDE.md` §0

---

## ADR-24: Read First (2026-07-05)

**Status**: SHIPPED
**Context**: Loop workflow.
**Decision**: Read first: `progress.md` (loop ledger) + this file, before touching anything.
**Consequences**: Context preserved.
**Reference**: `CLAUDE.md` §0

---

## ADR-23: After Every Loop (2026-07-05)

**Status**: SHIPPED
**Context**: Loop workflow.
**Decision**: After every loop: append a `## Loop Run` block to `progress.md` (Date / Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority).
**Consequences**: Loop ledger updated.
**Reference**: `CLAUDE.md` §0

---

## ADR-22: Verify Checkpoint (2026-07-05)

**Status**: SHIPPED
**Context**: Loop workflow.
**Decision**: Verify checkpoint each loop: targeted pytest + `prod_check.py` + `/health`=`environment:production` (§6 Definition of Done). Reply in the CANONICAL 9-field loop format (`docs/LOOP_ENGINEER.md`): Goal / Inspected / Problems Found / Changed / Tests Run / Verification Evidence / Risks / Remaining / Next Highest Priority.
**Consequences**: Loop verification standardized.
**Reference**: `CLAUDE.md` §0

---

## ADR-21: Highest-Impact Order (2026-07-05)

**Status**: SHIPPED
**Context**: Loop workflow.
**Decision**: Highest-impact order = `docs/LOOP_ENGINEER.md`, BUT `## Current State` sprint goal wins when it conflicts.
**Consequences**: Prioritization guidance.
**Reference**: `CLAUDE.md` §0

---

## ADR-20: Stays Inside Gates (2026-07-05)

**Status**: SHIPPED
**Context**: Loop discipline.
**Decision**: Stays inside the gates: §5 compliance + secrets, §6 DoD, §8 no commit/push/deploy without the user asking. A "fix" that weakens a compliance gate = ABORT, not a fix.
**Consequences**: Compliance never weakened.
**Reference**: `CLAUDE.md` §0

---

## ADR-19: Full Spec (2026-07-05)

**Status**: SHIPPED
**Context**: Documentation.
**Decision**: Full spec (8 role defs · permanent rules · loop anatomy · cross-system inspect list · 15-item production-ready checklist · canonical 9-field output format): `docs/LOOP_ENGINEER.md`.
**Consequences**: Complete spec available.
**Reference**: `CLAUDE.md` §0

---

## ADR-18: Token Discipline (2026-07-05)

**Status**: SHIPPED
**Context**: Token management.
**Decision**: Token discipline: Yeh file har turn load hoti hai — lean rakho. Dated history → `docs/SESSION_LOG.md` (auto-load NAHI). Deep knowledge → `memory/` (section 9). Build/incident logs YAHAN mat likho. Naya session / cold-start? `docs/HANDOFF.md` = master handoff (infra map, sharp edges, SOP pointers). (2026-07-05).
**Consequences**: Token usage optimized.
**Reference**: `CLAUDE.md` preamble

---

## ADR-17: Code vs Memory Conflict (2026-07-05)

**Status**: SHIPPED
**Context**: Knowledge management.
**Decision**: Code vs memory conflict = code wins — phir memory fix karo.
**Consequences**: Code is source of truth.
**Reference**: `CLAUDE.md` preamble

---

## ADR-16: Project Charter (2026-07-05)

**Status**: SHIPPED
**Context**: Project definition.
**Decision**: Project charter: FastAPI SaaS (LIVE: https://leadsgenai.in, single Hostinger VPS Mumbai) that sells DO alag products to small Indian local businesses.
**Consequences**: Clear project scope.
**Reference**: `CLAUDE.md` §1

---

## ADR-15: Two Products (2026-07-05)

**Status**: SHIPPED
**Context**: Product definition.
**Decision**: (1) AI Automated Marketing = MAIN product — Main ₹1,999/mo + Combo/Advanced ₹5,999/mo (voice callback sirf ek FEATURE, 500 min); (2) AI Voice Calling Agent = standalone full AI telecaller, flat per niche-band ₹4,999/₹9,999/₹19,999/mo (DLT-gated for cold outbound).
**Consequences**: Two distinct products.
**Reference**: `CLAUDE.md` §1

---

## ADR-14: Money Path Complete (2026-07-05)

**Status**: SHIPPED
**Context**: Business model.
**Decision**: Money path: free lead magnets (`/audit`, `/site-audit`, `/demo`) + programmatic SEO + auto email-outreach → inquiry → `/pricing` → `/start` → manual UPI (CANONICAL — owner decision 2026-08-05, ADR/issue #243 closed not_planned; Stripe REMOVED 2026-07-10, Razorpay REMOVED 2026-06-18, so `PROVIDER_VERIFIED` is unreachable BY DESIGN) → subscription + top-up minute packs.
**Consequences**: Complete revenue path.
**Reference**: `CLAUDE.md` §1

---

## ADR-13: Entire AI Stack Free (2026-07-05)

**Status**: SHIPPED
**Context**: Cost constraint.
**Decision**: Entire AI stack = FREE providers only (user mandate — koi paid STT/TTS/LLM nahi).
**Consequences**: No AI costs.
**Reference**: `CLAUDE.md` §1

---

## ADR-12: Marketing + Voice Bundle USP (2026-07-05)

**Status**: SHIPPED
**Context**: Marketing.
**Decision**: "Marketing + voice bundle" USP framing GALAT hai — use mat karo.
**Consequences**: Avoid incorrect positioning.
**Reference**: `CLAUDE.md` §1

---

## ADR-11: Repo Location (2026-07-05)

**Status**: SHIPPED
**Context**: Source control.
**Decision**: Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
**Consequences**: Single repo.
**Reference**: `CLAUDE.md` §1

---

## ADR-10: First Paying Customer (2026-07-05)

**Status**: SHIPPED
**Context**: Traction.
**Decision**: Currently 1 real paying customer (jiya makeover); first invoice INV/2026-27/0001.
**Consequences**: First revenue verified.
**Reference**: `CLAUDE.md` §1

---

## ADR-9: 1 Cr MRR Target (2026-07-05)

**Status**: SHIPPED
**Context**: Business target.
**Decision**: Operating target: # ₹1,00,00,000 NET COLLECTED REVENUE PER MONTH across the two owner projects.
**Consequences**: Primary business target.
**Reference**: `CLAUDE.md` §2

---

## ADR-8: Planning Reference (2026-07-05)

**Status**: SHIPPED
**Context**: Financial planning.
**Decision**: Planning reference: approximately ₹3.33 lakh collected revenue/day. If an equal contribution scenario: approximately ₹1.67 lakh/day/project. Never use the historically incorrect: ₹33.33 lakh/day.
**Consequences**: Correct planning numbers.
**Reference**: `CLAUDE.md` §2

---

## ADR-7: Revenue Tracking (2026-07-05)

**Status**: SHIPPED
**Context**: Financial tracking.
**Decision**: Track separately: gross collected cash, refunds, net collected revenue, new revenue, recurring revenue, setup revenue, renewal revenue, expansion revenue.
**Consequences**: Detailed revenue tracking.
**Reference**: `CLAUDE.md` §2

---

## ADR-6: Do Not Count Fake Revenue (2026-07-05)

**Status**: SHIPPED
**Context**: Revenue accounting.
**Decision**: Do not count these as collected revenue: leads scraped, emails sent, calls attempted, meetings booked, proposals produced, invoices generated, payment links generated, verbal intent — until actual payment evidence exists.
**Consequences**: Only real cash counts.
**Reference**: `CLAUDE.md` §2

---

## ADR-5: Dynamic Run-Rate (2026-07-05)

**Status**: SHIPPED
**Context**: Planning.
**Decision**: For real operations, dynamically calculate: `remaining monthly target / remaining operating days` and display the required daily run-rate.
**Consequences**: Adaptive planning.
**Reference**: `CLAUDE.md` §2

---

## ADR-4: Evergreen Prompt (2026-07-05)

**Status**: SHIPPED
**Context**: Prompt design.
**Decision**: Do not trust SHA values, PR numbers, branch names, production versions, container IDs, queue counts, feature flags, provider status, customer counts or runtime claims inherited from an older session.
**Consequences**: Always verify current state.
**Reference**: `CLAUDE.md` §3

---

## ADR-3: Same-Day Execution (2026-07-05)

**Status**: SHIPPED
**Context**: Execution discipline.
**Decision**: The owner expects the maximum achievable implementation to be completed TODAY DURING THE CURRENT EXECUTION SESSION.
**Consequences**: No deferral of executable work.
**Reference**: `CLAUDE.md` §4

---

## ADR-2: Operating Loop (2026-07-05)

**Status**: SHIPPED
**Context**: Execution workflow.
**Decision**: Today's operating loop is: VERIFY → FIX → TEST → REVIEW → MERGE/DELIVER → DEPLOY WHEN ELIGIBLE → LIVE VERIFY → MEASURE → RECORD → NEXT TASK.
**Consequences**: Standardized workflow.
**Reference**: `CLAUDE.md` §4

---

## ADR-1: Evidence-Backed State (2026-07-05)

**Status**: SHIPPED
**Context**: Verification.
**Decision**: By the end of the run, each P0/P1 domain inspected today must carry an evidence-backed state such as: PRODUCTION-PROVEN, LIVE-VERIFIED, TEST-PROVEN, READY-TO-DEPLOY, PARTIAL, GATED-INERT, EXTERNALLY-BLOCKED.
**Consequences**: No unverified claims.
**Reference**: `CLAUDE.md` §4

---

*End of ADR log. New entries go at the TOP.*
