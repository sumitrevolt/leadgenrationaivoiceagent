# Full-Stack Audit: Architecture · Infrastructure · Project Organization
**Date:** 2026-08-05 · **Scope:** whole repo · **Method:** Harness/Loop/Graph 3-layer model + evidence-based code inspection
**Status:** AUDIT ONLY — no production behaviour changed. Execution plan in §6, gated on owner approval.

---

## 0. Executive summary (padho sirf yeh agar time nahi hai)

Teen alag health problems hain, teeno ka severity alag hai:

| Area | Verdict | One-line diagnosis |
|---|---|---|
| **Architecture (agent layer)** | 🟠 Built-but-not-wired | Ek conformant harness (`app/agents/harness/`) exist karta hai jo L2–L3 capable hai, par **production me INERT/shadow** hai. Actual traffic 5 alag legacy loops chala rahe hain, sab L1. |
| **Infrastructure** | 🔴 Two live P0 footguns | Root pe legacy `docker-compose.yml` (known 502 incident trigger) + **~52 scripts** jo canonical `deploy_vps.sh` ke saare guarantees bypass kar sakte hain. |
| **Project organization** | 🔴 Worst offender | Root pe **235 files, sirf 69 tracked** → 166 untracked litter. `docs/` me **373 .md**, jisme ~80+ dated snapshots canonical docs ke saath same tier pe pade hain. `README.md` ek **mar chuke product** ko describe karta hai. |

**Sabse zyada ROI wale 3 kaam (is order me):**
1. `README.md` rewrite (galat product describe kar raha hai — har naya insaan/agent sabse pehle yehi padhta hai)
2. Legacy `docker-compose.yml` quarantine + deploy-script consolidation (P0 prod risk)
3. Root + `docs/` reorg (Phase 0 already done, baaki approval pe)

---

## 1. Architecture audit — Harness / Loop / Graph

### 1.1 The model
- **HARNESS** = environment: context assembly, tool registry + permissions, sub-agents, memory, verifier, response shaping
- **LOOP** = feedback cycle: goal + success criteria, gather→act→verify, **stopping rules** (max iters, budget/time, no-progress, completion check)
- **GRAPH** = topology: ordering, branches, parallel fan-out, approval gates, merge/join, terminal states

Failure → layer mapping used for classification:
- missing tools / wrong permissions / context lost / state scattered → **HARNESS**
- repeats wrong thing / drift / weak evals / no feedback → **LOOP**
- wrong step order / broken joins / bottleneck / no parallelism → **GRAPH**

### 1.2 Per-loop findings

| # | Loop | Entry | Layers present | Stopping rules | Maturity |
|---|---|---|---|---|---|
| 1 | `app/agents/self_improve.py` | `run_iteration` (:1488) | LOOP only. **Zero** harness refs (`grep -c harness` = 0). GRAPH: none | daily cap, `_ITER_TIMEOUT_S=240` (:43), budget gate (:1304-1308). **No no-progress detector**, no wall-clock run cap | **L1** |
| 2 | `app/agents/coordinator.py` | `coordinate_advanced` (:695) | LOOP strongest in repo (real plan→verify→reflect, `_verify` LLM-judge :655-680). HARNESS = shadow only (:398, :995) | `min(3, max_iterations)` (:720), `quality_bar` early-stop (:737), neutral-0.6 anti-infinite-loop fallback (:679). No token/wall-clock cap here | **L1** overall (L2-ish loop quality) |
| 3 | `app/agents/dag_engine.py` | `advance` (:290) | **Only real GRAPH in repo** — branch/merge join any/all (:116-117), skip-not-taken (:312), `ST_WAITING="waiting_approval"` (:34,:301) | `max_steps=16` (:290), per-step `_STEP_TIMEOUT_S` (:370). No cost cap | **L1–L2** |
| 4 | `app/agents/process_engine.py` | `advance` (:181) | Near-duplicate of #3's loop (`max_steps=10`, :205, :249-252) **minus** branch/merge/approval | step count + per-step timeout only | **L1** |
| 5 | `app/agents/staff_supervisor.py` | (:53) | Third paradigm — LangGraph supervisor, `USE_LANGGRAPH_SUPERVISOR`, not imported at startup (:10-12) | none visible in-repo; delegates to framework defaults | **unaudited** |
| — | `app/agents/harness/` | `Harness.step()` (loop.py:212-322), `run()` (:588-617) | **All three, correctly.** Ordered VA-01→GV-01 pipeline (loop.py:10-23), `StopController` (stop.py:61-152), Redis kill switch fleet+per-run (stop.py:70-94), fail-closed approval (loop.py:62-79) | `Budget`: max_iterations=12, max_tool_calls=40, max_usd=1.00, max_tokens=200k, max_wall_clock_s=300, **no_progress_window=3** (stop.py:36-43) | **L2–L3 capable** |

