# Phase-1 Regression Pins — 2026-09-14

**Owner:** Tessa (testing-expert) · **Task:** #1 · **Repo HEAD:** `20e4180b`
**Scope:** Pure test addition. **No production code was modified.**
**Environment:** Windows 11, `.venv/Scripts/python.exe` (Python 3.11.14, pytest 7.4.4).

---

## 1. What was written

| File | Bytes | Status | Pins |
|---|---|---|---|
| `tests/test_ci_required_lanes.py` | 7,411 | modified (extended) | **T-1** merge gate can fail on pytest |
| `tests/test_compliance_gate_structural.py` | 5,640 | new | **T-2** DND prod refusal branch (AST) |
| `tests/test_workforce_telemetry_truth.py` | 6,094 | new | **T-3** orchestrator telemetry is inert |
| `tests/test_email_optout_fail_closed.py` | 4,375 | new | **T-4** email opt-out fails CLOSED |

### T-1 — `tests/test_ci_required_lanes.py` (pure addition)
Two new tests added in the file's existing idiom:

* `test_aggregator_run_block_asserts_pytest_job_result_not_echoes` — parses the
  real `ci.yml` (yaml.safe_load), extracts the `tests` aggregator job's `run:`
  block, keeps only lines that **start with `test `** (a real shell assertion),
  and requires one of them to reference `needs['pytest-job'].result` and compare
  it to `"success"`. An `echo` or a `#` comment cannot satisfy it. Also asserts
  `prod-check` and `pip-audit` are asserted, not echoed.
* `test_aggregator_does_not_rely_on_echo_for_any_required_lane` — belt-and-braces:
  every lane that is `echo`ed must ALSO be `test`-asserted (`echoed <= asserted`).

**Mutation-verified:** feeding the pre-fix echo-only `run:` block raises
`AssertionError`; the real `ci.yml` passes. The pin genuinely fails when the fix
is reverted.

### T-2 — `tests/test_compliance_gate_structural.py`
AST proof (not grep). Discovers the module-level function in
`app/telephony/compliance.py` whose source contains **both** `DND_FAIL_OPEN` and
`_is_production` (verified to be exactly `_dnd_fail_open`), then asserts an
`ast.If` whose test references `_is_production` contains a `Return` of a falsy
`ast.Constant` (`False`/`None`/`0`). A comment, docstring, or stub cannot satisfy
it. Also pins the `_env("DND_FAIL_OPEN", "0")` fail-closed default, and includes
a parametrised self-check of the falsy-return detector so it cannot silently no-op.

**Mutation-verified:** a stub returning `True` with a comment mentioning the
predicate yields **zero** matching `If` nodes; a logging-only `if _is_production():`
branch is correctly rejected (no falsy return).

### T-3 — `tests/test_workforce_telemetry_truth.py`
* `test_orchestrator_main_is_inert` — monkeypatches `runtime_data.store_path` to a
  `tmp_path` file, calls `orch.main()`, reads the JSON and asserts
  `status == "NOT_INSTRUMENTED"`, `active_workers == 0`, `actions_today == 0`,
  `evidence_kind == "inference_probe_only"`, `task_execution_verified is False`,
  `agents == []`. **Actual schema matches the brief exactly** (field names as
  described; `main()` is `write_inert_status()` + a banner).
* Source guards (AST, docstring-aware): no `LOCAL_ACTIVE` code string outside a
  docstring; no `actions_today += …` AugAssign; any literal written to the
  `actions_today` key is exactly `0`; `run_continuous_batch` body is `pass` only.

**Mutation-verified:** a synthetic module with `"LOCAL_ACTIVE"` status,
`actions_today += cycle_num * 31`, and `{"actions_today": 277528}` is flagged by
all three guards.

### T-4 — `tests/test_email_optout_fail_closed.py`
All four required behaviours, monkeypatching `app.platform.email_unsub` only
(never the real ledger): (a) healthy store → `False` for a non-suppressed
address; (b) `suppressed is _UNREADABLE` → `True`; (c) live lookup raising →
`True`; (d) empty/`None`/whitespace address → `False`. Plus the default-arg path
and the sentinel-passed-as-2nd-arg path.

---

## 2. Exact commands and summary lines

```
.venv/Scripts/python.exe -m pytest tests/test_ci_required_lanes.py \
    tests/test_compliance_gate_structural.py tests/test_workforce_telemetry_truth.py -p no:cacheprovider
```
```
4 failed, 18 passed in 1.54s
```
(the 4 failures are **pre-existing stale tests**, see §4 — none are new)

