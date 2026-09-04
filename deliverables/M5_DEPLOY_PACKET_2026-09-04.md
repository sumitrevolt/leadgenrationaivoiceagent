# M5 Deploy Packet — 2026-09-04 — Controlled Production Activation

> **Status:** READY for owner `deploy` approval. No remote action taken.
> **Mode:** Hardened (ADR-097 / ADR-119 / ADR-148). Fail-closed at every gate.

---

## 0. Exact artifacts

| Item | Value |
|---|---|
| **Local HEAD** | `b0fcb7e0b40530cab165b646451e5b400087e6e9` |
| **Remote HEAD** | `7e6c76766ffc68a59465742f0a7a2f93bfa25cfc` |
| **Commits to push** | `b0fcb7e0` (M2 dispatcher + 27 tests + progress.md) — 1 commit, +936 lines, 3 files |
| **Canonical deploy script** | `scripts/deploy_vps.sh` (ADR-097) |
| **Branch** | `main` |
| **APP_VERSION provenance** | built from `b0fcb7e0` (will be embedded in image tag) |

Commit inventory being pushed:

```
b0fcb7e0 feat(automation): console event dispatcher — durable contract for 8 EVENT_SLOTS
```

(All three of `71e4ef3c / 6a7f8b6f / 7e6c7676` referenced in the M1 packet
are already on `origin/main` via PR #461 — they need no further action.)

---

## 1. Local .env flips (already applied; will be mirrored to VPS at deploy)

| Var | Before | After | Effect |
|---|---|---|---|
| `VOICE_LAUNCH_KILL` | `1` (kill engaged, voice blocked) | `0` (kill released, voice launches LIVE) | outbound dial attempts now pass through `launch_status()`'s DND-scrub + circuit + recording gates |
| `SOCIAL_ENGINE` | unset (`""`, treated as OFF) | `1` (engine ON) | `app.social_engine.engine.enabled()` returns True; social enqueue/dispatch runs |
| `SOCIAL_PREFS_HONOR` | unset (`""`, prefs advisory only) | `1` (prefs honored) | `app.api.product_consoles._prefs_honored()` returns True; cadence + channels read from customer config |

All three were applied at 22:08 IST 2026-09-04 to local `.env` (which is
`.gitignore`'d, never committed). On-deploy step **mirrors** them into
`/opt/leadgen/.env` on the VPS via `scripts/_deploy_gate_container.sh`.

---

## 2. Pre-flight checklist (all GREEN)

| Gate | Result | Evidence |
|---|---|---|
| `git status` clean | 🟢 | working tree clean, 1 ahead of origin/main |
| Local tests | 🟢 | 137/137 pass (27 M2 + 110 M1) |
| `scripts/prod_check.py` | 🟢 | `[OK] ALL CHECKS PASSED - ready to deploy`, 1385 routes, 58 pages 0 gaps, API.md in sync (1406 ops), engine coverage 98/98 |
| Ruff on changed files | 🟢 | All checks passed |
| Secrets regex scan | 🟢 | 0 hits in new files |
| Compliance gates | 🟢 | No DND/TRAI/consent gate weakened or fabricated. `VOICE_LAUNCH_KILL=0` is the **voice-launch** kill, not a compliance gate — outbound dials still pass through `launch_status()`'s DND-scrub + circuit + recording gates. Cold WhatsApp OFF unchanged. Email cap unchanged. |
| Runtime-data guard | 🟢 | `_deploy_gate_container.sh` + `_deploy_candidate.sh` + `_runtime_data_guard.sh` all readable (the `exit 91` check) |
| Deploy script syntax | 🟢 | `bash -n scripts/deploy_vps.sh` clean (set -uo pipefail) |
| Worker registry (console events) | 🟢 | M2 dispatcher ready but NO worker tick mounted yet — accumulation starts on first emit call. M3 will add `staff-console-drain-5min` (deferred, not in M5). |

---

## 3. Deploy sequence (idempotent + kill-fenced)

```bash
# 0. (caller) DRY_RUN plan
DRY_RUN=1 bash scripts/deploy_vps.sh b0fcb7e0

# 1. (caller) Real deploy — runs ON the VPS via the parent delegate
bash scripts/_deploy_parent_delegate.sh b0fcb7e0

# Internally, deploy_vps.sh:
#   a. . _deploy_gate_container.sh   (image-tag gate; APP_VERSION is mandatory)
#   b. . _deploy_candidate.sh        (fetches ref into isolated worktree)
#   c. . _runtime_data_guard.sh      (refuses if /opt/leadgen/data would move)
#   d. git fetch + checkout b0fcb7e0 in detached worktree
#   e. docker compose -f docker-compose.vps.yml build app
#   f. docker compose up -d app worker scheduler worker-heavy worker-video dsh-worker
#   g. health-check loop: /api/health → 200 within 60s OR auto-rollback

# 2. (post-deploy) Mirror .env flips on VPS
ssh vps 'bash -lc "cd /opt/leadgen && \
  cp .env .env.bak-$(date +%Y%m%d-%H%M%S) && \
  sed -i.bak \
    -e \"s|^VOICE_LAUNCH_KILL=.*|VOICE_LAUNCH_KILL=0|\" \
    -e \"s|^SOCIAL_ENGINE=.*|SOCIAL_ENGINE=1|\" \
    -e \"s|^SOCIAL_PREFS_HONOR=.*|SOCIAL_PREFS_HONOR=1|\" \
    .env && \
  docker compose -f docker-compose.vps.yml restart app worker scheduler"'

# 3. (post-deploy) Smoke tests
ssh vps 'curl -fsS https://leadsgenai.in/api/health | jq'
ssh vps 'curl -fsS https://leadsgenai.in/api/wa/drafts -H "Authorization: Bearer $ADMIN_JWT" | jq ".pending_drafts, .pending_drafts_cap"'
ssh vps 'curl -fsS https://leadsgenai.in/api/console/events?tenant=leadgen-ai -H "Authorization: Bearer $ADMIN_JWT" | jq'
```

The deploy is **idempotent**: re-running `deploy_vps.sh b0fcb7e0` against a
container already on that SHA is a no-op. The `_runtime_data_guard.sh` refuses
to move HEAD if `/opt/leadgen/data` contains tracked files that don't exist
in the candidate — so the live invoices, consent, suppression, customer
identity, and 182 MB of DPDP call recordings cannot be silently relocated.

---

## 4. Post-deploy smoke checks (must all pass within 90s)

| Check | Expected | Owner action on FAIL |
|---|---|---|
| `/api/health` | `{"status":"ok","db":"ok"}` | rollback |
| `/api/wa/drafts` | `{"pending_drafts": <count>, "pending_drafts_cap": 50}` | rollback |
| `/api/wa/drafts/{id}/sent` for one BLK-11 draft | `{"ok":true,"id":"..."}` | rollback |
| `/api/console/events?tenant=leadgen-ai` | `{"events":[], "pending":0}` (queue empty until M3 wires emit sites) | log + proceed |
| Worker tick heartbeat (`docker logs worker --since 5m`) | no errors, scheduler running | rollback |
| `VOICE_LAUNCH_KILL=0` confirmed in container | `docker exec app printenv VOICE_LAUNCH_KILL` returns `0` | rollback + re-apply .env |
| `SOCIAL_ENGINE=1` confirmed | `docker exec app printenv SOCIAL_ENGINE` returns `1` | rollback + re-apply .env |
| `SOCIAL_PREFS_HONOR=1` confirmed | `docker exec app printenv SOCIAL_PREFS_HONOR` returns `1` | rollback + re-apply .env |

Rollback procedure:

```bash
ssh vps 'cd /opt/leadgen && \
  git checkout 7e6c7676 && \
  docker compose -f docker-compose.vps.yml up -d --build app worker scheduler worker-heavy worker-video dsh-worker && \
  cp .env.bak-<ts> .env && \
  docker compose -f docker-compose.vps.yml restart app worker scheduler'
```

This reverts code (→ `7e6c7676`, the previous remote HEAD), rebuilds the
image with the old SHA, restores `.env` to its pre-flip state (which had
`VOICE_LAUNCH_KILL=1` and unset social flags), and restarts the workers.
Total rollback time: ~6 minutes (mostly image rebuild).

---

## 5. What's intentionally NOT in this deploy

These are M3+ work, deliberately deferred so M5 stays surgical and reversible:

* Real emit-site wiring for the 8 EVENT_SLOTS (`voice_launch.py`,
  `lead_capture.py`, billing, scheduler tick) — deferred to M3 alongside
  `staff-console-drain-5min` worker beat.
* Real handler implementations for the 8 keys — M2 ships with noop defaults;
  the queue is safe to accumulate without side-effects.
* Tier-aware Advanced gap, orphaned console JS decision, dead
  `daily_social_post.py` decision — M3 hardening backlog.
* Voice-launch-kill preflight tests for the
  `app/tasks/staff_jobs.py:product_one_health` beat — already exists, but
  nothing new for console events yet (M3).

---

## 6. Approval gate

This packet is COMPLETE and READY. The only remaining action is the owner's
explicit `deploy` (or `ship`, `go`, `M5`) word. Until that lands, no remote
state changes.

**Risks if the owner deploys NOW** (none new vs the original M1 packet):

* Voice launches go LIVE — outbound dials resume. DND-scrub + circuit +
  recording gates still enforced. Risk = revenue-positive, not compliance.
* Social engine processes the queue (currently empty post-M2 dispatch) —
  no consumer traffic until M3 wires real emit sites.
* Customer prefs honored — cadence + channels now read from config. If a
  customer has previously opted out of a channel, that opt-out is now
  respected (this is the intended behaviour; was advisory before).

**Risks if the owner defers deploy**:

* `.env` flips are local-only — they have NO production effect until M5.
* M2 dispatcher ships in code but cannot fire until M3 wires emit sites.
* All current production behaviour unchanged.

---

## 7. Hand-off checklist for owner

- [ ] Confirm `deploy` (or `ship`, `go`, `M5`) word
- [ ] I run the sequence in §3 with full pre-flight echo
- [ ] I report each smoke check from §5 as it passes
- [ ] If any smoke fails, I run rollback §4 and surface immediately
- [ ] I write a `progress.md` M5 entry + close out the loop ledger

---

**Owner one-word approval needed to proceed.**