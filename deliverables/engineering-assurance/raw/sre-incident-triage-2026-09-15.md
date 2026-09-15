# SRE Incident Triage — LeadGen AI Production (`leadsgenai.in`)

**Author:** Rex (雷克斯) · SRE Engineer, Engineering Assurance Team
**Date:** 2026-09-15 (evidence window ≈ 03:20–03:53 UTC / 08:50–09:23 IST)
**Host:** single Hostinger VPS, Mumbai · `72.61.245.204`
**Status:** **TRIAGE ONLY — no fix is claimed complete. Nothing was changed.**
**Scope:** evidence E1–E7 supplied by the team lead + independent read-only SSH re-verification by this author.

> **Method note.** Every fact below carries an evidence label. Labels used:
> `PRODUCTION-PROVEN` (observed on the live host) · `CODE-PRESENT` (exists in the repo/checked-in config) ·
> `TEST-PROVEN` (covered by a passing test) · `LOCAL-ONLY` (working tree only, not deployed) ·
> `PARTIAL` (partially established) · `STALE` (known outdated) · `UNKNOWN` (cannot determine).
> Where the team lead's evidence and my own probe agree, I mark it `PRODUCTION-PROVEN` and say "re-verified".
> Where I could not confirm, I say so instead of guessing.

---

## 0. Verification performed by this author

I re-ran read-only probes over SSH (no mutations). Results that **re-verified** the supplied evidence and **new** facts I added:

| Check | Result | Label |
|---|---|---|
| `ss -ltnp` on :8000 | `127.0.0.1:8000` held by `python` PIDs 847346 / 788346 / 788053 (parent + 2 workers) — **not** a container | PRODUCTION-PROVEN (re-verified) |
| `ss -ltnp` on WAHA/relay | `0.0.0.0:3002` **and** `[::]:3002` (dual-stack, public) via `docker-proxy`; `0.0.0.0:3110` + `[::]:3110` (public) | PRODUCTION-PROVEN (re-verified, **+IPv6 exposure**) |
| `:3111` | nothing listening (checked-in compose port unused) | PRODUCTION-PROVEN (new) |
| `docker ps` image tags | 5 distinct SHAs across leadgen services (`cdc28e0d` host, `95245ce8`, `d08f07c5`, `8b7fd7c3`, `28ba5d4e`) | PRODUCTION-PROVEN (re-verified) |
| `leadgen_waha` uptime | **`Up 34 minutes`** at 09:21 IST → container (re)started ≈ **08:47 IST / 03:17 UTC** | PRODUCTION-PROVEN (**new**) |
| `wa_health_check.json` | `waha_status: SCAN_QR_CODE`, `engine.state: UNPAIRED`, `me: null` | PRODUCTION-PROVEN (re-verified) |
| `waha_watchdog.log` | continuous `SCAN_QR_CODE — waiting for owner scan`, every 60 s through 09:22 IST | PRODUCTION-PROVEN (re-verified) |
| `/health` | `version cdc28e0d`, `environment production`, `uptime 1h 40m`, `dsh_runtime_enabled true`, `dsh_allowlist ["jiya_makeover"]` | PRODUCTION-PROVEN (re-verified, **+DSH flags**) |
| host `git HEAD` / `origin/main` | both `cdc28e0d` → the host's **remote-tracking ref is STALE** (real remote `main` = `e77f8e08`) | PRODUCTION-PROVEN (**new**) |
| dual runtime roots | **both** actively written: `/opt/leadgen/data/job_runs.jsonl` 29,222,849 B @03:52 **and** `/opt/leadgen-runtime/automation/job_runs.jsonl` 49,323,671 B @03:51 | PRODUCTION-PROVEN (re-verified) |
| `git ls-files data/` on host | **189** tracked files inside the checkout (`.gitignore:151 data/*` does not apply to tracked files) | PRODUCTION-PROVEN (re-verified) |
| `systemctl list-units` | `leadgen.service` active · `tmux-leadgen.service` **failed** · `leadgen-calls.service` inactive/dead · `leadgen-omni-bridge.service` active | PRODUCTION-PROVEN (re-verified) |
| `ufw status` | `Status: inactive` | PRODUCTION-PROVEN (re-verified) |
| `.env` keys (presence only) | `LEADGEN_RUNTIME_DATA_HOST_DIR` present · `LEADGEN_RUNTIME_DATA_DIR` present · `WAHA_WATCHDOG_URL` present · `WAHA_WATCHDOG_LOG_FILE` **absent** · `APP_ENV` appears **2×** | PRODUCTION-PROVEN (re-verified, **+duplicate APP_ENV**) |
| `scripts/deploy_vps.sh` `restart\|systemctl\|leadgen.service` | exactly **3** hits, all comments/echo (L163, L175, L243) — **no `systemctl restart`** | CODE-PRESENT (re-verified) |
| `deploy/compose/docker-compose.waha.yml:83` | `- "127.0.0.1:3111:3000"` — differs from the running `0.0.0.0:3002` | CODE-PRESENT (re-verified) |
| `docker-compose.vps.yml` data mounts | every app service mounts **both** `./data:/app/data` and `${LEADGEN_RUNTIME_DATA_HOST_DIR:-/opt/leadgen-runtime}:/var/lib/leadgen/runtime` | CODE-PRESENT (re-verified) |
| `scripts/runtime_data_preflight.py` | docstring documents "6 × `git reset --hard`, 1 × `git clean -fd`, 8 × `git pull`"; L116 "`git reset --hard` would destroy it" | CODE-PRESENT (re-verified) |
| `leadgen.service` unit | `EnvironmentFile=/opt/leadgen/.env`; `ExecStart=…uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --timeout-keep-alive 30`; `Restart=always`; `User=root`; mtime Jun 9 08:25; **no drop-ins** | PRODUCTION-PROVEN *(team lead; not re-probed by me)* |
| `/opt/leadgen/.env:573` | `APP_VERSION=cdc28e0d` | PRODUCTION-PROVEN *(team lead)* |
| `/proc/788053/environ` | `APP_ENV=production`, `APP_VERSION=cdc28e0d` — identical to `.env`; only possible source is `EnvironmentFile` (`systemctl show … -p Environment` empty; no drop-in; `app/main.py` has **no** `load_dotenv`) | PRODUCTION-PROVEN *(team lead)* |
| `app/api/health.py:111` | `"version": os.environ.get("APP_VERSION","dev")` → read from `os.environ`, **frozen at process start** | CODE-PRESENT |

