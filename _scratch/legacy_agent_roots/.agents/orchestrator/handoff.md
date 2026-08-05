# Handoff — Verified State

**Written:** 2026-07-21 · **Repo:** `C:\Users\Ratanshila\Documents\leadgenrationaiagent`
**Method:** every line below was verified by reading code or probing a live endpoint
during this session. Nothing is carried over from prior handoffs on trust.

> **Correction to the previous handoff.** It pointed at
> `c:/Users/Ratanshila/Documents/leadgenrationaivoiceagent` — a *different* path
> from this repo — and reported Milestone 3 as DEGRADED after subagents died on
> 429s. Treat that document as superseded. If `leadgenrationaivoiceagent` exists
> on this machine, someone must decide which checkout is canonical; that question
> is still open and is **not** answered here.

---

## Status vocabulary

These are deliberately kept separate. Do not collapse them into "done".

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | Code changed in the working tree |
| `TESTED` | Verified by executing something, in this environment |
| `COMMITTED` | In git history |
| `DEPLOYED` | Running on the VPS |
| `PROD-VERIFIED` | Confirmed by probing production |

---

## 1. Production truth — ⚠️ CORRECTED, and now STALE

**Earlier in this session I wrote "there is no drift". That is no longer true.**
Recording the correction rather than quietly overwriting it:

| | Value |
|---|---|
| Local `main` HEAD (re-read from `.git/refs/heads/main`) | **`9c1bb308ceb90388fd4937d7de016fca9b7c2dc4`** |
| Last-known production version | `d02a999c` |
| Gap | **exactly 1 commit**, undeployed |

The one commit main gained: `9c1bb30 fix(owner-os): wire Isha Runtime tenant/topic
UI controls` (2026-07-21 08:26 +0530).

**Main advanced DURING this session** — someone else (Cursor / another agent /
the user) committed while work was in progress. Assume this repo is concurrently
edited. Per CLAUDE.md §8: never `git add -A`; diff shared files before touching.

### ⚠️ The `/health` figure is NOT freshly verified

A second probe returned a response **byte-identical** to the first — same
`timestamp` (`2026-07-21T02:15:56.351467`) *and* same `uptime` (`9h 49m 8s`).
An uptime that does not advance across hours proves the response was **cached**,
not re-fetched.

So `d02a999c` is *last-known*, not *currently-confirmed*. **Re-probe before
making any deployment decision.** Do not repeat my earlier mistake of treating a
cached read as live evidence.

Not verified (no VPS access): container-level SHA consistency, migration state,
queue/DLQ depth.

---

## 2. Agent roster — TESTED

`app/platform/team.py` `STAFF` contains **exactly 31 keys** (`manager` = "Boss"
is one of the 31, not a 32nd). `agent_registry.build_registry()` returns 31 and
its key set is identical to `STAFF`'s.

Live lane distribution: **GREEN 20 · AMBER 9 · RED 2**.

---

## 3. Safety boundaries — TESTED at runtime

Executed against the real modules with no env overrides set:

| Gate | Value | Meaning |
|---|---|---|
| `platform_dial.enabled()` | `False` | Outbound calling OFF |
| `dial_gate.test_mode()` | `True` | Promotional calls fail-closed |
| `data/platform_dial.json` | absent | No file override enabling dial |
| `data/dial_test_mode.json` | absent | No file override disabling test mode |
| `PLATFORM_DIAL_DAILY` / `DIAL_TEST_MODE` / `DND_FAIL_OPEN` | all unset | No env override |

Registry safety invariants, all passing:

- RED lane count == 2, and the RED agents are exactly `ananya` + `swara`
- both RED agents have `default_mode == HARD_OFF`
- no AMBER or RED agent defaults to LIVE

**Calling is HARD OFF at every layer. Nothing in this session changed that.**

---

## 4. Corrected this session — IMPLEMENTED (not committed)

### 4.1 `app/platform/agent_registry.py` — dangerous false docstring

The module docstring claimed:

