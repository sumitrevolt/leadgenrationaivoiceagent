# Deploy Checklist + Hermes Harness + Merge-Gate / Deploy-Authority / DSH Reconciliation

**Repo:** `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent`
**Local HEAD (unmodified by this work):** `20e4180b` · **Prod `/health`:** `95245ce8` (environment=production)
**Author:** Rex (SRE Engineer) · Engineering Assurance Team
**Date:** 2026-09-14 · **Method:** working-tree edits + read-only prod/VPS/GitHub inspection. **Nothing committed, pushed or deployed.**
**Evidence labels used:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

> **Read this first.** Every change below is an **uncommitted working-tree edit** → labelled `CODE-PRESENT (working tree, uncommitted)`. It becomes `TEST-PROVEN` only after CI runs it on a commit. No deploy was performed or triggered.

---

## 0. HEADLINE — two P0s, one of which is worse than the reported one

| # | Finding | Evidence | Label |
|---|---------|----------|-------|
| **P0-A** | **`main` has NO branch protection and NO ruleset — ZERO required status checks.** The merge gate is not merely *defective*; it is **unenforced**. Any PR can merge with fully red CI. | `GET /repos/sumitrevolt/leadgenrationaivoiceagent/branches/main` → `protection.enabled=false`, `required_status_checks.enforcement_level="off"`, `contexts=[]`; `GET .../rulesets` → `[]`; org rulesets → 404 | `PRODUCTION-PROVEN` |
| **P0-B** | **Two divergent release mechanisms.** `deploy-vps.yml`'s `deploy` job SSHes to a root wrapper (`/usr/local/sbin/leadgen-deploy-release`) that **pulls a GHCR image and never calls `scripts/deploy_vps.sh`** — so it silently skips the canonical script's runtime-data guard, `prod_check --deployment`, ff-only checkout advance, **5-service anti-skew rollout**, **`/health.version == <sha>`**, smoke suite and lineage retention. | VPS read: `/usr/local/sbin/leadgen-deploy-release` (3506 B) contains `docker compose pull` / `up -d --remove-orphans` / `alembic upgrade head` / `curl /health/ready` and **no** `deploy_vps` reference; canonical `/opt/leadgen/scripts/deploy_vps.sh` (27145 B) present | `PRODUCTION-PROVEN` |
| **P0-C** | **`auto-merge.yml` is armed and waits for nothing.** `allow_auto_merge=true` on the repo, and the workflow's `if:` checks only (a) the `auto-merge` **label is present** and (b) `draft == false`. GitHub native auto-merge merges "the moment required status checks pass" — and there are **zero**. ⇒ **applying the `auto-merge` label to any non-draft PR merges it immediately, with no CI at all.** The workflow is **half-installed**: its own header (`:11-13`) claims condition (b) protects it, and its setup block (`:15-18`) lists "protect `main`" — which was **never done**. | `repo.allow_auto_merge=true`; `branches/main/protection` → HTTP 404; `rulesets` → `[]`; `auto-merge.yml:32-34` `if:` = label + non-draft; `auto-merge.yml:40` `gh pr merge --auto --squash` | `PRODUCTION-PROVEN` |

**P0-A and P0-C are the same defect seen from two sides, and both are OWNER actions** (enable a `main` ruleset requiring the three contexts). I did **not** change GitHub settings — enabling protection could block every agent PR and the owner's auto-merge flow if a context does not report, which is a high-blast-radius governance change that is not mine to make. Enabling the ruleset and keeping auto-merge enabled are **mutually dependent**: the ruleset is what makes `auto-merge` safe, and `auto-merge` is only safe once the ruleset exists.

---

## 0b. Root-cause chain — the answer to "fix one thing, break another"

Six layers, each independently verified. This is why the merge gate looked fine from the file and still let red code through.