**New co-tenant fact:** the host also runs `leadgen-freeswitch` (telephony media server) alongside `buzz-prod-*` (minio/postgres/redis/relay), `tilakgram-*`, `livekit`, `leadgen_litellm`, and a ~17-container monitoring stack (prometheus, grafana, loki, tempo, alertmanager, gatus, uptime-kuma, ntfy, changedetection, searxng, cadvisor, node/pg/redis exporters). Total ≈ **47 containers**. `PRODUCTION-PROVEN`.

---

## 1. SEV Ratings

Severity is judged on **user impact × revenue impact × blast radius × duration**, scaled to this system's real customer base (**2 paying accounts: `jiya-makeover`, `0511a69b900e` "Kamal dar"** — `PRODUCTION-PROVEN`, `DAY_0_REVENUE_BASELINE.md`). "SEV1 = service down / all users affected" is applied **per affected lane**, not per whole product, because a fully-dead revenue lane is SEV1 to the business even while the web app stays up.

| ID | Issue (one line) | SEV | Justification |
|---|---|---|---|
| **E1** | Prod served by a **systemd host process**, not the documented `leadgen_app` Docker container; `AGENTS.md` §2 + project memory are wrong | **SEV2** | Not user-down today, but it invalidates the entire release-control model: the deploy validates/updates a container topology that isn't what serves traffic. Systemic enabler of the owner's complaint. Latent SEV1 blast radius. |
| **E2** | Canonical `deploy_vps.sh` **never restarts the process that serves traffic** (no `systemctl restart leadgen`) **and never sets `.env:APP_VERSION`** → it **cannot complete any SHA-changing deploy** (fails its own `/health` verify with `exit 3`) | **SEV1** *(release path)* | Mechanism now **proven (§8)**: the host process's `APP_VERSION` is a **frozen `EnvironmentFile` snapshot** taken at process start, so the script's verify step reads the OLD sha and aborts. The canonical release path is **functionally non-functional for any SHA change** → the live SEV1 (E4) cannot be remediated through the normal path, and prod only moves by an out-of-band `systemctl restart`. |
| **E3** | **Five-way image/version skew** across leadgen containers (`cdc28e0d` / `95245ce8` / `d08f07c5` / `8b7fd7c3` / `28ba5d4e`) | **SEV2** | Services sharing one codebase run 5 different builds (17 h → 3 d apart). Cross-service contract drift = silent automation failures; makes "fix one, break another" reproducible. No direct user-down proven. |
| **E4** | **WhatsApp (WAHA) session LOGGED OUT** — `SCAN_QR_CODE` / `UNPAIRED` | **SEV1** *(WhatsApp/revenue lane)* | All WhatsApp automations dead: weekly digests to **both paying customers**, post-call offer dispatch, delivery messages. Fail-closed = zero customer-facing output on that channel. Revenue-blocking. **Recurring** (same failure 2026-08-22, fixed 2026-08-23, broken again). Remedy is a human action → cannot self-heal. |
| **E5** | Security exposure: `ufw` **inactive**; WAHA published `0.0.0.0:3002` **and `[::]:3002`**; relay `0.0.0.0:3110`; live webhook token in plaintext in `wa_health_check.json` | **SEV2** | No host firewall + dual-stack public binds = internet-reachable attack surface on a box that also holds production ledgers and 182 MB of DPDP call recordings. WAHA returns 401 (auth required) — mitigating. No compromise proven. Plaintext token: **SEV3** (contained: not in git). |
| **E6** | **Data-integrity split brain**: two live runtime roots both written; live production state lives in **189 tracked files inside the git checkout**; 15 repo-wide destructive paths (`git reset --hard` / `git clean -fd`) can destroy it | **SEV1** *(latent, catastrophic)* | `git reset --hard` on the checkout would revert/delete the invoice ledger, consent ledger, suppression ledgers, customer registry and DPDP recordings. Currently intact (no ` M` in `git status`), but blast radius is total data loss. The active split-brain itself (two roots diverging) is **SEV2** today. |
| **E7** | **Multi-tenant host running a full staging stack in production**, sharing the **same** `./data` + `/opt/leadgen-runtime` mounts as prod | **SEV2** | `leadgen_app_staging` (3 d) + `leadgen_db_staging` + `leadgen_redis_staging` (2 wk) write to the **production** data roots → staging can corrupt prod state (sub-risk **SEV1-class**). Plus resource contention, a failed `tmux-leadgen` unit, and a blast radius that spans unrelated tenants (buzz-prod, tilakgram, livekit). |

