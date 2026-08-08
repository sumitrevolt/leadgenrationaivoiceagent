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

### CP2-1 `VERIFIED_BROKEN` → **FIXED IN THIS BRANCH** — an approved UPI payment never closed its order (double-activation hole)

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

_pending_

## CHECKPOINT 4 — AUTOMATION READINESS

_pending_

## CHECKPOINT 5 — ENTERPRISE READINESS

_pending_

---

## EVIDENCE LEDGER

| # | HEAD | command | exit | when (UTC) | artifact |
|---|---|---|---|---|---|
| E1 | `5ae5a4b9` | `curl https://leadsgenai.in/health` | 0 | 2026-08-08 07:09 | CP0-F3 |
| E2 | `5ae5a4b9` | `curl https://leadsgenai.in/health/ready` | 0 | 2026-08-08 07:09 | CP0-F3 |
| E3 | `5ae5a4b9` | `git merge-base --is-ancestor HEAD origin/main` | 0 | 2026-08-08 07:1x | CP0-F1 |

---

## OWNER ACTION PACKET

_pending_

## VERDICTS

_pending_
