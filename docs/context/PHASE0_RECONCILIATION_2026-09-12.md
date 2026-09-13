# PHASE 0 RECONCILIATION — Master Directive (2026-09-12) vs Repo Truth

**Compiled:** 2026-09-12 15:58 IST · **By:** WorkBuddy AI (acting as team-lead Qi persona)
**Method:** read-only reconciliation of the incoming 19-section "final 24×7 architecture" directive against
actual repository + existing canonical records (`PHASE0_BASELINE.md`, `24X7_ARCHITECTURE_RECORD.md`,
`progress.md`, `AGENT_REGISTRY.md`). No files changed outside this document.
**Evidence labels:** PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN

---

## 0. HEADLINE

The incoming directive is **not a greenfield build**. The 24×7 migration is already substantially planned
(PHASE 0 + PHASE 1 DONE) and PHASE 4 (Owner Command Center) is already built and test-verified. The
remaining work is mostly **owner-gated** and one **architectural conflict** must be resolved by the owner
before any further build.

> **Critical conflict:** the directive mandates *"CENTRAL OMNIROUTE GATEWAY"* as a 24×7 dependency. The
> repo's frozen, owner-approved architecture (ADR-111 / ADR-189, `24X7_ARCHITECTURE_RECORD.md §8A) states
> the opposite: **OmniRoute lives on the owner's Windows desktop, is INERT in prod, and must stay an
> optimization lane — NOT a 24×7 dependency.** Promoting it to central gateway would *re-create* the exact
> desktop dependency the directive wants eliminated. See §3.

---

## 1. REPO / DEPLOY BASELINE (live, read-only)

| Field | Value | Label |
|---|---|---|
| Local branch | `fix/smartflo-stream-routing` | — |
| Local HEAD | `bfb824643a44` — *fix(smartflo): route AI stream calls on the active provider + honour the block contract*, 2026-09-12 13:22 IST | LOCAL-ONLY |
| Deployed (PROD) per PHASE0 | `0b848b34` — Smartflo call-drop root cause fix, 2026-09-09 | PRODUCTION-PROVEN |
| Working tree | 5 modified (incl `progress.md`, `data/leadgen_dev.db`) + 9 untracked (incl revenue reconcilation reports, scripts) | LOCAL-ONLY |
| Control plane | **DevTask** (`app/models/dev_task.py`) chosen canonical in PHASE1 freeze | CODE-PRESENT |

⚠️ Local HEAD (`bfb82464`, 09-12) is **ahead of** the PHASE-0 baseline commit `d0183bf1` and the prod tip
`0b848b34`. The directive's own PHASE1 freeze rule still applies: **base migration work on prod tip, not
local HEAD**, to avoid silently reverting the 15 prod-only commits.

---