**Overall incident rating: SEV1** (driven by E4 — a fully-dead, revenue-blocking, recurring customer channel — plus E2 — the canonical release path is broken — with E6/E7 as latent SEV1 data-loss risk).

---

## 2. Impact Scope (plain terms)

**What is actually broken for the customer (`jiya-makeover`, a paying Starter ₹1,999/mo account in Nagpur):**
- The **WhatsApp lane is dead**. Weekly digests, delivery/offer messages and post-call WhatsApp dispatch are **fail-closed** — Jiya receives nothing on the channel the product depends on to deliver value. (`PRODUCTION-PROVEN` for the dead session; `PARTIAL` for the exact set of queued messages — `REVENUE_BLOCKERS.md` records historic `delivery_stuck.jsonl` counts Jiya 20×, Kamal 14×, but I did **not** re-count current queued items.) → **churn risk on the highest-value relationship.**
- The customer-facing web app is **up** (`/health` healthy, `production`, routes present) — so this is a **degraded delivery** incident, not a site outage. `PRODUCTION-PROVEN`.

**What is broken for revenue:**
- Every automated WhatsApp touchpoint (digest → offer → close) is offline until a human re-links the session. This is the same lane that gated `BLK-05` (voice post-call offer dispatch) historically. `PARTIAL` (depends on which automations ride WAHA).
- The owner's two named revenue gates (Smartflo console DID→Voice-Bot destination, manual UPI collection) are **out of scope** of this triage and were not re-probed. `UNKNOWN` here.

