# Enterprise / Launch / Revenue / Automation Readiness — 2026-08-08

Recovery + verification run by Claude Cloud (engineering lead role) in isolated worktree.
**This document is evidence, not narrative.** Every claim carries a fingerprint
(HEAD SHA · command · exit code · timestamp) or is labelled `UNVERIFIED`.

- Candidate branch: `claude/leadgen-enterprise-readiness-edf3a9`
- Candidate HEAD: `5ae5a4b9` (re-pointed onto `origin/main` — see CP0-F1)
- Deployed production: `42493e3f` (`/health.version`, probed 2026-08-08 07:09 UTC)
- Worktree: `C:\Users\Ratanshila\Documents\leadgenrationaiagent\.claude\worktrees\leadgen-enterprise-readiness-edf3a9`

Finding classes: `VERIFIED_BROKEN` · `WORKING_AND_PROVEN` · `WORKING_BUT_UNVERIFIED` ·
`OWNER_OR_EXTERNAL_BLOCKED` · `OPTIONAL_IMPROVEMENT`

---

## CHECKPOINT 0 — RECOVERED

### CP0-F1 `VERIFIED_BROKEN` (coordination) — local `main` is a dead pre-rewrite lineage

`origin/main` history was rewritten (secret/PII history purge). The rewrite re-based
everything after `76cbb2f6` (2026-06-17). Local `main` is the **pre-rewrite** copy.

Evidence (`git`, worktree, 2026-08-08):

| probe | result |
|---|---|
| `git merge-base HEAD origin/main` (pre-fix) | `76cbb2f6` — 2026-06-17 |
| `git rev-list --count origin/main..a42d869c` | `1802` |
| `git rev-list --count a42d869c..origin/main` | `1842` |
| `git diff --stat a42d869c b5b61231` | **empty** — identical trees, different SHAs |
| `git log origin/main --grep "untrack root prospect PII"` | `2cc695f0` / merge `b5b61231` (local twin: `108da99e` / `a42d869c`) |

So PR #265 exists twice: `a42d869c` (dead) and `b5b61231` (canonical).

**Branch lineage audit (all worktrees):**

| branch | sha | lineage |
|---|---|---|
| `main` (local) | `a42d869c` | **DEAD** — ahead 1802, base 2026-06-17 |
| `cursor/swara-paid-free-faq-fix` | `e8d34921` | **DEAD** — ahead 1801, base 2026-06-17 · **35 uncommitted files** |
| `fix/admin-harden-wave1` | `eaf5a39f` | healthy (base 2026-08-07) |
| `opencode/bernstein-pr-orchestration-pilot-2026-08-07` | `c8ca6184` | healthy |
| `fix/d2-post-prospect-harvest` | `091e1109` | healthy |
| `feat/call-lead-crm-sync` | `7962730a` | healthy |
| `fix/safe-settings-snapshot` | `49984af1` | healthy |
| `fix/admin-auth-boot-deploy-race`, `feat/coord-hub-heartbeat-script`, `fix/admin-master-blueprint-nav`, `fix/reply-auto-send-interaction-log`, `fix/voice-paid-free-faq` | — | merged into origin/main |

**Impact:** a PR from `cursor/swara-paid-free-faq-fix` would present ~1801 phantom commits
and could re-introduce the purged history. This is an **Owner action** — the primary
checkout is Cursor-owned and dirty; not touched by this session.

**This session's fix (own branch only):**
`git checkout -B claude/leadgen-enterprise-readiness-edf3a9 origin/main` → HEAD `5ae5a4b9`,
`git merge-base --is-ancestor HEAD origin/main` = 0. Working tree clean.

### CP0-F2 `VERIFIED_BROKEN` (docs) — three context docs each state a different production SHA

| doc | claims | reality |
|---|---|---|
| `docs/context/CURRENT_STATE.md` | prod `33651cfc`, also `e06687c7` in two places | wrong |
| `docs/context/ACTIVE_WORK.md` | prod `/health` = `084cd990` | wrong |
| `docs/context/SESSION_HANDOFF.md` | base `31169c7` | stale |
| **live probe** | **`42493e3f`** | authoritative |

`CURRENT_STATE.md` also self-contradicts (`33651cfc` in §Production SHA vs `e06687c7` in
§Production health). Fixed in this branch — see CP0 remediation.

### CP0-F3 truth ledger (probed 2026-08-08 07:09 UTC, `curl https://leadsgenai.in/health{,/ready}`)

```
/health       {"status":"healthy","version":"42493e3f","environment":"production","uptime":"1h 7m 16s"}
/health/ready database=healthy redis=healthy llm=configured(groq)
              disk free_gb=49.48 free_percent=25.7
              memory used_percent=89.5 available_mb=1686.0
```