| # | Layer | State | Evidence |
|---|-------|-------|----------|
| 1 | `ci.yml` aggregator **echoed** `pytest-job` instead of asserting it → a red lane could not fail the check | **FIXED** (this work) | `ci.yml` before: `echo "pytest-job=…"` with no `test …` |
| 2 | `main` has **no branch protection** → zero required checks, every gate advisory | **OPEN — owner action** | `branches/main/protection` → 404; `rulesets` → `[]` |
| 3 | `auto-merge.yml` **armed** with `allow_auto_merge=true` → the label = immediate merge, no CI | **OPEN — owner action** | `repo.allow_auto_merge=true`; `auto-merge.yml:32-34,40` |
| 4 | `deploy-vps.yml` SSH'd a wrapper that **bypassed the canonical script** → the green gate was not the last line of defence | **FIXED** (this work) | VPS wrapper read; `deploy-vps.yml` build/deploy jobs removed |
| 5 | `pytest-job` runs the whole suite and **4 tests were red for 10 days** → the lane was red the entire time | **FIXED** (Tessa, `11 passed` now) | reported by team-lead |
| 6 | **local `main` ≠ `origin/main` ≠ prod** → three codebases; "current" is undefined | **OPEN — owner decision** | merge base `071dc31b`; local `20e4180b` (1 commit origin lacks); `origin/main` `95245ce8` (2 commits local lacks); prod `95245ce8`. Surface = 5 files, +402/−53 |

**Read the chain top-down:** layer 1 made a red lane silent, layer 2 removed the requirement entirely, and layer 3 turned "removed the requirement" into "merges on a label". Any one of the three alone is survivable; together they are a merge path with no gate that *looks* gated.

---

## 1. Merge gate (P0 completion)

### What was already true at `20e4180b`
`ci.yml`'s required check `prod_check + pytest` (the `tests:` aggregator) asserted only `prod-check`, `pytest-job`, `pip-audit`. `harness-redis-integration` and `quality` were **not even dependencies**, so a red secrets-scan or a skipped real-Redis suite still produced a green aggregate.

### Per-job decision (each job was inspected, not assumed)

| Job | What it actually does | Decision | Why |
|-----|----------------------|----------|-----|
| `quality` ("Lint + syntax + secrets") | **Blocking:** `compileall`, `check_secrets.py`, `security_scan.py`, skill ratchet, queue-idempotency ratchet (`ci.yml:67-82`). **Non-blocking:** `mypy … \|\| true`, `ruff … \|\| true` (`ci.yml:83-88`). No job-level `continue-on-error`. | **ASSERT `success`** | It is a real gate — the only advisory steps are explicitly neutered **inside** the job with `|| true`, so the job result cannot go red for a cosmetic style reason. Asserting `success` is meaningful and cannot fail spuriously. |
| `harness-redis-integration` | Mandatory real-Redis gate; `HARNESS_REQUIRE_REDIS=1` turns "no Redis" into a failure and a `grep` guard converts a SKIPPED suite into a failure (`ci.yml:246-256`). | **ASSERT `success`** | A genuine gate with an anti-skip guard. Its only non-code failure mode is a **bounded, retried** Docker Hub pull (`ci.yml:210-232`) — and it was **already** a standalone required context, so asserting it here adds **no new flake surface**. |
| `pip-audit` | MUST-PASS installed-env CVE audit. | already asserted — unchanged | Real gate. |
| `pytest-job` | Network-free pytest, `-n auto`. | already asserted — **verified correctly placed inside the aggregator step**, not a stray line | Real gate. |
| `quality`'s `mypy` / `ruff` steps | Advisory only. | **stay advisory** (inside `quality`) | Promoting them would create a gate that fails for 1522 pre-existing type errors / style debt — a gate that fails spuriously. Not promoted. |

### Change applied
`.github/workflows/ci.yml`
- `needs:` now `[prod-check, pytest-job, pip-audit, quality, harness-redis-integration]` — **line 193**.
- Added assertions — **lines 208 & 210**: `test "${{ needs['quality'].result }}" = "success"` and `test "${{ needs['harness-redis-integration'].result }}" = "success"`.
- The job `name:` stays exactly `prod_check + pytest` (ruleset context string — must not be renamed).
- Header (`ci.yml:9-28`) now records the **verified** enforcement state (P0-A) instead of asserting a ruleset that does not exist.
- **YAML validated** (`yaml.safe_load`) and job list confirmed: `quality, prod-check, pip-audit, pytest-job, tests, harness-redis-integration`.
- **Label:** `CODE-PRESENT (working tree, uncommitted)`.

> **Do not create a gate that cannot fail, and do not create one that fails spuriously.** Both asserted jobs are real gates; the advisory steps are left advisory. That is the deliberate split.

