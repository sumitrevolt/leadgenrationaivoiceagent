# Documentation-Truth Assessment — LeadGen AI production

**Author:** Docu (多库) · Technical Writer · Engineering Assurance Team
**Date:** 2026-09-15 · **Revision 2** (incorporates team-lead post-audit measurements, points 1–4) · **Scope:** where the repo's documentation describes a system that does not exist
**Method:** read the actual files, grep the actual claims. Production facts (systemd unit config, `is-enabled`, three runtime roots, duplicate `.env` key, remote SHA) were measured by team-lead and are labelled `PRODUCTION-PROVEN`. I did **not** modify, commit, push or deploy anything.
**Companion:** `raw/sre-incident-triage-2026-09-15.md` covers the incident/SEV view; this file covers the *documentation* view.

## Evidence labels used

`PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

> **Single most important finding.** The serving process on `127.0.0.1:8000` is a **host systemd unit** (`leadgen.service`), not a container — and `scripts/deploy_vps.sh` **never restarts it** (`grep -nE "restart|systemctl|leadgen\.service" scripts/deploy_vps.sh` → 3 hits, all comments/echo: lines 163, 175, 243). Meanwhile AGENTS.md — loaded every turn — tells every agent the server is `leadgen_app` in Docker. So the one document that governs agent behaviour is wrong about the one fact that governs whether a deploy takes effect. That is the "ek fix hota hai toh dusra tod jaata hai" loop: an agent updates 5 containers, `/health` is checked against the **un-restarted host process**, and the two disagree.

> **Verified unit (PRODUCTION-PROVEN, team-lead).** `systemctl is-enabled leadgen` → **`enabled`** (not disabled — every doc that says "disabled" is inverted). `systemctl is-active` → `active`. `WorkingDirectory=/opt/leadgen`, **`EnvironmentFile=/opt/leadgen/.env`**, `ExecStart=/opt/leadgen/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --timeout-keep-alive 30`, `Restart=always`, `RestartSec=5`, `User=root`.
> ⚠️ **Quirk to record:** `systemctl show leadgen -p EnvironmentFile` prints **empty** even though the unit sets it — a `systemctl` display quirk that would make a future reader conclude (wrongly) that `.env` is not loaded. Do not trust `systemctl show` for this field; read the unit file.

> **Local git refs lie (methodology truth, PRODUCTION-PROVEN).** `origin/main` is **`e77f8e08`** (`gh api repos/sumitrevolt/leadgenrationaivoiceagent/git/ref/heads/main`). The local `refs/remotes/origin/main` reads `6678405b` and is **stale** (`git fetch --prune origin` prints the update but the ref does not move; cause `UNKNOWN`). **Use `gh api` as authoritative for remote SHAs — never local refs.** Any doc (or reconciler) that quotes a SHA from a local ref inherits this bug.

---

## 1. Divergence register

Grouped by divergence class (DOC-1…DOC-7). Every path/line below was opened and read by me; the "actually true" column is `PRODUCTION-PROVEN` per team-lead verification unless noted.

### DOC-1 — Architecture docs say Docker; production is systemd

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-01 | `AGENTS.md` | L25 (§2 ARCHITECTURE MAP) | `Caddy (host, TLS leadsgenai.in) ──> leadgen_app :8000 (FastAPI, Docker, uvicorn WEB_CONCURRENCY=2, HTTP-only)` | No `leadgen_app` container exists. `127.0.0.1:8000` is served by host `leadgen.service` (`ExecStart=/opt/leadgen/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2`). | Doc `CODE-PRESENT`; reality `PRODUCTION-PROVEN` | Rewrite the edge line to systemd; separate "host server" from "app-image worker containers". |
| D-02 | `CLAUDE.md` | L25 | Byte-identical copy of D-01 | Same as D-01 | Doc `CODE-PRESENT`; reality `PRODUCTION-PROVEN` | Same correction; keep byte-parity with AGENTS.md. |
| D-03 | `README.md` | L43 (§Architecture) | `Caddy ... ──> leadgen_app :8000 (FastAPI)` | Same as D-01 | Doc `CODE-PRESENT`; reality `PRODUCTION-PROVEN` | Replace node with `systemd leadgen (host uvicorn :8000)`. |
| D-04 | `docs/ARCHITECTURE.md` | L20, L150, L156 | `subgraph app [FastAPI leadgen_app :8000]`; `VPS -->\|docker compose build\| IMG[leadgen_app image]`; `Rollback: systemd 'leadgen' disabled but installed` | systemd is **enabled + active** and is the server; Docker serves workers only. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Fix the diagram + invert the rollback note. |
| D-05 | `docs/ARCHITECTURE_BLUEPRINT.md` | L259 | `leadgen_app :8000 (host) / :8080 (in-network) — FastAPI` | Not the serving process; `:8000` is the host unit. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Mark the block as "app-image **worker** containers"; add host server row. |
| D-06 | `docs/infrastructure/DOCKER_RECONCILIATION.md` | L9–21, L70 | §1 "Canonical Production App/Core (11 containers) … `leadgen_app` - API, Web, Dashboard routes (127.0.0.1:8000)"; Verdict: "Parity is ACHIEVED" | `leadgen_app` is not serving; parity verdict was never about the host unit. Doc is dated 2026-08-17. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Remove `leadgen_app` from the serving path; add a "host services" section. |
| D-07 | `docs/runbooks/README.md` | L4, L9 | "(…Docker, `/opt/leadgen`)" · "**App** = Docker container `leadgen_app` :8000" | Host unit serves :8000. | Doc `STALE`; reality `PRODUCTION-PROVEN` | This is the runbooks' *standing facts* header — highest-value single fix. |
| D-08 | `docs/HANDOFF.md` | L29, L31 | container list incl. `leadgen_app :8000`; "systemd `leadgen` = installed-but-**DISABLED**" | Inverted: unit is **enabled and active**. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Fix inventory + invert L31. |
| D-09 | `docs/PROJECT_HANDOFF.md` | L173 | "**App = Docker container `leadgen_app` :8000** … systemd `leadgen` DISABLED (rollback ke liye installed)." | Inverted: unit is enabled/active. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Rewrite. |
| D-10 | `docs/PROJECT_SOP.md` | L86, L77 | "**App:** Docker container `leadgen_app:8000`…"; "Last resort: systemd `leadgen` (installed but disabled) se rollback." | Inverted: unit is enabled/active. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Rewrite. |
| D-11 | `docs/DISASTER_RECOVERY.md` | L95 | "systemd `leadgen` service installed but **disabled** — emergency rollback path." | Inverted: unit is enabled/active and **is** the production path. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Rewrite; DR must restart the unit, not recreate a container. |
| D-12 | `docs/SAAS_INFRA_TRUTH_AND_GAPS_2026_06_15.md` | L165 | "FastAPI monolith (`leadgen_app`, uvicorn `WEB_CONCURRENCY=2`) on a single Hostinger VPS … Docker Compose (~13 containers)" | Host unit + ~47 containers. | Doc `STALE`; reality `PRODUCTION-PROVEN` | Note as historical snapshot; add pointer to SSOT. |
| D-13 | `docs/ROADMAP_2026_Automation_Revenue_Hardening.md` | L4 | "Single Hostinger VPS (Mumbai, **Docker**)" | VPS is multi-tenant and the server is systemd. | Doc `STALE` | Correct the constraint line. |
| D-14 | `docs/HOSTINGER_HERMES_SETUP.md` | L174 | "FastAPI app, Docker pe Hostinger KVM VPS (Mumbai). Containers: `leadgen_app` (:8000)…" | Not serving. | Doc `STALE` | Correct. |
| D-15 | `DAY_0_REVENUE_BASELINE.md` | L56 | "`leadgen_app` (FastAPI web server on port 8080 internal / 8000 host)" | Host unit; also the "5/5 Zero-Skew" block is a stale snapshot. | Doc `STALE` | Correct + date-stamp the snapshot. |
| D-16 | `docs/hermes/ROOT_MEMORY.md` | L1 | "Live system on Hostinger VPS … (Docker: leadgen_app/worker/scheduler)" | Not serving. | Doc `STALE` | Correct. |
| D-17 | `docs/PRODUCTION_CUTOVER.md` | L1, L3, L8, L107–111, L140–143 | Title: "Lean (SQLite + **systemd**) → **Docker** stack"; pre-step `systemctl stop leadgen`; rollback `systemctl start leadgen` | The cutover it plans has been **reversed in production** — systemd serves, Docker runs workers. As written it is an instruction to take prod down. | Doc `STALE` (dangerous) | Banner the file as superseded/reversed; do not delete (rollback history). |
| D-18 | `docs/context/CURRENT_STATE.md` | L341, L350 | "-> docker compose (celery profile) up"; deploy path via containers | Partial — worker topology is right, serving process is wrong. | Doc `PARTIAL` | Add the host-unit step. |

### DOC-2 — The deploy docs omit that the serving process is never restarted

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-19 | `AGENTS.md` / `CLAUDE.md` | L45 (§3) | "Ye script hi CANONICAL hai … SAARE 5 app-image services deploy karti hai (skew rok-ti hai) … aur `/health.version == deployed sha` + per-container skew + smoke verify karke hi OK bolti hai" | Script does `git pull --ff-only` (L277) + `docker compose … up -d --no-deps $ALL_ROLLOUT_SERVICES` (L360–361) + verifies `/health` on `127.0.0.1:8000` (L486). It contains **no `systemctl restart leadgen`** and never sets `APP_VERSION` in `.env` (the `.ENV GUARD` at L162–199 only *validates* the key). `/health.version` = `os.environ.get("APP_VERSION","dev")` read at request time (`app/api/health.py:111`); the unit has `EnvironmentFile=/opt/leadgen/.env`, read at **process start** — so the host process keeps the old value until restarted. The documented success criterion is therefore unachievable by this script alone unless the host unit is restarted out-of-band. | Doc `PARTIAL`; mechanism `UNKNOWN` (needs SRE SSH proof) | Add the missing step/invariant; flag the verify-vs-serving mismatch. |
| D-20 | `docs/PROJECT_SOP.md` | L60–61, L232 | deploy = `docker compose -f docker-compose.vps.yml build app && up -d --no-deps app` (one service) | Not the canonical script (which deploys 5); no systemd restart; contradicts AGENTS.md §3. | Doc `STALE` | Replace with pointer to `deploy_vps.sh` + host restart step. |
| D-21 | `docs/PROJECT_HANDOFF.md` | L269–270 | same single-service docker deploy | Same as D-20. | Doc `STALE` | Same. |
| D-22 | `docs/runbooks/RUNBOOK_PRODUCTION_DEPLOY_FAILURE.md` | L20, L30, L41 vs L27 | Primary path = `docker compose … up -d --no-deps app`; host systemd framed as the exception ("**if running on host instead**, hard-reload") | Host **is** production. L27 already knows the right command (`systemctl stop leadgen; pkill -9 -f uvicorn; …; systemctl start leadgen`) but labels it as the fallback. | Doc `PARTIAL` / inverted | Promote the systemd path to primary. |
| D-23 | `memory/playbooks.md` | L274 | GSC enable: `docker compose -f docker-compose.vps.yml restart leadgen_app leadgen_worker leadgen_scheduler` | `leadgen_app` container does not exist → command fails; and it restarts containers, not the server. | Doc `STALE` | Fix to `systemctl restart leadgen` + recreate workers. |
| D-24 | `memory/playbooks.md` | L~296 (Boss autonomy) | recreate `app worker scheduler`; `docker exec leadgen_app …` canary | `docker exec leadgen_app` fails (no such container). | Doc `STALE` | Fix exec target. |
| D-25 | Deploy-script inventory (repo) | `scripts/*` | "the deploy procedure" is described in ≥5 docs with ≥3 different commands; 9 competing scripts exist (`vps_pitch_deploy.sh`, `_mcp_deploy_remote.sh`, `vps_deploy_dashboard.py`, `vps_build_deploy.py`, `vps_deploy_call_learn.bat`, `vps_force_pull.py`, `vps_deploy_workflow_fix.py`, `scripts/legacy/*.bat`). Only `vps_deploy_call_learn.bat` is referenced by any doc (`docs/DND_NCPR_COMPLIANCE_ADR_2026-09-07.md`, `progress.md`). `app/platform/runtime_data.py` L8–10 documents that `_mcp_deploy_remote.sh` and `vps_pitch_deploy.sh` run **`git reset --hard origin/main`** — a data-destroying alternative to the canonical script. | "The deploy procedure" has no single documented owner. | Doc `CODE-PRESENT` | One deploy authority doc; archive/annotate the 9 scripts. |

### DOC-3 — Runtime-data docs vs reality (partial cutover; three roots, two live)

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-26 | `docs/runbooks/RUNTIME_DATA_CUTOVER.md` | L19–25, L42, L65, L98–104 | State machine: until every store reaches `CUTOVER_COMPLETE`, "live writers do **not** move"; the checkout copy stays authoritative; a root mounted into only some services "is a split brain, not a migration". No doc claims completion — but the doc implies the pre-cutover state (writers still on the checkout). | **Both roots are actively written**: `/opt/leadgen-runtime/automation/job_runs.jsonl` 49 MB @03:47 **and** `/opt/leadgen/data/job_runs.jsonl` 29 MB @03:46. `docker-compose.vps.yml` mounts **both** into every app service (13 pairs: L96/97, 160/161, 362/363, 423/424, 456/457, 489/490, 522/523, 555/556, 588/589, 622/623, 688/689, 749/750, 915/916). Root sizes: `/opt/leadgen/data` = **3974 files**, `/opt/leadgen-runtime` = **456 files**. | Doc `PARTIAL`; live roots `PRODUCTION-PROVEN` | Add a "current live state" block: which root is authoritative per store; the design doc must not be read as current-state. |
| D-27 | `docs/runbooks/RUNTIME_DATA_CUTOVER.md` | L7 | "**186 files under `data/` are git-tracked**" (2026-07-28) | `git ls-files data/` = **189** today; `.gitignore:151 = data/*` does not apply to tracked files. | Doc `STALE` | Refresh the count; state that the number is a snapshot. |
| D-28 | `app/platform/runtime_data.py` | L1–14 (module docstring) | "Mutable production state **currently lives at** `/opt/leadgen/data` — inside the Git checkout, bind-mounted into all five application services" | Both roots are mounted and written; the docstring presents a single-root LEGACY state. | Doc `PARTIAL`; reality `PRODUCTION-PROVEN` | Note the dual-mount reality + point at the manifest. |
| D-29 | `app/platform/runtime_data_manifest.py` | L1–16, `MANIFEST_VERSION="2026-07-26.1"` | "Every `current_authority` and `production_activity` value below is backed by read-only production evidence (… taken **2026-07-26**)" | Manifest is ~7 weeks stale while money/compliance stores (invoices, consent, suppression) may have moved. | Doc `STALE` | Re-derive evidence; bump version; gate staleness. |
| D-41 | (no document) | — | Nothing documents the **host** runtime root | **`/var/lib/leadgen/runtime` = 0 files** (two empty subdirs created at process start 02:40); `findmnt` shows it is a plain directory on `/`, **not a mount point**. This is the value the **host** systemd process resolves from `.env` (`LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime`), while containers bind `${LEADGEN_RUNTIME_DATA_HOST_DIR:-/opt/leadgen-runtime}` → `/var/lib/leadgen/runtime`. **Same env value, two different physical directories depending on host vs container.** | `PRODUCTION-PROVEN`; undocumented | This is the sharpest single SSOT violation: document it, and reconcile the two roots before any cutover claim. |

### DOC-4 — WAHA docs vs running config

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-30 | `scripts/WAHA_WATCHDOG.md` | L29, L48 | "the checked-in WAHA compose publishes `127.0.0.1:3111:3000`"; default `WAHA_WATCHDOG_URL = http://127.0.0.1:3111`; "defaults match this VPS layout" | Running container `leadgen_waha` publishes **`0.0.0.0:3002->3000`**; `ufw status` = **inactive**. The checked-in compose does **not** match the running container. `WAHA_WATCHDOG_URL` **is** set in `/opt/leadgen/.env` (override live), but `WAHA_WATCHDOG_LOG_FILE` is **absent** (default used). Session currently `SCAN_QR_CODE` ("waiting for owner scan"). | Doc `STALE`; reality `PRODUCTION-PROVEN` | Correct the "defaults match this VPS" claim; record the real port + the env vars actually set. |
| D-31 | `deploy/compose/docker-compose.waha.yml` | L79–83 | `ports: - "127.0.0.1:3111:3000"`, comment "localhost only, 3111 (NOT 3000…)" | Running bind is `0.0.0.0:3002`. Checked-in compose ≠ running config (config drift, not just doc drift). | Doc `STALE`; reality `PRODUCTION-PROVEN` | Reconcile compose to reality (or reality to compose) and add an exposure note. |

### DOC-5 — Operator-facing text embedded in code that is wrong

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-32 | `app/platform/runtime_data_ratchet.py` | L149–150 (`format_failures`) | `action: classify the store (allowlist entry with owner, migration_tier, review_condition) **or provide an evidence-backed exclusion**` | No exclusion mechanism exists: `grep -rnE "exclusion\|exclude\|EXCLUDE\|exempt\|EXEMPT"` over `scripts/runtime_data_path_scan.py`, `app/platform/runtime_data_allowlist.py`, `app/platform/runtime_data_manifest.py` → **0 hits**. `scripts/runtime_data_path_scan.py:10–12`: "There is deliberately no `--accept-current-state`, no auto-update and no bypass variable". | Doc-in-code `CODE-PRESENT` (false); mechanism absent `CODE-PRESENT` | Replace the string (draft in §3, C-5). |

### DOC-6 — Multi-tenant host and staging-on-prod are undocumented

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-33 | `AGENTS.md` / `CLAUDE.md` | L20 (§1) | "single Hostinger VPS Mumbai" | True but **incomplete**: the VPS also runs `buzz-prod-minio-1`, `buzz-prod-postgres-1`, `buzz-prod-redis-1`, `buzz-prod-relay-1`, `tilakgram-meilisearch`, `tilakgram-minio`, `livekit` (47 containers total). | Doc `PARTIAL`; reality `PRODUCTION-PROVEN` | State "shared host — do not touch non-leadgen workloads"; add ownership note. |
| D-34 | (no document) | — | Nothing documents a staging stack on prod | `leadgen_app_staging` (image `28ba5d4e`, Up 3 days), `leadgen_db_staging`, `leadgen_redis_staging` have run ~2 weeks **sharing production's data mounts**. | `PRODUCTION-PROVEN`; undocumented | New section: staging lifecycle + mount isolation. |
| D-35 | (no document) | — | Nothing documents the host systemd unit inventory | `tmux-leadgen.service` = **failed**; `leadgen-calls.service` = **inactive dead**; `leadgen-omni-bridge.service` = active; `leadgen.service` = enabled/active. No runbook. | `PRODUCTION-PROVEN`; undocumented | New runbook (see §4 gap #3). |
| D-36 | `docs/infrastructure/DOCKER_RECONCILIATION.md` | L56–59 | "Staging Environment (3 containers) … `leadgen_app_staging` (Port 8001)" | Does not flag that staging shares prod data mounts, nor that `leadgen_app` is not serving. | Doc `PARTIAL` | Add isolation status. |

### DOC-7 — Security doc describes infrastructure that does not exist

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-38 | `SECURITY.md` (root) | §Infrastructure Security L45–52 · §Data Security L55 | "VPC with private subnets" · "Database with private IP only" · **"Secrets in Google Secret Manager"** · "Workload Identity for CI/CD" · "Encryption at rest (Cloud SQL)" · "Non-root container user" · "Container image scanning" | Production is a **single Hostinger VPS (Mumbai)** with a Postgres container, secrets in `/opt/leadgen/.env` (gitignored), host systemd `User=root`. No GCP, no VPC, no Cloud SQL, no Workload Identity, no Secret Manager. | Doc `STALE` (security-relevant) | **High priority.** Replace the checkbox block with the real posture; a reader could "fix" the compliance posture toward a stack that is not deployed, or trust protections that do not exist. |

### SSOT-integrity divergences

| # | Document (path) | Line/§ | What it claims | What is actually true | Evidence label | Correction needed |
|---|---|---|---|---|---|---|
| D-37 | `docs/context/PRODUCTION_TRUTH.md` | L1–45 | Header "PRODUCTION_TRUTH — **live-proven only**"; prod SHA `d32a4934` (2026-07-20); "`PLATFORM_DIAL_DAILY` **HARD OFF**" | Live `/health` = `95245ce8` (2026-09-14); `PLATFORM_DIAL_DAILY=1` (per AGENTS.md §5 L64). This file is named as the facts SSOT and is ~8 weeks stale with `PRODUCTION-PROVEN` labels attached to dead facts. | Doc `STALE` | Promote to the machine-checked SSOT (§2) and stop hand-editing labels. |
| D-39 | `/opt/leadgen/.env` (config) | — | — | `.env` contains **`APP_ENV=production` twice**. `EnvironmentFile` is last-wins, so currently benign — but a duplicate-key hazard: a future edit to the first line silently does nothing. | `PRODUCTION-PROVEN`; config defect | De-duplicate; add a config-lint (single key per name) to the deploy gate. |
| D-40 | local git refs | `refs/remotes/origin/main` | Any doc quoting a SHA from a local ref | `origin/main` = **`e77f8e08`** (`gh api`); local `origin/main` reads `6678405b` and is **stale** (fetch prints the update but the ref does not move; cause `UNKNOWN`). **Local refs lie; the API does not.** | `PRODUCTION-PROVEN` | Rule: remote SHAs come from `gh api` only. Reconciler must not read local refs. |

**Count: 41 divergences** (DOC-1: 18 · DOC-2: 7 · DOC-3: 5 · DOC-4: 2 · DOC-5: 1 · DOC-6: 4 · DOC-7: 1 · SSOT-integrity: 3).

### Top 5 by impact

1. **D-19** — `AGENTS.md`/`CLAUDE.md` §3: deploy is documented as complete and skew-safe while `deploy_vps.sh` never restarts the process that serves `:8000`. This is the exact "fix one, break another" mechanism.
2. **D-01/D-02** — the architecture map every agent loads each turn says the server is a Docker container. Everything downstream of it is built on a false premise.
3. **D-07** — `docs/runbooks/README.md` "standing facts" (the header every incident runbook inherits) says "App = Docker container `leadgen_app`". During an outage an operator will recreate the wrong thing.
4. **D-38** — `SECURITY.md` documents a GCP posture (Secret Manager, VPC, Cloud SQL, Workload Identity) that does not exist on a single Hostinger VPS. Security-relevant: it can drive a wrong "fix" and it overstates protections.
5. **D-26/D-41** — runtime-data docs describe a single-authority state machine; production has **three roots** (two live, one empty) over money/compliance stores, and the host app's runtime root is an empty directory.

*(D-30/D-31 — WAHA docs/compose point at `3111`, running container is `0.0.0.0:3002` with `ufw` inactive — is a close 6th and is revenue-relevant.)*

---

## 2. The single source of truth proposal

**The owner's mandate is "one authoritative description of production". The correct artifact is not a prose doc and not `AGENTS.md`** (which is loaded every turn and must stay lean, and which is a byte-copy of `CLAUDE.md`, so facts written there are double-maintained and drift).

**Proposal — one versioned machine-checkable facts file + one reconciler + a thin pointer:**

1. **`infra/prod_manifest.json`** — the SSOT (versioned, schema-checked, no prose):
   - `host.services[]`: name (`leadgen.service`), `is_enabled` (asserted `enabled`), `is_active` (`active`), bind (`127.0.0.1:8000`), `exec_start`, `working_directory`, **`environment_file` (`/opt/leadgen/.env`)**, `restart_policy`.
   - `host.other_services[]`: `leadgen-calls` (inactive/dead), `tmux-leadgen` (failed), `leadgen-omni-bridge` (active).
   - `edge`: Caddyfile path, upstream.
   - `containers[]`: `{name, compose_service, role, image_tag, serves_traffic: bool}` — with `leadgen_app.serves_traffic: false` and an explicit **assertion that `docker exec leadgen_app` fails** (no such container).
   - `data.roots[]`: `{path, files, mounted_into[], authoritative, on_host: bool}` — including `/var/lib/leadgen/runtime` (0 files, not a mount) vs `/opt/leadgen-runtime` (456 files) vs `/opt/leadgen/data` (3974 files).
   - `deploy`: `{authority: scripts/deploy_vps.sh, restarts_serving_process: false, sets_app_version_in_env: false}`.
   - `config.env_keys`: `{name: [occurrences]}` — to catch the duplicate `APP_ENV`.
   - `exposure[]`: `{port, bind, firewall, ufw_state}`.
   - `shas`: `{remote_main: <gh api value>}` — remote SHAs from `gh api` only.
   - Every value carries `evidence_label` + `verified_at`.
   Replace the hand-edited `docs/context/PRODUCTION_TRUTH.md` with a pointer to this (link, don't duplicate).

2. **`scripts/prod_truth.py`** — the reconciler / drift detector. Reads the manifest, probes live, exits non-zero on any mismatch. **Hard requirements from team-lead:**
   - **Remote SHAs from `gh api` only — never local refs** (else it inherits the exact bug it exists to catch, D-40).
   - **Asserted facts it MUST check:** `systemctl is-enabled leadgen` = `enabled`, `systemctl is-active leadgen` = `active`, the unit's **`EnvironmentFile` value** (read from the unit file, **not** `systemctl show` — see the quirk note), and **`docker exec leadgen_app` fails**.
   - Also: `ss -ltnp` bind for `:8000`, `docker ps` inventory, `/health` version + `environment`, the three data roots' file counts, duplicate env keys, and `ufw status`.
   Wire it into (a) the `deploy_vps.sh` gate path and (b) the existing `*/10` `vps_selfheal.sh` cron, alerting via the existing `ops_alerts` → ntfy lane. Add a monthly prod probe as the backstop. Drift becomes a *machine* finding, not a human one.

3. **`AGENTS.md` keeps ≤5 lines**: a pointer to the manifest + the one invariant that must never be violated: *"Production `:8000` is served by the host `leadgen.service` unit (enabled, `EnvironmentFile=/opt/leadgen/.env`); `deploy_vps.sh` does NOT restart it and does NOT set `APP_VERSION` in `.env` — restart the unit after any app-code deploy."*

**Who updates it:** the person who performs the deploy updates `infra/prod_manifest.json` in the same change; the reconciler is the enforcement, so an un-updated manifest fails loudly instead of quietly misleading. **How drift is detected:** `prod_truth.py` in CI + cron + the deploy gate, with the monthly probe as a backstop.

---

## 3. Corrections to write now (highest impact — proposed, NOT applied)

### C-1 · `AGENTS.md` L25 and `CLAUDE.md` L25 (apply to both, keep byte-parity)

Before:
```text
Internet ──> Caddy (host, TLS leadsgenai.in) ──> leadgen_app :8000  (FastAPI, Docker, uvicorn WEB_CONCURRENCY=2, HTTP-only)
```
After:
```text
Internet ──> Caddy (host, TLS leadsgenai.in) ──> 127.0.0.1:8000  (FastAPI)
              served by HOST systemd unit `leadgen.service` (enabled, EnvironmentFile=/opt/leadgen/.env)
              (uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2; NOT a container)
                                                    ├── leadgen_worker / leadgen_scheduler / leadgen_worker_heavy / leadgen_worker_video
                                                    │   = app-IMAGE containers (workers only — they do not serve HTTP)
