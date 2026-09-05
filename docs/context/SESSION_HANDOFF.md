# SESSION HANDOFF — 2026-09-05 (Freebuff autopilot: hardening sweep + OmniRoute 14-combo rebuild + worker routing)

> Autopilot mode (owner: "jo best hai wo karo, don't ask, keep going"). Four
> workstreams completed: revenue-conversion hardening, squad/owner_admin repair,
> the OmniRoute 14-combo canonical rebuild, and app/platform worker routing onto
> the canonical 14-combo map. All changes LOCAL-ONLY (not committed/pushed — §8
> owner gate).

## What shipped this session (verified)

### Workstream A — revenue conversion (session 1)
| Change | File | Status |
|---|---|---|
| Telephony readiness false-green FIX | `app/telephony/telephony_readiness.py` | ✅ `outbound_probe` no longer hardcoded `True`; consults `verify_outbound_connectivity()` when `VOBIZ_VERIFY_CALLER_ID_OUTBOUND=1`, weight=0 when unarmed |
| Trial nudge conversion upgrade | `app/billing/trial_nudge.py` | ✅ UPI deep-link in body (`pay_link` param), "100+ businesses" social proof, "aaj" urgency ≤1 day |
| Whitespace/import-sort cleanup | 5 files (`daily_social_post`, `social_post_beats`, `video_generator`, `video_pipeline`, `natural_dialog`) | ✅ W293/W291/I001 fixed |

### Workstream B — squad/owner_admin repair (session 2)
| Change | File | Status |
|---|---|---|
| Star-imports → explicit imports + dispatch rewrite | `app/platform/owner_admin.py` | ✅ `cmd_squad_task` previously NameError on ALL 11 squads (`squad_voice_calling()` as callable); now calls real functions |
| Removed machine-specific sys.path | `app/platform/owner_admin.py` | ✅ `/opt/leadgen` + `C:\Users\Ratanshila\.openclaw\workspace` hardcoded paths deleted |
| Stale import removed | `app/platform/squad_voice_calling.py` | ✅ `STAFF_JOBS_VALID` (gone from team_scheduler); async wrapped via `_run_async` |
| Lazy defensive imports | `app/platform/squad_knowledge.py` | ✅ `gen_domain_briefs`/`validate_full_os` never existed; now `run()`/`main()` |

### Tests added
- `tests/test_owner_admin_squad_dispatch.py` (NEW, 6 tests)
- `tests/test_telephony_readiness_run_checks.py` (NEW, 5 tests)
- `tests/test_trial_nudge.py` (+4 pay_link/urgency tests)
- `tests/test_omniroute_canonical_combos.py` (NEW, 6 tests)
- `tests/test_omniroute_combo_watchdog.py` (NEW, 4 tests)
### Workstream C — OmniRoute 14-combo canonical rebuild (session 3)
| Change | File | Status |
|---|---|---|
| Canonical 14-combo seed | `scripts/seed_omniroute_14combos.py` (NEW) | ✅ deletes 67-combo mess (backup first), inserts `leadsgen combo 1..14` + 38 legacy aliases (same UUID), binds each combo to ONE email key, idempotent |
| Hardcoded API key removed | `scripts/sync_all_combos_all_apps.py` | ✅ `sk-…` literal gone; reads `OMNIROUTE_API_KEY` env only |
| Sync updated to 14 combos + Verdant | `scripts/sync_all_combos_all_apps.py` | ✅ 14 canonical (id/real/canonical/name); `sync_verdant()` added (best-effort); delegates SQLite seed |
| Live-lane slot repoint | `scripts/seed_omniroute_14combos.py` | ✅ 42 slots rebuilt from PROVEN-LIVE opencode free models after upstream provider keys found dead |

### Workstream D — app/platform worker routing → canonical 14-combo map (session 4)
| Change | File | Status |
|---|---|---|
| `_TASK_ROUTES` rewired to CANONICAL combo ids | `app/platform/omniroute_client.py` | ✅ every route primary = owning combo (1 coding, 2 coding-fast, 3 repo, 4 test, 5 agent-ops, 6 swara, 7 marketing, 8 prospect, 9 outreach, 10 seo, 11 governor, 12 project-best); fallback = DIFFERENT combo; 13/14 = failover/general lanes; **all 14 combos get traffic**, no self-route; privacy unchanged (swara CUSTOMER_MASKED) |
| Orchestrator ledger default → combo 1 | `app/platform/automation_orchestrator.py` | ✅ 3 spots (`leadsgen combo 1`) |
| Isha snapshot display fallback | `app/platform/owner_agent_execution.py` | ✅ `leadsgen combo 13` |
| Canonical-coverage contract tests (NEW) | `tests/test_omniroute_canonical_combos.py` | ✅ 6 tests: canonical naming, primary≠fallback, 14/14 referenced, ≤1 primary/combo, 12 tasks, all 31 agents resolve |
| Pinned tests updated | `tests/test_omniroute_client.py`, `tests/test_omniroute_governance.py` | ✅ canonical ids |