```
.venv/Scripts/python.exe -m pytest tests/test_email_optout_fail_closed.py \
    tests/test_log_redaction.py tests/test_fail_open_refused_in_production.py \
    tests/test_suppression_compliance_gates.py -p no:cacheprovider
```
```
95 passed in 1.93s
```

```
.venv/Scripts/python.exe -m pytest tests/test_compliance_gate_structural.py \
    tests/test_workforce_telemetry_truth.py tests/test_email_optout_fail_closed.py -p no:cacheprovider
```
```
21 passed in 0.48s
```

```
.venv/Scripts/python.exe -m pytest \
  "tests/test_ci_required_lanes.py::test_aggregator_run_block_asserts_pytest_job_result_not_echoes" \
  "tests/test_ci_required_lanes.py::test_aggregator_does_not_rely_on_echo_for_any_required_lane" -p no:cacheprovider
```
```
2 passed in 0.14s
```

> Note: the brief's literal `-q` collides with the ini `addopts = "-q"`, producing
> `-qq`, which **suppresses the final count line**. The runs above drop the extra
> `-q` so the summary is visible. (pytest.ini `timeout=120` guard is inactive —
> `pytest-timeout` is not installed locally.)

---

## 3. Findings

### F-1 (HIGH) — the aggregator fix now correctly REDs the merge on 4 pre-existing stale tests
`tests/test_ci_required_lanes.py` already contained **4 failing tests** before my
change (confirmed by a pre-edit run). They are the concrete instance of
"the merge gate could not fail on tests":

| Test | Why it fails |
|---|---|
| `test_pytest_is_a_parallel_matrix_not_a_serial_loop` | asserts `ci["jobs"]["pytest-shards"]` — job removed 2026-09-04 |
| `test_aggregator_reports_failure_not_skip` | asserts `needs['pytest-shards'].result` — stale name |
| `test_heavy_lanes_are_pr_or_dispatch_only` | `KeyError: 'pytest-shards'` |
| `test_lock_install_does_not_pull_torch` | asserts `pydantic-core==2.46.4`; action pins `==2.46.5` |

These tests run in the required pytest lane and are **not** network-marked. So the
lane was RED, the aggregator only *echoed* `pytest-job`, and the merge went GREEN —
exactly the reported failure mode. **Now that the aggregator asserts the lane, this
RED will block the merge** (the fix working as intended). **Recommendation:** the
lead must decide — reconcile the 4 tests with the current single-job layout
(`pytest-job` + xdist `-n auto`) and the real pin (`2.46.5`), or revert the
2026-09-04 restructure. **RESOLVED in task #7 — see §5:** reconciled (re-anchored,
not weakened). Kept here as the record of the original finding.

### F-2 (LOW) — T-4 call-site description in the brief was inaccurate
The brief said "the 6 call sites pass no argument". Actual: there are **7** call
sites of `_is_suppressed_email(...)` (excluding the definition), and **all 7 pass a
second argument** — the pre-loaded `_suppressed`/`suppressed` set (which is either a
real set or the `_UNREADABLE` sentinel). No call site uses the no-arg default. The
test therefore covers both paths: `test_default_arg_path_consults_live_store` and
`test_sentinel_passed_as_second_arg_blocks`. Evidence: `grep -c` = 8 (incl. def) →
7 call sites at lines 691, 757, 987, 1058, 1179, 1531, 1776.

---

## 4. What could NOT be pinned and why

* The 4 stale tests in `test_ci_required_lanes.py` (F-1). **Re-anchored in task #7
  (§5)** — reconciled to the current layout, not weakened. No invariant dropped.
* No production-code defect was exposed by the new tests — all new tests pass
  against the current working tree, and all mutation checks confirm the pins bite.
* `pytest-timeout` is absent locally, so the ini `timeout=120` guard is inert; a
  hang would not be bounded. (Environment fact, not a code defect.)

**Evidence labels:** all statements above are **TEST-PROVEN** (local) unless noted;
the 4 stale-test failures are **PRODUCTION-PROVEN** in the sense that they are the
observed RED the broken aggregator swallowed. No production behaviour was changed
or re-verified against the live VPS in this phase.

---

## 5. Task #7 — re-anchoring the 4 stale tests (2026-09-14)

**Decision: reconcile, do not revert, do not weaken.** The 4 tests were re-pointed
at the current CI layout. The aggregator now depends on **5** lanes
(`needs: [prod-check, pytest-job, pip-audit, quality, harness-redis-integration]`,
`ci.yml:193`) and asserts all five (`ci.yml:204-210`).

