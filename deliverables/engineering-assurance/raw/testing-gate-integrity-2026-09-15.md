# Testing & CI-Gate Integrity Assessment — LeadGen AI

**Author:** Tessa (泰莎) · Testing Expert, Engineering Assurance Team
**Date:** 2026-09-15
**Repo:** `sumitrevolt/leadgenrationaivoiceagent` (public) · default branch `main`
**Scope:** Does the merge gate actually gate? Read-only. No file was modified, committed, pushed or deployed. The runtime-data baseline was **not** regenerated.
**Owner complaint under investigation:** *"ek fix hota hai toh dusra tod jaata hai"* · *"deploy ke baad automation break hore"*

### Evidence labels used
`PRODUCTION-PROVEN` (observed on the live system / GitHub API) · `CODE-PRESENT` (read in source, not executed) · `TEST-PROVEN` (executed by me in this session) · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`.

---

## 0. Verdict up front

The merge gate **does not gate**. Three independent defects stack:

1. On every push to `main`, every meaningful CI job is **skipped** and the run still reports **success** — so `main`'s health is unmeasured. (`PRODUCTION-PROVEN`)
2. There is **no branch protection and no ruleset at all** — so even a red PR is mergeable, and auto-merge with a label merges instantly. (`PRODUCTION-PROVEN`)
3. The one gate that *would* have caught the drift (the runtime-data ratchet) is currently **failing at HEAD** and its failure is invisible on `main`. (`TEST-PROVEN` locally + `PRODUCTION-PROVEN` in CI logs)

Net effect: `main` reports green while the repo's own PR CI is **red with 44 failing tests**. That is precisely the "fix one thing, break another, deploy anyway" loop the owner is describing.

**One correction to the team-lead's brief:** the hypothesis "does a skipped `needs:` dependency satisfy `test "$result" = "success"`?" — **No, it does not.** `needs.X.result` is the literal string `"skipped"` for a skipped job, and `test "skipped" = "success"` exits 1. The aggregator's assertions are *correct*. The real defect is that the **aggregator itself carries the same PR/dispatch-only `if:`**, so on `push` it never runs its assertions at all (see §2).

---

## 1. Gate inventory

Legend for **Enforced?**: *Ruleset* = enforced by branch protection / ruleset; *Aggregator* = asserted by the `prod_check + pytest` aggregator; *None* = nothing fails a merge on it.

| Workflow | Job (`name:`) | Trigger events | Enforced? | Can it fail a merge? | Evidence |
|---|---|---|---|---|---|
| **ci.yml** | `Lint + syntax + secrets` | push, PR, dispatch | Aggregator (PR) — it **is** a `needs` dep (ci.yml:193) | **No** — it runs on push but is asserted only by the PR-only aggregator | ci.yml:53-88, :193 |
| ci.yml | `prod_check runtime gates` | **PR + dispatch only** | Aggregator (PR) | Only on PR | ci.yml:93 `if:` |
| ci.yml | `pip-audit installed env` | **PR + dispatch only** | Aggregator (PR) | Only on PR | ci.yml:110 |
| ci.yml | `Pytest Tests` | **PR + dispatch only** | Aggregator (PR) | Only on PR | ci.yml:148 |
| ci.yml | `harness real-redis integration` | **PR + dispatch only** | Aggregator (PR) | Only on PR | ci.yml:218 |
| ci.yml | `prod_check + pytest` (aggregator) | **PR + dispatch only** | **Nothing** (no ruleset) | **No** — skipped on push; not a required context | ci.yml:175, :193, :204-210 |
| **deploy-vps.yml** | `Gate (billing contract + golden eval)` | push, dispatch | Nothing | **No** (gate-only; no deploy job; not required) | deploy-vps.yml:37-80 |
| deploy-vps.yml | `pytest shard n/4` | push if `vars.DEPLOY_RETEST=='true'` | Nothing | No (opt-in, default OFF) | deploy-vps.yml:86 |
| deploy-vps.yml | `Release gate (billing contract + golden eval)` | push | Nothing | No (`needs:[gate]` only) | deploy-vps.yml:143 |
| **security-scan.yml** | `Trivy repo scan + SBOM` | push, PR, schedule, dispatch | Nothing | **No** (not a required context) | security-scan.yml:56 |
| security-scan.yml | `Trivy image scan (build \| explicit ref)` | push, PR, schedule, dispatch | Nothing | No | security-scan.yml:161 |
| **uptime.yml** | `External health probe` | schedule (`*/10`), dispatch | Nothing | No (detector only) | uptime.yml:30-31, :54 |
| **hermes-harness.yml** | `Hermes integration contract` | PR (paths), push (paths), daily cron, dispatch | Nothing | No | hermes-harness.yml:31-55 |
| **migrations.yml** | `Alembic round-trip + drift + lint` | PR (paths), push (paths), dispatch | Nothing | No | migrations.yml:18-25 |
| **dsh-runtime.yml** | `static-policy` / `linux-runtime` | PR (paths), push (paths), dispatch | Nothing | No | dsh-runtime.yml:3-35 |
| **llm-eval.yml** | `promptfoo` / `deepeval` | PR (paths), weekly cron, dispatch | Nothing | No (advisory, `continue-on-error`) | llm-eval.yml:12-18, :48 |
| **pr-factory-gate-a.yml** | `Gate A (non-required sketch)` | PR, dispatch | Nothing | No (self-declared non-required) | pr-factory-gate-a.yml:2, :27 |
| **pr-factory-ci-repair.yml** | `diagnose` | dispatch only | Nothing | No (read-only comment) | pr-factory-ci-repair.yml:26-27 |
| **auto-merge.yml** | `enable-auto-merge` | PR labeled/sync/reopened | Nothing | **Merges immediately** (native auto-merge, 0 required checks) | auto-merge.yml:51-60 |
| **CodeQL** (GitHub default setup) | dynamic | push / PR | Nothing | No | `code-scanning/default-setup → state=configured` |

**Required checks today: ZERO.**
- `GET /branches/main/protection` → `HTTP 404 {"message":"Branch not protected"}` (`PRODUCTION-PROVEN`)
- `GET /rulesets` → `[]` (`PRODUCTION-PROVEN`)
- `repo.allow_auto_merge = true` (`PRODUCTION-PROVEN`)
- The header comment at `ci.yml:9-12` states *"Required ruleset contexts (do NOT rename)"* and names three contexts — **that ruleset does not exist.** The file's stated premise is false. (`CODE-PRESENT`)

**Direct pushes to `main` are the normal path** (recent history: `e77f8e08`, `ac63bdfe`, `3bcd5fd4`, `b58f0558`, `ffd26b13` are all main commits), so the PR-only lanes never protect the branch that actually ships.

---

## 2. The hollow-green mechanism (precise)

### 2.1 The exact YAML

Every heavy lane repeats the same event filter, e.g. `ci.yml:93`:

```yaml
prod-check:
  name: prod_check runtime gates
  if: github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'
