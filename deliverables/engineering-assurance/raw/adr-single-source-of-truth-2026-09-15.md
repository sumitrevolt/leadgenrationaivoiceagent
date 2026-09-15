# ADR-194: Single Source of Truth for the LeadGen AI production topology

**File:** `deliverables/engineering-assurance/raw/adr-single-source-of-truth-2026-09-15.md`
**Author:** Archi (阿奇) · System Architect · Engineering Assurance Team
**Date:** 2026-09-15 · **Status:** Proposed · **Task:** architecture assessment + ADR (architect-2)
**Codebase bases (two, and that is itself finding A9):** prod checkout HEAD `cdc28e0d` · local HEAD = **real** remote `main` = `e77f8e08` (authoritative via `gh api …/git/ref/heads/main`). The local `refs/remotes/origin/main` reads `6678405b` — a **stale remote-tracking ref** (a known local-ref anomaly this session; `git fetch --prune` prints the update but the ref does not move), **not** a third lineage.
**Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`
**Method:** design only. Read-only production inspection over SSH (booleans/paths/versions only, never a secret value). No code changed, nothing committed, pushed or deployed.

> **The owner's symptom, stated architecturally:** *"ek fix hota hai toh dusra tod jaata hai"* is the expected behaviour of a system that has **more than one writable description of itself and no arbiter between them**. Every fix is applied to one copy of the truth; the copies the fix did not touch stay wrong; the next observer reads a different copy and sees a regression. This ADR is about collapsing the copies, not about fixing individual bugs.

---

## 0. Headline finding — the third runtime root is a **latent** split (found during this assessment)

The team-lead's evidence describes a **documented-vs-running** divergence (A1) and a **two-data-root** divergence (A5). Production inspection for this ADR found a **third runtime root that is not in A1–A8** — and, critically, it is a **latent** hazard, not an active second source of truth:

> **The process that serves `leadsgenai.in` and the container fleet resolve `LEADGEN_RUNTIME_DATA_DIR` to two different directories on disk — but the host-side directory is currently an empty tree the process does not write to.**

| Resolver | Env value read | Host directory actually used | Contents | Evidence |
|---|---|---|---|---|
| **systemd host uvicorn** (`leadgen.service`, serves traffic) | `LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime` from `/opt/leadgen/.env` | `/var/lib/leadgen/runtime` — **dev `2049:1321522`** | **0 files** (3 dirs total: root + `boss_autonomy/` + `boss_decision_governance/`, both empty; tree created at process start `02:40`) | `PRODUCTION-PROVEN` (empty) · `CODE-PRESENT` (latent) |
| **Every compose service** (`worker`, `scheduler`, `worker-heavy`, `worker-video`, `dsh-worker`, `worker_cli_*`, `app_vobiz`, `mcp`, `app_staging`) | `LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime` **inside the container**, bind-mapped from host `${LEADGEN_RUNTIME_DATA_HOST_DIR}=/opt/leadgen-runtime` | `/opt/leadgen-runtime` — **dev `2049:262673`** | **456 files** — populated cutover target (`automation/` 49 MB, `compliance/`, `customers/`, `billing/`, `content/`, …) + marker `migration/cutover.json` | `PRODUCTION-PROVEN` |
| *(legacy, for contrast)* in-checkout | `./data:/app/data` | `/opt/leadgen/data` | **3974 files** — still written (`job_runs.jsonl` 29 MB @03:52) | `PRODUCTION-PROVEN` |

**Facts that bound the claim (team-lead re-measured, 2026-09-15):**
- `/var/lib/leadgen/runtime` is **not a mount point** — `findmnt -T` → `TARGET / SOURCE /dev/sda1 ext4`; it is a plain directory on `/`.
- The host root holds **0 files**: `stat /var/lib/leadgen/runtime/boss_autonomy/state.json` → **No such file or directory**; the sibling `boss_autonomy/` and `boss_decision_governance/` are **empty**.
- The **live** boss state is `/opt/leadgen-runtime/boss_autonomy/state.json` — **136 B, root:root, mtime 2026-09-15 03:55:07** (actively written). `/opt/leadgen/data/boss_autonomy/state.json` does not exist.
- The host process (pid 788053) holds **no fd** under any of the three roots (`ls -l /proc/788053/fd | grep …` → no matches).

**So the correct characterisation is:** `/var/lib/leadgen/runtime` is the **`mkdir` side-effect of a `store_dir()`-style call at process start** — an **empty directory tree**, not an active writer. The host process does **not** currently write runtime data there. This is therefore a **LATENT split, not an active second brain**: it will silently become a real second source of truth the moment any host-side code path writes runtime data under `LEADGEN_RUNTIME_DATA_DIR` — and because the preflight runs **inside a gate container** (where `/var/lib/leadgen/runtime` *is* `/opt/leadgen-runtime`), nothing in the current tooling would notice. Label: `PRODUCTION-PROVEN` (the divergence exists and the directory is empty) + **latent** (not currently writing).

**Why it still matters (without overstating it):** the code, the compose file, the `.env`, and the preflight all agree — because they are all evaluated where the two paths coincide. Nobody checked the one process that is **not** in a container. A cutover marked `CUTOVER_COMPLETE` with `RUNTIME_DATA_CUTOVER_ENABLED=1` and **0 deployment blockers** (`PRODUCTION-PROVEN`) is therefore true for the workers, and **untested** for the web tier. Today the web tier happens not to be writing runtime data there; the defect is that the architecture would not tell us if it started.

**Consequence, stated precisely and no more strongly than the evidence:** the web tier *would* resolve its runtime stores against an empty root rather than the populated one, while the Celery workers write the populated root the web tier never reads. Whether any store currently fails closed, silently reads the legacy `data/` copy, or is simply never exercised on the web path is **`UNKNOWN` without per-store request tracing** — and that uncertainty, not a proven outage, is the defect. I am **not** claiming a customer-visible incident; the empty tree and the absent fds argue against an active one today. I am claiming the architecture cannot rule one out, and that closing it is cheap.

**This is the single highest-leverage architectural change in the document: make the host process and the container fleet resolve to one runtime-data root.** It is also the cheapest (one line in a systemd drop-in), which is why it should be the first fix, not the last. See **D-4**.

---

## 1. Requirement & goal — what "single source of truth" must mean here

### 1.1 The owner's mandate, translated into engineering constraints

The mandate is not "document the architecture better." It is **"a deploy must not break a working automation, and fixing one thing must not break another."** For this system that decomposes into four hard, testable properties:

| # | Property | What it means concretely | Current status |
|---|---|---|---|
| **R1** | **One serving authority** | Exactly one process serves `leadsgenai.in`, and that process is part of the release, not a bystander to it. | ❌ `PRODUCTION-PROVEN`: systemd host uvicorn serves; `deploy_vps.sh` never restarts it |
| **R2** | **One deploy authority** | Exactly one script can mutate production, and every other entry point delegates to it and inherits its exit code. | 🟡 `PARTIAL`: `_deploy_parent_delegate.sh` exists and 5 wrappers use it; ≥8 live scripts still carry their own `git reset --hard`/`git clean` |
| **R3** | **One runtime-data authority** | Exactly one directory holds mutable production state, and **every** process (host and container) resolves it to the same bytes. | ❌ `PRODUCTION-PROVEN`: **two active roots** — `/opt/leadgen-runtime` (456 files, workers) and the in-checkout `/opt/leadgen/data` (3974 files) — plus a **latent third** `/var/lib/leadgen/runtime` (0 files, empty tree the host process does not yet write) |
| **R4** | **One description of production** | A versioned artifact describes what production *is*, and a check fails when reality drifts from it — so the repo cannot lie about prod. | ❌ `PRODUCTION-PROVEN`: `AGENTS.md §2` says `Caddy → leadgen_app :8000 (Docker)`; the container does not exist |

### 1.2 Non-goals (explicit, to keep the sprint honest)

- Not a rewrite of the runtime-data subsystem. `app/platform/runtime_data.py`, `runtime_data_manifest.py`, `runtime_data_preflight.py`, `runtime_data_cutover.py` and `_runtime_data_guard.sh` already exist and are good; the task is **adoption and truth**, not replacement. (`CODE-PRESENT`)
- Not a compliance change. **No decision below weakens DND/TRAI/DPDP/consent.** Two decisions (D-1, D-4) are explicitly gated on "compliance stores behave identically before and after" — see §5.
- Not a migration of staging off the host as a *precondition*. D-5 recommends it but it is sequenced last.
- Not enabling any new feature. Every decision is a **deletion, a delegation, or a verification** — zero new runtime behaviour is introduced except the two verifications in D-3.

### 1.3 Constraints

- **C1 — Single 16 GB / 4-core VPS, up 19 days, load 1.37/1.71/1.98, 47 running containers, `ufw` inactive.** (`PRODUCTION-PROVEN`) No headroom for a second full stack "just in case."
- **C2 — One real paying customer (jiya makeover) with live ledgers inside the checkout.** (`PRODUCTION-PROVEN`) Blast radius of any data move is revenue-bearing.
- **C3 — Compliance gates are frozen surface.** (AGENTS.md §5) Any decision touching consent/suppression/DND must preserve fail-closed semantics.
- **C4 — 7-day revenue sprint.** Recommendations must be ordered by *cost-to-safety*, cheapest first.

---

## 2. Current-state architecture (as actually running)

### 2.1 What `AGENTS.md §2` claims (`STALE`)

```
Internet ──> Caddy (host, TLS leadsgenai.in) ──> leadgen_app :8000  (FastAPI, Docker, uvicorn WEB_CONCURRENCY=2)
```

### 2.2 What is actually running (`PRODUCTION-PROVEN`, verified this session)

```
                                    ┌──────────────────────────────────────────────┐
 Internet                           │  Hostinger VPS Mumbai 72.61.245.204          │
    │                               │  16 GB / 4-core · up 19 d · ufw INACTIVE     │
    ▼                               │  47 running containers · load 1.37/1.71/1.98 │
 ┌──────────────┐                   │                                              │
 │ Caddy (host) │  /etc/caddy/      │  ┌─────────────── HOST PROCESS ─────────────┐ │
 │  TLS + routes│  Caddyfile        │  │ systemd leadgen.service   [ACTIVE]       │ │
 └──────┬───────┘                   │  │  WorkingDirectory=/opt/leadgen           │ │
        │ :2,:47 reverse_proxy      │  │  ExecStart=… uvicorn app.main:app \      │ │
        │ 127.0.0.1:8000            │  │     --host 127.0.0.1 --port 8000 \       │ │
        ▼                           │  │     --workers 2                          │ │
 ┌─────────────────────────┐        │  │  EnvironmentFile=/opt/leadgen/.env       │ │
 │ systemd host uvicorn     │◄───────┼──┤  User=root · Restart=always              │ │
 │ 127.0.0.1:8000 (3 PIDs)  │        │  │  HEAD = cdc28e0d  ← SERVES THE SITE      │ │
 │ /health version=cdc28e0d │        │  │  NOT in deploy_vps.sh SERVICES           │ │
 └───────────┬──────────────┘        │  └──────┬───────────────────┬───────────────┘ │
             │                        │         │                   │                 │
             │ reads                  │         │ reads             │ reads           │
             ▼                        │         ▼                   ▼                 │
  /var/lib/leadgen/runtime  ◄─ LATENT │  /opt/leadgen/data     (legacy, still written)│
  (dev 2049:1321522)                  │   job_runs.jsonl 29 MB  @03:52                │
  0 FILES — empty tree                │                                               │
  (boss_autonomy/ +                   │                                               │
   boss_decision_governance/,         │                                               │
   both empty; created at proc start) │                                               │
                                      │  ┌─────────── deploy_vps.sh SERVICES ───────┐ │
                                      │  │ worker · scheduler · worker-heavy ·       │ │
                                      │  │ worker-video · dsh-worker   → 95245ce8    │ │
                                      │  │  (built by Dockerfile.lock; app is built  │ │
                                      │  │   but NO leadgen_app container runs)      │ │
                                      │  └───────────────┬───────────────────────────┘ │
                                      │                  │ reads                       │
                                      │  ┌─────────── NEVER deployed by the script ──┐ │
                                      │  │ 6 × worker_cli_*        → d08f07c5         │ │
                                      │  │ app_vobiz + mcp         → 8b7fd7c3         │ │
                                      │  │ app_staging             → 28ba5d4e         │ │
                                      │  │  (SERVICES at deploy_vps.sh:32-34 lists    │ │
                                      │  │   neither group → can never be updated)    │ │
                                      │  └───────────────┬───────────────────────────┘ │
                                      │                  │ reads                       │
                                      │                  ▼                             │
                                      │      /opt/leadgen-runtime  (dev 2049:262673)   │
                                      │      THE POPULATED CUTOVER TARGET + MARKER     │
                                      │      automation/ 49 MB · compliance/ ·         │
                                      │      customers/ · billing/ · content/ …        │
                                      │                                                │
                                      │  ┌──────── OTHER TENANTS ON THE SAME HOST ───┐ │
                                      │  │ buzz-prod-{minio,postgres,redis,relay}     │ │
                                      │  │ tilakgram-{meilisearch,minio} · livekit    │ │
                                      │  │ leadgen_app_staging + db_staging +         │ │
                                      │  │ redis_staging  (shares prod mounts)        │ │
                                      │  └────────────────────────────────────────────┘ │
                                      └────────────────────────────────────────────────┘

 PUBLIC BINDS (ufw inactive → internet-reachable, `PRODUCTION-PROVEN`):
   leadgen_waha     0.0.0.0:3002 -> 3000     (checked-in compose says 127.0.0.1:3111 — A7)
   buzz-prod-relay  0.0.0.0:3110