**Operational / reliability impact:**
- **Deploys are not trustworthy**: the canonical script updates Docker services but not the process serving `leadsgenai.in`, and the five services are on five different SHAs. "Deploy succeeded" ≠ "production runs the deployed code." `PRODUCTION-PROVEN` (script) + `UNKNOWN` (today's exact coupling, §7).
- **Every deploy is also a data-risk event**, because live production state is stored in tracked files inside the checkout the deploy pulls into. `PRODUCTION-PROVEN`.
- **Blast radius is the whole VPS**: ~47 containers incl. unrelated tenants; no host firewall. Any incident (OOM, disk, docker daemon, kernel) hits paying LeadGen customers **and** other businesses. `PRODUCTION-PROVEN`.

---

## 3. Incident Timeline

Only evidence-backed entries; anything not provable is marked `UNKNOWN`. Times given as IST (host local = UTC).

| When | Event | Label |
|---|---|---|
| **2026-08-22** | WAHA session `default` FAILED → `SCAN_QR_CODE`; paid-customer digests blocked (`delivery_stuck.jsonl`: Jiya 20×, Kamal 14×, TestHotelSpa 124×). *(historical, `REVENUE_BLOCKERS.md`)* | STALE (historical record) |
| **2026-08-23** | Owner re-scanned QR; session relinked; digests delivered end-to-end. *(historical)* | STALE (historical record) |
| **2026-09-14** | Engineering-assurance audit; staging stack running; 3-way lineage divergence documented (`local 20e4180b ≠ origin/main 95245ce8 ≠ prod`). | STALE (superseded by today) |
| **2026-09-15 02:40:39 UTC** | `leadgen.service` (systemd host uvicorn, parent PID 788053) restarted → read `EnvironmentFile=/opt/leadgen/.env` (which said `APP_VERSION=cdc28e0d`) **at process start**. `/health` therefore reports `cdc28e0d` = host `HEAD`. **This match is a timing coincidence, not a working deploy path** (§8). | PRODUCTION-PROVEN (mechanism, §8) |
| **2026-09-15 ~03:20 UTC** | Team lead's evidence capture (`/health uptime 1h 8m`). | PRODUCTION-PROVEN |
| **2026-09-15 03:17 UTC (08:47 IST)** | **`leadgen_waha` container (re)started** (`Up 34 minutes` at 09:21 IST). Cause UNKNOWN. | PRODUCTION-PROVEN |
| **2026-09-15 03:17–03:22 UTC (08:47–09:22 IST)** | Watchdog logs `session=SCAN_QR_CODE — waiting for owner scan` every 60 s (unbroken). | PRODUCTION-PROVEN |
| **2026-09-15 03:52 UTC (09:22 IST)** | My re-probe: 5-way skew; both runtime roots live; `ufw inactive`; `tmux-leadgen` failed; `HEAD == origin/main == cdc28e0d` (host ref stale vs real remote `e77f8e08`). | PRODUCTION-PROVEN |
| **UNKNOWN** | Exact instant the WhatsApp session was invalidated (only the persistent `SCAN_QR_CODE` state is proven). | UNKNOWN |
| **UNKNOWN** | Exact start time of each skewed container beyond `Up N` (17 h / 19 h / 29 h / 2 d / 3 d). | PARTIAL |
| **2026-09-15 02:40:39 UTC** *(resolved)* | Mechanism by which the systemd host process came to run `cdc28e0d`: **RESOLVED** — `EnvironmentFile=.env` snapshot taken at the 02:40:39 restart (§8). Not a mystery, and not a working deploy. | PRODUCTION-PROVEN |
| **UNKNOWN** | When/why `tmux-leadgen.service` entered `failed`. | UNKNOWN |

---

## 4. Root Cause Analysis (5 Why)

### 4A — "Deploy ke baad automation break" (E1 + E2 + E3 + E6 together)

1. **Why do automations break after a deploy?** Because after a deploy the system's parts **disagree**: some components run new code, others old, and/or live state is moved/reverted. (`PRODUCTION-PROVEN` skew + script)
2. **Why do the parts disagree?** Because `deploy_vps.sh` recreates **only Docker services** and **never restarts the systemd host process that actually serves `leadsgenai.in`** (E2), while the app-image services are already on **5 different SHAs** (E3). The one process that faces customers is outside the deploy's control.
3. **Why does the deploy only handle Docker?** Because the **documented topology is wrong**: `AGENTS.md` §2 and project memory say production runs as a `leadgen_app` Docker container, but reality is a systemd host uvicorn on `127.0.0.1:8000`. The script was written against the documented (false) topology. (`PRODUCTION-PROVEN`: no `leadgen_app` container exists; `ss` shows host python on :8000.)
4. **Why did documentation and reality diverge undetected?** Because **no guardrail asserts that the process serving :8000 is the process the deploy controls.** The script's own VERIFY curls `127.0.0.1:8000/health` and compares the version — which gives **false confidence**: it passes whenever the host happens to be current, regardless of whether the deploy caused it. No topology-drift detector exists.
5. **ROOT CAUSE:** Production has **no single authoritative release contract**. Four independent "sources of truth" — the documented topology, the deploy script, the running process, and the image tags — are never reconciled by a gate. Compounding it, **live mutable state lives inside the git checkout** (E6), so the deploy's own `git pull` / any `git reset --hard` mutates production data. **Net effect: each deploy perturbs code and data in ways nobody can predict or verify → "ek fix hota hai toh dusra tod jaata hai."**

### 4B — WhatsApp lane dead (E4)

1. **Why are WhatsApp automations dead?** The WAHA session status is `SCAN_QR_CODE` (not `WORKING`). (`PRODUCTION-PROVEN`)
2. **Why `SCAN_QR_CODE`?** The WhatsApp-Web (WEBJS) engine is `UNPAIRED`, `me: null` — the device link is no longer authenticated. (`PRODUCTION-PROVEN`)
3. **Why is it unpaired?** **UNKNOWN (hypothesis, not proven).** Candidates: device-link expiry/inactivity, an explicit logout, or the container (re)start ~34 min prior landing on `SCAN_QR_CODE` because auth state wasn't durably persisted. The container restart is proven; **causation is not.** (`PARTIAL`)
4. **Why doesn't it self-recover?** Re-linking requires a **human to scan the QR**; there is no automated re-pair and no self-service re-auth. The watchdog **correctly detects** but can only log — it has no remediation path. (`PRODUCTION-PROVEN`: watchdog emits only log lines; no restart/relink action observed.)
5. **ROOT CAUSE:** The WhatsApp lane has a **single human-in-the-loop dependency** (owner QR scan) and **no durable session persistence / automated re-pair**. Any session invalidation is therefore a **hard, recurring outage**. The prior fix (2026-08-23) was **manual**, so it removed the symptom, not the dependency — which is why it recurred.

---

## 5. Action Items

Owners: **owner-Ratanshila** = the business owner's action; **engineering** = code/infra change. Urgency: **P0** (do now) / **P1** (this sprint) / **P2** (backlog). Verification commands are **read-only** and run **on the prod host** unless noted.

| # | Action | Owner | Urg. | Verification command (proves fixed) |
|---|---|---|---|---|
| **A1** | **Re-link WhatsApp** — owner scans the WAHA QR for session `default`. *(This is the **single owner-facing SEV1 revenue action**; it is the same item as the team lead's P0 — kept as ONE instruction, not two.)* | owner-Ratanshila | **P0** | `curl -s -H "X-Api-Key: $WAHA_API_KEY" 127.0.0.1:3002/api/sessions/default` → `"status":"WORKING"`; then `tail -3 /opt/leadgen/data/waha_watchdog.log` shows no `SCAN_QR_CODE`; then one real digest delivers. |
| **A2** | **Stop the staging stack writing to production data.** Re-mount staging on its own roots, or stop `leadgen_app_staging` / `leadgen_db_staging` / `leadgen_redis_staging`. | engineering | **P0** | `docker inspect -f '{{json .Mounts}}' leadgen_app_staging` → contains **no** `/opt/leadgen/data` or `/opt/leadgen-runtime`; `docker ps --format '{{.Names}}' \| grep staging` → empty (if stopped). |
| **A3** | **Fix the broken release path — TWO required edits to `scripts/deploy_vps.sh`:** **(a) SET** `.env:APP_VERSION` to the deployed sha using a `sed -i` **replace** (NOT the `>>` append the script's own FIX hint suggests — `.env` already has exactly one `APP_VERSION=` line at :573; appending creates a duplicate key, and `EnvironmentFile` is last-wins so it "works" while polluting the file); **(b) `systemctl restart leadgen`**, placed **after** `git pull --ff-only` (~L272–278) **and after (a)**, and **before** the `/health` verify (~L467–503). Without **both**, the script's verify reads the frozen old env and `exit 3`s ("prod did NOT pick up this build") on **every** SHA-changing deploy. Must keep the **30 `tests/` files** that reference `deploy_vps` green (incl. `test_deploy_guard_ordering.py`, `test_deploy_parent_behaviour.py`, `test_deploy_vps_skew_resolution.py`, `test_deployment_path_manifest.py`) — do not propose an edit that ignores them. | engineering | **P0** | `grep -n "systemctl restart leadgen" scripts/deploy_vps.sh` non-empty **AND** `grep -c '^APP_VERSION=' /opt/leadgen/.env` → `1` **AND** after a real SHA-changing deploy: `curl -s 127.0.0.1:8000/health \| grep -o '"version":"[^"]*"'` == deployed SHA **AND** the `deploy_vps`-referencing test suite green. |
| **A4** | **Take WAHA and the relay off the public interface.** Recreate `leadgen_waha` from the checked-in compose (`127.0.0.1:3111`), or rebind to localhost; same for `buzz-prod-relay-1`. | engineering | **P0** | `ss -ltnp \| grep -E ':3002\|:3110'` → shows `127.0.0.1:…` only; **no** `0.0.0.0:` and **no** `[::]:`. |
| **A5** | **Enable the host firewall** (allow 22/80/443, default deny inbound). | engineering | **P0** | `ufw status` → `Status: active`; `ss -ltn` shows no unexpected public listeners. |
| **A6** | **Reconcile all leadgen services to one SHA** via the (fixed) canonical deploy — including the 6 CLI workers (`d08f07c5`), `app_vobiz`/`mcp` (`8b7fd7c3`) and the staging app. | engineering | **P1** | `docker ps --format '{{.Names}} {{.Image}}' \| grep leadgenrationaivoiceagent` → all non-staging app-image services end with the same `:<sha>`. |
| **A7** | **Add a topology-drift gate**: assert the `:8000` listener is the deploy-controlled systemd unit and that its SHA == deployed SHA; run pre-deploy and in CI. | engineering | **P1** | New check present + fails when a synthetic mismatch is introduced (mutation test). |
| **A8** | **Correct the docs of record**: fix `AGENTS.md` §2 / `CLAUDE.md` / project memory to state "prod served by `leadgen.service` (systemd host uvicorn :8000); Docker runs workers/scheduler only." | engineering | **P1** | `grep -rn "leadgen_app :8000 (FastAPI, Docker" AGENTS.md CLAUDE.md` → no hits; topology section names `leadgen.service`. |
| **A9** | **Make destructive git paths fail-closed** against the runtime data (`git reset --hard`/`git clean -fd` in `vps_pitch_deploy.sh`, `_mcp_deploy_remote.sh`, `vps_deploy_dashboard.py`, `vps_build_deploy.py`, `vps_deploy_call_learn.bat`, `vps_force_pull.py`). | engineering | **P1** | Each path calls `runtime_data_preflight.py check-deploy` and aborts; verified by a dry-run against a scratch repo. |
| **A10** | **Declare the single runtime-data root** (which of `/opt/leadgen/data` vs `/opt/leadgen-runtime` is truth) and execute the documented cutover (`RUNTIME_DATA_CUTOVER_ENABLED`). | engineering + owner sign-off | **P1** | `python scripts/runtime_data_preflight.py diagnose` → `mode: EXTERNAL_VERIFIED`, `host_path_inside_checkout: false`, `blocker_count: 0`. |
| **A11** | **Restore `tmux-leadgen.service`** or decommission it deliberately. | engineering | **P2** | `systemctl is-active tmux-leadgen` → `active` (or unit removed by decision). |
| **A12** | **Protect the webhook token**: rotate it **only if** it was exposed externally (it is **not** in git — verified); restrict permissions on `wa_health_check.json`; stop persisting the token in a plaintext status file. | engineering | **P2** | `stat -c '%a' /opt/leadgen/data/wa_health_check.json` → `600`; file contains no `token=` value. |
| **A13** | **De-duplicate `APP_ENV` in `.env`** (2 occurrences). Currently **benign** — `EnvironmentFile` is last-wins, so no live impact — but a duplicate-key hazard: the `.ENV GUARD`'s `head -1` reads the *first*, not the *winning*, value. | engineering | **P2** | `grep -c '^APP_ENV=' /opt/leadgen/.env` → `1`. |

> **Compliance note:** none of the above weakens a compliance gate. A1–A13 are availability/security/data-integrity actions; DND/TRAI/DPDP/consent gates must remain fail-closed. A9/A10 specifically **protect** the DPDP recordings and consent ledger.

---

## 6. Prevention (guardrail per issue)

| Issue | Guardrail that would have caught it before production |
|---|---|
| **E1** (wrong topology) | A **topology assertion** in the deploy/CI: "the PID listening on `:8000` belongs to the service the deploy restarts." Doc-truth test that fails if `AGENTS.md` topology ≠ a live probe. |
| **E2** (no restart) | **Fail-closed post-deploy gate**: if the traffic-serving unit's SHA ≠ deployed SHA, the deploy exits non-zero and does not report success. Single release authority. |
| **E3** (5-way skew) | Extend the existing skew check to **all** app-image services (today `ALL_ROLLOUT_SERVICES` covers 6; the 6 CLI workers, `app_vobiz`, `mcp`, and staging are outside it). Pre-deploy assertion that every app-image tag is identical. |
| **E4** (WAHA logout) | **Durable session auth** + **automated re-pair or owner page**. A **revenue-path liveness SLO** that alerts a human when the WhatsApp lane is not `WORKING` for >N minutes — not a log line. |
| **E5** (exposure) | **Firewall-as-code** (ufw rules in the deploy/bootstrap) + compose default `127.0.0.1:` binds + **secret scanning** over the runtime data dir (the token is already absent from git — keep it that way). |
| **E6** (data split brain) | **Move runtime state out of the checkout** (cutover gate exists — execute it); make `git reset --hard`/`git clean -fd` **fail-closed** via `runtime_data_preflight.py`; a **single declared runtime root** enforced at startup. |
| **E7** (staging in prod) | **Environment isolation**: staging gets its own host/namespace and **never** mounts production roots; resource quotas; a "no prod-data mount outside prod" policy check. |

---

## 7. What I Could NOT Determine (honest gaps)

1. **Exact instant the WhatsApp session was invalidated.** Only the persistent `SCAN_QR_CODE`/`UNPAIRED` state is proven; the onset time is unknown.
2. **Whether the WAHA container restart (~08:47 IST) caused, or merely followed, the logout.** Proven: the restart happened. Not proven: causation.
3. ~~**How the systemd host process came to run `cdc28e0d`**~~ **RESOLVED — see §8.** `EnvironmentFile=/opt/leadgen/.env` means `APP_VERSION` is a **snapshot taken at process start** (02:40:39 UTC); `.env` already said `cdc28e0d`, so `/health` matches HEAD **by timing coincidence**, not because the deploy path works. Corollary: `deploy_vps.sh` **cannot complete any SHA-changing deploy** (§8).
4. **A residual ~29-minute inconsistency between two `/health` uptime readings.** The team lead's reading (`1h 8m` at 03:48 UTC) is exactly consistent with the 02:40:39 start; my later probe (`1h 40m 2s` at 03:51:59 UTC) implies a ≈02:12 start. I cannot explain the gap — plausibly the app's uptime anchor differs from the OS process start (e.g. a module-level init). Low materiality; flagged for honesty.
5. **Which of the two runtime roots is authoritative.** Both are actively written; nothing in the evidence declares a winner. (`LEADGEN_RUNTIME_DATA_DIR=/var/lib/leadgen/runtime` is set, implying the external root is intended, but the checkout root is demonstrably still live.)
6. **Whether the two `APP_ENV` lines in `.env` agree**, and whether the `.ENV GUARD`'s `head -1` reads the correct one.
7. **Whether the running WAHA was started from a non-checked-in compose file** — proven it does **not** match the checked-in config; the actual source file/command is unknown.
8. **Current state of the two named revenue gates** (Smartflo DID→Voice-Bot destination; manual UPI collection) — out of scope, not re-probed.
9. **Any actual data corruption from the staging stack sharing production mounts** — risk established, corruption **not** proven.
10. **Whether `e77f8e08` (real remote `main`, 3 commits ahead) is intended to ship**, and whether any deploy is currently in flight. The host's `origin/main` ref is **stale** at `cdc28e0d`, so the host cannot tell without a fetch.
11. **Whether the plaintext webhook token was ever exposed externally.** Proven it is **not** in git; file provenance/exposure is unknown.

---

## 8. ANSWER — how the systemd process got its `APP_VERSION` (resolves §7 #3)

**Supplied and verified by the team lead; not independently re-probed by this author.** This closes the triage's biggest open question — and the answer is **worse** than "unknown": the release path is **provably broken**, not accidentally working.

**Proven mechanism (all `PRODUCTION-PROVEN`):**
1. `/etc/systemd/system/leadgen.service` (mtime Jun 9 08:25, **no drop-ins**) sets `EnvironmentFile=/opt/leadgen/.env` alongside `WorkingDirectory=/opt/leadgen`, the uvicorn `ExecStart` on `127.0.0.1:8000`, `Restart=always`, `RestartSec=5`, `User=root`.
2. `/opt/leadgen/.env:573` → `APP_VERSION=cdc28e0d`.
3. `/proc/788053/environ` → `APP_ENV=production`, `APP_VERSION=cdc28e0d` — identical to `.env`, and `EnvironmentFile` is the **only** way they got there (`systemctl show leadgen -p Environment` empty; `-p EnvironmentFile` prints empty (a `systemctl` quirk — the unit plainly sets it); no drop-in; `grep -n load_dotenv app/main.py` → **no hits**).
4. `app/api/health.py:111` → `"version": os.environ.get("APP_VERSION","dev")` — read from `os.environ`, **frozen at process start**.

**⇒ Conclusion.** `EnvironmentFile=` makes the process's `APP_VERSION` a **snapshot of `.env` taken at process start**. Something restarted `leadgen.service` at **02:40:39 UTC**; the process read `.env` (which already said `cdc28e0d`, matching host HEAD); `/health` therefore matches HEAD. **That match is a coincidence of timing — not a working deploy path.**

**⇒ Consequence — `deploy_vps.sh` cannot complete ANY SHA-changing deploy.** Sequence: the `.ENV GUARD` (~L163–203) only *validates* that `.env:APP_VERSION` is a sha — it never *sets* it (its own FIX hint tells the human to `echo 'APP_VERSION=$VER' >> .env`). The script then builds containers, `up -d`s them, `sleep 22`, and verifies `curl -s 127.0.0.1:8000/health` (~L486) — which hits the **systemd host process**, whose env is **frozen**. So `LIVE_VER` is still the OLD sha → L497 `if [ "$LIVE_VER" != "$VER" ]` → **`exit 3`** ("FATAL: prod did NOT pick up this build").

**⇒ Required fix (see revised A3):** it is not just "add a restart" — it is **two** currently-missing steps:
- **(a) SET** `.env:APP_VERSION=$VER` via a `sed -i` **replace** (not the `>>` append the script's hint implies; `.env` has exactly one `APP_VERSION=` line and `EnvironmentFile` is last-wins → an append "works" but pollutes the file).
- **(b) `systemctl restart leadgen`**, **after** `git pull --ff-only` (~L272–278) and **after (a)**, and **before** the `/health` verify (~L467–503).
- Any edit must keep the **30 `tests/` files** referencing `deploy_vps` green.

**Also folded in:** the duplicate `APP_ENV=` in `.env` is currently **benign** (last-wins) but is a real duplicate-key hazard (revised A13); and **A1 (owner WAHA re-scan) is the single owner-facing SEV1 revenue action** — same item as the team lead's P0, kept as one instruction.

---

## Appendix A — Evidence index (labels)

- **E1** systemd host process serves prod; `AGENTS.md` §2 contradicts reality → `PRODUCTION-PROVEN` + `CODE-PRESENT` (doc is `STALE`).
- **E2** `deploy_vps.sh` has no `systemctl restart leadgen` → `CODE-PRESENT` (re-verified, exactly 3 comment/echo hits).
- **E3** five-way image skew → `PRODUCTION-PROVEN` (re-verified).
- **E4** WAHA `SCAN_QR_CODE`/`UNPAIRED` → `PRODUCTION-PROVEN` (re-verified).
- **E5** `ufw inactive`; `0.0.0.0:3002` + `[::]:3002`; `0.0.0.0:3110`; plaintext token → `PRODUCTION-PROVEN` (re-verified).
- **E6** dual live runtime roots; 189 tracked data files; 15 destructive paths → `PRODUCTION-PROVEN` + `CODE-PRESENT` (re-verified).
- **E7** staging-in-prod sharing prod mounts; co-tenants; failed unit → `PRODUCTION-PROVEN` (re-verified).

**Boundary statement.** This document is triage only. No fix is claimed complete; no mutating command was run; no secret value is reproduced (the webhook token is withheld by policy). Where the supplied evidence was insufficient for a claim, the claim is marked `UNKNOWN`/`PARTIAL` rather than guessed.