> *"It is **INERT / additive**: nothing in the running app imports this yet. It
> adds NO runtime behaviour, touches NO compliance gate, and cannot change how
> any agent runs."*

**That was false.** The module is imported at runtime by four call sites:

| Caller | Line |
|---|---|
| `agent_runtime.evaluate_policy()` | 507 ← **enforcement** |
| `agent_runtime.runtime_status()` | 800 |
| `agent_status` | 189, 218 |
| `ops_assurance` | 82 |

`evaluate_policy` reads `get_contract()` as the dispatch source of truth (L516,
commented *"registry = source of truth"*) and blocks RED-lane dispatch off
`contract.lane` (L521).

**Why this mattered:** the docstring told any reader — human or agent — that
editing `_GOVERNANCE` was consequence-free. In reality, flipping a lane from RED
to GREEN there removes the L521 dispatch block for a voice agent. The docstring
was actively inviting the single most dangerous edit in the repo.

Docstring replaced with the true call-site list and an explicit warning. The
same false "INERT" claim was echoed in `tests/test_agent_registry.py`'s header
and was corrected there too.

**Mitigating fact:** the invariants *were* already protected by real tests —
`test_cold_outbound_voice_is_red_and_hard_off`, `test_no_amber_or_red_agent_defaults_to_live`,
and `test_lane_distribution_matches_scorecard_shape` (asserts `RED == 2`).
`test_agent_runtime.test_red_lane_remains_hard_off` additionally proves the block
survives an env flip. So the code was safe; the *documentation* was not. No new
test was added, because the existing ones already cover it — adding another would
have been theatre.

### 4.2 `scripts/prod_check.py` — orphan module tree detector

`check_stale_pycache()` skipped orphaned `.pyc` at L65-66 with
`# orphan pyc, harmless`. Correct about *import* safety (CPython won't load a
`__pycache__` `.pyc` without its source) — but it meant **nothing in the repo
detected that an entire module tree had vanished**.

Added a non-fatal `WARNINGS` channel that reports orphan *clusters* (2+ in one
directory). Deliberately does **not** touch the exit code: the orphans exist
right now, so failing the deploy gate would have been an unacceptable blast
radius for a change that cannot be fully exercised outside the VPS.

Verified by execution — it fires correctly on both real clusters:

```
ORPHAN MODULE TREE: app/integrations/openclaw — 9 .pyc files with NO .py source
ORPHAN MODULE TREE: tests — 5 .pyc files with NO .py source
                    (incl. test_openclaw_owner_copilot.py)
```

### 4.3 `audit-automation` skill — fabricated remediation command

`references/output-format-and-escalation.md:110` instructed, inside a **compliance
escalation** path: `python scripts/dnd_sync.py --rebuild`.

**`scripts/dnd_sync.py` does not exist and never did.** An operator following the
DND opt-out escalation would hit a dead end mid-incident.

Replaced with the real mechanism: the DND cache is in-memory
(`app/utils/dnd_checker.py`, `_cache`, 7-day expiry) with nothing to rebuild;
opt-outs are authoritative from the local consent ledger, not the registry API;
un-cached numbers return UNVERIFIED and fail **closed**; `DND_FAIL_OPEN` must
stay unset.

Fixed in **both** `.claude/skills/` and `.agents/skills/` — for this skill they
are genuine duplicate files, not junctions (confirmed: the `.agents` copy still
had the old text after the `.claude` copy was edited).

---

## 5. Open architectural questions — NOT resolved

### 5.1 OpenClaw — RESOLVED. Nothing was lost. See ADR-130.

**The "missing source" premise was wrong.** Full reasoning in
`memory/decisions.md` → **ADR-130 (2026-07-21)**. Summary:

`.gitignore:2` is `__pycache__/`. The source is safe on
**`feat/openclaw-owner-copilot` = `8fc1f62b`** (local == origin, pushed).
`docs/context/SESSION_HANDOFF.md:10` records that this branch *"remained dirty
and untouched"* as the primary checkout here. So: branch was checked out → running
it produced `.pyc` → someone switched back to `main` → git removed the tracked
`.py` files but **never touches gitignored files**, leaving `__pycache__/` behind.

