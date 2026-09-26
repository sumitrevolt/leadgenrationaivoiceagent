# WORKBUDDY-EMAIL-002 — `prod_check runtime gates` ratchet vs #565 stack

**Date:** 2026-09-24 · **Branch:** `feat/wb-email-002-typesafe-triage` @ `1d6867fe`
**Purpose:** Boss directive — "prod_check ki 9 ratchet findings ko #77 slice-1 PR #565
se compare karo aur branch dependency document/stack karo; WorkBuddy PR mein
allowlist entries duplicate mat karo."

---

## 1. What the ratchet lane fails on

`scripts/runtime_data_path_scan.py ratchet` (MUST-PASS lane `prod_check runtime
gates`, CI job `https://github.com/sumitrevolt/leadgenrationaivoiceagent/actions`
job id `107445229149`) verdict on branch `1d6867fe`:

```
baseline fingerprints : 788
unresolved now        : 988
newly unresolved      : 9
resolved since baseline: 0
removed since baseline : 6
RATCHET_RC=1
```

**9 newly-unresolved findings** (from `/tmp/rd_ratchet_out.txt`):

| # | file | symbol | op | path |
|---|---|---|---|---|
| 1 | `app/platform/telegram_coordinator.py` | `tmp` | REPLACE | `_LEASE_PATH.with_suffix('.tmp')` → `data/telegram_poll_lease.json.tmp` |
| 2 | `app/platform/telegram_coordinator.py` | `tmp` | REPLACE | same store, second finding |
| 3 | `app/platform/typesafe_integration.py` | `_RUNTIME_KEYS_FILE` | READ | `data/typesafe_keys.json` |
| 4 | `scripts/legacy/pilot_dispatch_0830_1455.py` | `p` | READ | `command_center/data/tasks.json` |
| 5 | `scripts/legacy/pilot_dispatch_0830_1455.py` | `p` | REWRITE | same |
| 6 | `scripts/legacy/pilot_nudge_run.py` | `p` | READ | `command_center/data/tasks.json` |
| 7 | `scripts/legacy/pilot_nudge_run.py` | `p` | REWRITE | same |
| 8 | `scripts/legacy/pilot_run_tick.py` | `p` | READ | `command_center/data/tasks.json` |
| 9 | `scripts/legacy/pilot_run_tick.py` | `p` | REWRITE | same |

→ **5 distinct source paths**, 9 findings (typesafe_keys is READ-only, others are
READ + REWRITE pairs, lease is REPLACE ×2).

---

## 2. Are these already handled by #565?

**YES — every one of the 5 distinct paths is exactly what #565 (`#77 slice 1`)
introduces in `app/platform/runtime_data_allowlist_entries.py`.**

Verified by `git diff main..origin/fix/ci-pilot-allowlist-slice1 --
app/platform/runtime_data_allowlist_entries.py`. The #565 head
(`fix/ci-pilot-allowlist-slice1` @ `282a9e44`) already declares:

| #565 `allowlist_id` | file | path_pattern |
|---|---|---|
| `communications.telegram_poll_lease.state` | `app/platform/telegram_coordinator.py` | `data/telegram_poll_lease.json.tmp` |
| `platform.typesafe_keys.runtime_store` | `app/platform/typesafe_integration.py` | `data/typesafe_keys.json` |
| `command_center.pilot.legacy_dispatch_0830_1455` | `scripts/legacy/pilot_dispatch_0830_1455.py` | `command_center/data/tasks.json` |
| `command_center.pilot.legacy_nudge_run` | `scripts/legacy/pilot_nudge_run.py` | `command_center/data/tasks.json` |
| `command_center.pilot.legacy_run_tick` | `scripts/legacy/pilot_run_tick.py` | `command_center/data/tasks.json` |

If #565 merges to `main` first, the ratchet lane on #569 rebase sees all 5 paths
already allowlisted → **9 new findings drop to 0** → lane goes green.

---

## 3. Branch dependency (stack order)

