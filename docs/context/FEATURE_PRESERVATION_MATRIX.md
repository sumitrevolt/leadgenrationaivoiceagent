# FEATURE PRESERVATION MATRIX — no-feature-loss guard (24×7 migration)

**Compiled:** 2026-09-10 · **By:** team-lead (Qi) · **Source:** PM discovery report (static inspection, SHA `d0183bf1`)
**Method:** `Glob`/`Grep` enumeration only. `.venv` is missing → **no pytest was run**. Every status below is a
**code-shape judgement, not runtime proof**. UNVERIFIED = registration/wiring seen only.

## A. HEADLINE COUNTS (how they were derived)

| Metric | Count | Derivation |
|---|---|---|
| Route decorators | **1448** | grep `@(app\|router\|bp).(get\|post\|put\|patch\|delete\|api_route)` in `app/**/*.py` |
| `APIRouter` instances | 131 | `APIRouter(` occurrences |
| `include_router` in `app/main.py` | 113 | file is 2850 lines |
| Files in `app/api/` | 136 | glob |
| HTML pages (`frontend/`) | **74** | glob `*.html` |
| React pages (`admin-dashboard/src/pages/`) | 7 | glob |
| DB tables | 41 created / **43 distinct `__tablename__`** | 25 alembic migrations / 29 model modules |
| Compose services | 13 | `docker-compose.vps.yml` |
| Test files | 900 | `tests/` + `chaos`/`e2e`/`load`/`security` |
| `.py` files under `app/` | 945 (208 in `app/platform/`) | glob |
| Automation flags | 208 | `app/platform/automation_flag_manifest.py` |

**NONE-FOUND: none.** All 37 requested categories returned code.

---

## B. 🔴 DOC vs CODE DRIFT

`docs/FEATURE_INVENTORY.md` = **376 rows / 32 domains, dated 2026-08-21 @ `ca757ca9`**. Repo is now `d0183bf1`.

### In code, ZERO mentions in the doc
| Missing from doc | Actually exists at |
|---|---|
| **Smartflo / Tata telephony** (whole 2nd provider!) | `app/telephony/smartflo_{stream,webhooks}.py`, `tata_smartflo_handler.py`, `app/api/telephony_smartflo.py:64,109,186,285` |
| **DevTask + `app/dev_control/`** | 34 routes + 17 modules + 2 tables |
| **Dunning / GST invoice** | `app/billing/{dunning,gst_invoice}.py` |
| **Council / reflexion** | `app/agents/llm_council.py`, `boss_council.py`, `self_improve.py`, `judge_calibration.py` |
| **SMS / DLT** | `app/integrations/sms_dlt.py`, `app/api/growth.py:277` |
| Reseller, affiliate, impersonation, customer TOTP, tenant quarantine, memory stack | various |