```
(Keep the remaining `├──` rows unchanged; only the edge line and the "who serves HTTP" fact change.)

### C-2 · `AGENTS.md` L45 and `CLAUDE.md` L45 (§3 deploy bullet)

Before (excerpt):
```text
Ye script hi CANONICAL hai … SAARE 5 app-image services deploy karti hai (skew rok-ti hai) … aur `/health.version == deployed sha` + per-container skew + smoke verify karke hi OK bolti hai
```
After:
```text
Ye script hi CANONICAL hai … SAARE 5 app-image services (worker/scheduler/worker-heavy/worker-video) + DSH worker deploy karti hai (skew rok-ti hai) aur per-container skew + smoke verify karti hai.
⚠️ YEH SCRIPT SERVING PROCESS KO RESTART NAHI KARTI aur .env me APP_VERSION bhi SET NAHI karti (`.ENV GUARD` sirf validate karta hai).
Prod :8000 ko host `leadgen.service` serve karta hai (EnvironmentFile=/opt/leadgen/.env, process-start pe padhta hai).
App-code change ke baad `systemctl restart leadgen` ZAROORI hai, warna /health purana APP_VERSION dikhata rahega jabki containers naye hain.
```

### C-3 · `docs/runbooks/README.md` L8–L9 ("Standing facts" — inherited by every runbook)

Before:
```text
- **App** = Docker container `leadgen_app` :8000 (`docker compose -f docker-compose.vps.yml`).
```
After:
```text
- **App** = HOST systemd unit `leadgen.service` (enabled; uvicorn, `127.0.0.1:8000`; `EnvironmentFile=/opt/leadgen/.env`) — NOT a container.
  Restart with `systemctl restart leadgen`; verify `curl -s 127.0.0.1:8000/health`. The app-IMAGE containers
  (`leadgen_worker`, `leadgen_scheduler`, `leadgen_worker_heavy`, `leadgen_worker_video`) run jobs only and do not serve HTTP.