### What still blocks the P0 (owner action)
Enable a `main` ruleset requiring exactly these three contexts (names must match the job `name:` strings verbatim):
`Lint + syntax + secrets` · `prod_check + pytest` · `harness real-redis integration`.

**This single action also closes P0-C.** Enabling the ruleset is not merely "make the aggregator required" — it is **the thing that makes `auto-merge.yml` safe**, because native auto-merge waits on required checks and currently has none to wait for. **The ruleset and auto-merge are mutually dependent:** the ruleset is what gives auto-merge something to wait for, and auto-merge is only safe once the ruleset exists.

**Stopgap if the owner wants a gate before touching repo settings:** turn auto-merge **OFF** (`Settings > General > Allow auto-merge = OFF`) — or simply stop applying the `auto-merge` label. Until one of those happens, the label is a silent-merge button.

---

## 1b. The live merge bypass — `auto-merge.yml` is armed and waits for nothing

| Property | Value | Label |
|----------|-------|-------|
| Repo flag | `allow_auto_merge = true` | `PRODUCTION-PROVEN` |
| `main` protection | HTTP 404 "Branch not protected" (no required checks) | `PRODUCTION-PROVEN` |
| Rulesets | `[]` (none) | `PRODUCTION-PROVEN` |
| Workflow `if:` | `contains(labels, 'auto-merge') && draft == false` (`auto-merge.yml:32-34`) | `CODE-PRESENT` |
| Workflow action | `gh pr merge --auto --squash` (`auto-merge.yml:40`) | `CODE-PRESENT` |
| Permissions | `contents: write`, `pull-requests: write` (it *can* merge) | `CODE-PRESENT` |

**⇒ Applying the `auto-merge` label to any non-draft PR merges it immediately, with zero CI requirement.**

**Why "half-installed" is the right frame.** The workflow's own header (`:11-13`) states the safety model: *"nothing merges unless (a) the owner explicitly labels it `auto-merge` AND (b) branch protection's required checks … are green."* **Condition (b) is void.** The setup block (`:15-18`) lists two prerequisites — "Allow auto-merge = ON" (**done**) and "protect `main`, require the Gate check" (**never done**). The token-saving automation is enabled; the gate it depends on was never installed. That is **worse than not having auto-merge at all**, because the file reads as if it has a gate.

**Two stale statements in the file, now corrected:**
- `:8` claimed *"deploy-vps.yml deploys automatically … with in-wrapper auto-rollback."* **False since P0-B was fixed** — I deleted the build/deploy jobs. Rewritten to point at the single authority, `scripts/deploy_vps.sh`.
- `:12` named the deploy-vps `gate` job as the required check. The merge authority is now the **`ci.yml` `tests` aggregator (5 lanes)**, not the deploy `gate` (which no longer gates a release, because deploy is manual). Corrected.

**Change applied — `.github/workflows/auto-merge.yml`:** added a prominent `🔴 (b) IS CURRENTLY VOID` block with the 404 / `rulesets=[]` / `allow_auto_merge=true` evidence, the half-installed framing, and the stopgap; rewrote the stale `:8`/`:12` statements; corrected the ONE-TIME SETUP block to name the three real contexts and mark step 2 `❌ NOT DONE`. YAML validated; job list unchanged (`enable-auto-merge`). **Label:** `CODE-PRESENT (working tree, uncommitted)`.

### Positive verification — no workflow can deploy except the one authority
Grepped every workflow for `docker/build-push-action`, `docker push`, `ghcr.io`, `deploy_vps.sh`, `ssh root@`, `appleboy/ssh`:
- `security-scan.yml` builds an image but with **`push: false` / `load: true`** (`security-scan.yml:234-235`) and its only permission is `contents: read` — it scans, it does not ship. ✅
- `packages: write` now appears **only inside a comment** in `deploy-vps.yml` — no workflow grants it. ✅
- `pr-factory-ci-repair.yml` explicitly excludes `deploy` / `deploy_vps.sh` / `DEPLOY_ENABLED` / prod SSH (`pr-factory-ci-repair.yml:17`). ✅

**⇒ The "one deploy authority" claim holds for images. The remaining gap is not deploy — it is MERGE.**

---

