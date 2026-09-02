# Chaos Game-Day — LeadGen AI

> Satisfies the Playbook "chaos tests executed" gate. The harness already exists
> (`tests/load/README.md`, Pumba). This is the formal **procedure + results template**.
>
> ⚠️ **EXECUTION IS STAGING-ONLY.** Pumba is destructive (pauses/kills/delays
> containers). The live VPS is a single SPOF — **never run chaos on prod**
> (`run.sh` has a prod-guard refusing `leadsgenai.in` / the VPS IP unless `CONFIRM_PROD=1`,
> which must stay unset). A staging environment (`:8001`) is required to execute and
> record a run. Until staging exists, this doc is the certified *plan*; the recorded
> run is infra-gated (operating-manual: external/infra dependency, not a code defect).

## Objective
Prove the resilience controls actually recover under fault injection:
- Self-heal cron (`scripts/vps_selfheal.sh`, */10)
- Dead-man trio (heartbeat + revive-beat */20 + watchdog)
- `/health/ready` degrade + recovery (DB+Redis pool)
- Circuit-breakers (LLM provider failover)

## Pre-run checklist
- [ ] Target is **staging** (`:8001`), prod-guard confirmed (`CONFIRM_PROD` unset).
- [ ] Baseline captured: `bash tests/load/run.sh smoke` green (p95 OK, all 200).
- [ ] Grafana open (Prometheus) + a terminal tailing `/health/ready`.
- [ ] One owner assigned; window agreed; rollback = `docker compose ... up -d` recreate.

## Scenarios (run one at a time, observe recovery before next)
| # | Fault | Inject (staging) | Expected recovery | Pass criteria |
|---|---|---|---|---|
| 1 | DB pause 20s | `pumba --random --interval 30s pause --duration 20s re2:leadgen_db` | `/health/ready` degrades then recovers | recovers ≤ 60s, no data loss |
| 2 | App network latency | `pumba netem --duration 60s delay --time 200 re2:leadgen_app` | p95 rises, stays < timeout, normalizes | no 5xx storm, p99 < 3s after |
| 3 | Cache Redis kill | `pumba --random kill re2:leadgen_redis_cache` | self-heal recreates container | back up ≤ 10min cron (or manual), no crash |
| 4 | Worker kill | `pumba --random kill re2:leadgen_worker` | beat re-schedules, queue drains | `llen celery` drains, no dup side effects |
| 5 | LLM provider 429 (simulate) | block primary provider egress | breaker fails over to next in chain | ok-rate recovers via fallback |

> Best workflow: run `tests/load/run.sh load` in one terminal (sustained traffic),
> inject a fault in another, watch Grafana + `/health/ready` for the recovery curve.

## Results template (fill per run — commit as evidence)
```
Chaos Game-Day — <date> — env: staging :8001 — owner: <name>
Baseline smoke: PASS/FAIL (p95=__ms)
Scenario 1 DB pause   : PASS/FAIL — recovery __s — notes:
Scenario 2 net latency: PASS/FAIL — p95 peak __ms / settle __ms — notes:
Scenario 3 redis kill : PASS/FAIL — recreate __ — self-heal? Y/N — notes:
Scenario 4 worker kill: PASS/FAIL — queue drain __ — dup side effects? Y/N — notes:
Scenario 5 provider   : PASS/FAIL — failover provider __ — notes:
Action items (bugs/gaps found):
Verdict: resilience controls VERIFIED / GAPS FOUND
```

## Post-run
- File the completed template under `docs/operations/chaos_runs/<date>.md`.
- Any control that did **not** recover → P1 reliability bug + regression test
  (`tests/test_loop_supervisor.py`, `test_ops_watchdog.py`) + runbook update.
- Record decision/finding as `docs/ADR_*.md` if architecture changed.