- Deployed `42493e3f` = `origin/main~1` (PR #281 admin auth boot race). `origin/main`
  tip `5ae5a4b9` (PR #280 coord-hub heartbeat script) is **not yet deployed**.
- Open PRs: #282 (ready, `fix/admin-harden-wave1`), #284 / #283 (Cursor, draft),
  #271 (OpenCode, draft).
- Open issues: #240 (Revenue P0 — immutable order reference on interested-offer →
  payment seam), #185 (customer input, jiya-makeover brief).

### CP0-F4 `OPTIONAL_IMPROVEMENT` — LLM chain doc drift

`/health/ready` reports `llm_chain_head[0] = groq:openai/gpt-oss-20b`; `CLAUDE.md` §2 and
`memory/integrations.md` describe **Mistral** as LLM primary. Runtime is authoritative;
docs are stale. No functional defect.

### CP0-F5 `WORKING_BUT_UNVERIFIED` → see CP5 — production memory pressure

`memory.used_percent = 89.5`, `available_mb = 1686`. Recorded here as a primitive
observation at the recovery step; assessed under Checkpoint 5 (capacity).

---

## CHECKPOINT 1 — ARCHITECTURE & COORDINATION

### CP1-1 `WORKING_AND_PROVEN` — every static gate green at `5ae5a4b9`

All eight canonical audit scripts run with cwd = this worktree, interpreter =
repo `.venv` (`ROOT = Path(__file__).resolve().parent.parent`, so they scanned
**this** tree, not the primary checkout).

| script | exit | headline |
|---|---|---|
| `prod_check.py` | 0 | 1267 routes · 49 pages 0 gaps · automation 0 gaps · explorer 356 nodes/349 edges/0 orphans · API.md 1289 ops in sync |
| `check_secrets.py` | 0 | clean |
| `check_html_js.py` | 0 | clean |
| `cross_path_audit.py` | 0 | clean |
| `deep_wiring_audit.py` | 0 | handlers=0 apis=0 anchors=0 gaps |
| `automation_health_audit.py` | 0 | ALL GREEN (local store — not production data) |
| `automation_wiring_audit.py` | 0 | 364 flags declared · 2 reserved-future · **0 never read** · 43 staff jobs 0 undispatchable · 44 beat tasks 0 unrecognized |
| `explorer_sync.py --check` | 0 | 89/89 engine coverage · no dangling edges · no orphans |

Scheduling parity (`STAFF_JOBS` ↔ Celery `beat_schedule` ↔ `scheduler_config.JOB_META`)
is machine-checked by `automation_wiring_audit.py` and reports zero drift. **No
new orchestrator, scheduler, registry, task DB or agent was created by this session.**

### CP1-2 `OWNER_OR_EXTERNAL_BLOCKED` — coordination defect, see CP0-F1

The one-writer / isolated-branch rules are being honoured by five of seven
feature branches. The two exceptions are on the dead lineage and one of them
(`cursor/swara-paid-free-faq-fix`) holds **35 uncommitted files** in the primary
checkout. Only the Owner can resolve this; this session did not touch it.

### CP1-3 file-ownership map used by this session (from open-PR heads)

| owner | files (do not edit) |
|---|---|
| PR #284 Cursor | `app/api/activation.py`, `app/api/automation_flags.py`, `scripts/automation_wiring_audit.py`, `.env.example`, `tests/test_upi_pending_digest_probe.py` |
| PR #283 Cursor | `docs/context/ACTIVE_WORK.md`, `docs/context/SESSION_HANDOFF.md`, `.claude/settings.json`, `docs/AGENT_WORK_RULES.md`, `docs/coordination/*`, `scripts/agent_team_*`, `scripts/canary_*`, `memory/backlog.md`, `memory/decisions.md` |
| PR #282 | `app/lead_scraper/google_maps.py`, `app/platform/tenant_quarantine.py`, `scripts/vps_enable_automation_max_flags.py` + its tests |
| PR #271 OpenCode | `tools/pr_factory/**`, `app/platform/automation_flag_manifest.py`, `docs/PR_FACTORY.md` |
| Cursor dirty tree | `docs/context/CURRENT_STATE.md`, `docs/context/AUTOMATION_MAX_READINESS_MATRIX.md`, `frontend/admin_dashboard.html`, `app/api/activation.py`, `tests/test_reply_offer_payment_block.py`, +30 more |
| **this session** | `app/platform/upi_payments.py`, `tests/test_upi_order_close.py`, `docs/context/ENTERPRISE_READINESS_2026-08-08.md`, `docs/context/PRODUCTION_TRUTH.md` |

`docs/context/CURRENT_STATE.md` / `ACTIVE_WORK.md` / `SESSION_HANDOFF.md` are
**contested** — their SHA drift (CP0-F2) is reported to the Owner rather than
edited here, to preserve one-writer-per-file.

---

## CHECKPOINT 2 — PRODUCT 1 (launch + revenue)

Product 1 recovered from source, not from the brief: `app/marketing/packages.py`
→ public plans are **Starter "AI Marketing Automation" ₹1,999** and **Combo
"Marketing + AI Voice" ₹5,999**; `Growth` is `public: False` (legacy hidden) and
is correctly filtered by `get_public_packages()` (`packages.py:291`).

### CP2-1 `VERIFIED_BROKEN` (latent) → **FIXED IN THIS BRANCH** — an approved UPI payment never closed its order (double-activation hole)

> **Reachability, stated up front so this is not misread.** Because nothing
> currently issues an offer (CP2-2), `order_ref` is never recorded in production,
> so this path has **never fired and is not firing today — no invoice has been
> duplicated**. It is a latent defect: the moment anyone wires issuance (packet
> item 6, the obvious next step) it becomes live. Fixed first, deliberately, so
> that wiring cannot open the hole. Merge urgency is "land before #240 gets a
> producer", not "stop a leak".

**Root cause.** `app/platform/upi_payments.py` consumes an offer reference but
never performs the terminal transition its own logic depends on. The order gate
comment (`upi_payments.py:423-430`) states the design explicitly:

> "once the owner approves and the offer flips to `paid`, or once it expires,
> `resolve_payable` refuses …"

`offers.mark_status()` had **zero callers in the entire app**:

```
$ grep -rn "offers\.\(issue_offer\|mark_status\|resolve_payable\|get_offer\|list_offers\)" --include=*.py app/
app/platform/upi_payments.py:436:  order, reason = offers.resolve_payable(order_ref_s)
```

**Failure scenario (concrete).** Offer `LG-…` issued for `starter`.
1. `submit_payment(order_ref=LG-…, upi_ref=TXN1)` → pending. Owner approves →
   `_try_activate` → plan active, GST invoice fired, offer still `issued`.
2. `submit_payment(order_ref=LG-…, upi_ref=TXN2)` — the idempotency guard keys on
   `(upi_ref, client_id, plan)` (`upi_payments.py:398-408`), so a different
   `upi_ref` slips through; `resolve_payable` still returns the offer as payable.
3. Owner approves the second row. `record.get("activated")` is falsy on this
   *new* row, so `_try_activate` runs again → `reset_usage_period()` re-zeroes a
   metered client's usage **and** `_fire_gst_invoice` issues a second Rule-46
   sequential invoice for one payment.

That is a revenue-truth and invoice-integrity defect, not a cosmetic one.

**Fix (additive, no flag).** New `_close_order()` helper marks the bound offer
`paid`:
- in `decide()` **before** the activation branches — the owner confirming the bank
  credit *is* the payment event, so an activation that fails or is deferred
  (unbound guest client) must still close the order;
- in the `submit_payment` auto-activate path;
- **not** on reject — a rejected claim means the money never arrived, so the real
  payer still needs a payable reference;
- best-effort and never-raise: an offer-store failure logs a warning and leaves
  the already-persisted payment untouched.

**Evidence.** New `tests/test_upi_order_close.py` (8 tests). Proven to fail
without the fix (`git stash push -- app/platform/upi_payments.py`):

```
PRE-FIX   5 failed  — approve_marks_offer_paid, paid_order_cannot_be_submitted_again,
                      approve_closes_order_even_when_client_is_unbound,
                      auto_activation_closes_the_order, re_approve_is_idempotent
          3 passed  — the negative controls (reject stays payable, no-order_ref
                      unaffected, store-failure never breaks approval)
POST-FIX  57 passed — test_upi_order_close.py + test_upi_order_ref_binding.py
                      + test_offers_order_ref.py + test_offers_commercial_authority.py
```

### CP2-2 `VERIFIED_BROKEN` — the whole `order_ref` reconciliation seam is inert: nothing issues an offer

`app/marketing/offers.py` is a complete, well-documented, tested subsystem
(immutable `LG-<uuid4hex>` refs, supersede chain, expiry, price freeze against
retro-quoting). The consumer side is hardened (`/api/upi/submit` accepts
`order_ref` but re-resolves it server-side and refuses unknown / expired /
superseded / already-paid / plan-mismatched references).

**`offers.issue_offer()` has zero non-test callers.** No route, no scheduler job,
no reply path mints an order, and `grep -rn "order_ref" frontend/` returns
nothing — so the customer pay flow can never send one.

Therefore in production the offer store is empty, `order_ref` is always absent,
and issue #240's Definition of Done ("an owner approving a UPI credit in
`/upi/pending` sees the exact deal it belongs to") is **not met**. Revenue
reconciliation is still a name match.

**Not fixed here — deliberately.** The natural producer is the interested-reply
offer seam in `app/platform/reply_agent.py`, and Cursor holds
`tests/test_reply_offer_payment_block.py` modified in the primary checkout. Under
the one-writer rule that file set is contested. The remaining work is specified
in the Owner Action Packet as a single scoped slice.

Note CP2-1's fix is the correct ordering regardless: it closes the replay hole
*before* anyone wires issuance and makes it reachable.

## CHECKPOINT 3 — PRODUCT 2 (launch + revenue)

Product 2 recovered from source: `app/marketing/voice_packages.py` — standalone AI
voice telecaller, flat per niche-band ₹4,999 / ₹9,999 / ₹19,999 per month. This is
a **separate product**, not a bundle with Product 1.

### CP3-1 `WORKING_AND_PROVEN` — the 30-calls-per-session contract is atomic, idempotent, and pre-provider

The brief asked whether a 30-per-session contract exists. It does:
`voice_launch.session_cap()` reads `VOICE_CALLS_PER_SESSION`, **default 30**,
hard-clamped ≤200 (`voice_launch.py:394`).

`reserve_session_slot()` (`voice_launch.py:764`) is a **single Redis `INCR`** —
multi-worker safe by construction, not by lock discipline:

- over-cap increment is **rolled back** (`SET key cap`) so a rejected reservation
  cannot permanently inflate the counter;
- Redis unavailable → `counter_unavailable` → **fail-CLOSED** (no dial);
- no active session → `no_session`; emergency stop → `session_stopped`;
- `release_session_slot()` decrements (floored at 0) when a slot was reserved but
  never provider-accepted;
- reservation sits **before the dispatch boundary** in `app/tasks/calling.py:486+`,
  after per-lead eligibility — so a blocked attempt never reaches the provider.

`tests/test_voice_session.py` already pins exactly the properties the brief
demands, and they pass at this HEAD:

| property | test |
|---|---|
| exactly cap, then attempt 31 rejected | `test_exactly_cap_reservations_then_31st_blocked` |
| **concurrent** attempts (asyncio.gather, 2× cap) still ≤ cap | `test_concurrent_reservations_still_exactly_cap` |
| **31st blocked before any provider request** | `test_dialer_31st_blocked_before_any_provider_request` |
| idempotency: claim once, duplicate blocked | `test_idem_claim_once_then_duplicate_blocked` |
| Redis down → fail-closed | `test_redis_down_fail_closed` |
| worker restart does NOT reset the counter | `test_worker_restart_does_not_reset_counter` |
| compliance block releases the reserved slot | `test_dialer_compliance_block_releases_session_slot` |
| daily cap enforced before session cap | `test_dialer_daily_cap_still_enforced_before_session` |

Evidence: `pytest tests/test_voice_session.py tests/test_voice_launch.py -q` →
**49 passed**, HEAD `5ae5a4b9`+fix, 2026-08-08.

The daily ceiling (`VOICE_DAILY_CALL_CAP`, default 100, hard-clamped ≤100) uses the
same atomic-INCR + fail-closed pattern with a 36h TTL keyed on the IST date.

### CP3-2 `WORKING_AND_PROVEN` — the per-lead compliance spine is fail-closed and single-source

`is_lead_eligible_for_voice_call()` (`voice_launch.py:521`) composes, cheapest-first:
admin kill switch → phone sanity → `dial_gate.check` (test-mode allowlist,
phone-type gate, learned IVR blocklist) → `compliance.get_compliance_gate().check`
(DND fail-closed, TRAI calling window, DLT/140, consent opt-out). It creates **no
new gate** — it reuses the canonical ones. Any internal error ⇒ promotional
**ineligible**. A `compliance_disabled` bypass is itself surfaced as unsafe rather
than silently honoured.

### CP3-3 `OWNER_OR_EXTERNAL_BLOCKED` — what Product 2 still cannot claim

- **No real outbound call was placed by this session.** Provider call creation,
  status callbacks, greeting/latency, recording and per-call cost are therefore
  `WORKING_BUT_UNVERIFIED` here. They need an Owner-approved allowlisted canary.
- Prod values of the calling flags could not be read from this environment
  (no `.env` access, `/api/activation/readiness` correctly returns 401).

---

## CHECKPOINT 4 — AUTOMATION READINESS

### CP4-1 `WORKING_AND_PROVEN` — flag/job/beat wiring is machine-verified, with semantic typing

`scripts/automation_wiring_audit.py` (exit 0) at this HEAD:
**364 flags declared · 2 reserved-future · 0 never read · 43 staff jobs, 0 undispatchable ·
44 staff beat-tasks, 0 unrecognized.**

The brief's warning about treating every config entry as a boolean is already
handled in-repo. `app/platform/automation_flag_manifest.py` types them, e.g.:

- `PLATFORM_DIAL_DAILY` — *"Boolean arm; cap=PLATFORM_DIAL_LIMIT"*
- `PLATFORM_DIAL_LIMIT` — *"value-carrying daily dial attempt ceiling (NOT a boolean)"*
- `VOICE_CALLS_PER_SESSION` — *"Redis-backed, reset ONLY via session lifecycle
  (worker restart NO); 31st attempt blocked before provider"*

`app/platform/platform_dial.py:85` even logs a warning when the name trap is hit.
This is the exact drift the brief asked to detect, and it is already closed.

### CP4-2 `OWNER_OR_EXTERNAL_BLOCKED` — protected controls: not touched, not re-verifiable from here

`WHATSAPP_AUTO_SEND` · `PLATFORM_DIAL_DAILY` · `REPLY_AUTO_SEND` · `UPI_AUTO_ACTIVATE` ·
`SELF_IMPROVE_LOOP`. **This session flipped nothing.** Each is recorded as
owner-armed by a dated decision (`PLATFORM_DIAL_DAILY` 2026-08-02 full-campaign
go-ahead; post-call WhatsApp 2026-08-03; `REPLY_AUTO_SEND` ADR-171; `UPI_AUTO_ACTIVATE`
armed-but-allowlist-scoped to one client id). Their **current** prod values require
an in-container probe the Owner must run — see the Action Packet.

### CP4-3 `WORKING_BUT_UNVERIFIED` — local automation-health green is N/A, not proof

`scripts/automation_health_audit.py` printed `ALL GREEN` including
`Recording Retention: ✅`. Reading the source (`automation_health_audit.py:437`):

```python
"retention_active": retention_enabled if telephony_configured else True,
```

Telephony is not configured locally, so that ✅ is an honest **N/A**, not evidence.
The same applies to `DLT`, `Opt-Out Enforced` and `High-Risk Approval`, and to
`DLQ Depth: 0` / `Queue Pending: 0` (local stores). **Do not quote this run as
production automation health.**

---

## CHECKPOINT 5 — ENTERPRISE READINESS

| # | domain | class | evidence |
|---|---|---|---|
| 1 | Security / authn / authz / RBAC | `WORKING_AND_PROVEN` | E19: 140 passed across 15 auth/RBAC/isolation suites; `/api/activation/readiness` + `/wizard` return 401 unauthenticated while only the coarse `/summary` is public |
| 2 | Tenant isolation | `WORKING_AND_PROVEN` (unit/HTTP) + 1 `WORKING_BUT_UNVERIFIED` | E19; but `test_live_tenant_isolation_proof.py` **skipped** — needs a real DB, so the live proof is not in evidence |
| 3 | Secrets / rotation | `WORKING_BUT_UNVERIFIED` | `check_secrets.py` exit 0; pre-commit runs `detect-secrets`, `bandit`, `detect private key` and a `no tracked personal-data CSV exports` hook — all Passed on this commit. **Open owner item:** the historically leaked `GEMINI_API_KEY` was scrubbed but deliberately **not rotated** (voice moved off Gemini); the burned key is still revocable in the Google console |
| 4 | Backups / restore / DR | `WORKING_BUT_UNVERIFIED` | `docs/DISASTER_RECOVERY.md` + rclone→Drive documented and previously restore-proven; **no drill run in this session** |
| 5 | SLO / monitoring / alerting | `WORKING_AND_PROVEN` (config) | `monitoring/alert_rules.yml` carries `HostMemoryHigh`, `HostDiskLow`, `ContainerHighMemory`, `RedisMainNearFull` etc. |
| 6 | Capacity / cost | `OPTIONAL_IMPROVEMENT` / RISK | see CP5-1 — one sample, alert not fired |
| 7 | Migrations / rollback | `WORKING_AND_PROVEN` | **single** alembic head `023_add_prospective_memory` across 23 revisions — no fork, no ambiguous `upgrade head`; `migrations.yml` CI green |
| 8 | Dependency / supply chain | **`VERIFIED_BROKEN`** | see CP5-3 — `security-scan.yml` is green but **29 Dependabot alerts are open** (8 high) |
| 9 | Privacy / DPDP retention | `WORKING_BUT_UNVERIFIED` | see CP5-2 |
| 10 | Billing / invoice / reconciliation | `VERIFIED_BROKEN` → 1 fixed, 1 open | CP2-1 (fixed) + CP2-2 (open) |
| 11 | Comms / consent / voice compliance | `WORKING_AND_PROVEN` (code path) | CP3-2 |
| 12 | Incident response / runbooks | `WORKING_AND_PROVEN` | `scripts/deploy_vps.sh` exact-SHA-mandatory; staging compose fail-closed on `APP_VERSION`; hardened GitHub deploy path with auto-rollback |

### CP5-1 `OPTIONAL_IMPROVEMENT` / **RISK** (capacity) — production is 0.5 percentage points from its own memory alert

> **One sample, no trend.** This is a single point-in-time reading taken 1h07m
> after a container restart. `HostMemoryHigh` has **not** fired. It is not
> classified broken — it is a headroom risk worth an Owner decision.

`/health/ready` at 2026-08-08 07:09 UTC: `memory.used_percent = 89.5`,
`available_mb = 1686`. `app/api/health.py:425` uses `psutil.virtual_memory()`, so on
this single VPS that is **host** memory ≈ 10.5 % available.

Two thresholds sit immediately above the current reading:
- `health.py:432` flips the check to `"warning"` at `>= 90`;
- `monitoring/alert_rules.yml:125` `HostMemoryHigh` fires at `< 0.10` available for 10m.

So the box is running with ~0.5 pp of headroom before it starts paging alerts, on a
host that also runs Postgres, Redis, Qdrant, FreeSWITCH, five app-image services and
~13 observability containers. Disk is at 25.7 % free (49.48 GB).

**Not "fixed" here on purpose** — raising a threshold would be weakening a gate, and
container `mem_limit` tuning is a production change requiring Owner approval. Flagged
for the Owner with the two candidate levers already named in the alert's own
description (container mem_limits, or leak check).

### CP5-3 `VERIFIED_BROKEN` (supply chain) — a green CI scan is hiding 29 open Dependabot alerts

Surfaced by the push itself, not by any gate this session ran:

```
remote: GitHub found 29 vulnerabilities on ...'s default branch
        (8 high, 16 moderate, 5 low)
```

Confirmed via `gh api .../dependabot/alerts` → **8 high, 16 medium, 5 low, all `open`**.
The high ones sit in the request path and the crypto path:

| package | advisory |
|---|---|
| `starlette` | SSRF + NTLM credential theft via UNC paths in `StaticFiles` |
| `starlette` | DoS via `multipart/form-data` |
| `starlette` | `request.form()` limits silently ignored for `x-www-form-urlencoded` |
| `cryptography` | vulnerable OpenSSL shipped in the wheels |
| `cryptography` | PKCS#7 `EnvelopedData` Bleichenbacher oracle |
| `cryptography` | duplicate self-signed intermediates → chain-building expense |
| `protobuf` | JSON recursion-depth bypass |
| `ecdsa` | Minerva timing attack on P-256 |

**Why the gates missed it.** `security-scan.yml` passing is a *different* assertion
from "no known-vulnerable dependency is pinned". `requirements.lock.txt` being the
single pinned source is exactly what makes the alerts actionable **and** what keeps
them frozen until someone bumps the lock. I originally scored this domain
`WORKING_AND_PROVEN` on the CI signal alone — that was wrong, and it is the same
"green dashboard hides the failure" shape this brief asks to hunt.

Not fixed here: bumping pins in `requirements.lock.txt` is a full-suite-revalidation
change and collides with nobody's branch but needs its own slice and its own test
budget. Added to the Owner packet as item 9.

### CP5-2 `WORKING_BUT_UNVERIFIED` (DPDP) — 90-day recording purge is report-only by default

`consent_ledger.retention_sweep()` reports files older than
`RECORDING_RETENTION_DAYS` (default 90) **always**, but **deletes only when
`RECORDING_RETENTION=1`** (`consent_ledger.py:710`). It is wired into the scheduler
(`team_scheduler.py:1176`). CLAUDE.md §5 lists 90-day recording retention as a DPDP
invariant, so whether the invariant actually holds depends entirely on one prod env
value this session cannot read. **Owner probe required** — if it is unset, recordings
are being reported, not purged.

---

---

# SESSION 2 — revalidation, CP5-3 remediation, CP2-2 handoff

## PHASE A — the reported checkpoint revalidated (independently, not trusted)

| claim | probe | verdict |
|---|---|---|
| PR #285 exists, draft, base `main` | `gh pr view 285` | confirmed — 3 files, `OPEN`, `isDraft: true` |
| PR head `b2a839f3` | `gh pr view` vs `git rev-parse HEAD` | **match** |
| `origin/main` = `5ae5a4b9` | `git fetch --prune; git rev-parse origin/main` | confirmed; branch 0 behind |
| production `42493e3f` | `curl /health` 07:53 UTC | confirmed, uptime 1h48m |
| worktree clean | `git status --porcelain` | clean |
| dead-lineage branches | `merge-base --is-ancestor` sweep | **unchanged** — `main` and `cursor/swara-paid-free-faq-fix` still on the 2026-06-17 base, primary checkout still 35 files dirty |

Nothing in the reported checkpoint had drifted, so its SHAs remain usable.

**PR #285 checks:** 11 SUCCESS, 1 IN_PROGRESS, and **`Trivy image scan (GHCR)` =
SKIPPED** — recorded under CP5-3 as a second reason the security badge was hollow.

**The eight payment/order tests re-verified** against the six properties named in
the brief: payment-confirmed offer closure ✅ · no closure on rejection ✅ ·
duplicate payment prevention ✅ (`test_paid_order_cannot_be_submitted_again` — the
replay is refused with `already_paid`) · no repeated `_try_activate` ✅ (only one
payment row survives for the order, so there is no second activation candidate) ·
no metered-usage reset ✅ and no duplicate Rule-46 GST invoice ✅ (both are
downstream of that single `_try_activate`, guarded by the same assertion).

## PHASE B — CP5-3 remediated in an isolated lane → **PR #286**

Branch `fix/dep-cve-2026-08-08`, worktree `C:\Users\Ratanshila\Documents\leadgen-secfix`,
base `origin/main` `5ae5a4b9`, head **`fb2aad72`**. Full ledger in
`docs/security/DEPENDENCY_REMEDIATION_2026-08-08.md` on that branch.

Kept out of PR #285 deliberately: different blast radius (every dependency vs one
function), different reviewer, and PR #285 must be mergeable on its own.