```
main ──────────────────────────────────────────────
            │
            ├─► #565  fix/ci-pilot-allowlist-slice1
            │          (adds 5 allowlist entries above)
            │          CI state: Pytest lane still red on Pytest Tests
            │                    (composition issue is deferred to #567)
            │
            ├─► #567  fix/ci-compose-webconcurrency-slice2
            │          base = fix/ci-pilot-allowlist-slice1 (stacked on #565)
            │          resolves compose lane + WEB_CONCURRENCY hardcoded 2
            │
            └─► #569  feat/wb-email-002-typesafe-triage  ← THIS BRANCH
                     base = main
                     MUST REBASE ON TOP OF #565 (+#567) BEFORE merge
```

**Why the stack is required:**
- #569's CI `prod_check runtime gates` lane is red **because #565 is not yet
  merged**. The 9 findings are #565's declared paths, not #569's own new
  writers — #569 does NOT add any new undeclared mutable path (verified
  against the ratchet diff).
- Boss directive: "allowlist entries duplicate mat karo" → #569's diff stays
  clean on this point (no `runtime_data_allowlist_entries.py` changes in this
  branch; verified `git log --oneline origin/main..HEAD -- app/platform/runtime_data_allowlist_entries.py`
  = empty).
- #567 is stacked on #565 for the compose lane, not for the ratchet lane; #569
  does not need #567's diff to clear the ratchet lane — #569 only needs #565
  merged first.

**Recommended merge order:** `#565` → `#569` (rebase #569 onto #565's merged
state) → `#567` (if owner wants to ship compose fix together with ratchet
clear).

If the owner wants #569 merged independently of #565/567, the alternative is
to **cherry-pick the 5 allowlist entries from #565 into #569's branch tip**
— but Boss explicitly forbids this ("WorkBuddy PR mein allowlist entries
duplicate mat karo"), so this path is **rejected by owner directive**.

---

## 4. What #569 itself adds (no overlap with #565)

Verified via `git diff main..feat/wb-email-002-typesafe-triage --
app/platform/runtime_data_allowlist_entries.py`:

**Empty.** #569 does not add, remove, or modify any allowlist entry.

#569's 3-file code diff (formatting + stable key + docstring alignment) does
not introduce new undeclared mutable paths. The ratchet lane failure on #569
is entirely a **stack-ordering artifact** of #565 not yet being on main.

---

## 5. Rollback / rebase SOP

```
# After #565 lands on main:
cd .worktrees/wb-email-002
git fetch origin main
git rebase origin/main            # replays 206152cc + 1d6867fe on top of #565-tip
# Re-verify targeted tests (20 new + 171 regression) still green
# Push --force-with-lease origin feat/wb-email-002-typesafe-triage
# Re-open PR #569 CI; expect prod_check runtime gates lane to go green
```

No rollback needed for #569's own changes — they are opt-in gated behind
`REPLY_AGENT_TYPESAFE*` / `REPLY_AGENT_FOLLOWUP_TASK` (default OFF in
production; verified via `grep -rn "REPLY_AGENT_" app/platform/reply_agent.py
| grep default`).

---

## 6. Proven / unproven status (as of this deliverable)

| claim | status |
|---|---|
| 9 ratchet findings on #569 = 5 distinct source paths, all covered by #565 allowlist | **PROVEN** (ratchet output + git diff vs #565) |
| #569 diff contains zero allowlist changes | **PROVEN** (empty git diff on that file) |
| Ratchet lane will clear once #565 merges to main | **INFERRED** (logical; not yet proven until #565 lands + rebase + CI run) |
| #569 targeted tests green | **PROVEN** (`tests/test_reply_typesafe_triage.py` 20/20, regression 171/171) |
| #569 live TypeSafe calls work in this env | **PROVEN** (2 live calls, jev-1.13.0, latency 1.2–1.3s, no fabricated decision IDs — trace at `EMAIL-002-typesafe-trace-2026-09-24.md` §4) |