Orphaned bytecode after a branch switch is **expected git behaviour**, not a lost
branch, not a bad revert.

**Safety review of the branch — PASS.** It is a complete, well-engineered
feature: 32 files, 3353 insertions, a **764-line test suite**, an ADR, a runbook.

- `owner_os_adapter` calls `owner_os.create_command()` → **Owner OS authority
  preserved, no second dispatcher**
- `policies.py` defines an explicit `RED_COMMANDS` frozenset, commented *"always
  refused even if allowlist misconfigured"* — covering `shell.execute`,
  `sql.execute`, `calling.enable`, `platform_dial.enable`, `billing.*`,
  `deploy.production`, `kill_switch.bypass`, `audit.disable`
- `OPENCLAW_ENABLED` defaults `0` (fail-closed); unknown command → `RED` → refuse
  (L172); RED is stripped from the allowlist (L140)
- No `subprocess`, `os.system`, `shell=True`, `celery send_task`, or `stripe`
- Tests include `test_red_rejected_even_with_allow_red_flag`,
  `test_red_calling_nl_rejected`, `test_sql_injection_chars_blocked`,
  `test_xff_spoof_does_not_bypass_source_check`,
  `test_stage_a_cannot_mutate_agent_state_in_production`, `test_agents_list_31`,
  plus tenant-isolation and Jiya billing-alias coverage

**NOT merged, deliberately.** Two blocking reasons:

1. `git merge-tree` reports **4 conflict indicators**. Branch base `ef5e8b4`
   (2026-07-20) is **7 commits** behind main; conflicts are expected in
   `CLAUDE.md`, `AGENTS.md`, `docs/context/*`.
2. Its own 764-line suite **could not be run** here (sandbox lacks `jose`,
   `edge_tts`, …). Merging 3353 lines of security-sensitive code without running
   its own tests would be a fake completion.

**Current truth, unambiguous:** OpenClaw is **complete and reviewed-safe, but NOT
installed on main** — it exists only on its branch. Deleting the orphan `.pyc` is
safe (gitignored artifacts; source is on origin) but was **not** done this
session.

### 5.2 Competing registries

`team.STAFF` is canonical and live. `agent_registry._GOVERNANCE` is a
hand-authored parallel 31-row table — reconciled at build time, but able to drift.
Also present: `engineer_agents._AGENTS`, `office_hq.RUNNABLE_MEMBERS`,
`staff_jobs.STAFF_JOBS`, `owner_agent_execution`'s per-agent job map.
`owner_os.agent_registry()` (L570) already computes `orphan_runnable`, i.e. drift
is expected and instrumented rather than prevented.

### 5.3 Other duplications observed, not addressed

- **Two dispatchers, two DLQs** — Celery (`dlq:failed_tasks` in Redis) and the
  in-process contract runtime (`data/agent_runtime_dlq.jsonl`).
- **Three tenant-identity resolvers** — `clients_store.canonical_client_id()`,
  `billing/usage.resolve_client_id()`, and a hardcoded `"jiya" → "jiya-makeover"`
  string match in `owner_os._extract_tenant()` (L888).
- **Two CI test workflows** — `.github/workflows/test.yml` *and* `tests.yml`.

### 5.4 Skills tree topology — handle with care

`.claude/skills/` and `.agents/skills/` are **one tree with a junction overlay**:
61 of `.claude/skills/`'s entries are Windows directory junctions into
`.agents/skills/`; ~60 are real duplicated directories with identical content
(differing only in CRLF vs LF). Membership differs: 23 `.agents`-only skills,
1 `.claude`-only.

⚠️ Per `.claude/skills/SKILLS_PARITY.md`: **never** run `rmtree` / `robocopy /MIR`
/ recursive delete across these trees — deletion propagates through junctions and
destroys the real content.

`SKILLS_PARITY.md:5` is stale: it says "~184 folders in `.claude/skills/`"; the
actual count is 121 directories. Its "23 `.agents`-only" figure is still correct.

