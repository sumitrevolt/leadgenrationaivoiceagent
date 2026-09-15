# Code Review — Deploy Integrity & "fix one, break another"

**Author:** Cody (科迪) · Code Reviewer, Engineering Assurance Team
**Date:** 2026-09-15
**Repo:** `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent` (HEAD `e77f8e08`)
**Scope:** the five owner defects D-A…D-E plus the code they touch. **Review only — nothing modified, committed, pushed or deployed.**
**Serving symptom:** *"ek fix hota hai toh dusra tod jaata hai"* / *"deploy ke baad automation break hore wo nahona chahiye."*

> **Evidence labels (only these):** PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN.
> Every claim below was checked against the file at the quoted line. Where the team lead's summary was stale or overstated, that is stated explicitly rather than confirmed.

---

## 1. Findings (severity-sorted)

| # | Severity | Category | File:Line | Problem | Recommended fix | Evidence |
|---|---|---|---|---|---|---|
| **1** | 🔴严重 | Correctness / release integrity | `scripts/deploy_vps.sh` (verify `:485-503`; **no restart anywhere**) | The canonical release never restarts `leadgen.service`, the systemd host process that owns `127.0.0.1:8000`. It also never **sets** `.env:APP_VERSION`. So its `/health.version == $VER` verify reads the host process's **frozen** env → **`exit 3` on every SHA-changing deploy**. "DEPLOYED $VER OK" is not evidence the serving process runs the new code. | After `git pull --ff-only` (`:289`) and before VERIFY (`:466`): `sed -i` **replace** `APP_VERSION=$VER` in `.env`, then `systemctl restart leadgen`, then wait for the unit. See §2.1. | CODE-PRESENT (script) + PRODUCTION-PROVEN (frozen-env mechanism, SRE §8) |
| **2** | 🔴严重 | Data-loss / destructive git | `scripts/vps_deploy_call_learn.bat:29` | Unguarded `git reset --hard origin/main -q` on `/opt/leadgen`, where **189 tracked files under `data/`** are bind-mounted into 13 live containers. Reverts live invoice/consent/suppression ledgers + DPDP recordings. **Invisible to both repo gates** (they skip `.bat`). | Delete, or replace the remote command with `bash scripts/deploy_vps.sh`. See §2.2. | CODE-PRESENT (line) + PRODUCTION-PROVEN (189 tracked files, mounts) |
| **3** | 🟠高 | Correctness / CLI contract | `scripts/runtime_data_path_scan.py:147-165` | `ratchet --json` prints the JSON document (`:110-128`) and then **falls through** into the human `=== debt ratchet ===` block (`:147-165`). Output = valid JSON + ~5.6 KB of non-JSON. `json.load` → `JSONDecodeError: Extra data: line 24098 column 1`. | `return` after emitting JSON, or gate the human block on `not args.json`. See §2.3. | CODE-PRESENT + LOCAL-ONLY (reproduced: block begins at line 24098) |
| **4** | 🟠高 | Security | `deploy/compose/docker-compose.waha.yml:79-83` vs running `leadgen_waha` | Checked-in config binds `127.0.0.1:3111:3000`; the running container binds **`0.0.0.0:3002->3000`** and `ufw status = inactive` → WAHA is internet-reachable on a host holding prod ledgers + DPDP recordings. | Recreate from the checked-in compose (localhost bind) **and** enable ufw (allow 22/80/443, default deny). See §2.4. | PRODUCTION-PROVEN (SRE re-verified) + CODE-PRESENT (compose) |
| **5** | 🟠高 | Gate integrity | `tests/test_deploy_guard_ordering.py:202-208`; `scripts/_deploy_surface_inventory.py:71-73` | Both scan only `.sh/.py/.yml/.yaml`. The anti-drift test that exists to catch "a NEW destructive script" **cannot see any `.bat`**, yet 4 non-legacy prod `.bat` deploy paths carry destructive git (finding 6). | Extend both to `.bat`/`.cmd`; add the `.bat` paths to `GUARDED_NOW`/`UNGUARDED_DEBT`. See §2.5. | CODE-PRESENT (TEST-PROVEN that the glob excludes `.bat`) |
| **6** | 🟠高 | Data-loss / destructive git | `deploy_godmode.bat:16`, `deploy_outreach_bounce_fix.bat:40`, `deploy_vobiz_fix.bat:12`, `scripts/legacy/{deploy_vps_now,deploy_main_now,fix_push_redeploy,deploy_brain,deploy_fix2,deploy_now}.legacy.bat` | Additional unguarded `git pull`/`git reset --hard` + `compose up -d` against `/opt/leadgen`. `fix_push_redeploy.legacy.bat:22` also runs `systemctl restart leadgen` (the only place in the repo that does). | Delete, or alias to the canonical parent. See §2.2. | CODE-PRESENT |
| **7** | 🟡中 | Truthfulness / DX | `app/platform/runtime_data_ratchet.py:149-150` | Every ratchet failure line says *"…or provide an **evidence-backed exclusion**."* No exclusion mechanism exists anywhere (`grep` for `exclusion|exclude|exempt` across the gate modules → zero implementation hits; the phrase appears only here). The failure output instructs a remedy that cannot be performed. | Correct the message to name only implemented options. **Recommended: option (i).** See §3. | CODE-PRESENT |
| **8** | 🟡中 | Maintainability / doc-truth | `tests/test_deploy_guard_ordering.py:70-110` vs `app/platform/deployment_path_manifest.py:204-327` | `UNGUARDED_DEBT` still lists `vps_build_deploy.py`, `vps_deploy_dashboard.py`, `vps_deploy_workflow_fix.py`, `deploy_all.sh`, `deploy_adr097.sh`, `vps_flywheel_deploy.sh` as **"unguarded — wave 2"**, but the manifest classifies them `GUARDED_BY_CANONICAL_PARENT` (they were consolidated 2026-07-26). Two in-repo sources disagree. | Remove the consolidated entries from `UNGUARDED_DEBT` (they contain no executed destructive command). See §2.6. | CODE-PRESENT |
| **9** | 🟡中 | Config drift / doc-truth | `deploy/compose/docker-compose.waha.yml:79-83`; `AGENTS.md:35`; `CLAUDE.md:35` | The repo describes a WAHA that does not exist in prod: checked-in port `3111`, running port `3002`; `AGENTS.md`/`CLAUDE.md` still say "own WAHA :3111". Docs describe a topology that is not deployed. | Update docs + compose to the real port, or rebind prod to the checked-in config. See §2.4. | PRODUCTION-PROVEN + CODE-PRESENT |
| **10** | 🟡中 | Runtime-data debt | `scripts/waha_watchdog.py:128` and `:227` | The watchdog writes two files inside the checkout: `log_file()` (`:80-81`, default `/opt/leadgen/data/waha_watchdog.log`, opened `"a"` at `:128`) and `health_file()` (`:76-77`, default `/opt/leadgen/data/wa_health_check.json`, opened `"w"` at `:227`). Both scan as **UNDECLARED_MUTABLE_PATH** and are absent from the 793-entry baseline (`grep waha_watchdog app/platform/runtime_data_baseline.py` → 0). The ratchet's remedy line for them is the non-existent exclusion of finding 7. | Route both through `app/platform/runtime_data.py`, or add reviewed allowlist entries. See §2.7. | CODE-PRESENT + LOCAL-ONLY (ratchet output) |
| **11** | 🟢低 | Robustness / DX | `scripts/waha_watchdog.py:47,64-65` | `DEFAULT_WAHA_URL = "http://127.0.0.1:3111"`. If `WAHA_WATCHDOG_URL` is ever unset, the watchdog silently targets a dead port and reports `unreachable / check_waha_service` — a *misleading* (though not silent) diagnosis that sends the operator to the wrong remedy. | Make the default fail loud (require the env var in prod), or default to the real port. See §2.4. | CODE-PRESENT |