## 2. Hermes CI harness (new)

### The honest constraint
Hermes is a **local Windows desktop app** (Electron GUI + a machine-level backend on `127.0.0.1:9119`) that talks to an OmniRoute gateway on `127.0.0.1:20128`. GitHub-hosted runners are **Linux** and cannot launch the GUI, and cannot reach either loopback port. A job that tried would be **permanently red** (no GUI) or **permanently skipped** (no self-hosted runner) — both worse than no workflow.

### Chosen design: a **contract harness**, not a fake launch
`.github/workflows/hermes-harness.yml` + `scripts/hermes_harness_contract.py`.

| Property | Value |
|----------|-------|
| **Trigger** | `pull_request` + `push:main` on the Hermes surface (`docs/hermes/**`, the launcher scripts, the harness itself, `HERMES_CONTROL_PLANE.md`, `HERMES_AGENT_ROSTER.yaml`); **daily `cron 0 3 * * *`**; `workflow_dispatch` |
| **Permissions** | `contents: read` (least privilege — it only reads tracked files) |
| **Timeout** | 10 min (checks take seconds; the bound is a hang guard) |
| **Not permanently skipped** | The daily cron guarantees it runs even in weeks with no Hermes edits |
| **Not permanently red** | The blocking contract checks are deterministic and pass today (verified); the network leg is advisory |

**What it proves (blocking):**
1. Every Hermes profile has **both** `profile.yaml` and `config.yaml`, each valid YAML.
2. Every `config.yaml` pins the one gateway contract: `provider: omniroute`, `base_url: http://127.0.0.1:20128/v1`, `key_env: OMNIROUTE_API_KEY`.
3. Every `model.default` is a **real** OmniRoute id — a canonical `leadsgen combo N` or a known alias from `app/platform/omniroute_aliases.py`. An unknown id **fails** (fail-closed: never invent a route).
4. The launcher scripts still declare the documented ports **9119** (backend) / **20128** (gateway).
5. `docs/hermes/mcp_servers.json` still declares `leadgen_admin_harness`.

**What it does NOT prove (stated in the file):** GUI launch, and live `9119`/`20128` listeners — loopback-only, they need a Windows host. The advisory prod leg only proves the one publicly reachable health-triple endpoint, `https://leadsgenai.in/health` (and it is advisory because `uptime.yml` already owns prod liveness — so a transient blip cannot red the contract gate).

**Local run (evidence):** `python scripts/hermes_harness_contract.py` → `OK — Hermes integration contract intact`, `profiles discovered: 13`, `RC=0` → `LOCAL-ONLY` today; becomes `TEST-PROVEN` when the workflow runs on a commit.

### Hermes profile set delivered
Real config locations found: profiles live in-repo at `docs/hermes/profiles/<name>/{profile.yaml,config.yaml}`; the desktop installs them under `%LOCALAPPDATA%\hermes\profiles\<name>` (evidence: `deliverables/workbuddy/hermes-log-diagnosis-2026-08-29.md:216`, `scripts/ensure-hermes-backend.ps1:32`).

**Gap found:** 4 of 13 profiles had a `profile.yaml` but **no `config.yaml`** → no model/provider binding → they could not route. **Added** (each mirrors the established schema; model ids are **real aliases only**):

| Profile | `model.default` | Real alias → combo | Rationale |
|---------|-----------------|--------------------|-----------|
| `claude` | `claude-code` | `omniroute_aliases.py:54` → 1 | name match |
| `openclaw` | `hermes-ops` | `omniroute_aliases.py:46` → 5 | profile binds `as: devops` |
| `verdant` | `hermes-ops` | `omniroute_aliases.py:46` → 5 | profile binds `as: devops` |
| `workbuddy` | `hermes-ops` | `omniroute_aliases.py:46` → 5 | specialist executor / ops lane |

**Label:** `CODE-PRESENT (working tree, uncommitted)`. The **alias→profile mapping is a proposal** and is flagged for owner confirmation — aliases are documented as display/consistency only, never a routing authority.

---

## 3. One deploy authority (P0-B)

**Declared single authority:** **`scripts/deploy_vps.sh`, run on the VPS from `/opt/leadgen`.**

```
cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &
# poll /tmp/dep.log ; DRY_RUN=1 prints the plan and changes nothing
```

