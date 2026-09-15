# Voice kill-switch: make the FILE authoritative (staged plan)

**Date:** 2026-09-15 · **Owner decision:** "ENV hatao, file toggle authoritative"
**Status:** PLAN — **not executed.** Stage 0 (preflight deletion) shipped 2026-09-15.

---

## 1. Why this is a plan and not a commit

The owner asked to delete the `VOICE_LAUNCH_KILL` ENV layer and make
`data/voice_launch_kill.json` the authoritative emergency stop.

**Executing that today would stop ALL outbound calling in production.** This is
not a theory — it was measured on prod before any edit:

```
$ cd /opt/leadgen && APP_ENV=production ./.venv/bin/python -c "<probe>"
is_production : True
repo_root     : /opt/leadgen
kill_file     : data/voice_launch_kill.json          <-- RELATIVE
file_status   : AdminKillStatus(engaged=True, source='FILE', reason='INVALID_PATH')
admin_status  : AdminKillStatus(engaged=True, source='FILE', reason='INVALID_PATH')
engaged       : True
```

Read-only probe, 2026-09-15 11:30Z, against the real prod venv.

### The two rules that make it ENGAGED

`app/telephony/voice_launch.py::_kill_file_status()` fails CLOSED on every
unhappy path. Two of them fire in production today:

1. `_kill_file()` returns the **relative** legacy path
   (`data/voice_launch_kill.json`), and production requires an absolute one:
   ```python
   if not p.is_absolute():
       return AdminKillStatus(True, "FILE", "INVALID_PATH")   # ENGAGED
   ```
2. Even made absolute, the file lives at `/opt/leadgen/data/...` — **inside**
   the repo root — and production refuses that on purpose:
   ```python
   if _rd._is_inside(resolved, _rd._repo_root()):
       return AdminKillStatus(True, "FILE", "OUTSIDE_RUNTIME_ROOT")  # ENGAGED
   ```
   Rationale (kept): an emergency control must not live where a deploy or a bad
   `git restore` can reset it. That is not a hypothetical — this repo has a
   documented 4041-file accidental-deletion incident.

So the file-based layer is not merely "inert" in production; it is
**permanently ENGAGED**. That is *why* ENV was made FINAL (`VOICE_LAUNCH_KILL=0`
short-circuits before the file is ever read). Removing the ENV layer without
first fixing the path and the mount = every dial path refuses.

## 2. What stage 0 already shipped (safe, zero prod change)

Deleted the dead, self-blocking `prod_check.py --deployment` VOICE_LAUNCH_KILL
preflight (see the NOTE in `scripts/prod_check.py`). Details in the commit of
2026-09-15. **Runtime kill switch untouched.**

Net effect of stage 0: releases can never be blocked by a control whose own
invocation had been lost, and two lying test files / doc claims are gone.

## 3. Remaining stages — order is load-bearing

The invariant to preserve at EVERY stage: **outbound calling behaviour must be
identical before and after each step.** Prod currently reads
`VOICE_LAUNCH_KILL=0` (disengaged) and the kill file says `{"kill": false}`
(disengaged). Both layers therefore agree — which is what makes a staged
migration possible at all.

### Stage 1 — create the external store (no code, no container)

```bash
install -d -m 0750 /var/lib/leadgen/runtime/telephony
printf '{"kill": false}\n' > /var/lib/leadgen/runtime/telephony/voice_launch_kill.json
```

`/var/lib/leadgen/runtime` is the canonical external root
(`app/platform/runtime_data_marker.py` → `runtime_root_identifier`).
**Verify:** file exists, is a regular file, parses, `kill` is a real bool.

### Stage 2 — make it visible to EVERY process (compose, still no code change)

The file must be reachable at the SAME absolute path from the systemd app
(host) and from every app-image container, or a subset of processes will read
MISSING → fail-CLOSED → stop calling.

- Add to every app-image service in `docker-compose.vps.yml`
  (worker, scheduler, worker-heavy, worker-video, dsh-worker — the same set the
  `./data:/app/data` bind uses):
  ```yaml
  - /var/lib/leadgen/runtime:/var/lib/leadgen/runtime
  ```