---

## 6. What was NOT done, and why

| Not done | Reason |
|---|---|
| Full `pytest` suite | Targeted governance/runtime suites now **RUN and GREEN on the host** (see §9). The *whole* suite is still unrun — CLAUDE.md §3 warns it can hang in the `team_pulse` area. |
| ~~`prod_check.py`~~ | **DONE — see §9.** Passed on the Windows host. The 1178 `PYCACHE` entries seen earlier were confirmed a sandbox mount-permission artifact: the host reports `0 stale .pyc removed`. |
| Deploy / canary / rollback | No VPS access, no credentials. |
| Authenticated admin-UI proof | Requires credentials. |
| Git commit | Left uncommitted for review. |
| 12 new "book-to-skill" skills | An audit found 6 of 12 targets already COVERED and 6 PARTIAL, **0 missing**. Creating 12 more would have produced exactly the duplicate-registry problem the brief forbids. Real gaps are narrower — see §7. |

---

## 7. Genuine skill gaps (keyword-verified absent repo-wide)

Not "missing skills" — missing *concepts*. Each returned zero hits:

- `canary`, `blue-green`, `progressive rollout`, `shadow traffic` — SRE/SLO
  material is strong (`slo-error-budget`, `ship-checklist`), canary is absent.
- `circuit break`, bulkhead, timeout budget — retry/backoff/DLQ exist; isolation
  patterns do not.
- `outbox`, `saga`, `exactly-once`, `dead letter` (as a pattern) — idempotency
  exists in practice; no distributed-consistency guidance.
- `team topolog` — topology *selection* exists; org-design framing does not.
- ADR *authoring process* — `product-split-adr` is one specific ADR (ADR-009),
  not a decision-registry practice.
- A single skill owning the **agent authority/policy model**. The code exists
  (`agent_permissions.py`, `risk_approve.py`, `agent_checkpoints.py`) but
  governance is split across `llm-security`, `self-improve-control`,
  `leadgen-security-rbac`, and `careful`.

---

## 9. Real Windows host verification — DONE 2026-07-21 (TESTED)

Executed via Desktop Commander in PowerShell against the real host + project venv.

**Host baseline:** `HEAD = 9c1bb308…`, branch `main`, `git diff --check` clean.

**Safety net created before any edit:**
- branch `safety/pre-enterprise-pass-20260721-085312` (pointer only, not switched to)
- `.git\leadgen-enterprise-pass-20260721-085312.patch` (72,572 bytes) — inside
  `.git\`, so it can never be accidentally committed

### `.venv\Scripts\python.exe scripts\prod_check.py` → **PASSED**

```
[1/6] 1420 source files parsed
[2/6] pycache check done (0 stale .pyc removed)
[3/6] app.main imports OK
[4/6] routes checked (1160 registered)
[5/6] config checked (env=development)
[6/6] wiring checked (48 pages 0 gaps; automation 0 gaps)
[WARN] 2 non-blocking signal(s):
  ~ ORPHAN MODULE TREE: app\integrations\openclaw ... 9 .pyc, no .py
  ~ ORPHAN MODULE TREE: tests ... 5 .pyc, no .py
[OK] ALL CHECKS PASSED - ready to deploy
```

Three things this proves:
1. **`0 stale .pyc removed`** — the 1178 `PYCACHE` failures from the sandbox were
   purely a mount-permission artifact. Not a repo defect.
2. The new orphan warnings are genuinely **non-blocking**: 2 warnings present and
   the verdict is still `ALL CHECKS PASSED`.
3. No `UnicodeEncodeError`. (An em-dash in the warning string did render as
   `?"` mojibake on the cp1252 console, so it was replaced with ASCII.)

Pre-existing, **not** introduced here: `[i] API.md endpoint index OUT OF DATE —
run scripts/sync_api_docs.py`.

### `.venv\Scripts\python.exe -m pytest tests/test_agent_registry.py tests/test_agent_runtime.py`

```
39 passed, 1 warning in 6.82s
```