**Change applied — `.github/workflows/deploy-vps.yml` (now structurally gate-only):**
- Workflow renamed to **`deploy-vps (gate-only)`** (line 22) so the Actions UI states the posture.
- **Deleted the `build:` and `deploy:` jobs entirely** (the GHCR-push + SSH-wrapper path). The workflow is now **structurally incapable** of publishing an image or touching the VPS — this is enforcement, not documentation. Remaining jobs: `gate`, `pytest-shards`, `release-gate`.
- Removed the `packages: write` grant; no job now references `VPS_HOST / VPS_USER / VPS_SSH_KEY / GHCR_PAT / VPS_DEPLOY_USER / VPS_SSH_KEY_DEPLOY`.
- An honest rationale block (lines 156-187) records **why**, names the canonical authority, and states that re-adding a deploy job here is an owner decision that **must** invoke `scripts/deploy_vps.sh`.
- **YAML validated**; job list confirmed: `['gate', 'pytest-shards', 'release-gate']`.
- **Label:** `CODE-PRESENT (working tree, uncommitted)`.

**Why this and not the wrapper:** the wrapper's only guarantees are *pull + up + alembic + `/health/ready`*. The script additionally enforces the runtime-data guard, the deployment gate, ff-only advance, the 5-service anti-skew rollout, **`/health.version == sha`**, the smoke suite and lineage retention. Keeping both was the ambiguity; `AGENTS.md §3` already forbids hand-written docker deploys, so the CI path was a bypass. **Label:** `PRODUCTION-PROVEN` (VPS wrapper read).

`DEPLOY_ENABLED` is unset, so the CI deploy path had never executed — removing it takes away a **live bypass** with no loss of working capability.

---

## 4. DSH reconciliation — the truth is **OPEN**, and the docs were STALE

**Live read-only probe, 2026-09-14T14:11:40Z (prod `95245ce8`):**

| Probe | Result |
|-------|--------|
| `/health` | `"dsh_runtime_enabled":true,"dsh_shadow_enabled":true,"dsh_allowlist":["jiya_makeover"]` |
| `docker exec leadgen_app printenv DSH_RUNTIME_ENABLED DSH_SHADOW_ENABLED DSH_AGENT_ALLOWLIST` | `1` / `1` / `internal` |
| `docker exec leadgen_dsh_worker printenv …` | `DSH_RUNTIME_ENABLED=1`, `DSH_SHADOW_ENABLED=1`, `APP_VERSION=95245ce8` |
| `leadgen_dsh_worker` image | `leadgen-dsh-worker:95245ce8` (in lockstep with `leadgen_app`) |

**Label:** `PRODUCTION-PROVEN`.

**The contradiction and its resolution.** `docs/context/ACTIVE_WORK.md:34` documented `DSH_RUNTIME_ENABLED=0 (fail-closed)`; `AGENTS.md:135` said the gates "OFF rahenge". **Both were STALE.** Production is **armed** (`=1`) with a **narrow single-agent allowlist** `["jiya_makeover"]` and shadow **on**.

**I chose to fix the DOC, not prod.** Reasons:
1. The open state is **owner-authorized** — `memory/decisions.md` (ADR-183) records the owner authorizing `DSH_RUNTIME_ENABLED=1`; PHASE0 §4 lists the arm as an owner gate that the owner has now exercised. This is an **under-documented** open gate, not an **unauthorized** one.
2. Changing prod is a deploy and an owner scope change; my mandate is read-only on prod.
3. Fail-closed is the correct **default** posture, and the *narrow allowlist* + shadow mode are the mitigating controls — so the honest finding is "docs stale", not "gate broken".

**Changes applied:**
- `docs/context/ACTIVE_WORK.md:34` — corrected to the probed truth (runtime+shadow armed, allowlist `["jiya_makeover"]`, dsh-worker in lockstep).
- `AGENTS.md:135` **and** `CLAUDE.md:135` — identical correction (the byte-copy test `tests/test_1000_engineers_skill.py:67` requires the two files to stay byte-identical; verified: both **37,556 B**, `cmp` = IDENTICAL, test PASS).
- **Label:** `CODE-PRESENT (working tree, uncommitted)`.