## 2. DIRECTIVE §17 ACCEPTANCE CRITERIA — STATUS MATRIX

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Desktop apps optional/manual, not required for 24×7 | ✅ DONE (by design) | `24X7_ARCHITECTURE_RECORD.md §8A` accepts Hermes/Buzz/OpenClaw/WorkBuddy as owner-manual-only; `ACTIVE_WORK.md` WS-DSH `DSH_RUNTIME_ENABLED=0` fail-closed |
| 2 | Canonical central ledger = only task truth | 🟡 PARTIAL | DevTask canonical (PHASE1 §2); CC ledger + `command_center/state.js` frozen snapshot still exist, retire pending PHASE2 |
| 3 | Supervisor bots run headlessly via CLI/API | 🟡 PARTIAL | Celery `worker`/`scheduler` reuse chosen (§8A spine); `dev_workers` table + heartbeat spec written but **not yet populated**; 12/31 agents armed |
| 4 | Agent roster reconciled from repo/runtime | ✅ DONE | `team.py CANONICAL_COUNT=31`; 12 dispatchable / 19 non-dispatchable documented (`24X7_ARCHITECTURE_RECORD.md §4`) |
| 5 | 31-agent target mapped / discrepancies resolved | ✅ RESOLVED | 31 defined; bot→agent map (9 bots ← 31 agents) in PHASE1 §4; swara FROZEN |
| 6 | Bot → agent hierarchy visible | ✅ CODE-PRESENT | `frontend/team_dashboard.html` + `app/platform/team.py`; PHASE4 OCC Agents tile |
| 7 | Every worker has heartbeat | 🟡 PARTIAL | `dev_workers.heartbeat_ts` spec exists; 0 rows until a supervisor registers (honest "not instrumented" default) |
| 8 | Stale worker recovery works | 🟡 PARTIAL | `reconcile_leases()` spec + 600s lease + reap sweep defined; not yet wired to startup beat |
| 9 | Lease/retry/idempotency works | 🟡 PARTIAL | lease column exists; `service._IDEMPOTENCY` still process-local dict (must move to DB unique col per PHASE1 §2) |
| 10 | OmniRoute canonical routing authority | 🔴 CONFLICT | see §3 — owner decision required |
| 11 | 14 combos inventoried/dedup/health/dashboard | 🟡 PARTIAL | 14 `leadsgen combo N` defs confirmed (`seed_omniroute_14combos.py`); only 12 task routes mapped; per-combo health table `omniroute_combo_health.py` CODE-PRESENT but unpopulated; combo source-of-truth `.omniroute-cutover/combos.json` ABSENT (gitignored) |
| 12 | Model/provider secrets protected | ✅ ENFORCED | `omniroute_export_combos.py --redact` pattern; no keys in dashboards; secret scan passes on new files |
| 13 | Owner Command Center complete | ✅ DONE (build) | `app/api/owner_command_center.py` + `app/admin/*` (13 files) + `frontend/owner_command_center.html`; 60+ tests PASS (progress.md 2026-09-11) |
| 14 | Task Kanban reflects canonical ledger | 🟡 PARTIAL | Admin task_ledger SQLite CRUD+Kanban built; must be pointed at DevTask, not a second truth |
| 15 | Voice automation verified | ✅ PROD-PROVEN | `app/telephony/vobiz_stream.py` + `free_ai.py`; Dial-Ticket choke point gated (PHASE1 §12) |
| 16 | WhatsApp automation verified | ✅ PROD-PROVEN | `app/integrations/whatsapp*.py`; cold/bulk OFF by design |
| 17 | Email automation verified | ✅ PROD-PROVEN | `email_sender.py`; 25/day cap |
| 18 | Video automation verified | 🟡 PARTIAL | `video_ad_cycle.py`; customer isolation/approval pending |
| 19 | Social automation verified | 🟡 PARTIAL | Postiz + meta_graph; own-brand live, customer pages Meta-review blocked |
| 20 | Leadgen/CRM/follow-up verified | ✅ PROD-PROVEN | `prospector.py`, `crm_sync.py`, `hubspot.py` |
| 21 | Billing/payment/revenue truth | ✅ PROD-PROVEN | manual-UPI only; `owner_feed.py` evidence ledger |
| 22 | Customer automation/delivery | 🟡 PARTIAL | delivery-command-center exists; per-customer SLA table missing |
| 23 | Owner vs customer approvals separated | 🟡 PARTIAL | `governor_reviews.py` + `production_approval_required`; queue inert until seeded (Q9) |
| 24 | Monitoring/incidents/audit visible | ✅ CODE-PRESENT | `automation_health.py` dead-man; `app/platform/admin_audit.py`; Sentry ARMED |
| 25 | Restart/recovery tested | 🔴 UNVERIFIED | 10/13 decommission proofs require a DEPLOYED env (PHASE1 §8A) — cannot prove locally |
| 26 | Feature preservation matrix | ✅ DONE | `docs/context/FEATURE_PRESERVATION_MATRIX.md` + `FEATURE_INVENTORY.md` exist |
| 27 | Security/secret scan passes | ✅ PASS | `scripts/check_secrets.py` OK on new files; `scripts/security_scan.py` present |
| 28 | Targeted + integration tests pass | ✅ PASS (partial) | OCC + admin 60+ PASS; OmniRoute suite present; full suite has HANG risk on team_pulse area |
| 29 | Deployment rollback path exists | ✅ EXISTS | `deploy_vps.sh` skew+smoke verify; `DEV_CONTROL_KILL` + flag-only revert; `docs/omniroute/ROLLBACK.md` |
| 30 | Runbooks/docs updated | 🟡 PARTIAL | many runbooks present; PHASE0/PHASE1/OWNER_COMMAND_CENTER handoffs written |
| 31 | Final handoff evidence recorded | ⏳ PENDING | this reconciliation is the PHASE0 input to it |

**Summary:** 13 ✅ · 11 🟡 PARTIAL · 1 🔴 CONFLICT (OmniRoute) · 1 🔴 UNVERIFIED (restart/recovery needs deploy) · 2 ⏳ pending.

---

## 3. 🔴 THE OMNIROUTE CONFLICT — OWNER DECISION REQUIRED

**Directive says:** "CENTRAL OMNIROUTE GATEWAY" sits between 31 agents and 14 combos; ALL persistent bots use it.

**Repo truth says (frozen, owner-approved):**
- `deploy/compose/docker-compose.omniroute.yml:21-22` — *"OmniRoute must stay absent from production per ADR-111."*
- `memory/decisions.md:2855` + `progress.md:291` (ADR-189) — OmniRoute is a **local-only desktop gateway** on the owner's Windows box (Docker Desktop, `127.0.0.1:20128`).
- `24X7_ARCHITECTURE_RECORD.md §8A` adopted safe default: **OmniRoute = optimization lane, NOT a 24×7 dependency.** 24×7 correctness must hold with it ABSENT; `free_ai.py` free-stack is the 24×7 path.
- Moving OmniRoute to VPS **overrides ADR-111/ADR-189 and is an explicit OWNER GATE.**