```

### 2.3 The divergence, itemised against `AGENTS.md §2`

| `AGENTS.md §2` claim | Reality (`PRODUCTION-PROVEN`) | Class |
|---|---|---|
| `leadgen_app :8000 (Docker)` serves | No `leadgen_app` container exists; systemd host uvicorn `:8000` serves | **Documented ≠ running** |
| `uvicorn WEB_CONCURRENCY=2` | True for the host process (`--workers 2`) — coincidentally correct | **Accidental truth** |
| `leadgen_worker + leadgen_scheduler [--profile celery]` | True, but on `95245ce8` while the site runs `cdc28e0d` | **Version skew** |
| Postgres/Redis/Qdrant topology | True | ✅ |
| WAHA "own WAHA :3111" | Running `0.0.0.0:3002`; checked-in `deploy/compose/docker-compose.waha.yml:79-83` says `127.0.0.1:3111` | **Documented ≠ running** |
| — (not documented at all) | `app_vobiz`, `mcp`, `app_staging`, `worker_cli_*` are running and **undeployable by the canonical script** | **Undocumented** |
| — (not documented at all) | The serving process's runtime root (`/var/lib/leadgen/runtime`, 0 files) ≠ the workers' runtime root (`/opt/leadgen-runtime`, 456 files) (§0) | **Undocumented latent split** |

**A9 (new finding): two codebases, not one — plus a stale local ref.** prod checkout = `cdc28e0d`; local HEAD = **real** remote `main` = `e77f8e08` (authoritative via `gh api …/git/ref/heads/main`). The local `refs/remotes/origin/main` reads `6678405b` — a **stale remote-tracking ref** (a known local-ref anomaly this session: `git fetch --prune origin` prints the update but the ref does not move; cause `UNKNOWN`), **not** a third lineage and **not** a "fourth sha matching nothing". Separately, the last canonical deploy log (`/tmp/dep.log`) records `DEPLOYED 867686ae OK` on Sep 13 — so the *serving* sha (`cdc28e0d`) moved outside a canonical deploy, which is the operative fact; that is a deploy-provenance observation, not another branch. (`PRODUCTION-PROVEN`)

### 2.4 Why the symptom follows from this diagram (the causal chain)

```
more than one writable copy of the truth
        │
        ├─ (1) deploy_vps.sh builds an `app` image and rolls out 5 services,
        │      but the SERVING process is a 6th thing it never restarts
        │      → /health may show old or new code, independent of the deploy
        │
        ├─ (2) 4 container groups (cli/vobiz/mcp/staging) are outside SERVICES
        │      → every deploy silently increases skew (A3)
        │
        ├─ (3) 8 sibling scripts each `git reset --hard origin/main` the same
        │      checkout the live ledgers sit in (A4) → any of them can revert data
        │
        ├─ (4) two ACTIVE runtime roots (/opt/leadgen-runtime, /opt/leadgen/data)
        │      + a LATENT third the web tier resolves (§0) → a write is
        │      authoritative only for the process that made it, and the web tier's
        │      root is empty (0 files) so it would diverge silently if it wrote
        │
        └─ (5) `AGENTS.md §2` describes none of this → the next engineer
               "fixes" the diagram, not the system
        ↓
   "ek fix hota hai toh dusra tod jaata hai"
