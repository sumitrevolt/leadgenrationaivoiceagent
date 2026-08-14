# External Agent Orchestrator — Proven Executors, Leases, Flags

> **Mission:** LG-00-EXTAGENTS-MAP-20260813 (docs only, no code)
> **Base SHA:** `8217de4faad084388a647a7b3c2d5e866a443f85` (origin/main #353)
> **Scope read:** `app/dev_control/external_agents/` (schema, policy, orchestrator, adapters, store, runner/*)
> **Verification basis:** exact source + `tests/test_external_agent_runner.py` (27 tests, all in repo at base SHA)
> **Status:** read-only map. No files outside `docs/` touched.

Purpose: document **exactly which executors, leases and flags already work**, so a new
adapter (e.g. an OpenCode runner) copies proven patterns instead of inventing its own.

---

## 1. What this system is

An **External Agent Orchestrator** that issues bounded missions to local CLI/desktop
agents and a **runner** (`runner/`) that may *invoke* allowlisted executors unattended.

- The **orchestrator records missions** (state machine, risk classes, leases, evidence).
- The **runner may execute** missions when BOTH flags are ON (`EXTERNAL_AGENT_ORCHESTRATOR`
  + `EXTERNAL_AGENT_RUNNER`), in an isolated environment only. Production stays OFF
  until a separate owner gate (`runner/__init__.py` docstring).
- Owner OS remains sole authority. Runner grants **no deploy / calling / billing / outreach**
  rights, ever (`authorize.py`, `status.py` note).

## 2. Executors — exactly which work

| Executor | Adapter class | Role | Worktree | Proven by |
|---|---|---|---|---|
| `cursor` | `CursorAdapter` | `executor` | **required** | `runner/cursor_exec.py`, tests (manifest extract, argv build, worktree+push-guard) |
| `claude` | `ClaudeAdapter` | `reviewer` | not required | `runner/claude_exec.py`, tests (review extract, usage envelope, bash disallowed) |

Only these two are registered. `adapters.known_executors()` returns `["claude", "cursor"]`.

### Registration points — an executor name must exist in ALL of these

1. `adapters._ADAPTERS` — `{CURSOR: CursorAdapter(), CLAUDE: ClaudeAdapter()}` (`adapters.py:206`)
2. `adapters.CURSOR` / `adapters.CLAUDE` string constants (`adapters.py:23-24`)
3. `eligibility.KNOWN_EXECUTORS` — `frozenset({"cursor", "claude"})` (`runner/eligibility.py`)
4. `app/api/dev_tasks.py:571` — `executor: Literal["cursor", "claude"]` (mission create API; a new
   executor is rejected at the API boundary until this Literal is widened)
5. `orchestrator.create_mission` — validates against `adapters.known_executors()`
   (`orchestrator.py:112-113`); Cursor additionally enforces `cursor_requires_allowed_paths`
   (`orchestrator.py:115-119`) and `cursor_requires_branch_worktree` (`eligibility.py`)
6. `orchestrator.py:639-640` — hardcoded summary counts per executor (`"cursor": …`, `"claude": …`)
7. Tests asserting executor-specific reason strings (e.g. `cursor_requires_allowed_paths`) —
   keep existing strings untouched, add new ones for the new executor

> **New-executor implication:** the eligibility `KNOWN_EXECUTORS` set, the API `Literal`,
> and the orchestrator summary dict are three hard gates besides the adapter itself. A
> partial registration (adapter only) fails at the API/eligibility boundary silently-ish
> ("unknown_executor") — that is by design, and it is the #1 thing a new adapter must not miss.

### Adapter contract (`adapters.py`)

- `build_packet(mission)` — structured, redacted brief. No shell, no file writes, no provider
  calls. `RED` missions always refused (`packet_for`).
- `validate_result(mission, result)` — deterministic acceptance incl. scope-breach detection
  via `policy.path_violations` (changed files outside `allowed_paths` → violation). Acceptance
  is **code, not an LLM assertion**.
- `validate_review` (Claude reviewer) — enforces review separation: `reviewer != executor`,
  `verdict ∈ {PASS, CHANGES_REQUIRED, BLOCKED}`, concrete citations required, synthetic
  citation `runner_auto_review` forbidden.
- `RESULT_SCHEMA` / `REVIEW_SCHEMA` — the exact manifest shapes the executor must return.

## 3. Leases — how single-writer is enforced

`store.py` — JSON documents under `data/external_missions` (path resolved by
`runtime_data_authority`, override `EXTERNAL_MISSION_DIR`). Correctness boundary = **CAS
backend** (`cas.get_backend()`: Redis when reachable, else portalocker file locks under
`data/external_missions/.locks/`), **never a process-local mutex** (`store.py` module docstring,
`persistence_report()`).

| Function | Behaviour | Proven by |
|---|---|---|
| `claim` | Cross-process compare-and-set lease; exactly one owner wins; rejects terminal missions | store + CAS tests |
| `heartbeat` | Renews lease + `last_heartbeat` under the mission doc lock | runner heartbeat tests |
| `release` | Clears lease, audit event | — |
| `transition_cas` / `apply_cas` | Load+mutate+save under doc lock; `expected_status` mismatch → `stale_transition`; `cas_version` audit counter bumped under lock | — |
| `recover_stale` | Expired lease + in-flight status → `FAILED_RETRYABLE` + recovery evidence; re-checks lease under lock | — |
| `find_by_idempotency_key` / `register_idempotency` | Atomic first-writer-wins idempotency registration | — |

**Lease/heartbeat safety contract** (`runner/lease_contract.py`, PR #147 cycle-6):
`interval <= lease_ttl / SAFETY_FACTOR(3)`; `MIN_LEASE_TTL_S=30`;
`DEFAULT_HEARTBEAT_INTERVAL_S=25`; `HeartbeatWatch` uses `time.monotonic` (no wall-clock
dependence). New executors must derive TTL/interval through `derive_lease_and_interval`
and keep the ratio — a violation fails `validate_heartbeat_contract` fail-closed.

**Timezone landmine (already fixed, do not reintroduce):** `store._utc_epoch` converts naive-UTC
wall-clock to epoch with explicit `tzinfo=utc` — `.timestamp()` on a naive datetime interprets
it as LOCAL time (5.5h off on IST hosts), which made every lease look expired and invited a
second runner. Any new lease code must use this helper.

## 4. Flags — complete inventory (defaults + gates)

| Flag | Module | Meaning | Default |
|---|---|---|---|
| `EXTERNAL_AGENT_ORCHESTRATOR` | `policy.FLAG` | Master orchestrator gate | OFF (prod) |
| `EXTERNAL_AGENT_RUNNER` | `runner/flags.py RUNNER_FLAG` | Runner may execute **only if orchestrator is also ON** (`runner_enabled()` = both) | OFF |
| `EXTERNAL_AGENT_PROFILE_ROOT` | `runner/profile.py` | Dedicated profile root override | temp dir `leadgen_ext_agent_profiles` |
| `EXTERNAL_AGENT_WORKTREE_ROOT` | `runner/worktrees.py` | Worktree root (missions must live inside it) | `C:\Users\Ratanshila\Documents\_leadgen_worktrees` |
| `EXTERNAL_AGENT_CURSOR_BIN` | `runner/status.py` | Cursor bin override (else `auto`) | `auto` |
| `EXTERNAL_AGENT_PASS_CURSOR_API_KEY` | `runner/process_safe.py` | Explicit gate to pass exact `CURSOR_API_KEY` (never wildcard) | OFF |
| `EXTERNAL_MISSION_DIR` | `store.py` | Mission store override | shared authority path |

Dual-gate rule (`runner/flags.py`): `runner_enabled() = orchestrator_enabled() AND truthy(RUNNER_FLAG)`.
`test_flag_registered` asserts flag registration; `test_runner_off_refuses` /
`test_orchestrator_off_blocks_runner` assert both refusal directions.

## 5. Runner safety layers — proven patterns new executors must copy

| Layer | File | Guarantees |
|---|---|---|
| Allowlisted subprocess | `runner/process_safe.py` | Only allowlisted basenames (`claude`, `agent*`, `cursor-agent*`, python helpers, fixtures); argv arrays only (no shell); shell-metachar / `%VAR%` / `!VAR!` refusal; python only for owned `process_helper.py` under `tests/fixtures`; worktree must be inside `allowed_root`; bounded output (512KB default, 4MB hard cap); `taskkill /T` full-tree terminate on Windows; heartbeat+cancel controllers |
| Deny-by-default env | `runner/process_safe.py` `_ENV_PROFILES` | OS base env + auth-profile dirs only; secret-name deny (`API_KEY`/`TOKEN`/`SECRET`/`PASSWORD`/…); no `CURSOR_*`/`CLAUDE_*` wildcards; `env_injection_refused` for anything else |
| Profile redirection | `runner/profile.py` | Dedicated HOME/USERPROFILE/APPDATA/LOCALAPPDATA per executor; hardlink→symlink→copy; Claude links only `.credentials.json`+`settings.json`; Cursor links only `agent-cli-state.json`/`cli-config.json`/`argv.json` + exact `APPDATA/Cursor/auth.json`; excluded home trees documented; evidence persisted as paths-only |
| Worktree provisioning | `runner/worktrees.py` | Branch regex `^feat/ext-[a-z0-9-]{3,48}$`; worktree inside allowed root; **push disabled via worktree-local `remote.<name>.pushurl=disabled://no-push`** — never `git remote remove` (shared remotes) |
| Authorization gate | `runner/authorize.py` | GREEN local canary: recorded auto-auth; AMBER always parks at `owner_decision_required`; RED refused; never grants deploy/calling/billing |
| Eligibility | `runner/eligibility.py` | GREEN-only auto; RED refused; AMBER parks; eligible statuses `{CREATED, PREFLIGHT, CLAIMED, CHANGES_REQUESTED, FAILED_RETRYABLE}`; ownership-conflict check via `policy.ownership_conflict`; retry-budget enforcement |

## 6. Proven test surface (`tests/test_external_agent_runner.py`, 27 tests)

Coverage themes (names from source):
- Flag/eligibility: `test_runner_off_refuses`, `test_orchestrator_off_blocks_runner`,
  `test_flag_registered`, `test_green_eligible`, `test_amber_requires_owner`, `test_missing_allowed_paths_refused`
- Injection/security: `test_shell_injection_refused`, `test_env_injection_refused`,
  `test_env_deny_by_default_no_cursor_claude_wildcard`, `test_claude_disallows_bash`
- Worktree: `test_worktree_outside_root_refused`, `test_disable_push_does_not_remove_origin`
- Auth: `test_authorize_green_ok`, `test_authorize_amber_blocked`
- Process: `test_process_argv_allowlist_ok`, `test_wall_timeout_respects_mission_caps`,
  `test_heartbeat_cancels_on_failed_beat`, `test_output_cap_truncates`, `test_terminate_uses_taskkill_on_windows`
- Manifest/review extraction: `test_cursor_result_manifest_file_preferred`,
  `test_cursor_result_inner_prose_extractable`, `test_runner_control_files_not_scope_breach`,
  `test_cursor_manifest_extract`, `test_claude_review_extract`, `test_extract_usage_from_claude_envelope`
- Loop/scope: `test_run_mission_once_refuses_when_runner_off`, `test_observed_changed_files_reads_git`

## 7. New-executor copy checklist (e.g. OpenCode)

Copy these proven pieces, do not re-invent:

1. **Adapter** in `adapters.py` — subclass `_BaseAdapter`, register in `_ADAPTERS`, add
   constant. Decide role (`executor` vs `reviewer`) and `requires_worktree`.
2. **Hard gates** — `eligibility.KNOWN_EXECUTORS`, `app/api/dev_tasks.py:571` Literal,
   `orchestrator.py:639-640` summary counts. Missing any one = `unknown_executor`/API reject.
3. **Runner module** `runner/<name>_exec.py` — mirror `cursor_exec.py`: resolve bin (absolute,
   allowlisted), build argv (no shell), extract result manifest (file-preferred),
   honor mission time/token budgets, run under `process_safe.run_allowlisted` with
   `env_profile` (add a profile in `_ENV_PROFILES` + profile material list), heartbeat +
   cancel via `HeartbeatController`.
4. **Eligibility reason strings** — new distinct reason (e.g. `opencode_requires_allowed_paths`);
   never reuse/modify `cursor_*` strings (tests assert them).
5. **Lease contract** — derive TTL/interval via `derive_lease_and_interval`; keep the
   `interval <= TTL/3` ratio; use `store._utc_epoch`-style conversion (naive-UTC → epoch).
6. **Tests** — mirror the 27-test suite at minimum: flag-gate refusals, eligibility,
   argv/env injection refusal, manifest extract, heartbeat cancel, timeout caps,
   worktree root guard, push-guard preservation.
7. **Docs/status** — add to `runner/status.py` bin-override env (pattern
   `EXTERNAL_AGENT_CURSOR_BIN`) and `note` text.

## 8. Current truth (at base SHA)

- Runner **dormant** in prod: `runner_status().environment_badge == "dormant"` unless both
  flags ON. No runner active in production; production enablement = separate owner gate.
- Store shared across app/worker/scheduler via `./data:/app/data` bind mount
  (`store.persistence_report()`); Redis is preferred CAS when reachable.
- Review separation is a declared-name convention under shared admin identity, not
  per-agent cryptographic attestation (`ClaudeAdapter.validate_review` docstring).