Covers RED-lane hard-off, env-flip resistance, roster reconciliation, tenant
isolation, budget, idempotency, DLQ, kill switches.

---

## 10. Production truth — FRESHLY VERIFIED 2026-07-21 (supersedes §1)

Cache-bypassed via `curl.exe` with `Cache-Control: no-cache, no-store, max-age=0`
+ `Pragma: no-cache` + a `?cache_bust=<epoch_ms>` query, run twice 32s apart:

| Probe | server timestamp | uptime | version |
|---|---|---|---|
| 1 | `03:37:41.520589` | `0h 18m 33s` | `9c1bb308` |
| 2 | `03:38:13.585819` | `0h 19m 6s` | `9c1bb308` |

Freshness proof: uptime advanced 33s across a 32s gap · no `Age:` header ·
response `Cache-Control: no-store, no-cache, must-revalidate` · version stable ·
`environment: production`.

**PRODUCTION = `9c1bb308` = local `main`. Zero drift.**

Two corrections this supersedes: `d02a999c` was (a) a cached read, and (b)
superseded by a real deploy ~19 min before the probe. Production was redeployed
during this session.

---

## 11. OpenClaw integration — MERGE-READY (not merged, not deployed)

Integrated in an **isolated worktree**, never on `main`.

| | |
|---|---|
| Worktree | `C:\Users\Ratanshila\Documents\leadgen-openclaw-integration` |
| Branch | `integration/openclaw-owner-copilot` |
| Base | `main` @ `9c1bb30` |
| Source | `feat/openclaw-owner-copilot` @ `8fc1f62` (local == origin) |
| Merge commit | **`2c48084`** |
| Worktree status | clean |
| Tracked `.pyc` in merge | **0** |

### Conflicts — 2 actual (merge-tree's "4" was a coarse indicator)

`app/main.py` and `frontend/owner_os.html` — the real integration points —
**auto-merged clean**.

1. **`.gitignore` → UNION.** main ignores `config/openclaw/.local/` (tokens/state);
   the branch un-ignores the plugin manifest. Both kept: secrets stay ignored,
   manifest stays tracked.
2. **`docs/context/SESSION_HANDOFF.md` → took MAIN's.** The branch copy is a stale
   2026-07-20 state doc; merging it would have overwritten current state.

### Security proof — empirical, not a code read

Worst case exercised: `OPENCLAW_ENABLED=1` **and** `OPENCLAW_ALLOW_RED_ACTIONS=1`
**and** every RED command injected into `OPENCLAW_COMMAND_ALLOWLIST`.

Result: **all 8 RED commands refused** (`shell.execute`, `sql.execute`,
`calling.enable`, `platform_dial.enable`, `billing.mutate`, `deploy.production`,
`kill_switch.bypass`, and an unknown command → RED). `allowed_commands()` leaked
**zero** RED entries. Defaults with no env set: `openclaw_enabled()` False,
`allow_red_actions()` False.

Authority path confirmed in source: `owner_os_adapter` → `owner_os.create_command()`.
No second dispatcher.

### Test evidence (project venv, real host)

| Suite | Result |
|---|---|
| `tests/test_openclaw_owner_copilot.py` | **46 passed, exit 0** |
| owner-os + governance + runtime + tenant-isolation + isha-ui (8 files) | **123 passed, exit 0** |
| `scripts/prod_check.py` in worktree | **ALL CHECKS PASSED** |

Worktree `prod_check` shows `1166 routes` (main: `1160`) = +6 OpenClaw routes, and
**no orphan warnings** — the detector correctly stops firing once the source exists.

**Verdict: MERGE-READY.** Not merged to `main`. **NOT DEPLOYED.**

---

## 12. Exact next action

Open a PR from `integration/openclaw-owner-copilot` → `main` for human review.
Do **not** fast-merge: `app/main.py` gained a router mount and `frontend/owner_os.html`
gained UI, both auto-merged without human eyes on them.

Still outstanding: **skill consolidation** (§7 gap list) — not started in any pass.