```

### C-4 · `docs/PROJECT_SOP.md` L86 and L77

Before (L86):
```text
- **App:** Docker container `leadgen_app:8000` (`docker-compose.vps.yml`, restart unless-stopped). Caddy host-proxy `127.0.0.1:8000`.
```
After:
```text
- **App:** HOST systemd unit `leadgen.service` (enabled; uvicorn `127.0.0.1:8000`, `Restart=always`, `EnvironmentFile=/opt/leadgen/.env`). Caddy host-proxy `127.0.0.1:8000`.
  Worker containers (`leadgen_worker`/`scheduler`/`worker_heavy`/`worker_video`) are separate and serve no HTTP.
```
Before (L77):
```text
| **App down post-deploy** | `docker compose logs app --tail=100`; agar bad image → previous image se `up -d`. Last resort: systemd `leadgen` (installed but disabled) se rollback. |
```
After:
```text
| **App down post-deploy** | `journalctl -u leadgen -n 100`; unit down → `systemctl restart leadgen`. Agar bad app-image → previous image se worker recreate + `systemctl restart leadgen`. |
```

### C-5 · `app/platform/runtime_data_ratchet.py` L149–150 (DOC-5 — operator-facing string; explicit request)

Before:
```python
"  action: classify the store (allowlist entry with owner, migration_tier, "
"review_condition) or provide an evidence-backed exclusion"
```
After:
```python
"  action: classify the store (allowlist entry with owner, migration_tier, "
"review_condition). There is NO exclusion/exemption path by design — an "
"undeclared writer must be classified or made to use the resolver."
```
(Do not weaken the gate: this removes a promised bypass that never existed; it adds none.)

### C-6 · `scripts/WAHA_WATCHDOG.md` L48 (+ note in `deploy/compose/docker-compose.waha.yml` L79–83)

Before (L48, excerpt):
```text
| `WAHA_WATCHDOG_URL` | `http://127.0.0.1:3111` | WAHA base URL. The default is the **host-published** port from the checked-in WAHA compose (`127.0.0.1:3111:3000`) … **If your VPS maps WAHA to a different host port, set this variable** |
```
After:
```text
| `WAHA_WATCHDOG_URL` | `http://127.0.0.1:3111` | WAHA base URL. ⚠️ The checked-in compose publishes `127.0.0.1:3111:3000`, but the RUNNING container on this VPS publishes
`0.0.0.0:3002->3000` — so the literal default is WRONG for prod. `WAHA_WATCHDOG_URL` IS set in `/opt/leadgen/.env` and that value is authoritative.
`WAHA_WATCHDOG_LOG_FILE` is NOT set (default used). Reconcile compose↔running before trusting either. |
```
Plus a compose comment: the checked-in bind does not match the running container, and `ufw` is inactive → the `0.0.0.0` bind is externally reachable.

### C-7 · `SECURITY.md` (root) §Infrastructure Security / §Data Security (D-38)

Before (L45–52 + L55, excerpts):
```text
- [x] VPC with private subnets
- [x] Database with private IP only
- [x] Secrets in Google Secret Manager
- [x] Workload Identity for CI/CD
- [x] Container image scanning
- [x] Non-root container user
…
- [x] Encryption at rest (Cloud SQL)
```
After:
```text
- [x] Single Hostinger VPS (Mumbai); Caddy host reverse-proxy with TLS leadsgenai.in
- [x] Postgres in a Docker container, not exposed publicly; reachable via PgBouncer :6432
- [x] Secrets in /opt/leadgen/.env (gitignored, never committed) — NOT a managed secret store
- [x] Host serving process runs as root under systemd (`leadgen.service`) — see infra/prod_manifest.json
- [ ] Container image scanning / Workload Identity — NOT in place (do not claim)
…
- [x] Encryption in transit (TLS); Postgres volume on host disk (encryption-at-rest not independently verified)
```
(Do not weaken any compliance statement — the TRAI/DND/consent lines at L57–58 are correct and stay.)

---

## 4. Runbook gaps

Operational procedures with **no runbook at all** (checked against `docs/runbooks/README.md`'s index of 7). Ordered by priority:

1. **How to restart the serving process after a deploy** *(highest — currently impossible to look up; the canonical script does not do it)*.
   Outline: `deploy_vps.sh` finished / app code changed → note it **never** restarts the host unit and **never** sets `APP_VERSION` in `.env` (`.ENV GUARD` only validates) → set `APP_VERSION=<sha>` in `/opt/leadgen/.env` if needed → `systemctl restart leadgen` → verify `curl -s 127.0.0.1:8000/health` reports the deployed SHA → confirm worker containers unaffected → rollback = previous SHA in `.env` + restart.
2. **How to re-link the WhatsApp (WAHA) session after a logout** *(live, revenue-blocking — WAHA is currently `SCAN_QR_CODE`, "waiting for owner scan")*.
   Outline: detect (`data/wa_health_check.json` `state=logged_out`, `actionable=owner_scan_qr`) → confirm watchdog running (`pgrep -af waha_watchdog`) → open QR via `/api/wa/selfhost/qr` (not the host port) → owner scans → verify `state=working` + a sweep `sent:n/n` → note the `0.0.0.0:3002`/`ufw`-inactive exposure.
3. **Host systemd unit inventory & triage.**
   Outline: `systemctl list-units 'leadgen*'` → `leadgen.service` (enabled/active, serves :8000) · `leadgen-calls.service` (inactive/dead) · `tmux-leadgen.service` (failed) · `leadgen-omni-bridge.service` (active) → what each is for, safe enable/disable, which are load-bearing. Note the `systemctl show -p EnvironmentFile` quirk.
4. **Multi-tenant host safety.**
   Outline: what else runs on the VPS (`buzz-prod-*`, `tilakgram-*`, `livekit`) → port ownership map → "never `docker system prune -a` / `compose down` without project scoping" → how to list only leadgen resources.
5. **Staging stack lifecycle & isolation.**
   Outline: identify `leadgen_app_staging`/`leadgen_db_staging`/`leadgen_redis_staging` → prove it does **not** mount prod `data/` → start/stop/verify → `APP_VERSION` fail-closed (`${APP_VERSION:?}`) → cleanup.
6. **Runtime-data root authority (which root wins today).**
   Outline: three roots (`/opt/leadgen/data` 3974 files, `/opt/leadgen-runtime` 456, `/var/lib/leadgen/runtime` 0 and not a mount) → how to tell which store resolves where (`runtime_data_authority.authority_mode()`) → never hand-copy between roots → escalate to the cutover doc.
7. **Deploy-script authority.**
   Outline: `deploy_vps.sh` is canonical → the 9 siblings (`vps_pitch_deploy.sh`, `_mcp_deploy_remote.sh`, …) and why two of them (`git reset --hard origin/main`) are unsafe → how to archive/annotate.
8. **Disk & image/build-cache retention.**
   Outline: the deploy script's disk guard (warn 80% / hard 90%) → lineage-aware retention → `docker builder prune` manual procedure when the guard blocks a deploy.

---

## 5. AGENTS.md lean-ness check

`AGENTS.md` states its own rule (L3): *"Token discipline: Yeh file har turn load hoti hai — lean rakho. Dated history → `docs/SESSION_LOG.md` … Deep knowledge → `memory/` … Build/incident logs YAHAN mat likho."* The file is **37,962 bytes / 151 lines** and violates that rule in several places:

| Location | Problem | Should move to |
|---|---|---|
| `## Current State` L111–151 (~41 lines, over its own "max 40") | "Last 3 significant decisions" actually lists **~13** dated ADRs (2026-07-23 … 2026-08-14) with full detail (ADR-159/164/165/167/168/177/179/181/182/183). Dated history. | `docs/SESSION_LOG.md` + `memory/decisions.md`; keep ≤3 bullets here. |
| L122–124, L135–137 | Buzz/relay/Owner-OS/DSH narrative paragraphs — deep detail, dated. | `memory/decisions.md` / `docs/integrations/BUZZ_LOCAL_RELAY.md`. |
| §7 KNOWN LANDMINES L71–84 | ~14 landmines, each a dated postmortem (2026-07-14, 07-18, 09-05…). AGENTS.md itself points at `memory/incidents.md` for postmortems. | Keep the invariant one-liner; full postmortem → `memory/incidents.md`. |
| §3 deploy bullet L45 | Long operational procedure in the always-loaded file. | Short pointer + the missing-restart invariant; full runbook → `docs/runbooks/`. |
| L140–145 "LINEAGE WARNING", L147–151 "TRUTH GATE" | Two large dated alert blocks. | `docs/context/PHASE0_BASELINE.md` (already cited) — leave a 1-line pointer. |
| Whole file | `AGENTS.md` and `CLAUDE.md` are **byte-identical (both 37,962 B)**; the re-sync rule (L94) is manual. | Single source + a copy/symlink step, or a test that asserts byte-parity, to remove dual-maintenance drift. |