### Before / after summary lines
| | Command | Result |
|---|---|---|
| before | `pytest tests/test_ci_required_lanes.py` | `4 failed, 6 passed` |
| **after** | `pytest tests/test_ci_required_lanes.py` | **`11 passed in 0.21s`** |
| after | RUN A (`ci` + structural + telemetry) | **`23 passed in 0.48s`** (was `4 failed, 18 passed`) |
| after | RUN B (email + log_redaction + fail_open + suppression_compliance_gates) | **`95 passed in 1.62s`** |

### What changed, per test (no assertion dropped)
| Old test | Re-anchored to | Why it is **stronger**, not weaker |
|---|---|---|
| `test_pytest_is_a_parallel_matrix_not_a_serial_loop` | `test_pytest_lane_runs_parallel_not_serial` | Same "parallel, not serial" invariant; now also asserts `-n auto` **and** the `pytest-xdist` extra are present. The pytest lane is *derived* from the aggregator's `needs`, not hardcoded. |
| `test_aggregator_reports_failure_not_skip` | same name | Now iterates **every** lane in `needs` (5, was 1) requiring a real `test … = "success"` line, **and** asserts every `needs` lane exists in `jobs` (fails loudly instead of `KeyError`). |
| `test_heavy_lanes_are_pr_or_dispatch_only` | same name | Heavy set = all jobs minus the aggregator minus the explicit always-on gate; a heavy lane that *loses* its `if:` now fails (previously it silently dropped out of the set). Also cross-checks `heavy ⊆ needs`. |
| `test_lock_install_does_not_pull_torch` | torch-only + new `test_pydantic_core_pin_matches_the_lock_pairing` | The torch ban is unchanged. The stale `pydantic-core==2.46.4` literal was replaced by a check that derives the expected version from the **lock** (`requirements.lock.txt` pins `pydantic==2.13.5`) and the pairing `tests.yml:63` documents (`2.46.5`), then asserts `action.yml` matches. A lock bump or action drift now fails loudly. |

**Mutation-verified** (in-memory, no production edit): removing `-n auto`; re-adding
the serial for-loop; dropping any single lane's `= "success"` assertion; adding a
`needs` entry with no job; stripping `if:` from `harness-redis-integration`; adding a
new ungated job; renaming `quality`; and drifting the action pin to `2.46.4` — **all
correctly fail**. The real `ci.yml` passes all.

### ⚠️ Ordering constraint (record this)
The 4 tests were RED *inside the required pytest lane*, and the aggregator only
echoed that lane, so merges went green. The aggregator now asserts the lane, so
**once the branch-protection ruleset is enabled it will RED every PR until these 4
are fixed.** They are fixed as of this task, so the safe order is:

1. land this test re-anchor (and Rex's aggregator fix) — **do NOT enable the ruleset first**;
2. then enable `Protect main`.

If the ruleset were enabled before this re-anchor, every PR would block immediately.

### Verdicts the lead asked for
* **Real AST shape of `_dnd_fail_open`** (T-2): `FunctionDef` → `If` with
  `test = Call(Name('_is_production'))` → body contains `Return(Constant(False))`
  (a direct child; a nested one would also match). Exactly one module-level function
  in `compliance.py` references both `DND_FAIL_OPEN` and `_is_production`. Pinned
  structurally; a stub/log-only branch does **not** satisfy it.
* **Real orchestrator status field names** (T-3): `status`, `active_workers`,
  `actions_today`, `working_members`, `active_members`, `peer_rescues_count`,
  `evidence_kind`, `task_execution_verified`, `agents`, `recent_rescues`, `cycle`,
  `timestamp`, `note`. Values pinned: `status="NOT_INSTRUMENTED"`,
  `active_workers=0`, `actions_today=0`, `evidence_kind="inference_probe_only"`,
  `task_execution_verified=False`, `agents=[]`. Matches the brief exactly.

### F-3 (MEDIUM) — the CI restructure had already orphaned 3 assertions for ~10 days
`ci.yml` moved from 4 shards to a single `pytest-job` on 2026-09-04; the tests here
kept referencing `pytest-shards` until this task. That is the exact "fix one
automation, break another" pattern. The durability fix (derive lanes from `needs:`,
assert `needs ⊆ jobs`) is what stops it recurring.

### F-4 (LOW) — brief said "iterate all five `needs`"; confirmed 5
`ci.yml:193` now has exactly five `needs` entries (Rex added `quality` and
`harness-redis-integration` in task #3). Verified, not assumed.