**Severity rationale.** #1/#2 are 🔴 because #1 makes the one sanctioned release path unable to ship (and its success message untrustworthy — the owner's exact symptom), and #2 is one command away from reverting live financial/compliance ledgers. #3–#6 are 🟠: a broken machine-readable CI gate, an internet-exposed service, a gate that cannot see a whole class of destructive scripts, and the destructive scripts themselves.

---

## 2. Detail for 🔴/🟠 findings

### 2.1 — Finding #1: the canonical deploy never controls the process it verifies (D-A)

**Verified code.** `grep -nE "restart|systemctl|leadgen\.service" scripts/deploy_vps.sh` → exactly **3** hits, all comments/echo:

```
163:# Systemd leadgen.service reads .env directly (host uvicorn on :8000). If .env
175:  echo "       Systemd leadgen.service reads .env directly — staging env ="
243:  echo "FATAL: candidate build failed — NOTHING restarted, live checkout NOT moved. Tail:"
```

So the script **knows** systemd exists (`:163`, `:175`) and never restarts it. The `.ENV GUARD` only *validates*:

```bash
180 if [ -z "$ENV_APP_VER" ] || [ "$ENV_APP_VER" = "dev" ]; then
181   echo "FATAL: .env has APP_VERSION='$ENV_APP_VER' (must be a commit SHA)."
182   echo "       Systemd reads this — 'dev' means unknown provenance in prod."
183   echo "       FIX: echo 'APP_VERSION=$VER' >> .env"     # <-- append, not replace
```