**Why this matters:** if OmniRoute is made the central 24×7 gateway while still living on the desktop host,
"24×7" becomes false and the migration silently re-creates the desktop dependency the directive explicitly
wants eliminated. This is a direct contradiction inside the directive itself.

**Two honest options for the owner:**
- **(A) Keep existing owner-approved decision** — OmniRoute stays optimization-lane; 31 agents + 14 combos
  route through `free_ai.py` + provider clients directly; combo *health* is still tracked centrally
  (`omniroute_combo_health.py`) but routing is best-effort/degraded-safe. **No VPS move, no ADR override.**
- **(B) Promote OmniRoute to VPS central gateway** — requires overriding ADR-111/ADR-189, deploying the
  `leadgen_omniroute` container to the VPS, and re-wiring all bots to it. **Owner gate + deploy required.**

---

## 4. EXPLICIT OWNER GATES — "NOT OURS TO FLIP"

Per `24X7_ARCHITECTURE_RECORD.md §7` + PHASE0 §10, the following require **explicit owner authorization**
(and/or a deploy). I will NOT touch these autonomously:

| Gate | What it unblocks | Risk if flipped blindly |
|---|---|---|
| `_KNOWN_TOOLS` edit (`coordination_hub_auth.py:23`) | headless bots reach `buzzlock_enrolled` | trust-boundary change; fail-closed otherwise |
| Rollout 12 → 31 agents (`PILOT_AGENTS`) | full 31-agent dispatch | unverified agents executing on prod |
| `DSH_RUNTIME_ENABLED=1` arm | DSH worker runtime | voice/desktop scope change |
| `.venv` rebuild (C-08) | local pytest for 6 MCP servers | local only, does not block prod |
| **Commit / Push / Deploy** | anything reaches VPS | reverts prod tip, live revenue risk |

---

## 5. WHAT I CAN SAFELY DO NOW (no owner gate, local, reversible, non-deploy)

From PHASE1 §8A "START NOW" list — all are code/config only, fail-closed by default, no deploy:

1. `app/platform/omniroute_aliases.py` — read-only legacy-alias resolver (no routing authority).
2. `config/desktop_apps/combo_distribution.yaml` re-scope `project_only → vps_and_project` (YAML-only, **NO gate** per §8A row 2).
3. `app/models/dev_task_event.py` — NEW hash-chained audit model (schema add; populate on deploy only).
4. `app/dev_control/reconcile.py` — startup/beat-safe `reconcile_leases()` + exponential backoff on requeue.
5. `app/platform/telegram_ingress.py` — NEW scheduled ingress behind `TELEGRAM_INGRESS_ENABLED=0` (fail-closed; Hermes can still re-poll).
6. Targeted tests for the above (local pytest via `.venv` — but `.venv` is the C-08 gate; may need Docker/prod probe per §8A #6).

I can implement + unit-test items 1–5 locally and leave them undeployed, ready for your sign-off.

---

## 6. RECOMMENDED NEXT 3 HIGHEST-VALUE TASKS (after owner decisions)

1. **Resolve the OmniRoute conflict (§3)** — blocks the entire "central gateway" narrative.
2. **Seal one task truth (§5 item 2 + 3 + 4)** — retire CC ledger + frozen `state.js`, wire `dev_workers` +
   `DevTaskEvent`, move idempotency to DB. This is the spine every other tile depends on.
3. **Deploy + prove decommission (§8A proofs a–k)** — requires the owner gate; only then mark any desktop
   responsibility MIGRATED. Until then, local evidence is insufficient per the architecture record's own rule.

---

## 7. REVENUE OBJECTIVE NOTE

₹5,00,000 / 7 days remains the business goal. The directive correctly subordinates it to consent / TRAI /
tenant-isolation / payment-truth. Current revenue blocker is **WS-GTM1** (2nd paying customer) — owner
action: `/app/inbox` 15–30 min + UPI re-approve + bank confirm. I will not fabricate revenue or arm
uncapped outbound to chase this number.

---

## 8. BOTTOM LINE

I will **not** blindly execute a 7-phase autonomous deploy. The migration is already mostly built and the
rest is correctly gated. My immediate, safe, evidence-producing action is this reconciliation + the local-only
coding items in §5 once you confirm scope. The two things I need from you: (1) the OmniRoute decision (§3),
(2) which owner gates (§4), if any, you authorize preparing/executing now.