### CP5-3 root cause — the lock is not installable by a resolving pip

```
$ pip install "fastapi==0.141.1" "starlette==0.35.1"
ERROR: ResolutionImpossible
```

`fastapi==0.141.1` declares `starlette>=0.46.0`; the lock pinned **`starlette==0.35.1`,
released 2024-01-11**. `Dockerfile.lock:25` and both CI workflows install with
`--no-deps`, so pip never checked. **Four** declared constraints were violated:
`fastapi→starlette`, `sse-starlette→starlette`, `google-api-core→protobuf`, and —
found by the new gate on its own first CI run — `google-cloud-bigquery→packaging`
(`>=24.2.0` vs pinned `23.2`).

### Fixed: 8 pins, 7 of 8 highs cleared

`starlette 0.35.1→1.3.1` · `cryptography 48.0.0→50.0.0` · `protobuf 4.25.9→5.29.6` ·
`aiosmtplib 3.0.1→5.1.1` · `h2 4.4.0→4.4.1` · `setuptools 82.0.1→83.0.0` ·
`sentry-sdk 1.39.2→1.45.1` · `packaging 23.2→25.0`.

`starlette 1.3.1` is the **lowest** version clearing all seven of its advisories —
1.5.0 shipped the same day and was declined. `app/` imports only four long-lived
starlette symbols, all present in 1.3.1, which is why a 0.35→1.3 jump is far
smaller than it looks.