### Count drift — no single agreed number exists
| Source | Routes | Routers | Tests | Migrations |
|---|---|---|---|---|
| `docs/FEATURE_INVENTORY.md` header | 129 | 104 | 844 | 24 |
| Actual (this audit) | **1448** decorators | 131 | 900 | 25 |
| `prod_check.py` (doc's own reference) | 1336 | — | — | — |

### Credibility red flag
The doc records **0 BROKEN / 0 UNKNOWN / 0 LEGACY across 376 rows** — implausibly clean for a repo with 208
automation flags. It also counts **21 `WORKING_BUT_INERT`** items (content calendar, LinkedIn publishing,
Hot Queue + `/app/inbox`, sales-autopilot WA, video content-hash binding) inside its **LIVE** rollup totals.
Inert ≠ dead, and inert ≠ live.

### There are ≥4 competing inventories
`docs/FEATURE_INVENTORY.md`, `CURRENT_REPO_DELIVERY_AUDIT.md`, `DELIVERY_OS_AUDIT.md`,
`DASHBOARD_ASSESSMENT_REPORT.md`, `COMMAND_CENTER_UNITY_MAPPING.md`.

---

## C. ⛔ DEPRECATED — DO NOT REVIVE (confirmed from in-code tombstones, not docs)

| Removed | Date | Tombstone evidence |
|---|---|---|
| **Stripe** | 2026-07-10 | `app/api/billing.py:189,194,400,745,813,1130` (route `stripe_webhook_removed` → 503), `app/api/webhooks.py:3`, `app/config.py:171`, `app/models/payment.py:37` |
| **Razorpay** | 2026-06-18 | `app/api/billing.py:198,419,513`, `app/api/activation.py:78,470`, `app/api/admin_ops.py:640` (stub → `key_prefix: "removed"`) |
| **Exotel** | 2026-06-18 | `app/config.py:83`, `app/telephony/webhooks.py:6`, `app/utils/dnd_checker.py:148,162` |
| **Twilio** | 2026-07-07 | `app/config.py:83`, `app/api/auth_deps.py:231`, `app/platform/engineer_agents.py:364` |

**Canonical replacements:** manual UPI (`app/platform/upi_payments.py`) · Vobiz telephony.
⚠️ Doc row 93 still lists Twilio voice-fallback as `EXTERNALLY_BLOCKED` — **the doc is wrong**; it is removed.
⚠️ Doc row 94 calls FreeSWITCH LIVE; only 4 files reference it → treat as **UNVERIFIED**.

---

## D. 🔴 FEATURES AT RISK (highest value first)

1. **SMS** — dormant + undocumented → silently dropped in a doc-driven rewrite.
2. **DevTask + `app/dev_control/`** — *is itself* one of the dashboards being consolidated. No `DEV_*` env vars
   appear in `docker-compose.vps.yml`, so its env/config lives outside compose and will be missed.
3. **Dunning / GST invoice / trial nudge / usage alerts / meter watch** — 5 sub-flows, 0 doc mentions each.
4. **Smartflo** — absent from the Aug-21 doc, yet the *current HEAD commit is a Smartflo fix*. Its `/stream`
   WebSocket, HMAC webhook and `/test-call` have no doc home.
5. **Human-in-the-loop-only features** — cannot survive a headless-bot migration without an explicit approval
   API: approvals bridge + `approval_notifications` + `publish_gate` + `risk_approve`; WhatsApp human-send
   boundary (`WHATSAPP_AUTO_SEND`); owner kill-switch board; impersonation (interactive session); admin 2FA/TOTP.
6. **The 21 `WORKING_BUT_INERT` items** — inert ≠ dead; a rewrite treats them as unused and deletes them.
7. **🚨 Framework fork in the road** — 74 server-rendered HTML pages **and** a separate 7-page React
   `admin-dashboard/`. If the Owner Command Center is React, the 74 HTML pages have no path; if server-rendered,
   the React app dies. **Both cannot survive by default — owner decision required.**
8. **4 orphan HTML pages** — `archify_landing`, `autonomous_mission_control`, `owner_dashboard`,
   `google1d137d4af9dad693` have zero backend reference → deleted with no error.
9. **`runtime_data_*` family (12 modules** — allowlist, ratchet, baseline, scan, authority, manifest) — safety
   machinery with **no UI at all**; trivially lost in a UI consolidation.
10. **Manual UPI** — the *only* payment path. Any billing rewrite assuming a PSP webhook breaks revenue.
11. **Reseller / affiliate / Office HQ / OKF / short links / NPS** — each has its own page+API, 0 doc mentions.

---

## E. BEFORE → AFTER PRESERVATION MATRIX

Fill `After` / `Preserved?` during Phase 4. **Nothing is permitted to move to `NO` without owner sign-off.**

| Feature | Before (current surface / path) | After (planned OCC surface) | Preserved? | Owner-verify method |
|---|---|---|---|---|
| Vobiz telephony (call, stream, webhooks) | `app/telephony/vobiz_{handler,stream}.py`; `app/api/telephony_vobiz.py` | TBD | TBD | Place 1 real call post-migration; CDR row appears |
| Smartflo / Tata telephony | `app/telephony/smartflo_{stream,webhooks}.py`; `app/api/telephony_smartflo.py` | TBD | TBD | POST `/api/telephony/smartflo/test-call`; stream WS connects |
| Voice pipeline (STT/LLM/TTS/AMD/qual) | `app/voice_agent/*` | TBD | TBD | End-to-end call + transcript + score |
| Lead harvesting + Places + scrapers | `app/platform/lead_harvester.py`; `app/lead_scraper/` | TBD | TBD | Seed 100 leads; confirm dedup + source tags |
| Dedup / suppression / consent | `app/platform/dpdp.py`; `consent_ledger.py` | TBD | TBD | Re-import same lead; count must not rise |
| Lead scoring + ICP + objection | `app/platform/lead_scoring{,v2}.py`; `icp_generator.py` | TBD | TBD | Score a known lead; compare to pre-migration score |
| CRM pipeline / stages / activity | `app/models/lead_pipeline.py`; `app/platform/crm_sync.py` | TBD | TBD | Move a lead across all stages; history intact |
| Hot Queue + `/app/inbox` | `app/platform/hot_queue_{followup,owner_pack}.py`; `frontend/inbox.html` | TBD | TBD | Force a hot lead; must appear in queue |
| HubSpot + Zoho sync | `app/integrations/{hubspot,zoho_crm}.py` | TBD | TBD | Push 1 record; confirm in provider UI |
| Email send / IMAP triage / warmup / unsub | `app/integrations/email_sender.py`; `app/platform/email_{warmup,unsub}.py` | TBD | TBD | Send 1; reply; confirm triage + unsub honoured |
| WhatsApp Meta Cloud + WAHA in/out | `app/integrations/whatsapp{,selfhost}.py` | TBD | TBD | Send + receive 1 message each direction |
| WhatsApp human-send boundary | `WHATSAPP_AUTO_SEND` gate | TBD | TBD | With flag off, no outbound may leave |
| **SMS / DLT** | `app/integrations/sms_dlt.py`; `app/api/growth.py:277` | TBD | TBD | With BSP creds set, 1 template send succeeds |
| Social publishing (Postiz, 5 channels) | `app/integrations/postiz.py`; `app/social_engine/*` | TBD | TBD | Publish 1 post per connected channel |
| Video render + approval saga + publish gate | `app/marketing/video_production/*`; `video_renderer/` | TBD | TBD | Render 9:16 clip; approve; publish |
| Content calendar + scheduled publishing | `frontend/calendar.html`; Postiz scheduler | TBD | TBD | Schedule 1 post; verify it fires |
| Customer portal (dash, Kanban, studio, flows, plugins) | `app/api/customer_*.py`; `frontend/customer_dashboard{,_v2}.html` | TBD | TBD | Log in as customer; all 5 sub-pages load |
| Customer TOTP + webhooks | `app/platform/customer_totp.py`; `app/api/customer_totp.py` | TBD | TBD | Enrol TOTP; login requires code |
| Admin 2FA / sessions / RBAC | `app/platform/{admin_2fa,admin_sessions,rbac}.py` | TBD | TBD | Enrol 2FA; RBAC denial on wrong role |
| Impersonation | `app/api/impersonation.py`; `frontend/impersonate.html` | TBD | TBD | Impersonate; audit row written |
| Tenant isolation + quarantine | `app/platform/tenant_manager.py`; `tenant_quarantine.py` | TBD | TBD | Cross-tenant read must 403 |
| Billing usage + entitlement + promo | `app/billing/*` | TBD | TBD | Compare invoice total pre/post |
| **GST invoice** | `app/billing/gst_invoice.py` | TBD | TBD | Generate 1 invoice; GST fields present |
| **Manual UPI payments** | `app/platform/upi_payments.py`; `app/api/upi_payments.py` | TBD | TBD | Record 1 manual UPI payment; entitlement activates |
| **Dunning + trial nudge + usage alerts + meter watch** | `app/billing/{dunning,trial_nudge,usage_alerts,meter_watch}.py` | TBD | TBD | Force overdue account; dunning email fires |
| Plans / credits / subscriptions | `app/billing/subscription.py:96`; `app/models/data_credits.py` | TBD | TBD | List all plan IDs pre and post; must match |
| Lifecycle (newsletter, unsub, winback, onboard) | `app/api/lifecycle.py`; `app/platform/winback.py`; `onboard_wizard.py` | TBD | TBD | Unsub link must suppress immediately |
| Analytics + PostHog + revenue attribution | `app/analytics/*`; `app/platform/revenue_attribution.py` | TBD | TBD | Compare KPI numbers on same date window |
| Reporting (client/team/revenue digest) | `app/platform/report_{generator,parser}.py`; `app/marketing/client_report.py` | TBD | TBD | Generate 1 report; byte-diff vs archived copy |
| Scheduler (Celery beat + scheduled_ops) | compose `scheduler`; `app/automation/scheduler.py`; `app/platform/scheduled_ops.py` | TBD | TBD | List beat entries pre/post; diff must be empty |
| Agent roster + 11 squads + harness | `app/agents/*`; `app/platform/squad_*.py`; `agent_runtime*.py` | TBD | TBD | Roster count must be unchanged |
| **Council / reflexion** | `app/agents/llm_council.py`; `app/platform/boss_council.py`; `self_improve.py` | TBD | TBD | Run 1 council query; members respond |
| Memory stack / vault / skills | `app/platform/memory_*.py`; `skill_{library,pack}.py`; `workforce_memory.py` | TBD | TBD | Write + recall 1 memory |
| OmniRoute + budget guard + model cookbook | `app/platform/omniroute_client.py`; `app/dev_control/governed_omniroute.py`; `app/llm/budget_guard.py` | TBD | TBD | Route 1 call per model; cost logged |
| Monitoring (Prometheus/Grafana/Gatus/Tempo) | `monitoring/*.yml` | TBD | TBD | All dashboards green; alert-rule count equal |
| Alerts (ops/lead/ntfy/webpush/deliverability) | `app/platform/{ops_alerts,lead_alerts,webpush,deliverability_monitor}.py` | TBD | TBD | Trigger 1 alert per channel |
| **DevTask + dev_control (claims/locks/budgets/gateway/reconcile/deploy)** | `app/models/dev_task.py`; `app/api/dev_tasks.py` (34 routes); `app/dev_control/*` | TBD | TBD | Create + claim + complete 1 task end to end |
| Approvals (bridge, notifications, publish gate, risk_approve) | `app/platform/approvals_bridge.py`; `app/models/approval_notification.py` | TBD | TBD | Request + approve + reject 1 item |
| Owner OS kill-switches + commands + audit | `app/api/owner_os.py:377`; `app/models/owner_os.py` | TBD | TBD | Engage + release every switch; audit rows |
| Security (audit log, HMAC, turnstile, idempotency) | `app/platform/admin_audit.py`; `app/security/turnstile.py`; `app/billing/idempotency.py` | TBD | TBD | Replay 1 idempotent request; no double effect |
| Compliance (DPDP, DND, dial gate, TRAI, privacy ops) | `app/platform/dpdp.py`; `app/telephony/compliance.py`; `dial_gate.py`; `app/utils/dnd_checker.py` | TBD | TBD | Export + erase 1 subject; DND number refused |
| Backups / DR (pg_backup, restore drill, rclone offsite) | `scripts/{pg_backup,vps_backup,pg_restore_drill,data_backup_rclone}.*` | TBD | TBD | Run restore drill; checksum matches |
| Reseller + affiliate | `app/platform/reseller.py`; `app/api/reseller.py`; `app/marketing/affiliate.py` | TBD | TBD | Load reseller page; referral link resolves |
| Office HQ / blueprint / map | `app/platform/office_{hq,schema}.py`; `frontend/office_*.html` | TBD | TBD | Load all 3 office pages |
| OKF public bundle | `app/api/okf_{admin,public}.py` | TBD | TBD | `GET /okf/` returns same markdown |
| Short links + minisite builder + bio_link | `app/platform/short_links.py`; `app/api/minisite_builder.py` | TBD | TBD | Resolve 1 existing short link |
| Web call / dialer / public site / assessment | `app/api/web_call.py`; `public_site.py`; `assessment.py` | TBD | TBD | Place 1 web test call |
| DSH worker + MCP gateway + plugin registry | compose `dsh-worker`/`mcp`; `app/api/dsh_internal.py` | TBD | TBD | Queue 1 DSH job; completes |
| Qdrant RAG / brain / knowledge | compose `qdrant`; `app/voice_agent/graph_rag.py`; `app/api/brain.py` | TBD | TBD | 1 query returns same top-k docs |
| NPS + booking | `app/platform/nps.py`; `app/api/booking.py` | TBD | TBD | Submit 1 NPS; book 1 slot |
| 4 orphan HTML pages | `frontend/{archify_landing,autonomous_mission_control,owner_dashboard,google1d137d4af9dad693}.html` | TBD | TBD | **Owner must explicitly bless deletion** |
| `runtime_data_*` safety family (12 modules) | `app/platform/runtime_data_*.py` | TBD | TBD | Run `runtime_data_scan`; baseline unchanged |

---

## F. OPEN QUESTIONS — recommended default vs owner decision needed

| # | Question | Recommended default (will proceed if owner silent) | Needs owner? |
|---|---|---|---|
| 1 | **OCC = React or server-rendered HTML?** | **Server-rendered HTML**, upgrading existing `frontend/` surfaces — 74 pages vs 7 argues for it, and the React app has no route parity. | **YES — irreversible fork** |
| 2 | Smartflo vs Vobiz primary? | Keep Vobiz primary, Smartflo secondary — HEAD's Smartflo fix does not change the provider contract. | No (evidence-sufficient) |
| 3 | SMS keep / fund / retire? | **Keep code, leave DORMANT**, do not fund a BSP until revenue justifies. | No |
| 4 | DevTask = canonical ledger, or new ledger + migrate? | **DevTask becomes canonical** (already Postgres, 18 states, atomic claim, 600 s lease). | No (Phase 1 confirms) |
| 5 | Who approves under headless bots? | **No auto-approval.** Every approval class stays human-gated via an explicit approve API; bots may only *request*. | **YES — policy** |
| 6 | Are `scripts/*.sh` backups cron'd on the VPS outside repo? | Assume **yes**; migration must not assume repo-only scheduling. | No (verify on box) |
| 7 | How to prove "no feature loss" with no venv? | **Snapshot the 1448-route list + 74-page list + 43-table list now**, diff after each phase. | No |

---

## G. STATUS

- [x] Feature inventory generated from code
- [x] Doc-vs-code drift identified
- [x] Deprecated list confirmed from tombstones
- [x] At-risk list + matrix skeleton
- [ ] `After` / `Preserved?` columns filled (Phase 4)
- [ ] Owner decision on React vs HTML (blocker for OCC design)
