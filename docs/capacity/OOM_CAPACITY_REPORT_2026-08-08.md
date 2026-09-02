# OOM / Capacity Report — 2026-08-08

Scope: complete the OOM investigation with hypothesis falsification, produce a
durable evidence-backed capacity report, and add a **reversible** containment
design that ships ONLY on the staging stack (no production compose behaviour
change in this change-set).

Companion incident records (source of the primitives below):
- `memory/incidents.md` — 2026-07-16 default-worker memcg OOM/SIGKILL loop; 2026-07-28
  leadgen_worker 14× memcg OOM/SIGKILL in 24h; 2026-07-15 kb_niche_refresh SIGKILL finding.
- `docker-compose.vps.yml` — current production mem_limits.
- `deploy/compose/docker-compose.staging.yml` — staging stack (this change-set's target).
- `docs/context/ENTERPRISE_READINESS_2026-08-08.md` — CP5-1 host-memory finding (89.5% used).
- `docs/archive/2026-07/ENTERPRISE_AI_AUDIT_2026-07-06.md` — observability containers lack `mem_limit`.

---

## 1. Causal classification (bottom line)

| Incident | Classification | Mechanism | Evidence |
|---|---|---|---|
| 2026-07-16 default-worker OOM loop | **Active application burst — mis-scoped warm-up** (config defect, not a leak) | Per-container **memcg** cap (2 GiB) exceeded at worker boot | Kernel killed `leadgen_worker` 2 GiB cgroup's ForkPool children every ~90 s, 08:20–08:43 IST; queues/DLQ zero; `/health` green |
| 2026-07-28 worker 14× OOM/SIGKILL | **Active application amplification inside a too-small per-container cap** (loop placement + watchdog + masked healthcheck) | Per-container **memcg** cap (2 GiB) exceeded by 4 forks × LLM-heavy continuous tick + watchdog re-seeding | Kernel killed default-worker forks 14×/24 h; queues/DLQ zero; `/health` false-green |
| 2026-08-08 host 89.5 % used (CP5-1) | **Normal baseline pressure on a single shared VPS** (undersized-host-adjacent, latent) | Host-level aggregate, not a container cap | Readiness probe: 0.5 pp from `HostMemoryHigh`; obs stack (~13 containers) documented `mem_limit`-less |

Both OOM incidents were **container-cgroup (memcg) events, not host exhaustion**.
The current host baseline is a real, separate latent risk — it is NOT the mechanism
of either incident and did NOT cause either SIGKILL.

---

## 2. Hypothesis table — what we falsified and what we accepted

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | "Undersized host caused the OOMs" | **FALSIFIED** | Kernel evidence is cgroup-scoped: the `leadgen_worker` 2 GiB memcg killed its own children. 2026-07-15 sibling finding documents "host had 5.2 GB free; this was a per-container cap collision, not host exhaustion". 2026-07-16 recovery was in-container (pool 4→2→1) with zero host-level change; a host-OOM would kill processes across cgroups, not a single container on a ~90 s cadence at boot. |
| H2 | "Task backlog / queue depth caused it" | **FALSIFIED** | Redis queues AND DLQ were zero at both incidents. On 07-16 the children died during the boot warm-up **before any task ran**. |
| H3 | "Transient host memory spike caused it" | **FALSIFIED** | Same cgroup-scoped evidence; a host spike does not produce a 90 s-regular, single-container, boot-time kill cadence with free host RAM. |
| H4 | "A classical unbounded application memory leak" | **FALSIFIED as primary (07-16)**; **rejected as the shape of 07-28** | 07-16: no tasks running at death time. 07-28: not an unbounded leak — a sustained, amplified footprint (4 forks × LLM-heavy `self_improve_tick` + re-seeded chains) colliding with a small cap; `worker_max_memory_per_child` (350 MB) only recycles **between** tasks, so mid-tick growth summed past the cgroup. |
| H5 | "A feature/routing flag doubled as process-role identity → all default-worker children ran the heavy warm-up" | **ACCEPTED (07-16)** | `on_worker_process_init()` gated its ~1.2–1.4 GiB Qdrant/fastembed/ONNX warm-up on `CELERY_HEAVY_QUEUE` — a SEND-side flag set on app, scheduler, default worker AND heavy worker — so all 4 default-worker forks paid the warm-up cost inside the 2 GiB cap. Persistent fix (already in code at this base SHA): exclusive `CELERY_HEAVY_WORKER=1` marker on `worker-heavy` (`docker-compose.vps.yml:335`) + `_is_heavy_worker()` gate (`app/worker.py:267`). |
| H6 | "Continuous-loop watchdog + placement inside a small cap + false-green healthcheck" | **ACCEPTED (07-28)** | `ensure_alive` re-seeded deliberately-sleeping chains (`daily_cap` post-sleep read as death); `self_improve_tick` ran on the default 2 g queue; healthcheck `inspect ping | grep -q pong` could miss Broken-pipe failure. Persistent fixes already in code at this base SHA: tick/revive routed to `heavy` (`app/worker.py:133-155`), fail-closed `scripts/celery_worker_healthcheck.sh`, healthcheck timeout ≥ 15 s. |
| H7 | "The 89.5 % host pressure is an urgent prod leak needing a prod change NOW" | **NOT CONFIRMED as leak; classified baseline pressure** | No leak signature claimed. Explicitly a **recommendation only** in §6 — no production compose change is made in this change-set. |

### Accepted root-cause chains

**Incident 2026-07-16 (default worker OOM loop):**
`on_worker_process_init()` warm-up gated on `CELERY_HEAVY_QUEUE` (SEND-side routing flag)
→ set on app + scheduler + default worker + heavy worker → **all four** default-worker
fork children loaded ~1.2–1.4 GiB of Qdrant/fastembed/ONNX at boot → 2 GiB memcg cap
exceeded → kernel SIGKILL loop every ~90 s → "unhealthy respawn" while `/health` stayed
green and queues stayed zero. Recovery was ephemeral in-container pool shrink; the
durable fix (exclusive `CELERY_HEAVY_WORKER` marker) is code-present at this base SHA.

**Incident 2026-07-28 (14× OOM/SIGKILL, SELF_IMPROVE_LOOP=1):**
`ensure_alive` treated post-`daily_cap` ~3600 s intentional sleep as death and
re-seeded parallel chains (35× `tick_slot` + 17× `daily_cap` receives) → sustained RSS
burn; `self_improve_tick` ran on the default queue (concurrency=4, mem_limit=2 g) where
4 forks × mid-tick LLM growth summed past the cgroup before `worker_max_memory_per_child`
could recycle; healthcheck could not detect Broken-pipe so the container stayed "healthy"
while forks died. Durable fixes (routing to `heavy`, cap-aware `ensure_alive`, fail-closed
healthcheck) are code-present at this base SHA.

---

## 3. Current production memory budget (docker-compose.vps.yml)

| Service | mem_limit | mem_reservation | cpus |
|---|---|---|---|
| app | 3 g | 1 g | 2.0 |
| worker | 2 g | 512 m | 1.5 |
| worker-heavy | 2500 m | 512 m | 1.5 |
| worker-video | 2000 m | 512 m | 1.5 |
| scheduler | 512 m | — | 0.5 |
| db (Postgres) | 2 g | 512 m | 2.0 |
| redis | 512 m | — | 1.0 |
| redis-cache | 384 m | — | 0.5 |
| qdrant | 768 m | — | 1.0 |
| pgbouncer | 256 m | — | 0.5 |

Explicit caps sum to ≈ 12.9 GB on a 16 GB host, plus the OS, plus the observability
stack (~13 containers) which the 2026-07-06 audit flags as **`mem_limit`-less**. That is
why the 89.5 % host baseline is real, why the obs stack is the soft spot, and why the
containment design below mirrors prod caps on staging.

---

## 4. Reversible containment design (shipped here = staging only)

1. **Staging is now profile-gated.** Every service in
   `deploy/compose/docker-compose.staging.yml` has `profiles: ["staging"]`. A bare
   `docker compose -f deploy/compose/docker-compose.staging.yml up -d` starts **nothing**
   (verified: `config --services` without the profile prints zero services). New run command:
   `docker compose -f deploy/compose/docker-compose.staging.yml --profile staging --env-file .env.staging up -d`.
2. **Staging mirrors prod memory controls + adds pids/oom guards** (all additive,
   Compose-spec v2 fields, verified via live `docker compose config`):
   - `app_staging`: `mem_limit: 3g`, `mem_reservation: 1g`, `cpus: "2.0"`,
     `pids_limit: 512`, `oom_score_adj: 100` → a staging leak/spike dies in the app first
     and a load-test fork-bomb cannot exhaust PIDs.
   - `db_staging`: `mem_limit: 2g`, `oom_score_adj: -200` → data-integrity container is
     the last to die at host OOM.
   - `redis_staging`: `mem_limit: 512m`, `oom_score_adj: -100` → broker/call-state
     protected ahead of the app.
   - Staging reproduces prod-like memory behaviour BEFORE prod, and a staging OOM cannot
     take down the host or prod data.
3. **Worker routing separation stays as-is** (no change needed). `CELERY_HEAVY_WORKER=1`
   is the exclusive process-role marker for the Qdrant/ONNX warm-up and exists ONLY on
   `worker-heavy` in `docker-compose.vps.yml`; staging has no worker service and no marker.
   Per the incidents.md rule, a new repo-wide exclusivity test (this change-set) proves
   that **no other compose file** declares the marker.
4. **Staging isolation is re-verified by tests**: loopback-only host binding
   (`127.0.0.1:8001:8080`), own network `leadgen_staging_net`, own volume
   `pgdata_staging`, and staging services are absent from the production compose set.

### Rollback path (undo every control)

- Staging compose controls: `docker compose -f deploy/compose/docker-compose.staging.yml --profile staging down`
  (or `down --remove-orphans`), then remove the added keys
  (`profiles`, `mem_limit`, `mem_reservation`, `cpus`, `pids_limit`, `oom_score_adj`) or
  revert the file. Nothing else is affected — this file is not part of the production stack.
- Production: **no production control was added or changed** by this change-set, so there
  is nothing to roll back on the running VPS. Prod recommendations (below) would each be
  separately approved, applied, and reverted on their own.

---

## 5. What this change-set did NOT change on the running VPS

- `docker-compose.vps.yml` — **untouched** (prod mem_limits, flags, commands identical).
- No production `mem_limit` / `pids_limit` / `oom_score_adj` change.
- No prod flags (no `CELERY_*`, no `SELF_IMPROVE_LOOP`, no `VOICE_LAUNCH_KILL`, etc.) flipped.
- No container started/stopped/restarted, no deploy, no image push.
- No `APP_VERSION`/image-tag behaviour changed (staging already fail-closed via
  `${APP_VERSION:?...}`; prod keeps `${APP_VERSION:-latest}` as-is per deploy-script gate).

## 6. Recommendations for production (NOT applied in this change-set)

1. **Add `mem_limit` to the observability-stack containers**
   (`docker-compose.observability.yml`: prometheus/loki/tempo/grafana/alertmanager/
   uptime-kuma/gatus). This is the single documented unbounded soft spot on the host and
   the most direct lever on the 89.5 % baseline (audit MEDIUM, 2026-07-06).
2. **Treat `HostMemoryHigh` (89.5 %) as a real cap-adjacent signal.** Do not raise the
   alert threshold; either add obs mem_limits or shed a container. Re-check `docker stats`
   after any change.
3. **Consider `oom_score_adj` on prod data containers** (db <0, redis <0) using the same
   values proven on staging — a host-level OOM should never prefer Postgres.
4. **Keep the `CELERY_HEAVY_WORKER` exclusivity rule enforced by the new repo-wide test**
   so no future compose file re-introduces the 2026-07-16 identity bug.

---

## 7. Verification (this change-set)

- `docker compose -f deploy/compose/docker-compose.staging.yml config --services` (bare) → **0 services**
- `docker compose ... --profile staging config --services` → `app_staging`, `db_staging`, `redis_staging`
- `docker compose ... config` without `APP_VERSION` → **fail-closed** (exit 1)
- Rendered config: `host_ip: 127.0.0.1`, `published: "8001"`, isolated network/volume names
- Pytest: new `tests/test_staging_compose_containment.py` + extended routing/marker regressions (see PR body)
- `ruff check`, `check_secrets.py`, `prod_check.py`, `git diff --check` all run (see PR body / agent report)