`packaging==25.0` was the one pin derived from a resolver error rather than an
advisory, so it was verified separately: a **resolving** (not `--no-deps`) dry-run
install of `packaging==25.0` together with all five packages the resolver named
(`google-cloud-aiplatform`, `google-cloud-bigquery`, `huggingface_hub`,
`marshmallow`, `onnxruntime`) exits 0 with no conflict.

### Accepted: 2 exceptions, justified and dated 2026-11-08

`ecdsa` (GHSA-wj6h-64fc-37mp, **no upstream fix**; unreachable because
`jwt_algorithm` is HS256, pinned by `test_jwt_algorithm_is_symmetric`) and `pytest`
(never imported by app code; two-major bump). `test_exceptions_have_not_expired`
turns the build RED when either lapses.

### Reachability distinction

GHSA-wqp7-x3pw-xc5r (UNC SSRF in `StaticFiles`) is **Windows-scoped**. Production
is `python:3.12-slim`, so it is not reachable there — but it is on the Windows dev
machines this repo is worked on daily. Fixed either way.

### Signal repaired without a second dashboard

`ci.yml`'s dependency scan was labelled `MUST-PASS` while ending in `|| true` and
auditing `requirements.txt` — a *reference* manifest. It now blocks, and moved to
the `tests` job to audit the **installed environment** (the `--no-deps` closure that
actually ships) from its own venv via `--path`. `security-scan.yml` was **not
touched** — it is uncommitted-dirty in the primary checkout with an in-flight owner
CRITICAL gate.