### 1.3 The headline finding

> **Tumne sahi cheez bana li hai, par usko plug nahi kiya.**

`app/agents/harness/` ek genuinely conformant control tier hai — least-privilege registry, real budgets, no-progress window, kill switch, checkpoint, audit trail. Ye exactly wahi hai jo 5 bikhre hue loops ko unify karne ke liye banaya gaya tha.

Lekin:
- `AGENT_HARNESS=0` default → **INERT** (`__init__.py:5`, `enforce.py:6-8`)
- Har integration point **observe-only shadow** hai (`observe_coordinator_action`, `observe_dag_action` :384 — comment literally "record-only" :380-384)
- `registry.py:9-11` khud kehta hai: *"Shadow-only in this phase... Nothing is enforced"*

**Net effect: production me effective maturity L0–L1 hai, jabki L2–L3 code repo me maujood hai.** Ye architecture gap nahi hai — ye ek **cutover gap** hai, aur wo bohot sasta fix hai.

### 1.4 Cross-cutting architectural gaps

| Gap | Layer | Evidence |
|---|---|---|
| **6 competing loop implementations** (5 legacy + 1 unenforced harness). `process_engine.advance` aur `dag_engine.advance` ka stop logic copy-paste hai | HARNESS | file pairs above |
| **2 competing tool registries** — `harness/tool_registry.py` (per-run) vs `harness/registry.py` (`CanonicalToolRegistry`), neither consumed by self_improve/process_engine/staff_supervisor | HARNESS | registry.py:9-11 |
| **Eval layer built but not gating** — `eval_gate.py`, `judge_calibration.py`, `live_eval.py`, `eval_metrics.py` exist; call-sites into the named loops not found. `coordinator._verify` ek uncalibrated LLM-judge hai jiska khud koi check nahi | LOOP | app/agents/*eval* |
| **No true parallelism** — even `dag_engine` deliberately avoids `asyncio.gather` (:9-10), so the one graph engine serializes within a tick | GRAPH | dag_engine.py:9-10 |
| **Router sprawl** — `app/api/` me **120 files, 110 `APIRouter(...)`**. FastAPI first-route-wins ke saath duplicate-route risk high; koi consolidated route registry nahi | HARNESS | app/api/ |
| **Two parallel approval mechanisms** — dag_engine ka `waiting_approval` vs harness ka PM-03 `risk_approve` HITL queue | GRAPH | dag_engine.py:34,:301 |

---

## 2. Infrastructure audit

### 2.1 Compose sprawl — 11 files at root

`docker-compose.vps.yml` (495 ln) hi **canonical** hai (header :2, `deploy_vps.sh:29` hardcodes it). Baaki 10 me se:

- 🔴 **`docker-compose.yml` (root) = live incident trigger.** Bare `docker compose up` isko default uthata hai → `voice_agent_*` containers, `postgres:15` (vs canonical `16`), app internal port 8000 (vs canonical 8080), colliding host ports 8000/5432/6379. **Yehi documented prod-502 ka mechanism hai.**
- `docker-compose.prod.yml` — khud disclaim karta hai (:6-7) "NOT the live deploy path", phir bhi repo me armed pada hai
- **15+ images `:latest` pe pinned** — observability (9), addons (3), tools (3), edge, ollama, waha, postiz. Koi bhi `docker compose pull` silent breaking upgrade la sakta hai
- `docker-compose.staging.yml` — properly hardened (mandatory `APP_VERSION`, isolated net) ✅

### 2.2 Dockerfiles — drift

| File | Used by | Python | Digest pin |
|---|---|---|---|
| `Dockerfile.lock` | ✅ canonical (vps compose :37,252,319,375,421 + CI :142) | 3.12 | ✅ sha256 pinned |
| `Dockerfile` | **ORPHAN** — zero references | 3.11 | ❌ |
| `Dockerfile.production` | dead prod compose + dead CI workflows + Makefile | 3.11 | ❌ |
| `Dockerfile.video` | `docker-compose.video.yml:30`, `FROM ${APP_IMAGE}` | derived | n/a ✅ |

### 2.3 Deploy path — the big one

`scripts/deploy_vps.sh` (507 ln) genuinely strong hai: fail-closed missing-helper `exit 91` (:55-65), isolated worktree (:67-95), **`APP_VERSION` refusal for `""/latest/dev/1.0.0`** (:85-91 = ADR-097 encoded), `set -uo pipefail` (:26), disk guard (:143-157), in-image `prod_check.py` gate (:210-215), `up -d` **all 5 app-image services** (:31) to prevent skew, `/health.version == $VER` poll (:374-395), per-service skew check (:401-425), revenue smoke (:431-436), DLQ check (:438-440).

🔴 **Par ~52 doosre entry points isko bypass kar sakte hain:**
- **35 `.sh`** scripts jo directly `docker compose` chalate hain — including root `DEPLOYMENT_AUTOMATION.sh:148` jo sirf `app worker scheduler` recreate karta hai, **`worker-heavy`/`worker-video` chhod deta hai** = exactly wahi skew bug jise rokne ke liye `deploy_vps.sh` bana tha
- **17 `.bat`** Windows triggers jo SSH + deploy karte hain
- `deploy/scheduler/` me systemd `.timer`/`.service` = **teesra scheduling path** (Celery beat + in-process `RUN_IN_PROCESS_SCHEDULER` ke alawa) → duplicate-fire risk

### 2.4 CI/CD
- `deploy-vps.yml` — `gate` job **BLOCKING** ✅ (import smoke, prod_check, billing contract, pytest shards). ruff + golden-eval advisory. Deploy `DEPLOY_ENABLED`-gated (disabled) ✅
- 🟠 `ci-cd.yml` — self-labelled "⛔ DEPRECATED... DELETE after 2026-08" (:1-3) **aaj 2026-08-05 hai, ab bhi maujood**, aur `workflow_dispatch` se **GCP Cloud Run production deploy** kar sakta hai (:244-306)
- 🟠 `deploy.yml` — same pattern, Cloud Run canary (:175-251)

### 2.5 Observability
**Strong:** `monitoring/alert_rules.yml` (272 ln, 6 groups) — SLO multi-window burn rate, `CeleryQueueBacklog`/`CeleryDLQNonEmpty`/`CeleryWorkerDown`, `BackupStale`/`RestoreDrillFailed`/`RestoreDrillStale`, LLM chain degraded. `gatus.yaml` synthetic-checks revenue endpoints + TLS expiry. **Restore drill automated + alerted = genuinely good.**

**Missing (aur yeh exactly wahi cheezein hain jo pehle tooti hain):**
1. ❌ **Image/version skew alert** — `deploy_vps.sh` deploy-time pe catch karta hai, par deploys ke *beech* drift ka koi backstop nahi
2. ❌ **Scheduler/beat liveness** — sirf queue depth monitor hoti hai, beat khud zinda hai ya nahi wo nahi
3. ❌ **Voice/FreeSWITCH** — voice stack kisi bhi compose ya observability file me nahi hai → **zero Prometheus target, zero alert surface** (ye tumhara ₹4,999–₹19,999/mo product hai)

### 2.6 Runtime + DR — mostly healthy ✅
Sab 10 canonical services pe healthcheck + `restart: unless-stopped` + `mem_limit` hai. Ports sirf `127.0.0.1` pe published (koi 0.0.0.0 nahi). Backups: `pg_backup.sh` (cron 02:30, 30d retention), `data_backup_rclone.sh` (02:45, 7d), rclone→GDrive, `pg_restore_drill.sh` + staleness alert. **RPO ≈ 24h; RTO undocumented** ← ek gap.

Minor: `app` runs `user: "0:0"` (:48, bind-mount ownership ke liye), `pgbouncer AUTH_TYPE: plain` (:162, internal-only).

---

## 3. Project organization audit

### 3.1 Root — 235 files, sirf 69 tracked

| Category | Count | Tracked? |
|---|---|---|
| `_tmp_*` scratch (`.bat`/`.txt`/`.log`) | 91 | **0 tracked** — pure litter |
| root `.bat` | 81 | mostly untracked |
| root `.txt` | 37 | mostly untracked |
| root `.md` | 20 | tracked |
| **Untracked litter total** | **~166** | — |

Biggest offenders: `pytest_full.log` (1.9MB), `pytest_run.log` (1.4MB), `_tmp_uv.log` (699KB), `scratch_loop_alembic.db` (696KB), `progress.md` (**309KB** — live but unrotated), `_tmp_oc_uvicorn.log` (80KB), `forensics_billing_dlq.txt` (30KB).

### 3.2 docs/ — 373 .md files, no archive convention
- 160 files directly in `docs/` root, 213 in subdirs
- **Sirf ~22 files ka koi live pointer hai** (CLAUDE.md/AGENTS.md se referenced)
- **~80+ dated one-time snapshots** (`*_AUDIT_2026_06_21.md`, `ADR-2026-06-25-Batch*.md`, etc.) canonical docs ke saath **same tier** pe pade hain
- **`docs/archive/` exist hi nahi karta** — yehi root cause hai
- Unbounded logs: `docs/SESSION_LOG.md` (415KB) + `memory/decisions.md` (409KB) + `progress.md` (309KB) = 3 alag ever-growing logs, koi rotation nahi

### 3.3 docs/context/ — protocol drift
Mandate 5 files ka tha, ab **16 files** hain. Extra me single-session dumps hain jo "live context" ka bhes bana ke baithe hain: `CURSOR_TAKEOVER_2026-08-01.md`, `PRODUCTION_DEPLOYMENT_RECORD_510ed7bc.md`, `OWNER_ACTION_PACKET_20260731.md`.

✅ **Achhi khabar:** core 5 files (`CURRENT_STATE`/`ACTIVE_WORK`/`SESSION_HANDOFF`/`SYSTEM_MAP`/`AI_OPERATING_PROTOCOL`) aapas me **consistent** hain aur CLAUDE.md se bhi match karte hain — prod SHA `33651cfc`, `VOICE_LAUNCH_KILL`, `DIAL_TEST_MODE=0`, `UPI_AUTO_ACTIVATE=1` drift note, sab same.

🔴 **Contradiction found:** `docs/context/DECISIONS.md:13` kehta hai `platform_dial HARD OFF` (2026-07-05 ka) — jabki `CURRENT_STATE.md` + CLAUDE.md §5 kehte hain **FULL CAMPAIGN LIVE (2026-08-02)**. Ye pointer table go-live ke baad update hi nahi hua.

Bonus irony: `CONTRADICTION_LEDGER_2026_08_03.md` — drift track karne wali file khud stale hai (`origin/main` ko `303b061f` pe pin karti hai).

### 3.4 memory/ — sabse healthy layer ✅
`decisions.md` **genuinely append-only** hai (ADR-158 renumber in-place note se handle hua, history edit nahi hui). `backlog`/`incidents`/`playbooks` sab 2026-08-04/05 tak fresh.

Gaps:
- `INDEX.md` me `memory/CURRENT_SESSION.md` listed hi nahi (5.6KB, 2026-07-13 se abandoned)
- **ADR-150 duplicate** — `docs/adr/ADR-150-agent-lease-reclaim...md` **aur** `ADR-150-coordination-hub-owner-os-projection.md`, do alag decisions same number pe
- ADR-129 kahin referenced nahi; ADR-139 aur ADR-149 ki files hain par `decisions.md` me index nahi
- Koi ADR **allocator** nahi → collisions repeat hote rahenge (ADR-158 pehle 157, phir 160 likha gaya tha)
- `glossary.md` stale (2026-07-05)

### 3.5 Agent-instruction roots — 8 parallel roots
| Root | Tracked | Verdict |
|---|---|---|
| `.claude/` | 482 files | ✅ **LIVE canonical** (ADR-131) |
| `agent-os/` | 49 files | ✅ **LIVE** — 31-agent persona roster ka source |
| `.agents/` | 38 files | 🟠 stale orchestrator/sentinel scratch; ADR-131 ne `.agents/skills` hataya tha par dir zinda hai |
| `.cursor/` | 6 | 🟠 `.claude/` ka partial mirror — duplication risk |
| `.codex/` | 1 | 🟡 minimal, Codex CLI ke liye |
| `.kiro/` | 4 | 🟠 mostly untracked orphan |
| `.superpowers/` | 1 | 🟠 mostly untracked scratch |
| `.commandcode/` | **0** | 🔴 fully untracked dead weight |

### 3.6 🔴 README.md — sabse damaging stale doc
`README.md` (2026-06-19, pivot se pehle ka) ek **"B2B Intelligence Platform"** describe karta hai: company-search API, per-lookup pricing (₹5+/lookup), enrichment credits, HubSpot/Zoho CRM integrations.

**Actual product ka zikr tak nahi:**
- ❌ AI Automated Marketing ₹1,999 / ₹5,999 — absent
- ❌ Standalone AI Voice Calling Agent ₹4,999 / ₹9,999 / ₹19,999 — absent
- ❌ Manual UPI (the only payment rail) — absent
- ❌ Stack table me `STT | Deepgram`, `TTS | ElevenLabs, Azure` — actual free stack (Groq whisper / EdgeTTS) ke bilkul ulta

✅ `CLAUDE.md` vs `AGENTS.md` byte-identical confirmed (md5 `11595665815d0cefb6f4d5f384c2108c`) — protocol met.

---

## 4. Consolidated gap register (severity ranked)

| # | Sev | Area | Gap | Fix effort |
|---|---|---|---|---|
| G1 | 🔴 P0 | Infra | Legacy root `docker-compose.yml` = bare-`docker compose up` prod-502 trigger | S |
| G2 | 🔴 P0 | Infra | ~52 scripts bypass `deploy_vps.sh` guarantees; `DEPLOYMENT_AUTOMATION.sh:148` reproduces skew bug | M |
| G3 | 🔴 P0 | Docs | `README.md` describes a dead product | S |
| G4 | 🟠 P1 | Arch | Harness L2–L3 built but INERT; 5 legacy L1 loops govern prod | M |
| G5 | 🟠 P1 | Infra | `ci-cd.yml` + `deploy.yml` armed for GCP Cloud Run deploys; one overdue for deletion | S |
| G6 | 🟠 P1 | Infra | Zero alerting on image skew, beat liveness, **voice stack (no Prom target at all)** | M |
| G7 | 🟠 P1 | Docs | 373 docs, ~80+ dated snapshots, no `docs/archive/` | M |
| G8 | 🟠 P1 | Docs | `docs/context/DECISIONS.md` contradicts CURRENT_STATE on `platform_dial` | S |
| G9 | 🟡 P2 | Project | 166 untracked files at root (91 `_tmp_*`, 1.9MB+1.4MB pytest logs) | S |
| G10 | 🟡 P2 | Arch | 2 competing tool registries; eval layer built but not gating loops | M |
| G11 | 🟡 P2 | Arch | 110 routers in `app/api/`, first-route-wins duplicate risk, no route registry | L |
| G12 | 🟡 P2 | Infra | 15+ `:latest` image pins outside canonical stack | S |
| G13 | 🟡 P2 | Docs | ADR-150 duplicate; no ADR allocator; ADR-129/139/149 orphaned | S |
| G14 | 🟡 P2 | Project | 8 agent-instruction roots, 6 legacy/untracked | S |
| G15 | 🔵 P3 | Infra | Triple scheduling path (beat / in-process / systemd timer), no documented SoT | S |
| G16 | 🔵 P3 | Docs | 3 unbounded append logs (415K + 409K + 309K), no rotation | M |
| G17 | 🔵 P3 | Infra | `.env.production.template` git-ignored (untracked); `.env.example` missing 30 prod keys | S |
| G18 | 🔵 P3 | Infra | RTO undocumented (RPO ≈ 24h is fine) | S |

---

## 5. Target project structure

```
leadgenrationaiagent/
├── README.md              ← REWRITE: 2 products, UPI-only, free AI stack
├── CLAUDE.md / AGENTS.md  ← byte-identical (already ✅)
├── CHANGELOG.md  LICENSE  SECURITY.md  CONTRIBUTING.md
├── Makefile  pyproject.toml  requirements.lock.txt
├── Dockerfile.lock        ← ONLY dockerfile at root (+ .video)
├── docker-compose.vps.yml ← ONLY compose at root
│
├── app/                   ← unchanged (backend)
├── frontend/  unity/  alembic/  tests/  evals/
│
├── deploy/
│   ├── compose/           ← staging, observability, addons, tools, edge, ollama, waha, postiz, video
│   ├── legacy/            ← QUARANTINE: docker-compose.yml, .prod.yml, Dockerfile, Dockerfile.production
│   └── scheduler/
│
├── scripts/
│   ├── deploy_vps.sh      ← THE only deploy entrypoint
│   ├── legacy/            ← QUARANTINE: 35 .sh + 17 .bat bypass scripts
│   └── ...
│
├── docs/
│   ├── context/           ← STRICTLY the 5 mandated files
│   ├── adr/               ← all ADRs + allocator script
│   ├── runbooks/  architecture/  reference/  playbooks/
│   └── archive/2026-06/ 2026-07/ 2026-08/   ← every dated snapshot
│
├── memory/                ← unchanged (healthiest layer)
├── monitoring/  infrastructure/
├── .claude/  agent-os/    ← the 2 LIVE agent roots
└── _scratch/              ← gitignored; all _tmp_*, logs, scratch dbs
    └── legacy_agent_roots/  ← .agents .codex .cursor .kiro .commandcode .superpowers
```

**Root file count: 235 → ~20.**

---

## 6. Phased execution plan

### ✅ Phase 0 — DONE in this session (zero risk)
91 untracked `_tmp_*` files → `_scratch/2026-08-05/`. Nothing tracked was touched; fully reversible (`mv` back).

### Phase 1 — P0 safety (recommend: do next, ~1 loop)
1. `git mv docker-compose.yml deploy/legacy/docker-compose.legacy.yml` → bare `docker compose up` ab error dega instead of succeeding wrong
2. `DEPLOYMENT_AUTOMATION.sh` + `EXECUTE_LAUNCH_NOW.sh` → `scripts/legacy/`, top pe loud `exit 1` banner ("use scripts/deploy_vps.sh")
3. `.github/workflows/ci-cd.yml` + `deploy.yml` **delete** (dono self-labelled dead, dono Cloud Run pe deploy kar sakte hain)
4. `README.md` rewrite

### Phase 2 — Project organization
5. `docs/archive/2026-06|07|08/` banao, ~80+ dated snapshots `git mv` karo
6. 14 root `.md` relocate (`FIX_PLAN`, `TEST_RESULTS`, `PRODUCTION_AUDIT_REPORT`, etc. → archive; `Business_Playbook` + content kit → `docs/playbooks/`)
7. `TASKS.md` delete (khud ko superseded declare karta hai)
8. `progress.md` → `docs/` + rotation policy
9. `docs/context/` ko 5 files pe wapas trim karo, baaki archive
10. `.agents .codex .cursor .kiro .commandcode .superpowers` → `_scratch/legacy_agent_roots/`
11. `.gitignore` me `_scratch/`, `*.log`, `pytest_*.log` add karo
12. Compose files → `deploy/compose/`, deploy scripts → `scripts/legacy/`

### Phase 3 — Architecture cutover (the real prize)
13. **Harness canary:** ek loop ko shadow se enforce pe le jao — `dag_engine` best candidate (already sabse mature GRAPH). `AGENT_HARNESS=1` + per-loop allowlist, `StopController` ko live budget do
14. `process_engine.advance` ko **delete** karo, callers ko `dag_engine` pe move karo (near-duplicate, zero unique capability)
15. `self_improve.py` ko harness me wire karo (highest blast radius, currently zero harness refs)
16. `registry.py` `CanonicalToolRegistry` ko **enforce** karo, `tool_registry.py` retire
17. `eval_gate.py` ko `coordinator._verify` se connect karo — judge ko khud calibrated banao
18. Route registry + duplicate-route CI check (110 routers)

### Phase 4 — Infra hardening
19. Alerts add: image/version skew, celery-beat liveness, **voice/FreeSWITCH targets** (abhi zero visibility)
20. Non-canonical compose files ke `:latest` pins → digest/version
21. Scheduling SoT document karo (beat vs in-process vs systemd), do ko disable karo
22. RTO document karo; `.env.production.template` track karo; `.env.example` ke 30 missing prod keys sync karo

---

## 7. Verification checklist for each phase

Har phase ke baad, CLAUDE.md §6 DoD:
- [ ] duplicate-route grep clean
- [ ] targeted pytest green
- [ ] `scripts\prod_check.py` PASS
- [ ] `scripts\check_secrets.py` clean diff
- [ ] `/health` → `environment: production`, `version` == deployed sha (never `latest`)
- [ ] Phase 3 ke liye additionally: `scripts/agent_tester.py` scorecard

**Koi bhi phase compliance gate weaken nahi karta** — DND fail-closed, TRAI window, AI-disclosure, consent ledger, DLT gate, secrets-in-.env-only: sab untouched.