and the verify curls the port the host process owns:

```bash
486   HEALTH="$(curl -s -m 10 127.0.0.1:8000/health || true)"
487   LIVE_VER="$(printf '%s' "$HEALTH" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')"
...
497 if [ "$LIVE_VER" != "$VER" ]; then
498   echo "FATAL: /health did not report $VER after $HEALTH_MAX_ATTEMPTS attempts."
...
502   exit 3
```

`app/api/health.py:111` → `"version": os.environ.get("APP_VERSION", "dev")` — read from `os.environ`, **frozen at process start** (`leadgen.service` sets `EnvironmentFile=/opt/leadgen/.env`).

**Precise consequence (and where the team-lead's framing is wrong).**
The summary said the verify *"can pass while the serving process runs stale code."* Under the systemd topology this is **inverted**: because the reported version is the *same frozen env var* the process is running with, the verify **cannot** pass on stale code — it **fails** (`exit 3`) for every SHA change. The accurate, more severe statement is: *the canonical release path cannot complete any SHA-changing deploy, and its "OK" is never evidence that the serving process runs the deployed code.* A pass can occur only when something **outside the script** (a `Restart=always` crash-restart, or a manual restart) restarted systemd after `.env` already said `$VER` — i.e. the pass is a **coincidence**, not a controlled outcome. Both readings share one root defect: **the script verifies a process it does not control.**

**Topology caveat (open question, §5).** `docker-compose.vps.yml:82` publishes `127.0.0.1:8000:8080` for `leadgen_app`, which **conflicts** with a systemd process also on `127.0.0.1:8000`. Only one can bind. The SRE triage says systemd holds it (`ss` → host python PIDs). If instead the *container* serves 8000, then the fix is different (the systemd unit is a zombie and the docs are the defect). **The fix below is correct only under the systemd topology** — hence it must be applied together with the topology assertion in §5.

**Recommended minimal diff (NOT applied).** Insert after the live-checkout block (`:283-289`) and before the build/verify sequence:

```diff
 LIVE_SHA="$(git -C "$REPO" rev-parse HEAD)"
 if [ "$LIVE_SHA" != "$CANDIDATE_SHA" ]; then
   echo "FATAL: live checkout is at $LIVE_SHA but the gated release is $CANDIDATE_SHA."
   echo "       Refusing to start containers on code that was never gated."
   exit 2
 fi
 echo "LIVE_SHA=$(git -C "$REPO" rev-parse --short HEAD) (gated)"
+
+# ---- set the version the TRAFFIC-SERVING host process will read on restart ----
+# leadgen.service reads .env via EnvironmentFile= at process start (frozen). The
+# .ENV GUARD above only VALIDATES it; it never sets it. Replace (never append:
+# .env already has exactly one APP_VERSION= line and EnvironmentFile is last-wins,
+# so `>>` would create a duplicate key).
+if grep -qE '^APP_VERSION=' "$REPO/.env"; then
+  sed -i "s|^APP_VERSION=.*|APP_VERSION=$VER|" "$REPO/.env"
+else
+  echo "APP_VERSION=$VER" >> "$REPO/.env"
+fi
+
+# ---- restart the process that actually owns 127.0.0.1:8000 -------------------
+# Without this the verify below reads the frozen OLD sha and exits 3.
+if ! systemctl restart leadgen; then
+  echo "FATAL: systemctl restart leadgen failed — traffic-serving process not updated."
+  exit 10
+fi
+for _i in $(seq 1 12); do
+  systemctl is-active --quiet leadgen && break
+  sleep 2
+done
```

> Constraint: 30 `tests/` files reference `deploy_vps`; any edit must keep them green (notably `test_deploy_guard_ordering.py`, `test_deploy_parent_behaviour.py`, `test_deploy_vps_skew_resolution.py`, `test_deployment_path_manifest.py`). This diff adds lines after the destructive literal, so guard-ordering is preserved.

### 2.2 — Findings #2/#6: unguarded `.bat` deploy paths (D-B, corrected)

**The team-lead's D-B is materially STALE.** Six of the "nine competing paths" were **already consolidated on 2026-07-26** to delegate to the canonical parent; the summary quotes their *docstrings* (which describe the removed chain) as if they were live code:

| Script | Team-lead's claim | Reality (verified) |
|---|---|---|
| `vps_deploy_dashboard.py` | "`git fetch --all -q && git reset --hard origin/main -q`" | Docstring `:7` only. Body calls `subprocess.run(SSH + [REMOTE])` where `REMOTE` = `bash scripts/deploy_vps.sh`. **Delegates.** |
| `vps_build_deploy.py` | "`git reset --hard origin/main -q` (`:7`)" | Docstring `:7` only. Body: `subprocess.run(["bash", str(PARENT)])`. **Delegates.** |
| `vps_deploy_workflow_fix.py` | "`:4`" | Docstring only. Body delegates. **Delegates.** |
| `vps_pitch_deploy.sh:7` | "`git reset --hard origin/main -q`" | True — **but `. _runtime_data_guard.sh` at `:5` precedes it.** Guarded. |
| `_mcp_deploy_remote.sh:12` | "`git reset --hard origin/main`" | True — **but guard at `:8`.** Guarded. |
| `vps_force_pull.py:48` | "`git clean -fd frontend/explorer.html`" | True; `preflight_ok()` gate at `:34` precedes the whole chain; the `clean` is scoped to one file. Guarded. |

**What is genuinely still unguarded** is the entire `.bat` surface — invisible to `test_deploy_guard_ordering.py` (globs `.sh/.py`) and `_deploy_surface_inventory.py` (`.sh/.py/.yml/.yaml`):

```
scripts/vps_deploy_call_learn.bat:29   git reset --hard origin/main -q        # most severe
scripts/deploy_godmode.bat:16          git pull origin main + compose up
scripts/deploy_outreach_bounce_fix.bat:40  git pull + build/up
scripts/deploy_vobiz_fix.bat:12        sed .env + git pull + build/up
scripts/legacy/deploy_vps_now.legacy.bat:21   git reset --hard origin/main -q
scripts/legacy/deploy_main_now.legacy.bat:13  git reset --hard origin/main -q
scripts/legacy/fix_push_redeploy.legacy.bat:22 git reset --hard + systemctl restart leadgen
scripts/legacy/deploy_brain|deploy_fix2|deploy_now.legacy.bat  git pull + up
```

**Classification (delete / alias / harden):**

- **Safe to delete:** all `scripts/legacy/*.bat` (already named `.legacy.`; nothing in CI/cron/systemd references them — `grep` across `.github/`, `*.service`, `crontab` → empty) and `deploy_godmode.bat`, `deploy_outreach_bounce_fix.bat`, `deploy_vobiz_fix.bat` (one-off fixes; not referenced by any gate).
- **Must be kept but hardened/aliased:** `scripts/vps_deploy_call_learn.bat` — **referenced by docs** (`docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md:149`, `progress.md:3050-3051`). Replace its remote chain with the canonical parent:

```diff
-"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "set -o pipefail; cd /opt/leadgen && git fetch --all -q && git reset --hard origin/main -q && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app worker && sleep 22 && curl -sf http://127.0.0.1:8000/health" >> "%LOG%" 2>&1
+"%SSH%" -i "%KEY%" -o BatchMode=yes %HOST% "set -o pipefail; cd /opt/leadgen && bash scripts/deploy_vps.sh" >> "%LOG%" 2>&1
```

> Do **not** propose weakening any compliance gate here. `vps_deploy_call_learn.bat:33` arms `DND_CARRIER_SCRUB=1`; `progress.md:3050-3051` records that this var was a **messaging** fail-open until it was scoped to `voice` only. That scoping (`app/utils/dnd_checker.py`) must stay intact — the hardening above changes only the *deploy* mechanism, not the DND behaviour.

### 2.3 — Finding #3: `ratchet --json` emits non-JSON (D-D)

**Confirmed by reading and by running.** In `main()`:

```python
110     if args.json:
111         print(json.dumps({... }))          # valid JSON document
129     else:
130         print("=== runtime-data mutable-path scan ===")
...
147     if args.mode == "ratchet":             # <-- reached even when args.json is True
152         print("\n=== debt ratchet ===")    # human text appended AFTER the JSON
```

Reproduced: `python scripts/runtime_data_path_scan.py ratchet --json` → the `=== debt ratchet ===` banner is at **line 24098** of stdout — exactly the team-lead's `Extra data: line 24098 column 1`.

**Only `ratchet` is affected.** Traced the other three modes:
- `groups` (`:75-108`): both branches `return 0` → no fall-through. ✅
- `scan` (`:144-145`): `return 0` before the ratchet block. ✅
- `validate` (`:168`): falls to `return 1 if problems else 0`, and the human actionable block is inside the `else` at `:140`. ✅

**Recommended minimal diff (NOT applied):**

```diff
     if args.mode == "ratchet":
         # Monotonic: existing frozen debt is tolerated, NEW unresolved debt and
         # classification regressions are not. Counts alone would not catch
         # "one dangerous writer added, one unrelated finding removed" — the
         # comparison is over fingerprints, so that trade shows up.
+        if args.json:
+            # JSON was already emitted above; the human block is for humans only.
+            return 0 if verdict["ok"] else 1
         print("\n=== debt ratchet ===")
         print(f"  baseline fingerprints : {verdict['baseline_fingerprints']}")
```

### 2.4 — Findings #4/#9/#11: WAHA config drift (D-E)

**Checked-in** (`deploy/compose/docker-compose.waha.yml:79-83`):

```yaml
    ports:
      # localhost only, 3111 (NOT 3000 — Grafana owns 3000 on this VPS). ...
      - "127.0.0.1:3111:3000"
```

**Running** (PRODUCTION-PROVEN, SRE re-verified): `leadgen_waha` → `0.0.0.0:3002->3000` (+ `[::]:3002`), `ufw status = inactive`. So the service is internet-reachable and the repo does not describe prod.

**Watchdog assessment — the env-override design is SOUND.** `waha_watchdog.py:64-95` resolves every host/port/path from env-first with a documented default; `api_key()` (`:114-116`) has **no hardcoded fallback** (correct). `classify()` (`:173-194`) now separates `unreachable` from `logged_out` (`SCAN_QR_CODE`/`UNPAIRED`) — the historical false-negative (`{"waha_status":"UNKNOWN","raw":{"error":"Connection refused"}}`) is fixed. `WAHA_WATCHDOG_URL` is set in `/opt/leadgen/.env`, so the watchdog reaches 3002. ✅

**Residual issues:**
- `DEFAULT_WAHA_URL = "http://127.0.0.1:3111"` (`:47`) — the *only* remaining 3111 assumption in code. If the env var is unset, the watchdog targets a dead port and reports `unreachable / check_waha_service`, i.e. a **misleading** (not silent) remedy. Recommend failing loud in prod instead of defaulting to a stale port.
- `WAHA_WATCHDOG_LOG_FILE` is ABSENT in `.env` → falls back to `/opt/leadgen/data/waha_watchdog.log` (inside the checkout — interacts with D-F). Works, but see finding #10.
- `AGENTS.md:35` / `CLAUDE.md:35` still say "own WAHA :3111" → STALE.

**Recommended fix (security, owner-facing):** recreate WAHA from the checked-in compose (localhost bind) **and** enable ufw. Do **not** only edit the compose file — the running container was not started from it (SRE §7.7), so an edit alone changes nothing until a recreate.

### 2.5 — Finding #5: the anti-drift gate cannot see `.bat`

`tests/test_deploy_guard_ordering.py:202-203`:

```python
for path in sorted(SCRIPTS.glob("*")):
    if path.suffix not in {".sh", ".py"} or path.name in {GUARD, PREFLIGHT}:
        continue
```

and `scripts/_deploy_surface_inventory.py:71-73` filters to `{".sh", ".py", ".yml", ".yaml"}`. Both **silently skip `.bat`**, so the test whose docstring says *"this suite exists so the list cannot silently grow again"* cannot see the exact class of file that carries the live `git reset --hard` (finding #2). This is a gate-integrity defect, not a style nit.

**Recommended fix:** extend both to `.bat`/`.cmd`, and add the four non-legacy `.bat` paths to `GUARDED_NOW` (after aliasing) or `UNGUARDED_DEBT` (with an owner + wave). The test's `_first_destructive_line` already skips `echo`-prefixed lines, so Windows batch is usable as-is.

### 2.6 — Finding #8: two in-repo sources disagree

`tests/test_deploy_guard_ordering.py:70-110` still lists six scripts as *unguarded debt — wave 2*, while `deployment_path_manifest.py` marks the same files `GUARDED_BY_CANONICAL_PARENT`. The manifest is the newer, evidence-cited source. Because `test_no_undeclared_destructive_script` treats `UNGUARDED_DEBT` as `known`, the stale entries cannot fail the test — they just mislead. **Fix:** drop the consolidated entries from `UNGUARDED_DEBT` (they no longer contain an executed destructive command).

### 2.7 — Finding #10: the watchdog writes runtime state into the checkout

`waha_watchdog.py` defaults two writable paths into `/opt/leadgen/data/` (inside the checkout): `log_file()` (`:80-81` → `/opt/leadgen/data/waha_watchdog.log`, opened `"a"` at `:128`) and `health_file()` (`:76-77` → `/opt/leadgen/data/wa_health_check.json`, opened `"w"` at `:227`). On HEAD `e77f8e08` both scan as `UNDECLARED_MUTABLE_PATH`:

```
scripts/waha_watchdog.py 128 APPEND  UNDECLARED_MUTABLE_PATH | sym= log_file
scripts/waha_watchdog.py 227 REWRITE UNDECLARED_MUTABLE_PATH | sym= health_file
```

The baseline (793 entries) contains **no** `waha_watchdog` entry, so the ratchet reports both as new debt — and the remedy line it prints is the non-existent "evidence-backed exclusion" (finding #7). **Fix:** route both through `app/platform/runtime_data.py` (`store_path()`), or add reviewed allowlist entries with owner/tier/review_condition.

> **Note:** the ratchet run in this session exited **1** with `newly unresolved: 20`. Some are untracked local scratch (`tmp/prod_deploy_start.sh`, `gen_0913.py`). But both `scripts/waha_watchdog.py` findings are on a **tracked** file, so the failure is **not purely local** — see Open Question Q2.

---

## 3. D-C decision: correct the message (option i) vs implement an exclusion (option ii)

**The defect.** `runtime_data_ratchet.py:149-150` emits, for every new finding:

```
action: classify the store (allowlist entry with owner, migration_tier,
review_condition) or provide an evidence-backed exclusion
```

But `classify()` (`runtime_data_scan.py:1323-1376`) has a fixed order — AMBIGUOUS → `canonical_resolver_used` → canonical funcs → `FIXTURE_ONLY` → allowlist → `_STATIC_ASSET_RE`/`_CACHE_RE`/`_ARTIFACT_RE` → else `UNDECLARED_MUTABLE_PATH`. **There is no exclusion branch**, and `grep -rE "exclusion|exclude|EXCLUDE|exempt|EXEMPT"` across `runtime_data_path_scan.py`, `runtime_data_allowlist.py`, `runtime_data_manifest.py`, `runtime_data_scan.py`, `runtime_data_ratchet.py` returns **zero implementation hits** (the phrase appears only in this message; in tests it qualifies a *manifest edit*, e.g. `tests/test_runtime_data_path_allowlist.py:444-464`). The module's own docstring (`runtime_data_path_scan.py:1-13`) states the opposite principle: *"There is deliberately no `--accept-current-state`, no auto-update and no bypass variable: a scanner that can write its own exceptions is a scanner that always passes."*

**Argument for (ii) — implement a real exclusion:** a reviewer may genuinely conclude a finding is a false positive (e.g. a heuristic miss) and want a first-class, documented way to say so without inventing a store.

**Argument for (i) — correct the message (RECOMMENDED):**
1. **The message is the only thing that is wrong.** The mechanism the message implies would be a *second, weaker* declaration path alongside the allowlist. The allowlist already requires `store_id` (validated against the manifest), `owner`, `migration_tier`, `access_modes`, `review_condition`, and is checked **bidirectionally** against live findings (no stale declarations) — `runtime_data_allowlist.py:60-109`. An "exclusion" with none of those is a bypass wearing a review label.
2. **It contradicts the module's stated design principle** (docstring `:1-13`) and the ratchet's core distinction between CONTROLLED ALLOWLIST and KNOWN_UNRESOLVED_DEBT (`runtime_data_ratchet.py:1-23`). Adding an exclusion category would create exactly the "691 unexamined writers become 691 approvals" failure the module exists to prevent.
3. **The real options are already implemented** and just not named: (a) an allowlist entry; (b) if the finding is a classifier false positive, **fix the classifier** (add/adjust a heuristic or classification); (c) move the write behind `app/platform/runtime_data.py`. (i) is a one-line change that restores truthfulness and **cannot weaken the gate**; (ii) adds new attack surface to the gate for no capability gain.

**Recommended minimal diff (NOT applied) — option (i):**

```diff
-            "  action: classify the store (allowlist entry with owner, migration_tier, "
-            "review_condition) or provide an evidence-backed exclusion".format(
+            "  action: classify the store (allowlist entry with owner, migration_tier, "
+            "review_condition), fix the classifier if this is a false positive, or move "
+            "the write behind app/platform/runtime_data.py".format(
```

Optionally add a regression test asserting the failure message names only options that exist in `classify()`/the allowlist (so the message cannot drift from the implementation again).

---

## 4. Defects I looked for and did NOT find (cleared)

- **`scan` / `validate` / `groups` do not share the `--json` fall-through.** Verified by tracing `main()` (`runtime_data_path_scan.py:75-168`): `groups` returns in both branches; `scan` returns at `:144`; `validate`'s human block is inside `else`. Only `ratchet` is broken (finding #3). *This partially corrects the team-lead's "check whether scan/validate/groups have the same defect" — they do not.*
- **`vps_pitch_deploy.sh` and `_mcp_deploy_remote.sh` ARE guarded.** Guard sourced at `:5` / `:8`, before the `git reset --hard` at `:7` / `:12`. Not unguarded paths.
- **`vps_force_pull.py` IS guarded.** `preflight_ok()` (`:21-30`) runs at `:34`, before the `git stash`/`clean`/`pull` chain (`:45-56`); denial returns 90 without executing. Its `git clean` is scoped to `frontend/explorer.html`.
- **`vps_build_deploy.py` / `vps_deploy_dashboard.py` / `vps_deploy_workflow_fix.py` contain no executed `git reset`.** Only their docstrings describe the removed chain; bodies delegate to `deploy_vps.sh`. The team-lead's D-B quotes those docstrings as code.
- **CI is not a competing deploy path.** `.github/workflows/deploy-vps.yml:158-176` documents that the `build:`/`deploy:` jobs were removed; the workflow is gate-only and cannot reach the VPS.
- **No in-repo cron / systemd timer / drop-in restarts `leadgen` or invokes any of these scripts.** `grep` over `*.service`, `*.timer`, `crontab*`, `.github/` → empty (the only `systemctl restart leadgen` is in a legacy `.bat`, finding #6).
- **No hardcoded WAHA API key / secret fallback.** `waha_watchdog.py:114-116` reads env then `.env`, no fallback; the compose uses `${WAHA_API_KEY:?...}` (fail-closed). No secret values reproduced in this review.
- **`deploy_vps.sh`'s guard ordering, exit-code contract and 5-service anti-skew rollout are correct and behaviourally tested.** `_runtime_data_guard.sh:43-79` fails closed (exit 90) with no bypass; `tests/test_deploy_guard_ordering.py` proves guard-before-mutation.
- **The `_runtime_data_guard.sh` "no `|| true`" invariant holds.** `tests/test_deploy_guard_ordering.py:135-148` asserts it; verified in the file.
- **No SQL injection / path traversal / unsafe deserialization** in the reviewed Python (scanner, ratchet, preflight, watchdog). File writes use fixed/derived paths; the preflight prints no secret values.

---

## 5. Open questions for the owner

1. **Which process actually binds `127.0.0.1:8000` — systemd `leadgen.service` or the `leadgen_app` container?** `docker-compose.vps.yml:82` publishes `8000:8080` for `leadgen_app`, and the systemd unit also binds `8000`; only one can win. The D-A fix in §2.1 is correct **only** under the systemd topology (SRE's `ss` reading). If the container serves 8000, the defect is the reverse (a zombie systemd unit + wrong docs), and the fix changes. **Do not apply §2.1 until this is asserted** — ideally by a topology-drift gate (SRE A7).
2. **Is the `ratchet` gate currently RED on `main`?** On HEAD `e77f8e08`, `scripts/waha_watchdog.py` is tracked and absent from the 793-entry baseline, so `new_unresolved` includes it even on a clean checkout. Was the baseline regenerated (or is a `runtime_data_baseline_changes` record expected) after the 2026-09-14 watchdog landing? I could not confirm a green CI run.
3. **Is `scripts/vps_deploy_call_learn.bat` still in operational use?** It is referenced by `docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md` and `progress.md`. If yes → harden (alias to the parent). If no → delete it and the legacy `.bat` set outright.
4. **Is the running `leadgen_waha` container reproducible from the checked-in compose?** SRE §7.7 says it was not started from it. If prod is hand-managed, the checked-in file is aspirational and the port drift will recur.
5. **What is the intended WAHA host port going forward — 3111 or 3002?** The answer must land in *one* place (compose + `DEFAULT_WAHA_URL` + `AGENTS.md`/`CLAUDE.md`), or the next drift is guaranteed.

---

*Review only. No file was modified, committed, pushed or deployed; all diffs above are suggestions. No compliance gate (DND/TRAI/DPDP/consent) or security control is proposed to be weakened — findings #2/#6/#10 and the D-C recommendation all protect the live ledgers.*