### The gate is proven on CI, not asserted

```
auditing installed environment at:
  /opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/site-packages
Found 1 known vulnerability, ignored 4 in 1 package
scrapy 2.17.0   PYSEC-2017-83   (no fix versions)
```

Two things matter in those lines. `--path` resolved to the **real 3.12 environment**,
so the audit describes the shipped closure rather than a re-resolved fiction. And
**not one of the eight remediated packages appears** — independent confirmation, from
a *different vulnerability database* than the one the fixes were derived from, that
the bumps landed and the CVEs are gone from the installed set.

The one finding is new: OSV carries `PYSEC-2017-83`, the Dependabot list did not. No
upstream fix exists; nothing imports `scrapy` (transitive via `advertools`) and the
advisory needs a files/images pipeline — no `S3FilesStore`, `FILES_STORE` or
`IMAGES_STORE` is configured anywhere in `app/` or `scripts/`. It is therefore a
**third** documented exception dated 2026-11-08, not a bump. Security-lane head is
now `150ce4a5`.

### CP5-4 `VERIFIED_BROKEN` (data integrity) — the test suite writes to a real customer's ledger

Found while verifying, unrelated to dependencies. Running the suite appended
real-looking events to `data/delivery_ledger/jiya-makeover.jsonl` — a **tracked**
file for the only paying customer:

```
{"at": "2026-08-08T08:39:49+00:00", "client_id": "jiya-makeover", "event": "post_approved", ...}
{"at": "2026-08-08T08:41:15+00:00", "client_id": "jiya-makeover", "event": "plan_activated", "detail": "starter", "actor": "backfill", ...}
```

`.gitignore` does not cover already-tracked files, so a `git add -A` after any test
run commits fabricated delivery events for a paying customer — corrupting the
customer-visible delivery proof Product 1 sells. Reverted, not committed. This is
the concrete mechanism behind `AGENT_WORK_RULES` R7. Needs its own slice
(`tmp_path`-scoped ledger fixture, or untrack the customer ledgers) — Owner item.

## PHASE C — bounded verification