**Residual owner gates (unchanged):** promoting agents beyond `jiya_makeover`, widening the allowlist, and retiring the legacy direct executor.

---

## 5. Customised pre-deploy checklist (this repo)

Run from `/opt/leadgen` **on the VPS**. Every item maps to a real guard in `scripts/deploy_vps.sh`.

### 5.1 Pre-deploy (before anything moves)
- [ ] **Announce the window**; confirm no second writer is mid-release (five writers share this tree — `docs/context/CONCURRENT_WORKER_COLLISION_2026-09-10.md:74-79`).
- [ ] **Disk headroom:** `df -h /` ≥ 20% free. The script hard-stops at ≥90% and warns at ≥80% (`deploy_vps.sh:146-160`).
- [ ] **Target SHA is explicit and immutable** — never `latest`/`dev`/`1.0.0` (`deploy_vps.sh:87-94`). Record it.
- [ ] **Prod/live divergence is known:** confirm whether the candidate is a descendant of the live HEAD (a non-descendant deploy can revert prod-only commits — see the LINEAGE WARNING in `AGENTS.md`).
- [ ] **Runtime-data guard helpers present** — `_deploy_gate_container.sh`, `_deploy_candidate.sh`, `_runtime_data_guard.sh`; the script exits **91** if any is unreadable (`deploy_vps.sh:57-68`). Exit 90 = guard denied.
- [ ] **`DRY_RUN=1 bash scripts/deploy_vps.sh`** first — prints the plan, the disk guard, the build-cache preview and the retention preview, and changes nothing (`deploy_vps.sh:162-176`).
- [ ] **Compliance gates untouched:** `DND_FAIL_OPEN` unset/false, `COMPLIANCE_ENABLED` on, `VOICE_LAUNCH_KILL=0`, DLT approved. **Any change here is an ABORT, not a fix.**

### 5.2 Deploy (the canonical path)
- [ ] Isolated candidate worktree materialised; candidate tree proven at exactly the release SHA (`deploy_vps.sh:96-134`).
- [ ] Gate-environment proof (booleans only) passes — exit **92** otherwise (`deploy_vps.sh:112-120`).
- [ ] Build from the **candidate** worktree succeeds (`/tmp/deploy_build.log`); image `…:<sha>` exists (`deploy_vps.sh:178-214`).
- [ ] **Deployment gate:** `prod_check.py --deployment` in the candidate image passes (`deploy_vps.sh:216-228`).
- [ ] **ff-only** advance of the live checkout to the gated SHA; refusal if it moved/dirtied (`deploy_vps.sh:230-250`).
- [ ] **5-service anti-skew rollout:** `app worker scheduler worker-heavy worker-video` **plus** `dsh-worker` all recreated (`deploy_vps.sh:32-34, 319-323`).
- [ ] **Alembic** `upgrade head` succeeds (`deploy_vps.sh:414-423`).

### 5.3 Post-deploy verification (evidence, not exit codes)
- [ ] **`/health.version == <deployed sha>`** within the bounded retry window (`deploy_vps.sh:427-464`). If it does not match, the deploy is **NOT** successful — do not report it as one.
- [ ] **Per-container skew check:** every app-image service reports `APP_VERSION == <sha>` and image tag ends `:<sha>` (`deploy_vps.sh:470-498`).
- [ ] **Smoke suite** all 200: `/health / /audit /site-audit /demo /pricing /start /app/inbox /api/public/audit/questions /api/voice/niches /api/billing/plans /api/public/pay-info` (`deploy_vps.sh:500-505`).
- [ ] **Queues/DLQ:** `celery` and `dlq:failed_tasks` depths sane (`deploy_vps.sh:507-509`).
- [ ] **Retention ran only after verification** (lineage-aware; never `rmi -f`) (`deploy_vps.sh:511-605`).

### 5.4 Abort triggers (stop and roll back)
- `/health.version` never equals the deployed SHA → **exit 3**.
- Any service reports a different `APP_VERSION`/image tag → **exit 4** (skew).
- Alembic fails → **exit 1** (refuse to verify a schema-stale deploy).
- Runtime-data guard denies → **exit 90**; guard unavailable → **exit 91**; gate-env proof fails → **exit 92**.
- Any compliance gate would be weakened → **ABORT unconditionally**.

---