```

The aggregator repeats it at `ci.yml:175`:

```yaml
tests:
  name: prod_check + pytest
  if: always() && (github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch')
  needs: [prod-check, pytest-job, pip-audit, quality, harness-redis-integration]
  steps:
    - name: Required lanes green
      run: |
        test "${{ needs['prod-check'].result }}" = "success"
        test "${{ needs['pytest-job'].result }}" = "success"
        test "${{ needs['pip-audit'].result }}" = "success"
        test "${{ needs['quality'].result }}" = "success"
        test "${{ needs['harness-redis-integration'].result }}" = "success"
```

### 2.2 Can `test "$result" = "success"` ever be false for a skipped job?

**Yes.** In GitHub Actions, `needs.<job>.result` ∈ `{success, failure, cancelled, skipped}`. A job whose `if:` evaluates false has result **`skipped`**, so `test "skipped" = "success"` exits **1** and the aggregator step fails. The assertion logic is sound. (`CODE-PRESENT`, GitHub-documented semantics)

### 2.3 So why is a push to `main` green?

Because the aggregator is skipped too — its own `if:` is `always() && (pull_request || workflow_dispatch)`, which is **false on `push`**. GitHub does not fail a workflow when jobs are skipped; a run with no failing job concludes `success`.

**Observed on commit `b58f0558` — CI run `34916109854` (`PRODUCTION-PROVEN`):**

| Job | Result |
|---|---|
| `Lint + syntax + secrets` | success |
| `prod_check runtime gates` | **skipped** |
| `Pytest Tests` | **skipped** |
| `pip-audit installed env` | **skipped** |
| `harness real-redis integration` | **skipped** |
| `prod_check + pytest` (aggregator) | **skipped** |
| **Run conclusion** | **success** |

So on `main`: no prod_check, no ratchet, no pytest, no pip-audit, no Redis integration — and a green check. The same commit's `security-scan` was **red** (`34916109827`, image scan failure) yet nothing prevented the push.

### 2.4 The aggregator *does* work — on PRs

On PR CI run `34891236952` the lanes really ran and the aggregator correctly reported **failure** (`prod_check + pytest → failure`, step `Required lanes green → failure`). This confirms §2.2: the mechanism is not the `test` assertion, it is the **event gate on the aggregator**. Fixing the gate is a one-line change with no new flake surface.

---

## 3. Proposed corrected event matrix (PROPOSAL ONLY — no file changed)

Rationale: `quality`, `prod-check` (allowlist + ratchet + prod_check.py) and `pip-audit` are **fast, deterministic and dependency-light** (seconds–~2 min) and must run on every event, because dependency CVEs and code drift can land on `main` without a PR. `pytest` and the real-Redis harness stay **PR-only** — see §4 for why running the full suite on every push is not safe yet. The aggregator must run on **every** event and assert only the lanes that are supposed to run for that event.

| Job | push | pull_request | workflow_dispatch | Recommended `if:` |
|---|---|---|---|---|
| `quality` | ✅ run | ✅ run | ✅ run | *(none — already unconditional)* |
| `prod-check` | ✅ **run (CHANGE)** | ✅ run | ✅ run | `if: ${{ !cancelled() }}` (drop event filter) |
| `pip-audit` | ✅ **run (CHANGE)** | ✅ run | ✅ run | `if: ${{ !cancelled() }}` |
| `pytest-job` | ⛔ skip | ✅ run | ✅ run | keep PR/dispatch-only (§4) |
| `harness-redis-integration` | ⛔ skip | ✅ run | ✅ run | keep PR/dispatch-only (Docker Hub dep) |
| `tests` (aggregator) | ✅ **run (CHANGE)** | ✅ run | ✅ run | `if: ${{ always() }}` |
| aggregator assertions | assert quality + prod-check + pip-audit only | assert all five | assert all five | event-aware assertion list |

Aggregator step becomes, in effect:

```yaml
tests:
  name: prod_check + pytest
  if: ${{ always() }}
  needs: [prod-check, pytest-job, pip-audit, quality, harness-redis-integration]
  steps:
    - run: |
        test "${{ needs['quality'].result }}" = "success"
        test "${{ needs['prod-check'].result }}" = "success"
        test "${{ needs['pip-audit'].result }}" = "success"
        if [ "${{ github.event_name }}" != "push" ]; then
          test "${{ needs['pytest-job'].result }}" = "success"
          test "${{ needs['harness-redis-integration'].result }}" = "success"
        fi
```

**Pre-condition before enabling `prod-check` on push:** the ratchet currently fails at HEAD (§3.1 / §5), so turning it on for `push` will immediately redden `main`. That is *correct* — but classify the 3 tracked-file findings first so the ratchet is honest before it is armed on the shipping branch.

### 3.1 Why pytest stays PR-only, prod_check + pip-audit move to push
- **pytest** — the full suite is not reliably runnable in bounded time (§4) and the local/CI environments diverge; putting it on every push would make `main` red for environmental reasons, not code reasons. It stays a PR gate.
- **prod_check + pip-audit** — both are fast, hermetic, and their failure modes (undeclared mutable writers, a newly-disclosed CVE in the locked closure) are exactly the "silent drift that ships" class. They belong on the shipping branch.

---

## 4. Test-environment parity (local vs CI)

| Dimension | Local (`.venv`) | CI (`ci.yml` / `setup-python-lock`) | Gap |
|---|---|---|---|
| Python | **3.11.14** (`TEST-PROVEN`) | **3.12** (ci.yml:63; action `python-version: "3.12"`) | **Major-version drift** |
| pytest | **7.4.4** (`TEST-PROVEN`) | 7.4.4 (requirements.lock.txt) | match |
| pytest-asyncio | (lock) 0.23.4 | 0.23.4 | match |
| `pytest-xdist` | **ABSENT** (`TEST-PROVEN`) | installed via `extras: "pytest-xdist"` (ci.yml:155) | **CI-only** |
| `pytest-timeout` | **ABSENT** (`TEST-PROVEN`) | pinned `pytest-timeout==2.4.0` in the composite action | **CI-only** |
| pytest ini | `timeout=120`, `timeout_method=thread`, `testpaths=["tests"]`, `asyncio_mode=auto` (pyproject:167-184) | same file | `timeout` is inert locally (plugin missing → unknown-ini warning only) |

### 4.1 Reproduced local failures
- `pytest -n auto` → **exit 4**, `error: unrecognized arguments: -n` (`TEST-PROVEN`). `pytest-xdist` is not in `requirements.lock.txt` and not in the local venv. The CI command in ci.yml:168 (`pytest -m "not network" -q --timeout=60 -n auto`) **cannot be reproduced locally**.
- Because `pytest-timeout` is also absent locally, the `timeout = 120` safety net in `pyproject.toml` **does nothing locally** — a hang blocks forever. This matches the team-lead's observation of a serial run reaching only 1% (214 tests) in 13m05s before being killed (`LOCAL-ONLY`, consistent).

### 4.2 Known-hang area
`AGENTS.md:41`: *"full suite team_pulse area pe HANG ho sakta — targeted suites prefer"*. A dedicated guard exists — `tests/test_team_pulse_no_hang.py` (`@pytest.mark.timeout(20)`, asserts `team_pulse()` returns a dict fast) — but it depends on `pytest-timeout`, which is CI-only. Locally the guard is silently a no-op. (`CODE-PRESENT`)

### 4.3 Recommended command sets

**Pre-merge gate (fast, deterministic, no network, no Docker):**
```bash
# 1. static + secrets + misconfig (mirrors ci.yml quality)
python -m compileall -q app scripts
python scripts/check_secrets.py
python scripts/security_scan.py

# 2. runtime-data gates (mirrors ci.yml prod-check)
python scripts/runtime_data_path_scan.py validate
python scripts/runtime_data_path_scan.py ratchet
python scripts/prod_check.py

# 3. targeted deterministic suites (the "drift" guards that actually break)
python -m pytest -q -m "not network" \
  tests/test_billing_truth_2026.py \
  tests/test_runtime_data_ratchet.py \
  tests/test_runtime_data_path_allowlist.py \
  tests/test_runtime_data_baseline_governance.py \
  tests/test_skill_tree_canonical_guard.py \
  tests/test_prod_check_deployment_cli.py \
  tests/test_team_pulse_no_hang.py
```
*(Add `pytest-timeout` + `pytest-xdist` to the local dev extras so commands 1:1 match CI — see the parity gap above.)*

**Nightly / full suite (bounded):**
```bash
pytest -m "not network" -q --no-header -p no:cacheprovider --timeout=120 -n auto
```
with `pytest-timeout` + `pytest-xdist` installed and `-n auto` capped (e.g. `-n 4`) on the local box; run it off the merge path.

---

## 5. Coverage gaps — which confirmed defects had NO test that would have caught them

| Defect | Was there a test? | What I would add (file + assertion) |
|---|---|---|
| **G1** push runs nothing, green aggregate | **NO** | `tests/test_ci_gate_integrity.py` — parse `.github/workflows/ci.yml` and assert: (a) the `tests` aggregator job's `if:` contains no `pull_request`/`workflow_dispatch` event restriction (i.e. it runs on push); (b) for every job in its `needs:`, the job's `if:` includes `push` **or** the aggregator's assertion for it is event-guarded. Assert the aggregator's `needs` set equals the set of lanes asserted. |
| **G2** no branch protection / ruleset | **NO** | `tests/test_github_governance.py` — via `gh api repos/{owner}/{repo}/rulesets`, assert a `main` ruleset exists and its `required_status_checks` include exactly `["Lint + syntax + secrets","prod_check + pytest","harness real-redis integration"]`; assert `allow_auto_merge` is `false` **unless** the ruleset exists. (Read-only; skips when `gh`/token unavailable so it can run in CI with a read token.) |
| **G3** ratchet fails at HEAD, unnoticed | **PARTIAL** — `tests/test_runtime_data_ratchet.py::test_current_state_passes_its_own_baseline` **exists and is RED** (CI log: `new_unresolved=3`). The test is not missing; it is unenforced. | Keep the existing test, but **enforce it**: it must be a required, always-run check. Add `tests/test_runtime_data_ratchet_tracked_only.py` that scans only `git ls-files` paths and asserts `evaluate(findings)["ok"] is True`, so the CI-visible set (3 tracked findings, §5.1) is asserted independently of untracked local files. |
| **G4** "evidence-backed exclusion" promised, not implemented | **NO** | `tests/test_runtime_data_failure_contract.py` — assert that every `action:` string emitted by `runtime_data_ratchet.format_failures()` names only mechanisms that exist: `grep` the source for the named mechanism, or assert the message set is a subset of `{allowlist entry, move the write behind app/platform/runtime_data.py}`. This fails today, forcing either the mechanism or the message to be fixed. |
| **G5** local/CI environment divergence | **NO** | `tests/test_env_parity.py` — assert `pytest.__version__ == pinned lock version`, and assert `importlib.util.find_spec("xdist")` / `find_spec("pytest_timeout")` are non-`None` **when `CI` is set** (so CI cannot silently lose a plugin the command line needs). |
| **G6** dead-man's switch fired, nobody paged | **NO** | `tests/test_uptime_alerting_wiring.py` — parse `uptime.yml` and assert the DOWN path has at least one alert step that is **not** behind an unset-variable condition (i.e. not `vars.NTFY_TOPIC != ''`), and that a repo variable/secret backing an off-VPS push channel is declared. Fails today (only GitHub failure-email remains). |

### 5.1 G3 reproduced (this session)
`python scripts/runtime_data_path_scan.py ratchet` → **exit 1** (`TEST-PROVEN`):
```
baseline fingerprints : 793
unresolved now        : 1005
newly unresolved      : 20
regressions           : 0
resolved since baseline: 0
removed since baseline : 5
RATCHET FAILED
```
Of the **20** new findings, **3 are from TRACKED files** (verified with `git ls-files --error-unmatch`):
- `scripts/waha_watchdog.py` — APPEND `log_file`, REWRITE `health_file` (2)
- `scripts/send_jiya_renewal.py` — CREATE `Path('data/outreach_drafts')` (1)

The other **17** come from **10 untracked** files (`data/hunter_leads/_hunt_insert_vps.py`, `gen_0913.py`, `scripts/hourly_audit.py`×3, `scripts/ops_rev_recon{,2,3,4}.py`, `scripts/prospect_stats.py`, `scripts/vobiz_monitor.py`×3, `tmp/prod_deploy_start.sh`). In a clean CI checkout those files are absent, so **CI sees exactly the 3 tracked findings** — corroborated by the PR CI log line `test_current_state_passes_its_own_baseline - AssertionError: new_unresolved=3`. **The gate is genuinely broken even in CI, not just locally.**

**Is this gate enforcing anything today? No.** `ratchet` lives in `prod-check`, which runs **only on PR/dispatch** (ci.yml:93). On `main` pushes it never runs (§2). On PRs it runs and fails — but with no required check and auto-merge enabled, nothing is blocked.

### 5.2 G4 conclusion — documentation defect, not a missed mechanism
I read `runtime_data_manifest.py` (`derived_blocker()`, `VALID_STATES`, tiers), the allowlist entry schema (`runtime_data_allowlist_entries.py`, fields at `runtime_data_allowlist.py:27-40`) and `runtime_data_scan.classify()` (runtime_data_scan.py:1323-1385). Findings:
- `classify()` has **no exclusion branch**. The only terminal states are: `AMBIGUOUS_REQUIRES_REVIEW`, `CANONICAL_RUNTIME_PATH`, `FIXTURE_ONLY`, `DECLARED_LEGACY_{READ,WRITE}` (allowlist), `STATIC_ASSET`/`REBUILDABLE_CACHE`/`GENERATED_ARTIFACT` (regex heuristics), `UNDECLARED_MUTABLE_PATH`.
- `runtime_data_ratchet.evaluate()` computes `new_unresolved` purely from `classification ∈ {UNDECLARED, AMBIGUOUS} and fp not in base`. **`migration_state` never enters the ratchet** — it only feeds `derived_blocker()` (deployment blocking), which is a different gate.
- `grep -rnE "exclusion|exclude|EXCLUDE|exempt|EXEMPT"` over `scripts/runtime_data_path_scan.py`, `app/platform/runtime_data_allowlist.py`, `app/platform/runtime_data_manifest.py`, `app/platform/runtime_data_allowlist_entries.py` → **zero hits**.
- `runtime_data_path_scan.py:10-12` states there is deliberately no bypass/auto-update.

⇒ The string *"or provide an evidence-backed exclusion"* (`runtime_data_ratchet.py:149-150`) advertises a mechanism that **does not exist**. **Documentation/UX defect** (`CODE-PRESENT`). The only real paths are: add an allowlist entry, or move the write behind `app/platform/runtime_data.py`. Note also a second, smaller wording mismatch: `_print_actionable()` (runtime_data_path_scan.py:46-50) says *"add an allowlist entry (store_id, owner, migration_tier, review_condition)"* — the schema has those fields, so that message is accurate.

### 5.3 G6 conclusion — detector works, alert path is the defect
- Failing scheduled runs (all `schedule` event): `34885638772` (19:14Z), `34904658756` (22:33Z), `34914951882` (00:52Z) — matching the staging-build-at-prod window — plus `34655280763` (2026-09-11). (`PRODUCTION-PROVEN`)
- In failing run `34914951882`, steps: `Probe … → success`, **`Notify ntfy.sh on DOWN (optional) → skipped`**, `Fail if DOWN → failure`. (`PRODUCTION-PROVEN`)
- Why the ntfy step skips: uptime.yml:121 gates it on `vars.NTFY_TOPIC != ''`. Repo variables today = **only `DEPLOY_ENABLED=false`** (`PRODUCTION-PROVEN`). `NTFY_TOPIC` is unset ⇒ **the only alert channel is GitHub's failure email to the repo owner.**
- The in-repo notifier `app/integrations/ntfy.py` posts to `NTFY_URL` = the **self-hosted** `ntfy.leadsgenai.in`, which lives on the same VPS — so it is dead in exactly the scenario the watchdog exists for (`CODE-PRESENT`). `scripts/send_owner_ntfy.py` is a one-shot "morning prep pack" script, not an alert router.
- **To page a human:** (a) set `vars.NTFY_TOPIC` to a public `ntfy.sh` topic and subscribe the owner's phone (zero creds, off-VPS, already coded at uptime.yml:120-128), **and/or** (b) add an off-VPS webhook step (e.g. a public ntfy topic, or a Telegram/Slack webhook via a repo secret) that is **not** conditional on an unset variable. The Telegram path is not wired today.

### 5.4 G7 sanity checks (not re-litigated)
- `security-scan` uses `concurrency: cancel-in-progress: true` (security-scan.yml:44-46) — confirmed live: runs `34924377644` and `34915786904` are **cancelled** (`PRODUCTION-PROVEN`). A missing scan result must not be read as a pass. **Correct, keep.**
- Trivy image gate uses `--ignore-unfixed` (security-scan.yml:250) — only *fixable* HIGH/CRITICAL can fail. Documented trade-off, not a defect. (`CODE-PRESENT`)
- `prod_check.py` exit 0 / 1435 routes, `check_secrets.py --all` clean (4136 files) — taken as given from the team-lead's prior verification; **not re-run in this session** (`STALE` from my side). I did observe the PR CI `prod-check` step 6 `Production readiness check → skipped` because step 5 (ratchet) failed first — so CI is not currently exercising it either.

---

## 6. The one gate change that buys the most safety per unit of risk

**Make the `tests` aggregator unconditional: change `ci.yml:175` from
`if: always() && (github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch')`
to `if: ${{ always() }}`, with event-aware assertions (§3), and move `prod-check` + `pip-audit` onto `push` (ci.yml:93, :110).**

Why this and not the ruleset:
- **Highest safety/risk ratio.** It is a ~3-line diff to one workflow. It has **no new dependency, no new flake surface, no new secret** — it only makes assertions that already exist actually execute on the branch that ships. Today those assertions are dead code on `push`.
- It immediately converts the failure mode from "silent green" to "explicit red": a skipped lane yields `result == "skipped"`, and the assertion fires.
- **The ruleset is the necessary second half, not the first move.** A `main` ruleset requiring the three contexts is the true fix for PRs (G2), but it is riskier: with `harness real-redis integration` depending on a third-party Docker Hub pull (ci.yml:223-232), a registry outage would block the merge train. Arm the aggregator first (cheap, reversible, no flake), then add the ruleset — and consider excluding the Redis lane from required contexts, or keeping its bounded retry, when you do.

**Do NOT, as part of this change:** regenerate the runtime-data baseline, add a bypass/`--accept-current-state`, weaken `--ignore-unfixed`, or touch any DND/TRAI/DPDP/consent gate. The ratchet must be made honest by classifying the 3 tracked findings, not by re-freezing it.

---

## 7. Defect summary

| ID | Defect | Severity | Evidence label |
|---|---|---|---|
| G1 | Push to `main` runs no tests; run reports success | **Critical** | PRODUCTION-PROVEN |
| G2 | No branch protection, no ruleset, auto-merge on | **Critical** | PRODUCTION-PROVEN |
| G3 | Ratchet fails at HEAD (3 tracked findings); invisible on `main` | **High** | TEST-PROVEN + PRODUCTION-PROVEN |
| G4 | Failure message promises a non-existent "exclusion" mechanism | Low (doc/UX) | CODE-PRESENT |
| G5 | Local (py3.11, no xdist/timeout) vs CI (py3.12, both) divergence | Medium | TEST-PROVEN |
| G6 | Dead-man's switch fires; only alert is a GitHub email | **High** | PRODUCTION-PROVEN |

**Cross-cutting finding (new, added by me):** the only automated signal that runs the full suite — PR CI — is currently **red with 44 unique failing tests across 19 files** (run `34891236952`, `PRODUCTION-PROVEN`), including drift guards unrelated to that PR's dependency bump: `test_runtime_data_ratchet.py` (6), `test_runtime_data_path_allowlist.py` (2, e.g. `assert 97 == 94`), `test_runtime_data_baseline_governance.py` (2), `test_skill_tree_canonical_guard.py` (1). Combined with G1/G2 this means **`main` is green while it is in fact broken** — the exact "fix one thing, break another" loop, mechanised.