The full suite was partitioned into **6 shards over 746 test files**, each with
`--timeout=90 --timeout-method=thread` and a 1500 s wall clock, specifically so the
documented `team_pulse` hang could not hide the rest.

| shard | files | result |
|---|---|---|
| 00 | 120 | **completed** — 0 failures, 10 declared skips, exit 0 |
| 01 | 119 | **completed** — 11 failures, **all expected**: only `test_dependency_security_floors.py`'s environment-dependent assertions, failing because the *primary venv is the vulnerable stack* (starlette 0.35.1). No other failure. |
| 02 | 127 | **completed** — 0 failures, exit 0 |
| 03 | 132 | **partial** — 0 failures at 68 %; still running when this session closed |
| 04 | 121 | **NOT EXECUTED** |
| 05 | 127 | **NOT EXECUTED** |

**Honest coverage: 366 of 746 files completed, ~90 in progress, 248 unexecuted.**
Unexecuted is its own category — it is neither a pass nor a skip, and the shards
that did not run are not evidence of anything. A timeout is likewise not a pass:
**zero timeouts** were recorded in the completed shards, and any that appear would
be reported as timeouts.

The shard design is the deliverable here regardless of how far it got: the
documented `team_pulse` hang can no longer swallow the whole suite, because a hang
is now bounded to one 90 s test inside one 1500 s shard and the other five still
report.

## PHASE D — CP2-2 handoff (no file conflict)

Independently re-verified on fresh `origin/main`: `offers.issue_offer()` still has
**zero** production callers. `reply_agent.py` and `admin_dashboard.html` remain
Cursor-owned, so **nothing was edited**.

`docs/missions/CP2-2_OFFER_PRODUCER_HANDOFF.md` carries a mission payload for the
**existing** Owner OS external-agent mechanism (`app/dev_control/external_agents`) —
no second ledger, no competing branch. It was validated against the canonical
schema locally: `Mission(**payload).validate()` → valid, state `CREATED`, risk
**`AMBER`** so it cannot self-advance without Owner approval. It carries the fresh
base SHA, isolated-worktree requirement, exclusive `allowed_paths` /
`prohibited_paths`, pricing/consent/idempotency/tenant constraints, required tests
and checks, rollback plan, the prohibition list, and the required finish state.

**Ordering constraint stated in the mission:** PR #285 must land first, or wiring
issuance re-opens the double-activation hole the moment it starts working.

---

## EVIDENCE LEDGER