## 6. Security risk notes

1. **Governance (highest):** `main` is **public** and **unprotected** — no required checks, no CODEOWNERS enforcement (`CODEOWNERS` is INERT until "Require review from Code Owners" is enabled). Anyone with write access can land anything, and **`allow_auto_merge=true` turns the `auto-merge` label into a no-CI silent-merge button (P0-C)**. **Owner action.**
2. **Release bypass (high, now closed in the tree):** the CI deploy path bypassed the canonical script's runtime-data guard and anti-skew checks. Removing `build`/`deploy` closes it — but only once committed.
3. **DSH authority (medium, mitigated):** runtime is armed in prod. Mitigations: single-agent allowlist (`jiya_makeover`), shadow mode on, documented owner authorization. The risk was **stale documentation**, now corrected.
4. **Secret hygiene:** no secret values were printed. Env inspection was **names-only**; `DSH_*` values shown are **booleans/allowlist**, not secrets. (`_work/rex_h2.txt` shows Hermes `.env` keys redacted.)
5. **Least privilege improved:** `deploy-vps.yml` no longer requests `packages: write`; `hermes-harness.yml` requests only `contents: read`.
6. **Not weakened:** no compliance gate (TRAI DND, consent ledger, DPDP, opt-out suppression, tenant isolation) was touched, and no security check was disabled to make CI green.

---

## 7. CI status

| Workflow | State | Note |
|----------|-------|------|
| `ci.yml` | `CODE-PRESENT` (uncommitted); YAML valid | aggregator now asserts 5 lanes; **still not enforced** (P0-A) |
| `deploy-vps.yml` | `CODE-PRESENT` (uncommitted); YAML valid | gate-only; cannot deploy |
| `hermes-harness.yml` | `CODE-PRESENT` (new, uncommitted); YAML valid | will run on PR/push + daily cron |
| `auto-merge.yml` | `CODE-PRESENT` (uncommitted); YAML valid | comments corrected (stale `:8`/`:12`); **armed and waits for nothing** until P0-A is fixed |
| all 12 workflows | YAML valid | verified with `yaml.safe_load` |
| `tests/test_1000_engineers_skill.py` | `TEST-PROVEN` | PASS (AGENTS/CLAUDE byte-identity) |
| `scripts/hermes_harness_contract.py` | `LOCAL-ONLY` | `RC=0`, 13 profiles, contract intact |

**No CI run has been triggered by this work** (nothing committed). CI status for these changes is therefore **`UNKNOWN` until committed.**

---

## 8. Go / No-Go

| Scope | Decision | Rationale |
|-------|----------|-----------|
| **Deploy of these changes to prod** | **NO-GO** | Not my call and not needed: the changes are CI/governance/doc + local-only profile configs. Prod is healthy at `95245ce8`; a deploy would be risk without reward. |
| **Merge of these changes (once reviewed)** | **GO (conditional — TWO conditions)** | All YAML valid; the contract harness passes locally; the byte-copy test passes. **Condition 1:** the owner enables the `main` ruleset (P0-A), otherwise the improved aggregator is still unenforced. **Condition 2:** the auto-merge dependency (P0-C) is reconciled — either the ruleset from Condition 1 is in place (which makes `auto-merge` safe) **or** auto-merge is turned OFF as the stopgap. Condition 1 alone fixes the aggregator; only Condition 2 stops the label from being a silent-merge button. |
| **Merging via the `auto-merge` label** | **NO-GO until P0-A/P0-C resolved** | With zero required checks, the label merges immediately with no CI. Do not apply it until a ruleset exists. |
| **Enabling `main` branch protection** | **OWNER GO required** | High blast radius (could block all agent PRs if a context never reports). Explicitly **not** done by me. |
| **Prod DSH change** | **NO-GO** | Correct posture already in place (narrow allowlist + shadow); the defect was documentation. |
| **Canonical deploy (`scripts/deploy_vps.sh`)** | **GO when the owner schedules it** | Unchanged and still the sole authority. |

---

## 9. Rollback plan