**Worker-routing end-to-end evidence (2026-09-05):**
- **LIVE dispatch: 12/12 `_TASK_ROUTES` answered through the real gateway** — real `generate()` per route → output_text on every combo: combo1 (nemotron-3.5-lightning-free), combo2 (nemotron-3-ultra-free), combo3 (big-pickle), combo4 (mimo-v2.5-free), combo5, combo6 (CUSTOMER_MASKED swara path), combo7, combo8, combo9, combo10, combo11 (muse-spark-1.2-contributor-free), combo12. Fallback lanes 13/14 referenced.
- Tests: 53 passed / 1 pre-existing xfail (omniroute_client+governance+agent_os_routing+canonical), voice+orchestrator suites green (2 pre-existing xfails). Ruff clean. **Voice surface untouched** (FROZEN — voice_sticky_route reverted to HEAD).

**OmniRoute live evidence (2026-09-05):**
- Gateway = Docker `leadgen_omniroute` :20128 loopback. DB at **`/app/data/storage.sqlite`** (old seeds targeted `/root/.omniroute/` = wrong path, never landed).
- **14/14 `leadsgen combo N` → HTTP 200 with real completions** (smoke-tested all). 42 slots (3/combo), 14 email keys bound, 38 aliases resolve (`leadgen-*`/`hermes-engineer`/`claude-omni-*`/`claude-code`/`vps-*`).
- **ALL upstream provider keys in the gateway are dead** (groq/gemini/cerebras/deepinfra/together/sambanova/hf/pollinations/qoder/fireworks 401 — rotated since 2026-09-01 provisioning). Only **opencode anonymous free tier** answers (5000+ real 200s/3d). Slots therefore point at the 6 proven opencode free lanes; each combo = 3 distinct live lanes, rotated primaries.
- Sync ran across DSH/Claude Desktop/WorkBuddy/Hermes (roaming+local)/OpenClaw/workspace `.mcp.json`. **Verdant not installed** → SKIP no-op (config writer ready).
- DB backups: `/app/data/db_backups/pre_14combos_*`.

### Workstream E — OmniRoute combo watchdog (session 5)
| Change | File | Status |
|---|---|---|
| 14-combo lane watchdog (NEW) | `scripts/omniroute_combo_watchdog.py` | ✅ self-discovers combos from `/v1/models`, probes via real `/v1/responses` (the app's own path), strike counter → ntfy alert once at 3 consecutive failures + recovery ping; `--loop N` / `--quiet` / `--json`; exit 0/1/2 |
| Opt-in Task Scheduler registration (NEW) | `scripts/register_omniroute_watchdog.ps1` | ✅ every-N-minutes registration (pattern = setup_autoboot.ps1); **NOT registered yet** (owner opt-in) |
| Hermetic state-machine tests (NEW) | `tests/test_omniroute_combo_watchdog.py` | ✅ 4/4 — blip never alerts, 3-strike alert once + persistent exit 1, recovery clears + pings, gateway-down exit 2 (caught a real exit-code bug) |

Watchdog evidence: live passes → combo 2 throttled `empty_output` recovered next pass (state reset), combo 10 strike-accumulated — state machine proven against the real gateway. State = `data/omniroute_combo_state.json` (gitignored). Alerts gated NTFY_URL+NTFY_TOPIC (unset = print-only).

## Verification evidence
- `ruff check app` → **0 errors** (was 28; 100% lint-clean)
- `prod_check.py` → ALL CHECKS PASSED (58 pages 0 gaps, automation 0 gaps, 362 nodes, API.md synced)
- `check_secrets.py` → no secrets (27 changed files)
- Watchdog tests 4/4 green; live two-pass strike/recovery verified; canonical-combo routing tests 6/6 green
- ~200 targeted tests GREEN across touched areas (billing truth, trial nudge, telephony readiness probe+run_checks, owner_admin dispatch, activation readiness, jio sip, suppression gates, compliance, hot-queue payment path, reply offer block, reply auto-send, revenue funnel)
- Prod `/health` = `719dbbd6` healthy production (DSH shadow jiya_makeover)

## Pre-existing env-deps (NOT regressions)
- `test_upi_payments.py` needs real Redis
- `test_call_learning_2026_07_06.py` needs API keys (Gemini/Groq/Cerebras)
- Full `tests/` sweep hangs on team_pulse area (known landmine) — use targeted suites

## Owner actions still required (unchanged)
1. Hot Queue `/app/inbox` blitz (42 warm cards, UPI links embedded)
2. UPI bind/bank-credit confirm
3. Vobiz caller-ID ownership (vendor) → then arm `VOBIZ_VERIFY_CALLER_ID_OUTBOUND=1`
4. Commit + deploy this worktree (owner gate)
5. **OmniRoute: refresh provider keys in the gateway dashboard** (Settings → Providers) to re-enable the non-opencode lanes; install Verdant → re-run `sync_all_combos_all_apps.py`
6. **OmniRoute combo watchdog (NEW, opt-in):** run `scripts/register_omniroute_watchdog.ps1` to arm periodic 14-combo lane checks (or `python scripts/omniroute_combo_watchdog.py --loop 300`); set `NTFY_URL` + `NTFY_TOPIC` for phone alerts (unset = print-only, no crash)

## Landmines touched this session
- Test runs can dirty `data/` files (e.g. `data/delivery_ledger/jiya-makeover.jsonl`) — `git checkout --` restore before commit.
- Full pytest needs `pytest-asyncio`, `pytest-timeout`, `requests` installed (were missing in fresh venv).
- `squad_knowledge.daily_index_update()` now actually writes knowledge domain index files on run (was dead code) — additive, files are repo-tracked .md.