Fingerprint = HEAD · command · exit code · result · time. Nothing below was re-run
once recorded; a re-run happens only if HEAD, command, config or environment changes.
Interpreter for every Python row: `C:\…\leadgenrationaiagent\.venv\Scripts\python.exe`
(the primary checkout's venv, used read-only). cwd for every row: this worktree.

| # | HEAD | command | exit | result | when (IST) |
|---|---|---|---|---|---|
| E1 | `5ae5a4b9` | `curl https://leadsgenai.in/health` | 0 | `version=42493e3f` `environment=production` `uptime=1h7m` | 12:39 |
| E2 | `5ae5a4b9` | `curl https://leadsgenai.in/health/ready` | 0 | db/redis healthy · llm groq · disk 25.7 % free · **mem 89.5 % used** | 12:39 |
| E3 | `5ae5a4b9` | `git merge-base --is-ancestor HEAD origin/main` | 0 | branch re-pointed, ancestry restored | 12:41 |
| E4 | `5ae5a4b9` | `git diff --stat a42d869c b5b61231` | 0 | **empty** — history-rewrite twins proven | 12:38 |
| E5 | `5ae5a4b9` | `scripts/prod_check.py` | 0 | 1267 routes · 49 pages 0 gaps · 1289 API ops in sync | 12:44 |
| E6 | `5ae5a4b9` | `scripts/check_secrets.py` | 0 | no secrets detected | 12:44 |
| E7 | `5ae5a4b9` | `scripts/check_html_js.py` | 0 | clean | 12:44 |
| E8 | `5ae5a4b9` | `scripts/cross_path_audit.py` | 0 | clean | 12:45 |
| E9 | `5ae5a4b9` | `scripts/deep_wiring_audit.py` | 0 | handlers=0 apis=0 anchors=0 gaps | 12:45 |
| E10 | `5ae5a4b9` | `scripts/automation_health_audit.py` | 0 | ALL GREEN — **local stores, N/A not proof** (CP4-3) | 12:45 |
| E11 | `5ae5a4b9` | `scripts/automation_wiring_audit.py` | 0 | 364 flags · 0 never read · 43 jobs · 44 beat tasks | 12:46 |
| E12 | `5ae5a4b9` | `scripts/explorer_sync.py --check` | 0 | 89/89 engines · 0 orphans · 0 dangling | 12:46 |
| E13 | `5ae5a4b9` | alembic head scan over `alembic/versions/*.py` | 0 | 23 revisions, **1 head** `023_add_prospective_memory` | 12:52 |
| E14 | `5ae5a4b9` | `gh run list --workflow {ci,tests,security-scan,migrations}.yml --branch main` | 0 | all `success` on tip `5ae5a4b9` | 12:53 |
| E15 | pre-fix | `pytest tests/test_upi_order_close.py` (with `app/platform/upi_payments.py` stashed) | 1 | **5 failed, 3 passed** — defect reproduced | 12:56 |
| E16 | `e10a34c9` | `pytest test_upi_order_close + test_upi_order_ref_binding + test_offers_order_ref + test_offers_commercial_authority` | 0 | **57 passed** | 12:55 |
| E17 | `e10a34c9` | `pytest tests/test_voice_session.py tests/test_voice_launch.py` | 0 | **49 passed** — session cap, concurrency, 31st-blocked-pre-provider | 12:58 |
| E18 | `e10a34c9` | CP2 batch — 15 billing/UPI/invoice/webhook suites | 0 | **127 passed, 0 failed, 0 skipped** | 13:05 |
| E19 | `e10a34c9` | CP5 batch — 15 tenant-isolation/RBAC/auth suites | 0 | **140 passed, 0 failed, 2 skipped** (see note) | 13:08 |
| E20 | `e10a34c9` | CP3 batch — 13 voice/telephony/compliance suites | 0 | **187 passed, 0 failed, 0 skipped** | 13:09 |
| E21 | `e10a34c9` | `ruff check` + pre-commit (black, isort, bandit, detect-secrets, private-key, PII-CSV) | 0 | all Passed on both commits | 12:59 / 13:07 |

**Targeted total: 560 tests, 0 failures, 2 skips.** The full suite was deliberately
NOT run (documented `team_pulse` hang; a hang reported as a pass is the exact failure
mode this brief forbids).

**The 2 skips are declared, not hidden** — both self-report their reason:
- `test_live_tenant_isolation_proof.py:13` — *"Admin endpoints require DB tables not
  available in test env"*. So the **live** tenant-isolation proof did not execute;
  isolation is proven by the other 14 suites (unit/HTTP level), and this one stays
  `WORKING_BUT_UNVERIFIED` until run against a real DB.
- `test_runtime_data_isolation.py:252` — POSIX path semantics, skipped on Windows.

---

## OWNER ACTION PACKET

One consolidated packet. Nothing below was executed by this session.

**Candidate:** branch `claude/leadgen-enterprise-readiness-edf3a9`, base `origin/main`
`5ae5a4b9`, one commit `e10a34c9`.
**Changed files:** `app/platform/upi_payments.py` (+43), `tests/test_upi_order_close.py`
(new, 8 tests), `docs/context/ENTERPRISE_READINESS_2026-08-08.md` (new).
**Risk:** low — additive, no flag, no route, no schema, no migration. A payment
without `order_ref` takes the identical pre-change path.
**Rollback:** `git revert e10a34c9` — no data migration to undo.
**Migration plan:** none required.
**Secrets/provider inputs required:** none.
**Abort condition:** any `test_upi_order_ref_binding.py` / `test_upi_payments.py`
regression, or a `could not close order` warning appearing in production logs.

### Decisions requested — one per line

1. **Dead-lineage branches (highest urgency, data-loss risk).** `main` and
   `cursor/swara-paid-free-faq-fix` sit on the pre-rewrite lineage; the latter holds
   **35 uncommitted files** in the primary checkout. Decide: re-point local `main` to
   `origin/main`, and have Cursor's work salvaged onto a fresh `origin/main` base
   (export the diff, re-apply) **before** anything is committed from that checkout.
   A PR opened from it today would carry ~1801 phantom commits.
2. **Merge this branch?** Draft PR on request; do not merge without your review.
3. **Deploy?** Separate approval. Current prod `42493e3f` is already one commit behind
   `origin/main` (`5ae5a4b9`, PR #280). Canonical path only:
   `bash scripts/deploy_vps.sh <full-sha>` under the `VOICE_LAUNCH_KILL=1` fence,
   requiring `DEPLOYED <full-sha> OK`. Reject `latest` / partial restarts.
4. **Run this in-container probe** (this session cannot read prod env) and paste the
   result — it decides three open items:
   `RECORDING_RETENTION` (DPDP purge active or report-only), the five protected-flag
   values, and current `dlq:failed_tasks` / `dlq:dead` / `celery` depths.
5. **Memory headroom (CP5-1).** Prod at 89.5 % used / 10.5 % available — 0.5 pp from
   `HostMemoryHigh`. Decide between container `mem_limit` tuning, a leak check, or
   accepting the risk. Do **not** raise the alert threshold.
6. **Finish #240 (CP2-2).** The offer store has no producer, so `order_ref` never
   exists in production. Scoped slice, assign to **one** writer with exclusive
   ownership of `app/platform/reply_agent.py` + `frontend/admin_dashboard.html`
   (both currently held by Cursor):
   call `offers.issue_offer(deal_id, package_code)` at the interested-reply seam,
   put the returned `order_ref` in the UPI `tn=` field, surface `order_ref` /
   `deal_id` / `expected_amount` / `amount_mismatch` in the `/upi/pending` queue.
   `am=` may only be emitted once a package is bound. The replay hole this would
   otherwise open is already closed by `e10a34c9`.
7. **Context-doc SHA drift.** `CURRENT_STATE.md` (`33651cfc` **and** `e06687c7`),
   `ACTIVE_WORK.md` (`084cd990`), `SESSION_HANDOFF.md` (`31169c7`) and
   `PRODUCTION_TRUTH.md` (`d32a4934`, plus a dangerous `PLATFORM_DIAL_DAILY = HARD OFF`
   that is now `1`) all disagree with the live `42493e3f`. Left unedited on purpose —
   these files are held by Cursor / PR #283. Assign the refresh to their owner.
8. **Optional:** revoke the burned `GEMINI_API_KEY` in the Google console (voice
   already moved off Gemini, so revocation is now zero-impact).
9. **Dependency bump slice (CP5-3).** 29 open Dependabot alerts, 8 high — `starlette`
   (SSRF via UNC paths in `StaticFiles`, multipart DoS, ignored form limits),
   `cryptography` (vulnerable bundled OpenSSL, PKCS#7 Bleichenbacher), `protobuf`,
   `ecdsa`. `starlette` is on the live request path, so this is the highest-severity
   *unfixed* finding in this report. Needs its own slice with a full revalidation
   budget, since `requirements.lock.txt` is the single pinned source.

### Not done, and why

- **No browser/authenticated UI proof.** No admin credentials are available in this
  environment, and driving prod admin flows is an Owner-boundary action. Every
  dashboard/button flow is therefore reported `WORKING_BUT_UNVERIFIED`, not upgraded.
- **No real outbound call, email, WhatsApp or payment.** All are external-effect
  actions requiring explicit approval and an allowlisted canary.
- **No full pytest run.** CLAUDE.md records the full suite hanging in the `team_pulse`
  area; a hang reported as a pass is precisely the failure mode to avoid. Targeted
  suites were used and are listed individually.
- **No production env read, no flag flip, no deploy, no merge.**

## VERDICTS

Evidence base: candidate `5ae5a4b9` + `e10a34c9`; deployed `42493e3f`; probes 2026-08-08.

| scope | verdict | why | next action |
|---|---|---|---|
| **Product 1** | **WAIT** | Public plans, entitlements, delivery and invoicing are coherent; 127 revenue/billing tests pass. One defect found and fixed (CP2-1) — **latent, not active: it cannot fire today because nothing issues an offer**. The payment→deal reconciliation seam is inert (CP2-2) and no authenticated browser proof exists. | Merge `e10a34c9` **before** anyone wires #240's producer, then assign that slice (packet item 6) |
| **Product 2** | **WAIT** | Session/daily caps, atomicity, idempotency and the fail-closed compliance spine are TEST-PROVEN at this HEAD (CP3-1/2). No provider-side proof: no call placed, no cost/outcome/recording evidence, prod flag values unread. | Owner-approved allowlisted canary + packet item 4 |
| **Revenue readiness** | **WAIT** | Manual UPI is the canonical rail and is armed; CP2-1 closes a double-activation + duplicate-invoice hole. Reconciliation is still a name match until #240 has a producer. **1 paying customer, MRR ₹1,999 — revenue-ready ≠ revenue-generated.** | packet items 2, 6 |
| **Automation readiness** | **WAIT** | 364 flags / 43 jobs / 44 beat tasks wired with zero drift, semantically typed, machine-verified (CP4-1). Held back only because the local health-audit green is N/A rather than proof, and prod DLQ/flag state is unread (CP4-2/3). | packet item 4 |
| **Enterprise readiness** | **NO-GO** | 8 of 12 domains proven or config-proven: single alembic head, hardened exact-SHA deploy with auto-rollback, fail-closed compliance, clean secret gates, 140 auth/isolation tests. Downgraded from WAIT to **NO-GO** on CP5-3: **8 high-severity dependency CVEs are open, including `starlette` SSRF and multipart DoS on the live request path.** Also open: DPDP purge unverified (CP5-2), capacity headroom (CP5-1). | packet item 9 first, then 4, 5 |
| **Production release** | **NO-GO** | Not the code — the **coordination state**. Two branches including the primary checkout's 35 uncommitted files sit on a rewritten-away lineage (CP0-F1). Releasing before that is resolved risks re-introducing purged history. Independently, no deploy may proceed without explicit Owner approval. | packet item 1, then 2, then 3 |

**Containment status:** production untouched by this session — no flag flip, no env
change, no deploy, no external message, no payment, no customer contact. All work is
isolated in one worktree on one branch, one commit, revertible with `git revert`.

---

# FINAL VERDICTS — after session 2

Evidence base: PR #285 head `8d527a3e` · PR #286 head `fb2aad72` · both based on
`origin/main` `5ae5a4b9` · production **still `42493e3f`, unchanged**.

| scope | verdict | why | next action |
|---|---|---|---|
| **Product 1** | **WAIT** | 127 revenue/billing tests green; the double-activation defect is fixed (latent, never fired). The reconciliation seam is still inert — but CP2-2 is now a schema-valid `AMBER` mission awaiting one Owner assignment rather than an open question. No authenticated browser proof. | merge #285, then assign the CP2-2 mission |
| **Product 2** | **WAIT** | Session/daily caps atomic + idempotent + fail-closed, 187 voice/compliance tests green. **Provider acceptance held at WAIT deliberately: no real call was placed or authorized.** No provider outcome, cost or recording evidence. | Owner-approved allowlisted canary |
| **Revenue readiness** | **WAIT** | Manual UPI armed; replay/duplicate-invoice hole closed. Reconciliation stays a name match until CP2-2 has a producer. 1 paying customer, MRR ₹1,999 — revenue-ready ≠ revenue-generated. | merge #285 → CP2-2 |
| **Automation readiness** | **WAIT** | 364 flags / 43 jobs / 44 beat tasks, zero drift, semantically typed. Held only because the local health-audit green is N/A rather than proof and prod DLQ/flag state is unread. | packet item 4 |
| **Enterprise readiness** | **NO-GO** | Unchanged verdict, changed reason. 7 of 8 high CVEs are **fixed in draft PR #286, not in production** — `42493e3f` still runs `starlette 0.35.1` with three live highs. The brief permits movement only when reachable high/criticals are fixed *or contained with evidence*; a branch is neither. New CP5-4 (tests writing to a paying customer's tracked ledger) is also open. | **merge + deploy #286** — that single act is what moves this to WAIT |
| **Production release** | **NO-GO** | Two branches, including the primary checkout's 35 uncommitted files, remain on the rewritten-away lineage. Nothing is merged or deployed, and no deploy may proceed without explicit Owner approval. | packet item 1, then 2/3, then 5 |

---

# CONSOLIDATED OWNER ACTION PACKET

Only decisions that now genuinely require Owner authority. Nothing below was executed.

| # | decision | why it needs you | risk if deferred |
|---|---|---|---|
| 1 | **Salvage the dead-lineage checkouts.** Re-point local `main` to `origin/main`; export Cursor's 35 uncommitted files and re-apply them onto a fresh `origin/main` base. | Someone else's working tree — never cleaned by this session | a PR from there carries ~1801 phantom commits and can re-introduce purged history |
| 2 | **Review / merge PR #285** (`fix(billing)` + readiness report + CP2-2 mission). | merge authority | the double-activation hole re-opens the moment CP2-2 is wired |
| 3 | **Review / merge PR #286** (dependency remediation). ⚠️ Its CI is the first real run of the now-blocking audit — it already caught the `packaging` conflict. If it goes red again, that is a finding: fix it, do not re-mute the gate. | merge authority | 3 high starlette CVEs stay live on the request path |
| 4 | **Run one in-container probe** and paste the result: `RECORDING_RETENTION` (DPDP purge active or report-only), the five protected-flag values, `dlq:failed_tasks` / `dlq:dead` / `celery` depths. | prod env access | DPDP retention and automation health stay unverifiable |
| 5 | **Deploy approval** — separate from merge. `bash scripts/deploy_vps.sh <full-sha>` under the `VOICE_LAUNCH_KILL=1` fence, requiring `DEPLOYED <full-sha> OK`. Reject `latest` / partial restarts. | production change | prod stays on the vulnerable lock |
| 6 | **Assign the CP2-2 mission to Cursor** — payload in `docs/missions/CP2-2_OFFER_PRODUCER_HANDOFF.md`, `AMBER` so it cannot self-advance. Requires a **fresh worktree off `origin/main`**, not the dirty checkout. | executor assignment + AMBER approval | #240 stays open; revenue reconciliation stays a name match |
| 7 | **Allowlisted canary approval** — Product 1 (real ₹1,999 UPI → LEDGER_PAID) and/or Product 2 (one real outbound call). | real money / real customer contact | both products stay at WAIT on provider acceptance |
| 8 | **Memory headroom (CP5-1)** — prod 89.5 % used, 0.5 pp from `HostMemoryHigh`. Container `mem_limit` tuning or leak check. Do **not** raise the threshold. | production change | OOM-kill risk on a single VPS |
| 9 | **CP5-4 slice** — stop the test suite writing to `data/delivery_ledger/jiya-makeover.jsonl`. | scope/priority call | a `git add -A` commits fabricated delivery events for a paying customer |
| 10 | **`Trivy image scan (GHCR)` is SKIPPED** on PR runs — the base-OS/system-package layer is unscanned. | CI/infra decision | image-layer CVEs invisible |
| 11 | **Context-doc SHA drift** — `CURRENT_STATE`, `ACTIVE_WORK`, `SESSION_HANDOFF`, `PRODUCTION_TRUTH` all disagree with live `42493e3f`; `PRODUCTION_TRUTH` still says `PLATFORM_DIAL_DAILY = HARD OFF` when it is `1`. Files held by Cursor / PR #283. | owner of those files | an agent acts on a dangerously stale calling-posture claim |
| 12 | *Optional:* revoke the burned `GEMINI_API_KEY` (voice already moved off Gemini — zero impact). | credential | — |

### Not done, and why

- **No browser/authenticated UI proof** — no admin credentials in this environment;
  driving prod admin flows is an Owner boundary. Dashboard flows stay
  `WORKING_BUT_UNVERIFIED`, not upgraded.
- **No real call, email, WhatsApp or payment.** No protected flag flipped.
- **No runtime-image scan** — the image build pulls torch/pipecat/kokoro/rembg, and
  `Trivy image scan (GHCR)` is skipped in CI. The amended-lock venv is the substitute;
  image parity is **not** claimed.
- **No full-tree local import under the amended lock** — repo `.venv` is Python 3.11,
  the image is `python:3.12-slim`, and the lock is 3.12-built. CI covers it.
- **Nothing merged, deployed, or cleaned in anyone else's checkout.**