**These changes** — all uncommitted working-tree edits. Rollback = discard the working-tree changes (or `git checkout -- <path>` per file). No prod impact, so no prod rollback is required. Files:
`.github/workflows/ci.yml` · `.github/workflows/deploy-vps.yml` · `.github/workflows/auto-merge.yml` · `.github/workflows/hermes-harness.yml` (new) · `scripts/hermes_harness_contract.py` (new) · `docs/hermes/profiles/{claude,openclaw,verdant,workbuddy}/config.yaml` (new) · `docs/context/ACTIVE_WORK.md` · `AGENTS.md` · `CLAUDE.md`.

**A real production deploy** (if one is ever run via the canonical script) rolls back through the script's own lineage mechanism:
1. The script captures `PREV_PROD_TAG` **before** replacing anything and writes a durable rollback tag to `/var/lib/leadgen/deploy_rollback_lineage.json` (`deploy_vps.sh:350-392, 511-550`).
2. **Runtime flag rollback** (fastest, no image change): `DSH_RUNTIME_ENABLED=0` returns dispatch to the canonical direct executor (`memory/decisions.md`). Never a hand-written compose rollback.
3. **Image rollback:** re-run `scripts/deploy_vps.sh <previous-sha>` — the script builds, gates and anti-skews the older SHA. **Never `:latest`**, never `docker compose up` by hand.
4. Retention is lineage-aware and refuses destructive cleanup on skewed/missing/malformed tags, so the rollback image is protected.

---

## 10. Changes manifest (file:line · evidence label)

| File | Change | Label |
|------|--------|-------|
| `.github/workflows/ci.yml:9-28` | header now states the **verified** enforcement state (P0-A) | `CODE-PRESENT` |
| `.github/workflows/ci.yml:193` | aggregator `needs:` += `quality`, `harness-redis-integration` | `CODE-PRESENT` |
| `.github/workflows/ci.yml:208,210` | assert both lanes = `success` | `CODE-PRESENT` |
| `.github/workflows/deploy-vps.yml:22` | renamed `deploy-vps (gate-only)` | `CODE-PRESENT` |
| `.github/workflows/deploy-vps.yml:156-187` | rationale block; `build:`+`deploy:` jobs removed | `CODE-PRESENT` |
| `.github/workflows/hermes-harness.yml` (new) | contract gate: PR/push + daily cron + dispatch; `contents: read`; 10 min | `CODE-PRESENT` |
| `scripts/hermes_harness_contract.py` (new) | profile/config/port/MCP contract; fail-closed on unknown model | `LOCAL-ONLY` (RC=0) |
| `docs/hermes/profiles/claude/config.yaml` (new) | `claude-code` | `CODE-PRESENT` |
| `docs/hermes/profiles/openclaw/config.yaml` (new) | `hermes-ops` | `CODE-PRESENT` |
| `docs/hermes/profiles/verdant/config.yaml` (new) | `hermes-ops` | `CODE-PRESENT` |
| `docs/hermes/profiles/workbuddy/config.yaml` (new) | `hermes-ops` | `CODE-PRESENT` |
| `docs/context/ACTIVE_WORK.md:34` | DSH corrected to probed truth | `CODE-PRESENT` |
| `AGENTS.md:135` + `CLAUDE.md:135` | DSH corrected; byte-identity preserved (37,556 B each) | `CODE-PRESENT` / `TEST-PROVEN` (identity test) |
| `.github/workflows/auto-merge.yml:4-27` | stale `:8`/`:12` corrected; `🔴 (b) IS CURRENTLY VOID` warning + stopgap added; setup block corrected | `CODE-PRESENT` |
| `.github/workflows/auto-merge.yml:32-34,40` | `if:` = label + non-draft; `gh pr merge --auto --squash` (the bypass, unchanged — documented) | `CODE-PRESENT` |
| GitHub repo flag | `allow_auto_merge=true` → label = immediate merge (P0-C) | `PRODUCTION-PROVEN` |
| VPS `/usr/local/sbin/leadgen-deploy-release` | inspected (does not call `deploy_vps.sh`) | `PRODUCTION-PROVEN` |
| GitHub `main` protection | none; `enforcement_level=off` | `PRODUCTION-PROVEN` |
| Prod DSH flags | runtime=1, shadow=1, allowlist `["jiya_makeover"]` | `PRODUCTION-PROVEN` |

**Not done (out of mandate):** no commit, no push, no deploy, no GitHub settings change, no prod mutation, no compliance-gate change.
