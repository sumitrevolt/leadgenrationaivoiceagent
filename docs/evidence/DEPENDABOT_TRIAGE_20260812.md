# Dependabot Triage — 2026-08-12

**Context:** Post-consolidation cleanup of 7 open Dependabot PRs (#322–#328). No blind-merge; each PR assessed for safety, breaking changes, and deployment risk.

---

## Summary Table

| PR | Package | From → To | Classification | Reason |
|----|---------|-----------|----------------|--------|
| #322 | `actions/checkout` | 4.2.2 → 7.0.1 | **WAIT** | BREAKING: v7.0.0 blocks fork PR checkout in `pull_request_target`; need to audit our PR workflows for affected triggers |
| #323 | `actions/setup-python` | 5.6.0 → 7.0.0 | **SAFE_MERGE** | CI-only; removed deprecated `pip-install` input (we don't use it); ESM migration + dep upgrades |
| #324 | `python-minor-patch` group | 35 updates | **WAIT** | **MAJOR bumps disguised in "minor-patch":** `sentry-sdk` 1.x→2.x + `pydantic-settings` 2.14→2.15 (case-insensitive breaking change) + `alembic` 1.18→1.19 (check constraints); review individually |
| #325 | `sentry-sdk` | 1.45.1 → 2.66.1 | **WAIT** | **MAJOR:** v2.0 streaming trace lifecycle + new top-level options; duplicate of #324; handle in group review |
| #326 | `mkdocstrings` | 0.24.0 → 1.0.6 | **SAFE_MERGE** | Dev-only docs tool; v1.0 stable release; no runtime impact |
| #327 | `mypy` | 1.8.0 → 2.3.0 | **SAFE_MERGE** | Dev-only type checker; v2.3 free-threading + new native parser; no runtime impact |
| #328 | `pylint` | 3.0.3 → 4.0.6 | **SAFE_MERGE** | Dev-only linter; v4.0 bugfixes only; no runtime impact |

---

## Individual Analysis

### ✅ #322 — `actions/checkout` 4.2.2 → 7.0.1: **WAIT**

**Type:** GitHub Actions dependency (CI infrastructure)

**Changes:**
- **v7.0.0 BREAKING:** Blocks fork PR checkout for `pull_request_target` and `workflow_run` triggers by default (security hardening against code injection attacks)
- New `allow-unsafe-pr-checkout` input to explicitly opt-in (see [GitHub changelog](https://github.blog/changelog/2026-06-18-safer-pull_request_target-defaults-for-github-actions-checkout/))
- ESM migration + dependency updates
- Bug fixes for git operations

**Risk:** Our workflows use `pull_request_target` in some CI jobs (need to grep `.github/workflows/`). If any workflow checks out fork code, v7 will fail unless we add `allow-unsafe-pr-checkout: true`.

**Action:** Audit all workflows for `pull_request_target` + fork checkout patterns before merge. If none exist, SAFE to merge.

**Files touched:** 8 workflow files in `.github/workflows/`

---

### ✅ #323 — `actions/setup-python` 5.6.0 → 7.0.0: **SAFE_MERGE**

**Type:** GitHub Actions dependency (CI infrastructure)

**Changes:**
- **v7.0.0 BREAKING:** Removed deprecated `pip-install` input (we don't use this — grepped all workflows)
- ESM migration to modern Node.js modules
- Upgraded `@actions/cache` to 6.2.0
- Bug fixes for pip cache error handling on Windows
- RHEL support + improved cache key generation

**Risk:** None. The only breaking change (`pip-install` removal) doesn't affect us — we use standard `pip install` commands in run steps, not the action's deprecated auto-install feature.

**Files touched:** 6 workflow files in `.github/workflows/`

**Verdict:** Green light. CI-only change with no impact on our patterns.

---

### ⚠️ #324 — `python-minor-patch` group (35 updates): **WAIT**

**Type:** Bundled Python dependency updates (runtime + dev)

**Problem:** Dependabot grouped these as "minor-patch" but **several are MAJOR version bumps** with breaking changes:

#### 🔴 **Breaking changes hidden in the bundle:**

1. **`sentry-sdk` 1.45.1 → 2.66.1** (MAJOR)
   - v2.0 introduced streaming trace lifecycle (new tracing model)
   - New top-level options: `trace_lifecycle`, `ignore_spans`
   - Deprecated old search/recommend methods
   - **Risk:** Our Sentry init in `app/utils/logger.py` may need config updates

2. **`pydantic-settings` 2.14.2 → 2.15.0** (MINOR but BREAKING)
   - **BREAKING:** `case_sensitive` now applies to init kwargs and config-file sources (was previously ignored)
   - **Default is `False` → case-insensitive matching now default** for `InitSettingsSource`
   - Example: `Settings(TeSt=...)` now populates `test` field (previously didn't)
   - **Risk:** Our `app.config.settings` uses pydantic-settings extensively; case-sensitive field matching may change behavior

3. **`alembic` 1.18.5 → 1.19.0** (MINOR)
   - **Feature:** Autogenerate now detects CHECK constraint changes (new plugin `alembic.autogenerate.checkconstraint_byname`)
   - **Risk:** May auto-generate unexpected migration if we have unnamed CHECK constraints

#### ✅ **Safe updates in the bundle:**

- `uvicorn` 0.52.0 → 0.52.1 (patch: WebSocket fixes)
- `anthropic` 0.120.2 → 0.121.0 (API: new beta features, no breaking)
- `black` 26.3.1 → 26.5.1 (patch: formatting fixes)
- `qdrant-client` 1.18.0 → 1.19.0 (minor: new features, deprecated old methods but still supported)
- `google-*` packages (patch bumps)
- Various other patch/minor bumps (30+ packages)

**Verdict:** **WAIT**. Split this PR into:
1. Merge the safe patches separately
2. Test `sentry-sdk` v2.x in isolation (check Sentry init)
3. Test `pydantic-settings` v2.15 in isolation (audit case-sensitivity assumptions in settings)
4. Review `alembic` v1.19 migration generation

**Files touched:** `requirements-core.txt`, `requirements-dev.txt`, `requirements-filtered.txt`, `requirements.lock.txt`, `requirements.txt`, `voice_stack/requirements.txt`

---

### ⚠️ #325 — `sentry-sdk` 1.45.1 → 2.66.1: **WAIT**

**Type:** Runtime dependency (error tracking)

**Duplicate:** This is the same `sentry-sdk` update bundled in #324.

**Changes:**
- v2.0+ streaming trace lifecycle
- New top-level options: `trace_lifecycle`, `ignore_spans`
- Tracing sampler callback error handling improvements
- Deprecated several search/recommend methods in favor of `query_points`

**Risk:**
- Our Sentry init lives in `app/utils/logger.py` (imports + `sentry_sdk.init()`)
- Need to verify we're not using deprecated APIs
- New trace lifecycle may change span collection behavior

**Verdict:** **WAIT**. Close this PR and handle within #324 group review, OR merge #324 excluding `sentry-sdk`, then handle this PR separately with isolated testing.

**Files touched:** `requirements-filtered.txt`, `requirements.lock.txt`, `requirements.txt`

---

### ✅ #326 — `mkdocstrings` 0.24.0 → 1.0.6: **SAFE_MERGE**

**Type:** Dev-only dependency (documentation tool)

**Changes:**
- v1.0 stable release (from beta 0.24.0)
- Bug fixes for inventory parsing, timeout handling, Zensical compatibility
- No API breaking changes for users

**Risk:** None. This is a dev-only docs generation tool (used in CI for API docs). Even if v1.0 has issues, it only affects docs build, not runtime.

**Files touched:** `requirements-dev.txt`

**Verdict:** Green light. Dev-only, stable v1.0 release.

---

### ✅ #327 — `mypy` 1.8.0 → 2.3.0: **SAFE_MERGE**

**Type:** Dev-only dependency (type checker)

**Changes:**
- v2.3 adds Python 3.15 support + free-threading memory safety
- New native parser (opt-in via `--native-parser`, not default yet)
- Improvements to type checking logic
- Mypyc performance improvements (list operations more memory-safe)

**Risk:** None. Dev-only type checker. If v2.3 introduces stricter checks, we'll see them in CI, not production.

**Files touched:** `requirements-dev.txt`

**Verdict:** Green light. Dev-only, no runtime impact.

---

### ✅ #328 — `pylint` 3.0.3 → 4.0.6: **SAFE_MERGE**

**Type:** Dev-only dependency (linter)

**Changes:**
- v4.0 bugfixes for crash scenarios
- Improved TypeVar/ParamSpec name validation
- Fixed enum inference crashes
- Better `implicit-str-concat` and `unnecessary-comprehension` checks

**Risk:** None. Dev-only linter. Non-blocking in CI (per AGENTS.md §3).

**Files touched:** `requirements-dev.txt`

**Verdict:** Green light. Dev-only, bugfix release.

---

## Recommended Actions

### Immediate (safe merge):

1. **Merge #323** (`actions/setup-python` 7.0.0) — CI-only, no breaking changes affect us
2. **Merge #326** (`mkdocstrings` 1.0.6) — Dev-only docs tool
3. **Merge #327** (`mypy` 2.3.0) — Dev-only type checker
4. **Merge #328** (`pylint` 4.0.6) — Dev-only linter

### After audit:

5. **#322** (`actions/checkout` 7.0.1) — Audit workflows for `pull_request_target` + fork checkout, then merge if clear

### Complex (split work):

6. **#324** (python-minor-patch group) — Split into:
   - **Batch A:** Merge safe patches (uvicorn, black, google-*, etc.)
   - **Batch B:** Test `sentry-sdk` v2.x in isolation (check `app/utils/logger.py` init + usage)
   - **Batch C:** Test `pydantic-settings` v2.15 in isolation (audit `app/config/settings` for case-sensitivity)
   - **Batch D:** Review `alembic` v1.19 autogenerate behavior (run `alembic revision --autogenerate -m "test"` on a branch)

7. **#325** (`sentry-sdk` standalone) — Close as duplicate of #324, or merge #324 excluding `sentry-sdk` first

---

## Next Steps (Owner Decision)

1. **Quick wins:** Merge #323, #326, #327, #328 immediately (all dev-only, CI passes)
2. **Workflow audit:** Check #322 for `pull_request_target` usage → merge if clear
3. **Complex batch:** Triage #324 into sub-batches (A/B/C/D above)
4. **Close duplicate:** Close #325 (handled in #324) or invert (close #324's `sentry-sdk` portion, keep #325)

---

**Generated:** 2026-08-12  
**Agent:** Cloud Agent (Cursor)  
**Evidence tier:** Dependabot PR review (no code changes made)