- Recreate those services with `APP_VERSION` pinned to the running tag.
- **Verify per container:** the file is readable and parses:
  ```bash
  for c in $(docker compose -f docker-compose.vps.yml ps -q); do
    docker exec "$c" python -c "import json,pathlib; \
      p=pathlib.Path('/var/lib/leadgen/runtime/telephony/voice_launch_kill.json'); \
      print('$c', json.loads(p.read_text()))"
  done
  ```
  **Gate:** all services print `{'kill': False}`. If ANY fails, STOP — do not
  proceed to stage 3. Calling is unchanged at this point.

### Stage 3 — cut the store over

Set the runtime-data cutover for `telephony.voice_kill_switch` so
`resolve_store_authority(...).active_path` is the external target
(`app/platform/runtime_data_authority.py`; `CUTOVER_GATE_ENV`). Update
`app/platform/runtime_data_manifest.py` / `runtime_data_allowlist_entries.py` if
the governance lists require the new path.

**Verify (prod, read-only probe again):**
`_kill_file()` must return the ABSOLUTE external path and
`_kill_file_status()` must be `engaged=False, reason='FILE_DISENGAGED'`.
**Gate:** if it is not `FILE_DISENGAGED`, STOP and roll the cutover back.

### Stage 4 — drop the ENV authority (the owner's ask)

Only now, in `app/telephony/voice_launch.py`:

- `admin_kill_status()` → consult `_kill_file_status()` directly; delete the
  `_KILL_TRUE` / `_KILL_FALSE` ENV branches.
- Delete `_KILL_TRUE` / `_KILL_FALSE` and the ENV-FINAL docstring.
- Redirect the "engage kill" flips that today edit `.env`
  (`app/platform/admin_api.py`, `app/platform/squad_deploy.py`
  `sed -i 's/VOICE_LAUNCH_KILL=0/VOICE_LAUNCH_KILL=1/'`) to **write the kill
  file** — otherwise the operator's kill button becomes a silent no-op.
- Update `app/platform/automation_flag_manifest.py` (`VOICE_LAUNCH_KILL` is
  registered as the `kill=` of `PLATFORM_DIAL_DAILY`),
  `app/api/automation_flags.py`, `app/platform/blueprint_graph.py`,
  `app/agents/harness/plugin_catalog.py`, `app/api/admin_ops.py`,
  `app/automation/console_dispatcher.py`, `app/api/telephony_smartflo.py`.
- Tests: `tests/test_voice_launch_kill_failclosed.py` expects
  `INVALID_ENV_VALUE` for a malformed ENV token — that case disappears with the
  ENV layer and must be replaced by an equivalent FILE case, not deleted.
- Leave `VOICE_LAUNCH_KILL=0` in prod `.env`; once ENV is not read it is inert.
  Remove it in a later cleanup, not in the behaviour-changing commit.

**Verify:** kill file `{"kill": true}` → every dial path refuses with
`FILE_ENGAGED`, with NO restart; `{"kill": false}` → calling resumes.
`deploy_vps.sh` `prod_check --deployment` still PASSes.

### Stage 5 — retire the ENV variable from `.env` and the docs

Only after stage 4 has soaked. Then delete `VOICE_LAUNCH_KILL=0` from
`/opt/leadgen/.env` and from `.env.example`.

## 4. Why the new behaviour is better, not just different

| | Today | After stage 4 |
|---|---|---|
| Emergency stop | edit `.env` + restart the process | write the file — **no restart** |
| Works from a container | only via env injection | via the shared bind mount |
| Fail-closed on missing/unreadable | file path never reached | **engages** (unchanged rule) |
| Release blocking | dead preflight (now deleted) | none |

## 5. Do NOT

- **Do NOT remove the ENV layer before stages 1–3 are verified.** Measured
  result: all outbound calling stops.
- **Do NOT relax the `_is_inside(repo_root)` production rule** to keep the file
  where it is now. That rule is the reason an emergency control survives a bad
  deploy or a bad `git restore`.
- **Do NOT re-add the `VOICE_LAUNCH_KILL` TRUE_TOKEN preflight** to
  `prod_check.py`. It passed only when the kill switch was ENGAGED, i.e. it
  would block every release of a healthy live campaign.
- **Do NOT touch** DND fail-closed, TRAI calling window, AI disclosure, the
  consent ledger, or the circuit breaker. This plan is about ONE switch.

## 6. Rollback

Every stage is independently reversible:
stage 4 → revert the commit; stage 3 → revert the cutover; stage 2 → drop the
compose bind and recreate with the pinned tag; stage 1 → the directory is inert
until something reads it. `deploy_vps.sh` keeps its own rollback lineage.
