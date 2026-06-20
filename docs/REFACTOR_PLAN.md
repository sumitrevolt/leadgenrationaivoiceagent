# Repo-Wide Refactor Plan & Audit (2026-06-20)

> Scope decision: user ne "har file refactor" maanga. Pure-repo **blind** rewrite (726 files, ~156k LOC, LIVE prod)
> safe nahi — isliye **phased + behaviour-preserving + verified** approach. Yeh doc whole-repo ko cover karta hai:
> Phase 1 (mechanical normalization) DONE; deeper structural phases niche documented (future sessions).

## Baseline (measured, not assumed)
- **726 `.py` files**, ~156,150 LOC (app/ + tests/, excl. .venv/data/logs/__pycache__).
- Project standard (already declared): `pyproject.toml` + `.pre-commit-config.yaml` → **black** (line-100, py310/311) · **isort** (black profile) · **ruff** (select E,W,F,I,B,C4,UP; ignores E501/B008/C901/UP007/F401/F841/F821…).
- Pre-commit autofix msg literally `"style: auto-fixes from pre-commit hooks"` → project EXPECTS this mechanical refactor; repo had simply drifted (358/593 files were not black-clean).
- Tooling note: local venv uses **black 26.5.1 / isort 8.0.1 / ruff 0.15.16** (newer than pinned 24.1.1/5.13.2/0.1.14). Behaviour-preserving regardless of version. If exact pin-match desired later, re-run with pinned versions (low priority — pre-commit wasn't actively enforced anyway).

## Phase 1 — Mechanical normalization to own standard  ✅ DONE (2026-06-20)
Ran project's own pipeline across `app/` + `tests/`:
- **black**: 356 files reformatted
- **isort**: 38 files import-sorted
- **ruff --fix** (safe fixes only): 271 fixes (UP006 `List`→`list`, UP045 `Optional[X]`→`X | None`, I001 import-sort, E401 split-imports, F541, UP012/UP015, B033, C420, W292…)

**Excluded (in-progress WIP, isolate-for-review):** `app/api/system_health.py`, `tests/test_readiness_infra_b3.py`, `tests/test_today_overview.py`. (Backup: `git stash` "pre-refactor-snapshot-2026-06-20".)

**Verification (all green):**
- `compileall app tests` → exit 0 (every file parses)
- `scripts/prod_check.py` → ALL PASSED (app.main imports, **752 routes registered, 0 wiring gaps, 0 automation gaps**)
- Contract/security suites → 57 tests green (billing-truth, IDOR, consent-ledger, reconsent-cooloff, tenant-billing, niche-kb)

**Net:** ~358 files normalized, behaviour-preserving, no logic touched.

## Residual lint (12 non-auto-fixable) — triaged, intentionally NOT changed in Phase 1
| File:Line | Rule | Verdict |
|---|---|---|
| `app/agents/self_improve.py:1002` | F811 `run_once` redefined | **REAL dead code** → Phase 2 (see below) |
| `app/platform/customer_totp.py:230` | B018 useless expr | **FALSE POSITIVE** — intentional `try: _RANDOM_KEY / except NameError` idiom; fixing = break. Leave. |
| `app/agents/self_improve.py:563` | C401 | cosmetic, ruff "unsafe" → leave |
| `app/lead_scraper/web_extract.py:61` | C416 | cosmetic/unsafe → leave |
| `app/marketing/client_report.py:38` | E731 lambda | cosmetic → optional Phase 2 |
| `app/marketing/voice_packages.py:171` | C416 | cosmetic/unsafe → leave |
| `app/platform/report_parser.py:399` | C416 | cosmetic/unsafe → leave |
| tests (B028×2, C405, B011, C408) | — | test-author choices → leave |

## Phase 2 — Structural (IN PROGRESS, started 2026-06-20)
- ✅ **self_improve.py dead `run_once` removed** — old line-579 impl (~108 lines) deleted; F811 gone; 1 `run_once` left (Phase-7 version); self_improve tests 7/7 green.
- ✅ **growth.py → `AUTOMATION_FLAGS` extracted** to `app/api/automation_flags.py` (159 lines); growth.py re-exports for backward-compat (admin_dashboard + 3 tests verified, re-export `is` identical).
- ✅ **growth.py → `/process/*` routes extracted** to `app/api/growth_process.py` (92 lines, sub-router via `include_router`); paths unchanged, prod_check **752 routes intact**, 6 process routes confirmed present.
- ✅ **growth.py → `/prospects/*` routes extracted** to `app/api/growth_prospects.py` (158 lines, 4 local models, sub-router include); 16 tests green. (commit 38cc5e0)
- ✅ **growth.py → agent automation-ops tail extracted** to `app/api/growth_automation.py` (350 lines, 9 models: self-improve/skills/upgrader/social/harvester/approvals/gates); `/process` rides transitively (growth→automation→process). prod_check 752 intact, 31 tests green. (commit 09bdc98)
- growth.py: **2741 → 2000 lines** (−741 / −27%, 4 modules extracted: automation_flags, growth_process, growth_prospects, growth_automation). Verification each step: black/isort/ruff + compileall + prod_check (752 routes, 0 gaps) + targeted tests (175+ green total).
- **Deployed (main 8e7c35f):** Phase 1 + self_improve + flags + /process. **Committed not-yet-deployed (feature):** /prospects (38cc5e0) + automation (09bdc98). NOTE: branch also carries 2 PARALLEL user commits (d69204f, 2577f23 — readiness/ops_watchdog/docker-compose) that a deploy would bundle.
- **Remaining growth.py groups** (sub-router pattern): revenue/GST (548-784) · AI-infra/observability (1035-1271) · feature-flags/CRM/research · marketing-AI/loyalty/reports · sales-team. Then other god-files per table below.

## HIGH-VALUE FINDING — duplicate `run_once()` in self_improve.py  ✅ FIXED (Phase 2)
`app/agents/self_improve.py` me `async def run_once()` **do baar** defined hai:
- **line 579** — older "Phase 1" version (basic pick→execute→learn)
- **line 1002** — "Phase 7 integrated" version (deterministic gates + cost-aware)

Python me last def jeetti → **line-579 wali ~400-line implementation DEAD/shadowed** (`self_improve.run_once` always = line-1002). Risk: koi 579 edit kare to no-effect; confusion.
**Action (Phase 2, careful):** `git log`/blame se confirm karo line-1002 = intended replacement, fir dead line-579 block remove karo. Critical forever-loop file — dedicated reviewed commit, self-improve tests (heartbeat/requeue) ke saath verify.

## Phase 2 — Structural refactor (FUTURE, risky, per-module, verified+deployed each)
God-files (split routers / extract helpers / remove dead code). **Additive + behaviour-preserving**; har file ke baad `/verify` + deploy-gate. **billing.py = careful zone (billing-truth contract), last me.**

| File | LOC | Refactor direction |
|---|---|---|
| `app/api/growth.py` | 1812 | split mega-router into sub-routers by concern (infra-flags / experiments / optimizer …) |
| `app/telephony/vobiz_stream.py` | 1730 | extract VAD/STT/TTS/cleanup helpers from giant session class |
| `app/api/marketing.py` | 1275 | sub-routers per tab-group; duplicate-route audit first (FastAPI first-route-wins) |
| `app/niche_knowledge.py` | 1247 | separate data from logic |
| `app/api/admin_dashboard.py` | 1220 | sub-routers; share helpers with customer_dashboard |
| `app/main.py` | 1198 | extract app-wiring/lifespan into modules |
| `app/api/billing.py` | 1172 | CAREFUL — contract-test-gated; helper extraction only, last |
| `app/agents/self_improve.py` | 931 | remove dead run_once (above) + split actions |
| `app/voice_agent/phone_stream.py` | 842 | mirror vobiz_stream helper extraction |
| `app/voice_agent/natural_dialog.py` | 832 | extract dialog-state helpers |

**Per-module loop:** grep callers + read full → additive extract (no behaviour change) → `compileall` + `prod_check` + targeted tests → commit → deploy + `/health` verify. One module per change-set; never bundle.

## Phase 3 — Optional polish (low priority)
- Add `.gitattributes` (`* text=auto eol=lf`) to stop CRLF/LF flapping (repo currently `core.autocrlf=true`, no `.gitattributes` → spurious "modified" noise).
- Bump pre-commit pinned tool versions to match installed, or pin installed→declared.
- Extend Phase 1 normalization to `scripts/` (left out of Phase 1).
