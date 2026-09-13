# 24x7 FINAL DECISION - Enterprise orchestration (2026-09-12)

**Status:** FINAL (decision only; no deploy). Builds on the **frozen** `docs/architecture/24X7_ARCHITECTURE_RECORD.md`
(PHASE 1 freeze) and the QA-verified `docs/context/PHASE0_BASELINE.md`.
**Question answered:** "Should there be 13 profiles / 8 roster bots / 6 CLI workers?" -> **neither. One registry; 6 of its 9 bots run as CLI workers.**

## 1. Non-negotiables (already frozen - do NOT re-open)
- **ONE control plane = `DevTask`** (`app/models/dev_task.py`, Postgres `dev_tasks`, 18 states, atomic claim,
  heartbeat, 600 s lease, + `DevTaskEvent` hash-chained audit). Everything else is a **shim**, a **read-only
  export**, or **subordinate** (AgentTask / CC ledger / `state.js` / `agent_runtime` / `HERMES_CONTROL_PLANE.md`).
- **ONE worker registry = `dev_workers`** (kind cli/api/desktop; heartbeat 60 s; lease 600 s; reap 60 s;
  backoff 60 s x2^n cap 15 m; max 3 attempts). Desktop workers are **advisory until HMAC-attested**.
- **ONE bot registry = 9 bots -> 31 agents** (`24X7_ARCHITECTURE_RECORD.md` section 4, derived from `team.py`).
- **ONE routing authority = OmniRoute**, canonical ids `leadsgen combo 1-14` (legacy names read-only aliases).
- **Products:** P1 = AI Automated Marketing (Rs 1,999/mo), P2 = AI Voice Calling Agent (banded). Both served by
  the **same** control plane - no per-product stacks.

## 2. The 9 bots (canonical) vs the CLI workers
The 9 bots are the registry. Only the headless *supervisor* bots are CLI workers; the rest are
authority/advisory. `cli_worker` metadata is set on **exactly these 6 profiles**:

| CLI worker (Hermes profile) | Agents owned (canonical section 4) | Product |
|---|---|---|
| `operations` | riya, raksha, ananya, swara | P1+P2 |
| `engineering` | vikram, guru, pranav, kabir, aryan | both |
| `platform` | hermes, kavya, tara, arya | both |
| `guardian` | arjun, meera, arnav, diya | both |
| `sales` | nikhil, priya, anika, ira | P1+P2 |
| `success` | isha, zara, kiran | P1+P2 |

**NOT CLI workers (by design):** `Pilot` (commander; `manager` is an orchestrator surface, never a worker -
ADR-165), `board` (owner authority: kill switches / deploy auth / budgets -> agents lekha, vidya),
`hunter` (specialist lead-gen -> agents rohan, dev, ravi, neha). Agents total: 24 (workers) + 7 (non-worker) = 31.

## 3. Over-engineering -> dispositions (this is the cleanup)
| Artifact | Verdict |
|---|---|
| `docs/hermes/CLI_WORKER_ROSTER.md` | **SUPERSEDED** -> reconciled to this file (was a 4th, independent mapping) |
| `HERMES_AGENT_ROSTER.yaml` (8 bots) | **SUPERSEDED** by section 4's 9-bot map -> deprecation banner added |
| `cli_worker:` blocks on other profiles | **REMOVED** - kept on exactly the 6 CLI workers |
| `telegram:` bindings on all 13 profiles | **UI/registry metadata only** - no runtime consumer today; either wire one reader or treat as inert (do NOT claim "live") |
| 13 Hermes profiles (UI bots) | **KEPT as a UI/identity layer**, not a worker layer. The runtime registry is `dev_workers` + the 9 bots |

**Do NOT build:** a 6th/4th registry, a second orchestrator, per-profile worker daemons, or a new roster doc.

## 4. 24x7 runtime (reuse what exists)
- Docker services: `app` + `worker` + `worker-heavy` + `worker-video` + `scheduler` (Celery, `--profile celery`)
  already defined and live on the VPS. Supervisor execution rides this; do not add bespoke always-on terminals.
- Liveness: `dev_workers.heartbeat_ts` (60 s) + the 600 s lease + the 60 s reap sweep + dead-man watchdog.
- **Why automations look "banned after deploy":** (a) the deploy gate forces `VOICE_LAUNCH_KILL` on (by design);
  (b) WAHA key mismatch -> 401 (FIXED 2026-09-12); (c) DND lookups fail-closed. None are code faults in the
  automation itself.

## 5. Owner gates (unchanged)
`_KNOWN_TOOLS` edit; rollout of non-dispatchable agents; arming CLI workers; Telegram chat creation + apply;
commit/push/deploy. Nothing here was committed or deployed.


## 6. Reference CLI worker (implemented 2026-09-12)

`app/workers/cli_worker.py` - the first headless worker runtime, wired to the existing registry:

- registers in `dev_workers` (`kind="cli"`, `supervisor_bot=<name>`, capabilities, version, pid_host)
- heartbeats every 60 s; claims the highest-priority QUEUED `DevTask` via `claim_next`; reports via `mark_result`
- **safe by default**: no side effects (claims + releases). Per-agent execution handlers are wired separately,
  so no customer/payment/voice action can run from an unaudited entrypoint
- bounded/testable: `--once` / `--cycles N`; rejects any supervisor not in the approved 6
- verified: `tests/test_cli_worker.py` -> 2 passed (registers `cli_operations` healthy/authoritative;
  rejects `board`)

Profile `cli_worker.command` for the 6 workers now points at the real entrypoint:
`python -m app.workers.cli_worker --supervisor <name>`.

### Compose service (add on deploy - owner-gated)
```yaml
  worker-cli-operations:
    image: ghcr.io/sumitrevolt/leadgenrationaivoiceagent:${APP_VERSION:?}
    command: ["python", "-m", "app.workers.cli_worker", "--supervisor", "operations"]
    env_file: .env
    restart: unless-stopped
    profiles: ["celery"]
    depends_on: [redis, db]
```
### Rollout
1. Deploy the image with `app/workers/cli_worker.py` present.
2. Start ONE worker (`operations`); confirm a `dev_workers` row with `health=healthy` and a fresh
   `heartbeat_ts` (< 60 s), plus the Owner Command Center Q4 tile turning `instrumented=true`.
3. Only then add the other 5 (`engineering, platform, guardian, sales, success`), one at a time.
4. Rollback: `docker compose ... stop worker-cli-operations` (the row goes `dead` in 600 s; `reap_stale` clears it).