```

Each layer independently converts a local, correct change into a global inconsistency. That is the mechanism; the ADRs below remove the layers.

---

## 3. Key decision records

### D-1 — Production is served by the **systemd host uvicorn**, declared as a first-class release artifact

**Context.** The container named `leadgen_app` in `AGENTS.md §2` and in `docker-compose.vps.yml:41` **does not exist**; the site is served by `leadgen.service` (host uvicorn, `EnvironmentFile=/opt/leadgen/.env`, `User=root`, `Restart=always`). `deploy_vps.sh` verifies `/health` on `127.0.0.1:8000` — i.e. it verifies the **systemd** process — yet its `SERVICES` list and rollout are entirely compose-side, and it contains **no `systemctl restart leadgen`** (`PRODUCTION-PROVEN`: 3 grep hits for restart/systemctl in the script, all comments/echo). So the script both *verifies a process it does not deploy* and *deploys a process it does not verify*.

**Options.**

| Option | Complexity | Cost | Risk | Time-to-safety |
|---|---|---|---|---|
| **(A) Declare systemd the serving authority; add it to the release** | Low | ₹0 | Low — one restart step + verify | **Days** |
| **(B) Switch serving to the `app` container; delete systemd** | High | ₹0 | High — Caddy upstream, two `DATABASE_URL` semantics (host `@127.0.0.1:5432` vs container `@pgbouncer:6432`), `./data` ownership (`user: 0:0`), PgBouncer DNS, cold-start, rollback path all change at once | **Weeks**, and the sprint cannot absorb it |
| **(C) Keep both (status quo)** | — | — | This *is* the defect | — |

**Decision: (A) now; (B) is the funded architectural target, gated behind a parity rehearsal.**

Reasoning:
1. (A) is the **smallest change that makes reality and the release agree**. The verify already reads the host process; adding the restart closes the loop. (C) is rejected by construction.
2. (B) is architecturally cleaner — one env namespace, one DNS namespace, and the serving process would finally be covered by the anti-skew check — but it moves *four* coupled variables at once onto a live single-VPS production with one paying customer and no staging parity proof. That is exactly the kind of change that produces the next "dusra tod jaata hai".
3. (A) also removes the §0 **latent** split for free (see D-4), which (B) would only remove later.

**Consequences.**
- *Easier:* the release now covers the process customers hit; `/health.version` becomes a real deploy signal instead of a coincidence.
- *Harder:* the systemd unit becomes frozen surface — changes to `ExecStart`/env require a reviewed PR, not an SSH edit.
- *Must revisit:* when (B) is funded, D-3's restart step is **replaced** (not layered) by a compose rollout of `app`; leaving both would recreate a two-authority serving path.

**Migration (A).**
1. Land the `systemctl restart leadgen` + host-verify step from **D-3** (single PR).
2. Add `Environment=LEADGEN_RUNTIME_DATA_DIR=/opt/leadgen-runtime` to the unit (see **D-4**) so the host process and the containers read one root.
3. Correct `AGENTS.md §2` / `CLAUDE.md §2` to say `systemd host uvicorn :8000 (not a container)`.
4. Record the unit verbatim in the production manifest (**D-6**) so a hand-edit is detectable.

**Rollback (A).** `systemctl restart leadgen` is reversible by re-deploying the previous `APP_VERSION` through the same script (`bash scripts/deploy_vps.sh <prev-sha>`), which restarts the host process at the old checkout sha. No data is moved by this decision, so rollback is code-only.

---

### D-2 — `deploy_vps.sh` becomes the **only** path that can mutate production; the other entry points become delegates or are deleted

**Context.** `deploy_vps.sh` is canonical (`AGENTS.md R10`, `memory/playbooks.md:32`). But the checkout also carries **≥8 live scripts that each deploy to the same `/opt/leadgen` tree**, most with their own destructive Git step (`PRODUCTION-PROVEN`, re-verified this session):

| Script | Destructive step | Verified |
|---|---|---|
| `scripts/vps_pitch_deploy.sh:6-7` | `git fetch --all` + `git reset --hard origin/main` | ✅ |
| `scripts/_mcp_deploy_remote.sh:11-12` | `git fetch --all --tags` + `git reset --hard origin/main` (its own header warns it reverts `data/`) | ✅ |
| `scripts/vps_deploy_dashboard.py:7` | `git reset --hard origin/main -q` | ✅ |
| `scripts/vps_build_deploy.py:6-7` | `git reset --hard origin/main -q` (docstring: "destroys uncommitted live data") | ✅ |
| `scripts/vps_force_pull.py:48-49` | `git clean -fd frontend/explorer.html` + `git pull origin main` | ✅ |
| `scripts/vps_deploy_workflow_fix.py:4` | release chain `git fetch` + `git reset --hard` | ✅ |
| `scripts/vps_deploy_call_learn.bat:29` | `git reset --hard origin/main -q` | ✅ (team-lead A4) |
| `scripts/deploy_godmode.bat`, `deploy_now.sh`, `deploy_outreach_bounce_fix.bat`, `deploy_vobiz_fix.bat` | git/compose mutation | `PRODUCTION-PROVEN` (surface scan) |

A **delegation mechanism already exists and is partially adopted**: `scripts/_deploy_parent_delegate.sh` exposes `delegate_to_parent()`, which resolves `deploy_vps.sh` next to itself, refuses if it is missing, runs it, and **preserves the parent's exact exit status** (90 = guard denied, 91 = guard unavailable). It is already sourced by `deploy_adr095.sh`, `deploy_adr096.sh`, `deploy_adr097.sh`, `deploy_all.sh`, `vps_flywheel_deploy.sh`. (`CODE-PRESENT`) A read-only inventory scanner also exists: `scripts/_deploy_surface_inventory.py` (greps for git/container/fs mutation + prod markers + guard usage). (`CODE-PRESENT`)

**Decision.**
1. **`deploy_vps.sh` + `_deploy_parent_delegate.sh` are the only two scripts permitted to contain a production-mutating primitive.** Every other script either (a) becomes a one-line `delegate_to_parent "$@"`, or (b) is deleted, or (c) moves to `scripts/legacy/`.
2. **Convert the 6 live duplicate deploy scripts** (table above, non-`.bat`) to delegates in one PR. Delete their local `git`/`compose` chains — do not leave them commented out (a commented chain is a re-arm waiting to happen).
3. **Retire the `.bat` deploy paths** to `scripts/legacy/` (they cannot run on the host anyway; they are Windows-side convenience wrappers whose only correct behaviour is to SSH and call the parent).
4. **Add a blocking CI gate** — extend `scripts/_deploy_surface_inventory.py` to fail (`--strict`) when any file outside `{scripts/deploy_vps.sh, scripts/_deploy_parent_delegate.sh}` matches `git (reset --hard|clean|pull)` or `docker compose … (up -d|down|build)` **and** a prod marker (`/opt/leadgen`, `docker-compose.vps.yml`, `leadsgenai.in`, `72.61.245.204`). This turns "one deploy authority" from a convention into a **test**.
5. **Make the CI release path call the parent.** `deliverables/engineering-assurance/deploy-check-hermes-harness-2026-09-14.md` §0 records **P0-B**: the CI `deploy-vps.yml` SSHed `/usr/local/sbin/leadgen-deploy-release`, a **3506-byte root wrapper** that does `docker compose pull`/`up -d`/`alembic`/`curl /health/ready` and **never calls `deploy_vps.sh`** — so it bypassed the runtime-data guard, `prod_check --deployment`, the ff-only advance, the anti-skew rollout and the exact-SHA verify. That wrapper still exists on the host (`PRODUCTION-PROVEN`, `-rwxr-xr-x 1 root root 3506 Jul 21`). **It must be deleted or made to `exec bash /opt/leadgen/scripts/deploy_vps.sh "$@"`.**

**Consequences.**
- *Easier:* one exit-status contract; the guard cannot be bypassed by choosing a different script.
- *Harder:* ad-hoc "quick deploy" habits break — by design. Any genuine need is served by `bash scripts/deploy_vps.sh <sha>`.
- *Blast radius of the CI gate:* if any legitimate non-prod script matches the regex it will red the gate; mitigate by scoping the prod-marker requirement (both a mutation **and** a prod marker must be present) and by an explicit allowlist file with justification.

**Alternatives considered.** (i) *Delete the duplicates without a CI gate* — rejected: they regrow, and this repo's history (A8 watchdog, ADR-097) is a record of exactly that. (ii) *Move everything to a CI-only deploy* — rejected for this sprint: the owner's flow is SSH-driven and the CI merge gate is still advisory (branch protection absent, per the SRE P0-A).

---

### D-3 — `deploy_vps.sh` guarantees the **serving** process runs the deployed SHA, without weakening the exact-SHA gate

**Context.** The script already has a strong exact-SHA contract: it refuses `latest`/`dev` (`:88-94`), resolves the sha from the fetched object DB (`:84`), materialises a detached candidate worktree (`:97`), gates on `prod_check --deployment` **inside the candidate image** (`:263`), advances the live checkout with `git pull --ff-only` and re-asserts `LIVE_SHA == CANDIDATE_SHA` (`:283-288`), rolls out 5 services, then verifies `/health.version == VER` (`:490`), `environment == production` (`:516`), `/health/ready == 200` (`:527`), route count ≥1300 (`:544`), and per-container skew (`:571-597`). (`CODE-PRESENT`)

The gap is narrow and exact: **the process whose `/health` is verified is the systemd host process, and the script never restarts it.** When the host process is already on the old sha, the verify loop (`HEALTH_MAX_ATTEMPTS` default 12 × 5 s) cannot succeed — so either the deploy fails at exit 3, or (as observed) something *outside the script* restarted the service. `/tmp/dep.log`'s last line is `DEPLOYED 867686ae OK` (Sep 13) while prod now serves `cdc28e0d` (a later commit) — i.e. the serving sha moved **without** a canonical deploy. (`PRODUCTION-PROVEN`)

**Decision.** Add a **host-app release step** to `deploy_vps.sh`, positioned after the live checkout is proven at `CANDIDATE_SHA` and before the existing verify:

1. **Capture** the currently-serving host version (`curl /health` → `PREV_HOST_VER`) and record it beside the existing image-lineage capture (`LINEAGE_STATE`).
2. **Set provenance:** write `APP_VERSION=$VER` into `/opt/leadgen/.env` atomically (the systemd unit reads it via `EnvironmentFile`; the current `.ENV GUARD` at `:168-199` checks APP_VERSION is *a* sha but not that it *equals* `VER` — this closes that).
3. **Restart** via a new guarded helper `scripts/_host_app_release.sh` (sourced like `_deploy_parent_delegate.sh`), which refuses if `leadgen.service` is absent/unreadable (exit 91 pattern) and otherwise runs `systemctl restart leadgen`.
4. **Verify** — the existing `/health.version == VER` loop now has a process that can actually change; no gate is weakened, the verify simply becomes satisfiable and therefore meaningful.
5. **Fail closed with rollback:** if `/health.version` still ≠ `VER` after the bounded retries, the script restarts the service at `PREV_HOST_VER`, re-verifies, and exits non-zero with an alert — i.e. the deploy never reports success while the site runs the wrong sha.
6. **Health-gate ordering:** keep the restart **after** the Alembic step (`:456-462`) so a schema-stale process is never briefly served, and **before** the smoke suite (`:599`) so smoke exercises the new code.

**Why this does not weaken the exact-SHA gate.** The gate's job is "do not start code that was not gated." The restart happens *only after* `LIVE_SHA == CANDIDATE_SHA` is proven, so the process it starts is exactly the gated code. The new step adds a *precondition* (the unit must exist) and a *failure action* (rollback), never a bypass.

**Alternatives considered.** (i) *Verify only the containers, drop the host verify* — rejected: it would make the script report success while the site runs stale code (the current failure mode, formalised). (ii) *Let the operator restart by hand* — rejected: that is the status quo and it is unverifiable. (iii) *Restart inside the candidate-image gate container* — impossible: systemd is a host concept.

**Consequences.** *Easier:* `/health.version` becomes a trustworthy deploy signal. *Harder:* a deploy now has a ~10–30 s web-tier interruption (systemd `RestartSec=5` + import cold start); the smoke + retry loop must absorb it, and `HEALTH_MAX_ATTEMPTS` may need a one-off raise for cold imports. *Risk:* in-flight voice/HTTP requests during the restart — mitigate by keeping the restart window short and relying on Caddy retry, and by scheduling deploys outside the TRAI calling window (`10:00–19:00` IST, `PLATFORM_DIAL` active).

---

### D-4 — Retire the in-checkout `./data` mount **and** collapse the host process's (latent, empty) runtime root onto the container root; ordering is resolver-first, mount-last

**Context (verified this session).**

- **State machine already on:** `/opt/leadgen/.env` has `RUNTIME_DATA_CUTOVER_ENABLED=1`, `LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime`, `LEADGEN_RUNTIME_DATA_HOST_DIR=/opt/leadgen-runtime`; the marker `/opt/leadgen-runtime/migration/cutover.json` exists (Jul 29). (`PRODUCTION-PROVEN`)
- **Manifest says done:** `runtime_data_manifest.py` now has **21 × `CUTOVER_COMPLETE`**, **0 × `deployment_blocker=True`**, 6 × `LEGACY_IN_CHECKOUT` (all `deployment_blocker=False`), 23 × `REBUILDABLE_CACHE`. (`CODE-PRESENT`) So `runtime_data_preflight.py deploy_denied()` returns **empty** and the guard **passes**.
- **But the legacy mount is still live in all 13 services** (`docker-compose.vps.yml` lines 96/160/362/423/456/489/522/555/588/622/688/749/915) **and still written** — `/opt/leadgen/data/job_runs.jsonl` 29 MB @03:52. (`PRODUCTION-PROVEN`)
- **And the host process resolves a third root** (§0): the systemd process reads `/var/lib/leadgen/runtime` (dev `2049:1321522`), which is **not** the container bind source `/opt/leadgen-runtime` (dev `2049:262673`). The host root is an **empty tree (0 files)** the process does not yet write — a **latent** split, not an active writer. (`PRODUCTION-PROVEN` empty · `CODE-PRESENT` latent)
- **189 files under `data/` are git-tracked** (`.gitignore:151 data/*` does not apply to tracked files), so the `git pull --ff-only` at `deploy_vps.sh:277` operates on the directory holding the ledgers. Currently `git status --porcelain data/` is clean (`PRODUCTION-PROVEN`) — i.e. the hazard is **latent, not gone**.

**The ordering constraint — and why it is *not* "mount first".**

The `RUNTIME_DATA_CUTOVER.md` runbook (2026-07-28) fixes the per-wave order: **CODE → MANIFEST → BYTES → MARKER → MANIFEST**. Mount removal is a **separate, later** step, because the mount is the *legacy read/write path*: remove it before every writer resolves through the authority and any un-migrated writer either crashes (fail-closed) or writes to the container's ephemeral `/app/data`. So:

```
STEP 0  (this ADR's first fix)  ONE host root
        add Environment=LEADGEN_RUNTIME_DATA_DIR=/opt/leadgen-runtime to leadgen.service
        → the serving process and the container fleet finally read the same bytes.
        This is independent of, and safer than, everything below; do it first.

STEP 1  PROVE code adoption
        scripts/runtime_data_path_scan.py --ratchet  → drive uncontrolled
        checkout-backed findings to ZERO for every production writer.
        (The Tier-0 ratchet in RUNTIME_DATA_TIER0_MIGRATION.md §6 demands exactly this.)

STEP 2  RECONCILE the dual-written automation stores
        job_runs.jsonl / cadence_runs.jsonl / sales/prospects.jsonl / staff_bus/dlq.jsonl
        exist in BOTH ACTIVE roots — /opt/leadgen-runtime (456 files) and the legacy
        in-checkout /opt/leadgen/data (3974 files) — and both grow. (This is distinct
        from the LATENT third root /var/lib/leadgen/runtime, which is empty.) Classify
        each: runtime-authoritative (migrate) or REBUILDABLE_CACHE (delete the legacy
        copy). "Both grow" is not a classification.

STEP 3  INTERMEDIATE — make the legacy mount read-only
        ./data:/app/data  →  ./data:/app/data:ro   in all 13 services.
        Any writer still touching the legacy path now FAILS LOUDLY instead of
        silently diverging. This is the step that converts "unknown" into "known".

STEP 4  SOAK + PROVE zero legacy writes
        observe legacy-path mtimes for a window; require zero new writes.

STEP 5  REMOVE the ./data mount entirely (all 13 services).

STEP 6  UN-TRACK the checkout data
        git rm --cached the 189 tracked files (files stay on disk), tighten
        .gitignore, so git pull --ff-only can never again be blocked or reverted
        by production state.
```

**Decision.** Adopt the order above. **Resolver/root first (Step 0–2), mount removal last (Step 5).** Reject the tempting "remove the mount now, it's just one line" — that inverts the dependency and is precisely how a cutover becomes a split nobody notices for a week (`RUNTIME_DATA_TIER0_MIGRATION.md:50-52`).

**Consequences.**
- *Easier:* after Step 0 the web tier and workers share one authority; after Step 6 `deploy_vps.sh`'s `git pull --ff-only` can no longer be blocked by live data, and the 8 duplicate scripts' `git reset --hard` (D-2) become harmless to data.
- *Harder:* Step 3 will surface every un-migrated writer as a runtime failure; that is the point, but it needs a maintenance window and a rollback (flip `:ro` back — one line).
- *Must revisit:* whether `job_runs`/`cadence_runs` belong in runtime at all, or should become DB tables (`DATABASE_AUTHORITY` already exists as a manifest state).

**Alternatives considered.** (i) *Keep `./data` mounted read-write and rely on the guard* — rejected: the guard now **passes** (0 blockers), so nothing stops a sibling script's `git reset --hard` from reverting tracked data. (ii) *Delete the checkout copy immediately* — rejected: `RUNTIME_DATA_CUTOVER.md:108` is explicit that deleting the source is the step that makes rollback impossible, and it must come only after the external root has survived real traffic.

---

### D-5 — Staging does **not** belong on the production host as a 24×7 tenant

**Context.** The prod host runs **47 containers**, including a full staging stack (`leadgen_app_staging` 28ba5d4e, `leadgen_db_staging`, `leadgen_redis_staging`) that has been up **~2 weeks**, **sharing the same production data mounts**, alongside other tenants (`buzz-prod-*` ×4, `tilakgram-*` ×2, `livekit`, `leadgen-freeswitch`, the full Obs stack, OmniRoute, WAHA, SearXNG, ntfy…). Host is 16 GB / 4-core, up 19 days, load 1.37/1.71/1.98. (`PRODUCTION-PROVEN`) `deploy/compose/docker-compose.staging.yml` already does the right isolation for DB/Redis (separate containers, volumes, network, `APP_ENV: staging`, `AUTO_EMAIL_OUTREACH=false`, `RUN_IN_PROCESS_SCHEDULER=0`, resource caps, `profiles: ["staging"]`), and its own header documents the intent: "test karo PHIR prod pe bhejo". (`CODE-PRESENT`)

**Decision.** **Recommend: no — staging must not run 24×7 on the production host. Make it on-demand and hard-isolated; migrate it off-host when a second VPS is affordable.**

1. **On-demand only.** `profiles: ["staging"]` already means a bare `up` skips it; enforce that it is *only* started for a rehearsal (`--profile staging up -d`), and **stopped after** (`--profile staging down`). The observed 2-week uptime means it is effectively permanent today.
2. **Hard-isolate the mounts.** `docker-compose.staging.yml` must **not** bind `./data` or `/opt/leadgen-runtime`; give staging its own root (e.g. `/opt/leadgen-staging-runtime`) with synthetic fixtures. Sharing the prod data mounts means a staging write is a prod write — and §0 shows prod already has a root nobody reconciled.
3. **Cap and pre-empt.** Keep `mem_limit`/`pids_limit`/`oom_score_adj: 100` (already present) so a staging leak cannot OOM the revenue path.
4. **Never publicly routable.** The compose header suggests `staging.leadsgenai.in → 127.0.0.1:8001` with basic-auth; if routed, it must be auth-gated **and** must not share the prod data root (see 2). Prefer no public route at all — SSH tunnel for rehearsals.
5. **Target state:** a second, cheap VPS (or ephemeral CI runner) for staging. Deferred — not a sprint blocker.

**Why not "keep it as-is":** the risk is not CPU (load is modest) — it is **data contamination + memory pressure on a host with no swap headroom**, both of which are exactly the class of failure that produces "deploy ke baad automation break".

**Consequences.** *Easier:* rehearsals become deliberate and reproducible; prod memory headroom returns. *Harder:* every rehearsal needs an explicit start/stop; a "staging is always up" habit breaks. *Rollback:* trivial — staging is profile-gated; re-enabling is one `up`.

---

### D-6 — One versioned description of production + a continuous drift check

**Context.** Today the "description of production" is spread across `AGENTS.md §2` (wrong), `CLAUDE.md` (mirror of the wrong text), `docs/ARCHITECTURE.md` / `ARCHITECTURE_BLUEPRINT.md` / `COMPOSE_GUIDE.md`, `docs/ADR-104_DEPLOY_RUNBOOK.md`, `memory/playbooks.md`, the checked-in compose files (which disagree with the host on WAHA ports — A7), and the host itself. There are already good **partial** drift instruments that nobody runs continuously:
- `scripts/runbook_drift.py` — flags drift between four sources of truth for **env keys** (runbook ↔ `activate.py` ↔ `app/api/activation.py` ↔ `.env.example`); `CODE-PRESENT`.
- `scripts/_deploy_surface_inventory.py` — read-only inventory of **who can mutate prod**; `CODE-PRESENT`.
- `scripts/runtime_data_preflight.py` — the **data-root** authority check; `CODE-PRESENT`.
- `scripts/check_skew.sh` — the **image-skew** check, but it **hardcodes `leadgen_app`** (a container that does not exist) and covers 6 containers, missing `worker_cli_*`/`app_vobiz`/`mcp`/`app_staging`; and it is **not wired into CI** (referenced only by `run_ship4.ps1`/`run_ship6.ps1`). `PRODUCTION-PROVEN`.

**Decision.** Introduce **one machine-readable production manifest** and **one drift checker** that reads it:

1. **`deploy/prod-manifest.yml`** (versioned, reviewed like code) — the authoritative description of *what production is*:
   - **host process(es):** unit name, `ExecStart`, `WorkingDirectory`, `EnvironmentFile`, `User`, `Restart` (record the unit **verbatim**, so a hand-edit is drift);
   - **container groups:** each with its compose file, service names, and the **image-provenance source** (which SHA/tag it must run);
   - **the deploy authority:** the one script allowed to mutate prod + the delegate helper;
   - **runtime-data roots:** host root and container root, with the **invariant that they resolve to the same inode** (this is the check that would have caught §0);
   - **public port binds** + expected reachability (to catch the WAHA `0.0.0.0:3002` / `ufw inactive` class);
   - **Caddy upstreams** and which process each maps to.
2. **`scripts/prod_drift_check.py`** — SSH read-only (or run on the host) and compare live state to the manifest; exit non-zero on any drift. It **subsumes** `check_skew.sh` (manifest-driven, no hardcoded container names) and adds: *is the serving sha the one the manifest says? is the host runtime root the same inode as the container root? is any public bind unexpected? does any non-authority script still carry a prod mutation?*
3. **Wire it in three places:** (a) as a **blocking CI job** on the schedule + on PRs touching `deploy/`, `docker-compose*.yml`, or the systemd unit; (b) as a **pre-flight** the operator can run before a deploy; (c) into the **daily owner brief** (`automation_health`) so drift is a number the owner sees, not a discovery during an incident.
4. **Correct the human docs to point at the manifest** (see §6) rather than restating topology — the restatement is what rots.

**Consequences.** *Easier:* `AGENTS.md §2` can never again silently diverge; the WAHA port class and the §0 root class both become red checks. *Harder:* the manifest must be updated in the same PR as any topology change — enforce via the CI job above. *Risk:* SSH-based checks are fragile (tunnel drops); make the check **fail-open on connectivity but fail-closed on observed drift**, and record "unreachable" as a distinct state (never as "clean").

**Alternatives considered.** (i) *Just fix the docs* — rejected: docs are a second copy of the truth; that is the disease. (ii) *A full IaC rewrite (Ansible/Terraform)* — over-scoped for a 7-day sprint and would itself become another description of production to keep in sync; the manifest + checker is the "good enough" 80 %.

---

## 4. Operability

### 4.1 What a deploy must verify (target = existing checks + the gaps)

**Already enforced by `deploy_vps.sh` (`CODE-PRESENT`):** guard helpers present (exit 91) → candidate sha resolved from fetched objects → provenance refusal (`latest`/`dev`) → isolated candidate worktree → runtime-data guard (exit 90) → gate-env proof → disk hard-stop ≥90 % → `.env` guard (APP_ENV=production, APP_VERSION is a sha, no `@pgbouncer:` in host DB URL) → candidate-image build → `prod_check.py --deployment` in the candidate image → `git pull --ff-only` + `LIVE_SHA == CANDIDATE_SHA` → compose rollout → Alembic `upgrade head` → `/health.version == VER` → `environment == production` → `/health/ready == 200` → route count ≥ 1300 → auto_mode/scheduler → per-service skew → smoke (12 paths) → queue/DLQ depth → lineage-aware image retention.

**Gaps this ADR adds (each is a hard gate, none weakens an existing one):**

| # | New verification | Owner decision | Failure action |
|---|---|---|---|
| V1 | `systemctl restart leadgen` performed **and** `/health.version == VER` on the **host process** | D-1, D-3 | rollback host to `PREV_HOST_VER`, exit non-zero |
| V2 | `.env` `APP_VERSION == VER` (not merely "a sha") | D-3 | refuse, exit 8 |
| V3 | **Host runtime root inode == container runtime root inode** | D-4 Step 0 | refuse deploy, alert |
| V4 | No production writer writes the legacy `data/` path (post-Step-3: mount `:ro`) | D-4 | refuse, exit non-zero |
| V5 | `prod_drift_check.py` clean (manifest == reality) | D-6 | warn pre-sprint, **block** once stable |
| V6 | Staging stack **not** sharing prod data mounts / not running unattended | D-5 | alert |

### 4.2 Alerts that must exist (minimum set)

- **Serving-sha drift:** `/health.version` ≠ the sha the manifest says is deployed → **page** (this is the owner's symptom's leading indicator).
- **Version skew across all container groups** (not just the 5 in `SERVICES`) → warn.
- **`/health/ready` ≠ 200** or `scheduler == stopped` or `auto_mode == false` → page (already partly covered by the deploy gate's environment/automation checks, but they only run **at deploy time** — they must also run **continuously**).
- **Legacy `data/` mtime advancing** after cutover Step 3 → page (a writer escaped the authority).
- **Host runtime root and container runtime root diverge** (inode or content) → page (§0's check).
- **Unexpected public port bind** while `ufw` is inactive → page (WAHA `3002`, relay `3110` today).
- **Marker invalid / `RUNTIME_DATA_CUTOVER_ENABLED` flipped** → warn.
- **Staging up > N hours** or sharing a prod mount → warn.

### 4.3 How drift is detected continuously

`prod_drift_check.py` on a **scheduled CI job** (e.g. hourly or per-deploy) comparing manifest ↔ live, plus the daily owner brief line "prod matches manifest: yes/no". The manifest is the single artifact; the checker is the single arbiter; the brief is the human surface. This replaces the current situation where `check_skew.sh` is hand-run and hardcoded, and `runbook_drift.py` is never scheduled.

---

## 5. Testing strategy

Every decision must be **proven by a named harness**, not by prose. Priorities: **P0 = compliance/availability, never weakened to land this ADR.**

| Decision | Proof | Harness / gate | Type |
|---|---|---|---|
| **D-1** (systemd is authority) | A behavioural test that fails if `deploy_vps.sh` can verify a host process it did not restart — i.e. restart step precedes verify and is not optional | new `tests/test_deploy_host_restart.py` (assert the restart call exists **and** is executed before the `/health` verify; a "line is present but never runs" test is not enough — mirror the existing `tests/test_deploy_parent_behaviour.py` style that caught the fail-open guard) | P0 |
| **D-1/D-3** | Cold-start: after restart, `/health.version == VER` within the retry budget on a real host | staging rehearsal (D-5) + post-deploy smoke | P0 |
| **D-2** (one deploy authority) | CI: any file outside the allowlist with a prod mutation + prod marker → fail | `scripts/_deploy_surface_inventory.py --strict` wired into `ci.yml` | P0 |
| **D-2** | Delegation preserves exit codes 90/91/0 | extend `tests/test_deploy_parent_behaviour.py` | P1 |
| **D-3** (provenance) | `.env` APP_VERSION ≠ VER is refused; `==` passes | unit test on the `.ENV GUARD` block | P1 |
| **D-3** (rollback) | Simulated `/health` mismatch → host restarts at `PREV_HOST_VER` and exits non-zero | behavioural test + one game-day drill on staging | P0 |
| **D-4 Step 0** | Host-process resolution == container resolution (same inode) | `runtime_data_preflight.py` extended to check the **host process** resolution (today it only checks from inside a gate container — the §0 blind spot) | **P0** |
| **D-4 Steps 1–6** | Ten per-store contracts already specified in `RUNTIME_DATA_TIER0_MIGRATION.md §5` (env-unset = legacy path; canonical path; inside-checkout fails closed; relative/missing/unwritable fail closed; writes land on one authority; read/write cannot split; no silent legacy fallback in CANONICAL; lock/tmp beside target; byte-compatible; tenant isolation) | shared parametrised harness + per-store specifics | **P0** |
| **D-4 Step 1** | Zero uncontrolled checkout-backed findings for production writers | `scripts/runtime_data_path_scan.py --ratchet` (Tier-0 ratchet, `TIER0_MIGRATION.md §6`) | **P0** |
| **D-4 Step 3** | With `./data:ro`, any legacy writer fails loudly (not silently) | integration test on staging | P1 |
| **D-5** | Staging cannot read/write prod data root | compose-level assertion test + CI check on `docker-compose.staging.yml` | P1 |
| **D-6** | Manifest ↔ live drift is detected; "unreachable" ≠ "clean" | `scripts/prod_drift_check.py --strict` in CI + unit tests for the unreachable state | P1 |
| **Compliance (frozen surface)** | DND fail-closed, consent-ledger append, suppression lookup, DPDP retention unchanged | existing suites (`tests/test_stripe_webhook_fail_closed.py`, consent/suppression tests) + voice `agent_tester.py` scorecard | **P0** |

**P0 tests are compliance/availability gates. If a decision cannot be landed without weakening one, the decision is wrong — not the test.**

---

## 6. Documentation structure

### 6.1 Existing docs that must be corrected (named)

| File | What is wrong | Fix |
|---|---|---|
| `AGENTS.md` §2 (lines 22–35) | "`leadgen_app :8000` (Docker)" — the container does not exist; omits `app_vobiz`/`mcp`/`app_staging`/`worker_cli_*`; WAHA "`:3111`" vs running `3002`; omits the systemd authority and the runtime-root split | Replace with a pointer to `deploy/prod-manifest.yml` + the corrected diagram in §2.2 |
| `CLAUDE.md` §2 (mirror, lines ~22–35) | Same wrong text | Mirror the `AGENTS.md` fix |
| `AGENTS.md` §7 landmines + `CLAUDE.md` §7 | The `.env`/systemd lesson (lines 162–167 of the deploy script) is not captured as a landmine; the host-vs-container env-key semantics are unstated | Add: "env keys in `.env` are read **both** by the host process and by containers with **different path semantics** — `LEADGEN_RUNTIME_DATA_DIR` is a container path but the host process reads it as a host path" |
| `AGENTS.md` "Current State" (~line 137) + `CLAUDE.md` | Records prod `/health = 95245ce8` (2026-09-14); prod now serves `cdc28e0d` | Update to the manifest-derived value; make it a **reference to the drift check**, not a hand-copied sha |
| `docs/runbooks/RUNTIME_DATA_CUTOVER.md` | **`STALE`**: says "every deploy is refused" and "21 blocking stores" (2026-07-28). Reality: **0 blockers**, gate **enabled**, marker **VALID**, guard **passes** | Rewrite the status section to reflect 0 blockers; keep the ordering/rollback content (still correct); add the §0 host-root step |
| `docs/runbooks/RUNTIME_DATA_TIER0_MIGRATION.md` | `STALE`/`PARTIAL`: describes PR A as "design, not yet implemented"; the manifest now shows 21 `CUTOVER_COMPLETE` | Reconcile status; keep §5 test matrix and §6 ratchet as the standing contract |
| `docs/ADR-104_DEPLOY_RUNBOOK.md`, `docs/COMPOSE_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_BLUEPRINT.md` | Describe the compose-served topology | Point to the manifest; remove topology restatements |
| `memory/playbooks.md` (deploy sections) | Describes only the compose rollout | Add the host-process restart step (D-3) |
| `scripts/check_skew.sh` | Hardcodes `leadgen_app` (absent) and covers 6 containers | Replace with manifest-driven `prod_drift_check.py` (or make it read the manifest) |
| `deploy/compose/docker-compose.waha.yml:79-83` | Checked-in `127.0.0.1:3111` vs running `0.0.0.0:3002` | Reconcile to reality **or** change the host to match the file; either way the manifest records the truth |

### 6.2 New docs required

1. **`deploy/prod-manifest.yml`** — the versioned, machine-readable production description (D-6). *This is the single source of truth the owner asked for.*
2. **`docs/runbooks/PRODUCTION_TOPOLOGY.md`** — the human-readable companion: the diagram from §2.2, the "who serves what", the runtime-root invariant, and how to run `prod_drift_check.py`.
3. **`docs/adr/ADR-194-single-source-of-truth.md`** — extract of this ADR on acceptance (194 = next free after 193).

---

## 7. Risks & trade-offs

### 7.1 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **D-1/D-3: the restart briefly takes the site down** (import cold start, `RestartSec=5`) | Medium | Medium (customer-facing blip) | Keep the window short; rely on the existing retry loop; deploy outside the TRAI calling window; game-day drill on staging first |
| **D-3 rollback fires spuriously** if `/health` is slow to report the new sha | Medium | Low | Bounded retries (already 12×5 s); raise once for cold imports; make the rollback a *verified* action (restart old sha + re-verify), not a blind one |
| **D-4 Step 0 changes what the live web tier reads** — today it resolves an **empty** root (`/var/lib/leadgen/runtime`, 0 files); pointing it at the populated `/opt/leadgen-runtime` (456 files) changes which bytes consent/suppression/DND lookups see | Medium | **High** (compliance path) | Land Step 0 **alone**, behind a rehearsal on staging with prod-shaped data; verify consent/suppression/DND lookups explicitly before/after; one-line rollback (remove the systemd `Environment=`) |
| **D-4 Step 3 (`:ro`) surfaces un-migrated writers as failures** | **High** (by design) | Medium | It is the point; schedule a window; rollback = flip `:ro` back; have the legacy path's readers audited first (Step 1 ratchet to zero) |
| **D-4 Step 5/6 removing the mount and untracking `data/`** — blast radius | Medium | **High** — the ledgers live there | Do it **last**, after a soak with zero legacy writes; keep the checkout copy on disk (never delete); `git rm --cached` only (files remain); keep the external root + marker as the rollback |
| **D-2 CI gate reddens on legitimate scripts** | Medium | Low | Require mutation **and** prod marker; explicit allowlist with justification |
| **D-6 SSH-based drift check is flaky** | Medium | Low-Medium | Fail-open on connectivity, fail-closed on observed drift; record "unreachable" as its own state, never "clean" |
| **Scope creep into a full IaC rewrite** | Medium | Medium | Manifest + checker only; explicit non-goal in §1.2 |
| **Someone re-arms a retired deploy script from git history** | Medium | Medium | Delete, don't comment; the CI gate catches the re-add; document in the runbook |
| **D-5 removing staging reduces pre-prod coverage** | Medium | Medium | On-demand start, not deletion; keep the compose file; rehearsals become explicit |

### 7.2 Honest blast-radius statement — removing the `./data` mount

This is the highest-risk step in the document and it is deliberately **last**. The mount is the legacy read/write path for **189 tracked files plus untracked-but-authoritative stores** (invoice ledger, consent ledger, WAHA/email/voice suppression, customer registry, ~182 MB of DPDP call recordings — `RUNTIME_DATA_CUTOVER.md:7-13`). Removing it before every writer resolves through the authority does one of two things, both bad: a migrated-but-misconfigured writer **fails closed** (compliance lookups return "block"), or an un-migrated writer silently writes to the container's ephemeral `/app/data` and the write is lost on the next recreate. That is why the order is **resolver/root → ratchet-to-zero → reconcile → `:ro` → soak → remove → untrack**, and why the `:ro` intermediate exists: it converts an invisible divergence into a loud, immediately-attributable failure *before* anything is deleted. **Nothing in this plan deletes a source.** The checkout copy survives every step; the external root + marker is the rollback; only a later, separately-approved decision deletes the checkout copy.

### 7.3 Accepted trade-offs

- We accept a short web-tier interruption per deploy (D-3) in exchange for a **verifiable** deploy. The current alternative — an unverifiable deploy that "usually works" — is what produced the owner's symptom.
- We accept the cost of an on-demand staging rehearsal (D-5) in exchange for prod memory headroom and data isolation.
- We accept a manifest to maintain (D-6) in exchange for the repo being **unable to lie** about prod.
- We keep the systemd host process for now (D-1) rather than the architecturally cleaner container-served model, in exchange for not moving four coupled variables at once onto a live production. The container-served target is recorded, not abandoned.

---

## Appendix A — Evidence ledger (labels)

**`PRODUCTION-PROVEN` (read-only SSH this session, booleans/paths/versions only):**
systemd `leadgen.service` active with the stated `ExecStart`/`WorkingDirectory`/`EnvironmentFile`/`User=root`/`Restart=always`; `ss` shows 3 python PIDs on `127.0.0.1:8000`; no `leadgen_app` container; 47 running containers; image tags `95245ce8` (worker/scheduler/worker-heavy/worker-video/dsh-worker), `d08f07c5` (6 × worker_cli_*), `8b7fd7c3` (app_vobiz, mcp), `28ba5d4e` (app_staging); `/health version=cdc28e0d environment=production uptime≈1 h`; `/opt/leadgen/.env` has `RUNTIME_DATA_CUTOVER_ENABLED=1`, `LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime`, `LEADGEN_RUNTIME_DATA_HOST_DIR=/opt/leadgen-runtime`, `APP_VERSION=cdc28e0d`; marker `/opt/leadgen-runtime/migration/cutover.json` present; `/var/lib/leadgen/runtime` dev `2049:1321522` ≠ `/opt/leadgen-runtime` dev `2049:262673`, neither a symlink nor a bind mount; **file counts: `/var/lib/leadgen/runtime` = 0 (3 dirs: root + empty `boss_autonomy/` + empty `boss_decision_governance/`, tree created 02:40 = process start), `/opt/leadgen-runtime` = 456, `/opt/leadgen/data` = 3974**; `findmnt -T /var/lib/leadgen/runtime` → `TARGET / SOURCE /dev/sda1 ext4` (not a mount point); `boss_autonomy/state.json` absent in `/var/lib/leadgen/runtime` and in `/opt/leadgen/data`, present in `/opt/leadgen-runtime` (136 B, root:root, mtime 2026-09-15 03:55:07); host process (pid 788053) holds no fd under any of the three roots; `/opt/leadgen/data/job_runs.jsonl` 29 MB @03:52; `git ls-files data/` = 189; `git status --porcelain data/` = 0; prod checkout HEAD `cdc28e0d` (2026-09-14 23:22); last `/tmp/dep.log` = `DEPLOYED 867686ae OK` (Sep 13); `/usr/local/sbin/leadgen-deploy-release` present (3506 B); WAHA `0.0.0.0:3002`, relay `0.0.0.0:3110`; `ufw status` = inactive; `/etc/caddy/Caddyfile` `reverse_proxy 127.0.0.1:8000` at :2 and :47. **(SHA/ref correction, team-lead-measured:** real remote `main` = local HEAD = `e77f8e08` via `gh api …/git/ref/heads/main`; local `refs/remotes/origin/main` = `6678405b` is a **stale remote-tracking ref**, not a lineage.)

**`CODE-PRESENT` (files read this session):** `scripts/deploy_vps.sh` (full), `docker-compose.vps.yml` (app/mcp + mount inventory), `app/platform/runtime_data.py` (full), `app/platform/runtime_data_manifest.py` (states + STORES head), `scripts/runtime_data_preflight.py` (`gather`/`deploy_denied`), `scripts/_runtime_data_guard.sh` (full), `scripts/_deploy_parent_delegate.sh`, `scripts/_deploy_surface_inventory.py`, `docs/runbooks/RUNTIME_DATA_CUTOVER.md`, `docs/runbooks/RUNTIME_DATA_TIER0_MIGRATION.md`, `AGENTS.md` §1–§8, `scripts/check_skew.sh`, `scripts/runbook_drift.py`, `deploy/compose/docker-compose.staging.yml`, the 6 duplicate deploy scripts (A4).

**`STALE`:** `AGENTS.md`/`CLAUDE.md` §2 and "Current State" (`95245ce8`, `leadgen_app`); `RUNTIME_DATA_CUTOVER.md` ("every deploy refused", 21 blockers); `RUNTIME_DATA_TIER0_MIGRATION.md` ("design, not yet implemented"); `deploy/compose/docker-compose.waha.yml` port; `scripts/check_skew.sh` container names.

**`UNKNOWN`:** the per-store effect of the §0 **latent** root split on the live web path (fail-closed vs legacy-fallback vs unexercised) — requires per-store request tracing, explicitly **not** claimed here, and the empty host root + absent fds argue against an active split today; the exact reason the systemd process was restarted to `cdc28e0d` outside a canonical deploy; the cause of the stale `refs/remotes/origin/main`; whether `job_runs`/`cadence_runs` are runtime-authoritative or `REBUILDABLE_CACHE`.

## Appendix B — Decisions at a glance

1. **D-1** — Production is served by the **systemd host uvicorn**; declare it the authority, add it to the release. Container-served is the deferred target, gated on parity.
2. **D-2** — `deploy_vps.sh` (+ the delegate helper) is the **only** mutator; convert the 6 live duplicates to delegates, retire the `.bat`s, delete the CI wrapper that bypasses the parent, and **enforce it with a CI gate**.
3. **D-3** — Add the missing `systemctl restart leadgen` + `.env APP_VERSION == VER` + host-verify + rollback, **without** weakening the exact-SHA gate.
4. **D-4** — **Step 0 first:** point the host process at `/opt/leadgen-runtime` so web and workers share one root. Then ratchet → reconcile → `./data:ro` → soak → remove mount → untrack. **Mount removal is last.**
5. **D-5** — Staging must **not** run 24×7 on the prod host, and must **not** share prod data mounts; make it on-demand and isolated; move off-host when affordable.
6. **D-6** — **One versioned `deploy/prod-manifest.yml` + `scripts/prod_drift_check.py`**, wired into CI and the daily owner brief — so the repo cannot lie about prod.

**Highest-leverage change:** **D-4 Step 0** — one systemd `Environment=` line makes the process customers talk to and the workers that write the compliance ledgers resolve to the same directory. It is the cheapest fix in the document and it closes the **latent** split (empty host root, 0 files) that the preflight cannot see because the preflight runs inside a container.

**Biggest risk:** **D-4 Step 5/6 (removing the `./data` mount / untracking the 189 files)** — the ledgers live there; it is why the step is last, why `:ro` precedes it, and why nothing in this plan ever deletes a source.