**Keep in AGENTS.md** (genuinely always-needed): §5 CRITICAL INVARIANTS (compliance gates), the §2 architecture map **once corrected**, the canonical-command names, and the §6 Definition of Done. Everything dated or deep belongs one tier down.

---

## Appendix — files read for this assessment

`AGENTS.md` · `CLAUDE.md` · `README.md` · `SECURITY.md` · `DAY_0_REVENUE_BASELINE.md` · `scripts/deploy_vps.sh` · `scripts/WAHA_WATCHDOG.md` · `scripts/waha_watchdog.py` · `scripts/runtime_data_path_scan.py` · `app/platform/runtime_data_ratchet.py` · `app/platform/runtime_data.py` · `app/platform/runtime_data_manifest.py` · `app/api/health.py` · `app/main.py` · `docker-compose.vps.yml` · `deploy/compose/docker-compose.waha.yml` · `docs/ARCHITECTURE.md` · `docs/ARCHITECTURE_BLUEPRINT.md` · `docs/infrastructure/DOCKER_RECONCILIATION.md` · `docs/HANDOFF.md` · `docs/PROJECT_HANDOFF.md` · `docs/PROJECT_SOP.md` · `docs/DISASTER_RECOVERY.md` · `docs/PRODUCTION_CUTOVER.md` · `docs/SAAS_INFRA_TRUTH_AND_GAPS_2026_06_15.md` · `docs/ROADMAP_2026_Automation_Revenue_Hardening.md` · `docs/HOSTINGER_HERMES_SETUP.md` · `docs/hermes/ROOT_MEMORY.md` · `docs/context/CURRENT_STATE.md` · `docs/context/PRODUCTION_TRUTH.md` · `docs/SYSTEM_TRUTH_MAP.md` · `docs/runbooks/README.md` · `docs/runbooks/RUNTIME_DATA_CUTOVER.md` · `docs/runbooks/RUNTIME_DATA_TIER0_MIGRATION.md` · `docs/runbooks/RUNBOOK_PRODUCTION_DEPLOY_FAILURE.md` · `memory/playbooks.md` · `.gitignore`.

**Production measurements incorporated (team-lead, PRODUCTION-PROVEN):** `leadgen.service` unit file + `is-enabled`/`is-active`; three runtime roots with file counts (`/opt/leadgen/data` 3974 · `/opt/leadgen-runtime` 456 · `/var/lib/leadgen/runtime` 0, not a mount); duplicate `APP_ENV=production` in `.env`; `origin/main` = `e77f8e08` via `gh api` (local ref `6678405b` stale).
