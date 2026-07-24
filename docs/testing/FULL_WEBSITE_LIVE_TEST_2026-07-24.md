# FULL WEBSITE LIVE TEST — 2026-07-24

## 1. Outcome
**PARTIAL — production-proven unauth surface crawl + P1 OpenClaw intent fix Draft PR; authenticated role matrix BLOCKED without credentials.**

Labels used below: `LIVE_IN_PRODUCTION` | `MERGED_ON_MAIN_NOT_DEPLOYED` | `LOCAL_FIX_ONLY` | `DRAFT_PR` | `BLOCKED`

## 2. Truth
| Item | Value | Label |
|---|---|---|
| Prod `/health` | `7cab5f60` healthy · production | LIVE_IN_PRODUCTION |
| origin/main | `5199b24` (PR #112 merge) | MERGED_ON_MAIN_NOT_DEPLOYED |
| PR #112 | MERGED 2026-07-24T03:27:20Z → `5199b24` — **not reopened** | MERGED_ON_MAIN_NOT_DEPLOYED |
| Main tip vs prod | `5199b24` ahead of `7cab5f60` | MERGED_ON_MAIN_NOT_DEPLOYED |
| Calling | HARD OFF (`PLATFORM_DIAL_DAILY=0`) | LIVE_IN_PRODUCTION |
| OpenClaw Stage A | ON at prod (prior canary); unauth UI badge shows OFF until login | LIVE_IN_PRODUCTION |

## 3. VPS read-only
| Service | Image tag | APP_VERSION | Health | Restarts | OOM |
|---|---|---|---|---|---|
| app | `:7cab5f60` | 7cab5f60 | healthy | 0 | false |
| worker | `:7cab5f60` | 7cab5f60 | healthy | 0 | false |
| scheduler | `:7cab5f60` | 7cab5f60 | healthy | 0 | false |
| worker-heavy | `:7cab5f60` | 7cab5f60 | healthy | 0 | false |
| worker-video | `:7cab5f60` | 7cab5f60 | healthy | 0 | false |

Queues: `celery=0` `heavy=0` `video=0` `dlq:failed_tasks=0` `dlq:dead=0`.

## 4. Phase B — Dirty merged-source worktrees

External backup root: `C:\Users\Ratanshila\Documents\_leadgen_wt_backup_2026-07-24\`

### leadgen-dist-cancel (`docs/distributed-cancellation-production-proof` @ `20d8992`)
| Artifact | Class |
|---|---|
| Proof docs (family on main via #109 `c248168`) | ALREADY_MERGED |
| Tip commit `20d8992` (not ancestor of main) | OBSOLETE (content family merged; SHA unique) |
| `_ci_key.txt` (0 bytes, empty) | SECRET_OR_CREDENTIAL_RISK path — **deleted** (empty; no rotation needed — no exposure of contents) |
| `tmp_*.sh` / `tmp_*.py` / `_job_logs.txt` | TEMPORARY_GENERATED — **deleted** after backup |
| Worktree remove | BLOCKED (`git branch -d` would fail; unique tip SHA) |

Status after cleanup: **clean working tree**.

### leadgen-nikhil-flag (`docs/nikhil-production-canary-proof` @ `8151257`)
| Artifact | Class |
|---|---|
| Proof docs (family on main via #110 `71baf70`) | ALREADY_MERGED |
| Tip commit `8151257` | OBSOLETE (content family merged) |
| Staged `tmp_*` canary/deploy scripts | TEMPORARY_GENERATED / RUNTIME_OR_CANARY_PROOF — **deleted** after backup; no secrets found in prior audit |
| Worktree remove | BLOCKED |

Status after cleanup: **clean working tree**.

### leadgen-omniroute-governance (`codex/omniroute-governance` @ `1e2d014`)
| Artifact | Class |
|---|---|
| Merged governance via #108 | ALREADY_MERGED |
| Uncommitted `dry_rehearsal` + `--dry-run` + tests + training docs | VALID_UNMERGED_CODE / VALID_UNMERGED_TEST — **preserved** → Draft PR #113 |
| WT tip vs main huge divergence | OBSOLETE fork tip — do not merge tip as-is |
| Wrong authority assertions in dirty `test_omniroute_governance.py` (`free-coding-safe`) | OBSOLETE / REGRESSION risk — **not** ported |
| WT dirt reset | BLOCKED this session (auto-clean gate); backup + PR #113 exist |

## 5. Full Website Coverage Matrix (first-party)

Probe file: `docs/testing/_probe_unauth_routes_2026-07-24.json` — **71/71 HTTP 200** unauth.

| Route | Unauth HTTP | Browser | Auth role matrix | Notes |
|---|---|---|---|---|
| `/` | 200 | OK (390×844) | n/a | CSP/PostHog P2 |
| `/pricing` | 200 | — | n/a | |
| `/start` | 200 | — | n/a | |
| `/audit` | 200 | — | n/a | |
| `/site-audit` | 200 | — | n/a | |
| `/geo-check` | 200 | — | n/a | |
| `/demo` | 200 | — | n/a | |
| `/voice-agent` | 200 | — | n/a | |
| `/compare` | 200 | — | n/a | |
| `/privacy` | 200 | — | n/a | |
| `/terms` | 200 | — | n/a | |
| `/refund` | 200 | — | n/a | |
| `/reseller` | 200 | — | n/a | |
| `/status` | 200 | — | n/a | |
| `/blog` | 200 | — | n/a | |
| `/health` | 200 | — | n/a | version `7cab5f60` |
| `/robots.txt` | 200 | — | n/a | |
| `/sitemap.xml` | 200 | — | n/a | |
| `/llms.txt` | 200 | — | n/a | |
| `/manifest.json` | 200 | — | n/a | |
| `/sw.js` | 200 | — | n/a | |
| `/pricing.md` | 200 | — | n/a | |
| `/for/salon` | 200 | — | n/a | |
| `/for/clinic` | 200 | — | n/a | |
| `/b/jiya-makeover` | 200 | — | n/a | public mini-site |
| `/app/login` | 200 | OK | customer entry | |
| `/app/admin-login` | 200 | — | admin entry | |
| `/app/customer` | 200 shell | — | BLOCKED auth | API gated |
| `/app/customer/marketing` | 200 | — | BLOCKED | |
| `/app/customer/flows` | 200 | — | BLOCKED | |
| `/app/customer/voice` | 200 | — | BLOCKED | |
| `/app/customer/pipeline` | 200 | — | BLOCKED | |
| `/app/customer/office` | 200 | — | BLOCKED | |
| `/app/admin` | 200 shell | OK unauth | BLOCKED auth | OpenClaw OFF badge unauth |
| `/app/admin/db` | 200 | — | BLOCKED | |
| `/app/owner` | 200 | — | BLOCKED | Owner OS |
| `/app/office` | 200 | — | BLOCKED | |
| `/app/automation` | 200 | — | BLOCKED | read-only mandate |
| `/app/inbox` | 200 | — | BLOCKED | Hot Queue |
| `/app/analytics` | 200 | — | BLOCKED | |
| `/app/agents` | 200 | — | BLOCKED | |
| `/app/ops` | 200 | — | BLOCKED | |
| `/app/team-access` | 200 | — | BLOCKED | |
| `/app/brain` | 200 | — | BLOCKED | |
| `/app/voice-keys` | 200 | — | BLOCKED | |
| `/app/calendar` | 200 | — | BLOCKED | |
| `/app/deals` | 200 | — | BLOCKED | |
| `/app/segments` | 200 | — | BLOCKED | |
| `/app/studio` | 200 | — | BLOCKED | |
| `/app/onboard` | 200 | — | BLOCKED | |
| `/app/impersonate` | 200 | — | BLOCKED | |
| `/app/test-call` | 200 | — | BLOCKED | no real calls |
| `/app/team` | 200 | — | BLOCKED | |
| `/app/marketing` | 200 | — | BLOCKED | |
| `/app/whatsapp` | 200 | — | BLOCKED | no send |
| `/app/minisite-builder` | 200 | — | BLOCKED | |
| `/app/outreach` | 200 | — | BLOCKED | |
| `/app/clients` | 200 | — | BLOCKED | |
| `/app/assistant` | 200 | — | BLOCKED | |
| `/app/journeys` | 200 | — | BLOCKED | |
| `/app/growth-tools` | 200 | — | BLOCKED | |
| `/app/command-center` | 200 | — | BLOCKED | |
| `/app/delivery-command-center` | 200 | — | BLOCKED | |
| `/app/dev-control` | 200 | — | BLOCKED | |
| `/app/dashboards` | 200 | — | BLOCKED | |
| `/app/agent-tools` | 200 | — | BLOCKED | |
| `/app/conversations` | 200 | — | BLOCKED | |
| `/app/dialer` | 200 | — | BLOCKED | calling HARD OFF |
| `/app/battlecard` | 200 | — | BLOCKED | |
| `/app/explorer` | 200 | — | BLOCKED | |
| `/app/control-center` | 200 | — | BLOCKED | |

### API auth gates (unauth)
| Method | Path | Status |
|---|---|---|
| GET | `/api/owner-copilot/status` | 401 |
| POST | `/api/owner-copilot/nl` | 401 |
| GET | `/api/admin/owner-os/inventory` | 401 |
| GET | `/api/activation/summary` | 200 (public) |
| GET | `/health` | 200 |

## 6. OpenClaw Language Safety phrase table

| Phrase | Expected | Observed (code @ main/prod lineage) | Post-fix Draft #114 |
|---|---|---|---|
| Enable calling | RED `calling.enable` | **GREEN** `platform.status` (P1 DEF-001) | RED |
| calling enable | RED | RED | RED |
| enable calls | RED | **GREEN** | RED |
| start calling | RED | **GREEN** | RED |
| Call chalu karo | RED | RED | RED |
| platform_dial on | RED | RED | RED |

Live authenticated execute=false canary on prod UI: **BLOCKED** (no credentials). Auth gate 401 proven. Unit matrix 11/11 green on fix branch.

## 7. Defects summary
See `docs/testing/FULL_WEBSITE_DEFECTS_2026-07-24.json`.
- P0: 0
- P1: 1 → Draft PR #114
- P2: 2
- P3: 1

## 8. Draft PRs (do not merge/deploy)
1. https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/113 — OmniRoute dry-rehearsal preserve
2. https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/114 — OpenClaw Enable calling RED synonyms

## 9. What was NOT done (by mandate or block)
- No prod deploy, no PR merge, no Stage B, no calling enable
- No billing / Jiya mutation / social publish / WhatsApp / real calls
- No force-push / reset --hard / clean -fd / git add -A
- No `.agents/skills` junction recreate
- Authenticated customer/admin/super_admin deep card crawl

## 10. Verification evidence
- `/health` = `7cab5f60` healthy (multiple probes)
- Queues all 0
- `pytest` OpenClaw phrase matrix: 11 passed
- OmniRoute `test_governor_model_review.py`: 10 passed (on preserve branch)
- Unauth route probe: 71 pass / 0 fail

## 11. Risks
- P1 misclassification is **intent** defect; GREEN path was read-only `platform.status` (not enable calling), but must stay RED for defense-in-depth.
- Auth matrix gap means video/media tenant isolation + Owner OS bypass not re-proven live this session.

## 12. Remaining
1. Credentialed auth matrix (customer Jiya RO, admin, super_admin)
2. Viewport 1440×900 + 1024×768 completion
3. Owner authorize WT removals / OmniRoute dirt reset
4. Review+merge Draft PRs when ready (still no deploy unless asked)

## 13. Exact Next Action
**Owner:** (a) review Draft PR #114 for OpenClaw RED synonyms; (b) provide disposable canary login so Phase C auth matrix + live OpenClaw phrase canaries can finish on prod `7cab5f60` without printing secrets.
