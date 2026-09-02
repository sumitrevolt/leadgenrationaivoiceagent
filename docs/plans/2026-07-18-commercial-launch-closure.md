# Commercial Launch Closure — 2026-07-18

Production baseline: SHA `1803f819` · Alembic `020` · Calling HARD OFF · `PLATFORM_DIAL_DAILY=0`

## Phase 1 — Second-customer E2E (disposable)

| Field | Value |
|---|---|
| Client ID | `041a2fb0ca1e` |
| Email | `launch-e2e-20260718101104@leadsgenai.in` |
| Slug | `launch-e2e-disposable-20260718101104-041a` |
| Plan | `starter` ₹1,999 |
| Payment ID | `upi_2_53b383f5` (`auto_activated` then admin `approved` idempotent) |
| Invoice | `INV/2026-27/0002` (gross ₹1999, plan starter) |
| Drafts | 3 queue items `status=draft` |
| Ledger | customer_created → plan_activated → onboarding_* → post_draft_created |
| Jiya | still `starter`/`active`/`jiya-makeover` |

Notes:
- Turnstile armed; public signup HTTP still succeeded (token path OK in this run).
- `UPI_AUTO_ACTIVATE=1` in prod → payment confirmed on submit (admin approve still authorized + idempotent).
- `plan_provisioned=false` on signup response; activation completed on UPI path (`plan_activated` ledger).
- Customer JWT correctly denied `/api/upi/pending` (401). `/api/owner/agents` returned 404 (route shape) — still no admin data.
- Portal dashboard includes `onboarding` key (checklist surface present).

## Phase 2 — ₹1,999 Delivery Contract Matrix

Status legend: **automatic** · **approval-gated** · **admin-assisted** · **manual** · **not yet available** · **on-demand (Studio)**

| Feature | Automation status | Trigger | Agent/workflow | Approval | Customer output | Frequency | Failure alert | Evidence source |
|---|---|---|---|---|---|---|---|---|
| Roz AI social posts | approval-gated (auto-gen) | scheduler `content` 07:00 IST | Isha / `auto_content.run_daily_content` | content_approval pending → customer OK → manual share | portal drafts + ledger `post_draft_created` | daily | dead-man `content` 1800m | `packages.py` `_STARTER_CORE`; `scheduler_config.py`; `auto_content.py` |
| Branded post frames / 4 posters/mo | approval-gated | `content` job | Isha | pending | deliverable `branded_posters` | daily gen / monthly quota | via `content` | `product_one_delivery.py` |
| Festival/tyohar posts | approval-gated | `content` + festival calendar | Isha | pending | festival items | calendar | via `content` | `product_one_delivery.py` |
| WhatsApp content pack | approval-gated / draft-only send | `content` | Isha | send gated `WHATSAPP_AUTO_SEND=0` | whatsapp_pack drafts | daily | integration_readiness | `product_one_delivery.py`; env |
| Per-client blog / pSEO | automatic (gen) | scheduler `blog` 06:30 | Isha | n/a page publish path | blog page | daily | dead-man `blog` 1800m | `scheduler_config.py` |
| GBP audit 0–100 | on-demand | Studio `gbp-audit` | customer click | none | `data/gbp_audits/<cid>.json` | on click | none | `customer_marketing_studio._TOOLS` |
| Review reply drafts | on-demand | Studio `review-reply` | customer click | none | studio output / deliverable | on click | none | `_TOOLS` |
| Monthly marketing report | admin-assisted / partial auto | month-end workflow + admin button | report builder | none | `data/client_reports/` | monthly | no dedicated dead-man | `product_one_delivery.py` |
| Proof of published work | admin-assisted / gated auto | `social_drain` if SOCIAL_ENGINE | Postiz | approval→publish | ledger `post_published` | on publish | integration_required label | `content_approval` + `social_drain` |
| Business profile / brand kit | manual + AI assist | setup wizard | customer | n/a | setup checks | once | n/a | `_setup_checks` |
| Customer health + SLA recovery | automatic (monitor) | `product_one_health` hourly :20 | platform | n/a | ledger sla_* / approval_reminded | hourly | gap 180m | `scheduler_config.py` L184-188 |
| Approval email nudge | automatic (gated OFF) | `approval_email_sweep` | platform | allowlist | email | hourly | gap 180m | needs `APPROVAL_EMAIL_NOTIFY` |
| ~78 other marketed Studio tools (carousel, meme, schema, ROI, coach, …) | on-demand | customer Studio click | Studio `_TOOLS` | none | tool artifact | on click | none | `customer_marketing_studio.py` |
| Hands-Free: weekly rank track / mention monitor / lifecycle nurture / stale-inquiry / signup→paid sequence / evergreen auto-repost | not yet available (or on-demand mislabeled) | — | — | — | — | — | — | honesty gap vs `packages.py` Hands-Free group |

### Jiya reconciliation (ledger truth)

- Generated drafts exist; **10 approvals open 100h+**; **zero** `post_approved` / `post_published` / reports.
- Health RED / score 0; SLA breach + approval_reminded firing correctly.
- Root cause: customer approve→share loop stalled; `AUTO_DELIVER_VALUE` gated; WhatsApp auto-send OFF (intentional ban-safety).
- **value_delivered = False** despite paid starter — ops must send approve links / coach first approval.

## Phase 3 — Payment / billing safety

| Check | Result |
|---|---|
| UPI config present (no VPA print) | PASS — `pay-info enabled=true`, has_vpa/has_qr |
| Payment-reference creation | PASS — `upi_2_53b383f5` / ref `LAUNCH-E2E-20260718101104` |
| Pending → confirmed | PASS — `auto_activated` then admin `approved` |
| Unauthorized status mutation | PASS — customer approve → 401 |
| Admin confirmation auth | PASS — super_admin JWT approve 200 |
| Duplicate confirmation idempotency | PASS — second approve 200, same record |
| Plan activation | PASS — tenant `plan=starter` + ledger `plan_activated` |
| Tenant-scoped invoice | PASS — `INV/2026-27/0002` visible only to disposable; jiya fetch of disposable invoices = 0 |
| Real money charge | NONE — synthetic UPI ref only |
| Launch note | `UPI_AUTO_ACTIVATE=1` means prod currently auto-activates on claim — for human-reviewed canary set `=0` |

## Phase 7 — Controlled first-customer launch policy

- Max paying customers: **1–3** (currently Jiya + disposable test; disposable to be cleaned)
- Social publishing: **approval-required** (`SOCIAL_PREFS_HONOR=1`; SOCIAL_ENGINE publish not forced)
- Bulk email: disabled (no bulk campaign in this closure)
- WhatsApp auto-send: **OFF** (`WHATSAPP_AUTO_SEND=0`, `VOICE_CLOSE_WHATSAPP=0`)
- Outbound calling: **HARD OFF** (`PLATFORM_DIAL_DAILY=0` + platform_dial.json + scheduler)
- Payment confirmation: prefer admin-reviewed → recommend `UPI_AUTO_ACTIVATE=0` for canary window
- Daily Owner OS checklist + daily customer delivery audit (esp. Jiya approvals)
- Observation window: **48–72h** after next real paid activation
- Rollback owner: platform owner (deploy_vps previous SHA); support owner: same until staff hired
- Do **not** enable voice calling in this window

## Rollback / recovery pointers

- Image rollback: redeploy previous `APP_VERSION=<prior sha>` via `scripts/deploy_vps.sh`
- Schema: Alembic `020` head; forward-only preferred; schema-compatible rollback = redeploy prior image if no destructive migration
- Backup: `scripts/pg_backup.sh` + `scripts/pg_restore_drill.sh` (isolated container)
- RTO target: restore-drill proven path; owner steps in `memory/playbooks.md` + `docs/DISASTER_RECOVERY.md`

## Phase 4 — Notification smoke

| Event | Result | Evidence |
|---|---|---|
| Admin attention (ntfy) | PASS | `POST /api/growth/notify/test` → `{enabled:true,sent:true}` |
| Payment confirmed | PASS (path) | UPI submit auto_activated + ntfy path; record `upi_2_53b383f5` approved; invoice written |
| Signup received | PASS (audit) | ledger `customer_created` + signup HTTP 200; automation/log path |
| Deliverable ready email | GATED OFF | `APPROVAL_EMAIL_NOTIFY` unset + empty allowlist (fail-closed) — intentional |
| Bulk / WA / call side-effects | PASS none | worker grep for disposable = 0 |

## Phase 5 — Backup / restore

| Check | Result |
|---|---|
| Fresh PG backup | PASS `leadgen_20260718_1015.dump.gz` (7.2M) |
| Owner OS + customer tables in dump | PASS TOC includes `owner_agent_controls`, `owner_os_audit_events`, `users`, `leads`, `subscriptions`, `invoices`, `billing_records` |
| Disposable restore drill | PASS 39 tables, content integrity OK (prod untouched) |
| Alembic | `020_add_owner_agent_controls (head)` |
| Prior image rollback available | `ghcr.io/...:ce562408`, `:85b060e2` present |
| Offsite rclone (this interactive run) | SKIPPED — `RCLONE_REMOTE` unset in shell; cron/offsite path not re-proven here |

## Phase 6 — Owner alerting

Alertmanager rules present for: AppInstanceDown, container mem, CeleryQueueBacklog, CeleryDLQNonEmpty, BackupStale, RestoreDrillFailed, LLMProviderDegraded/LLMChainDegraded, PostgresDown, etc. Gatus probes `/health/ready`. Controlled ntfy test sent. `OPS_ALERTS=1`. Scheduler skips audit via `record_scheduler_skip` (no dedicated ntfy). Sentry armed in prod.

## Gates

- Billing/UPI/isolation/invoice targeted pytest: **91 passed** (VPS `.venv`)
- Owner OS async trio: 3 failed on host event-loop env (`RuntimeError: no current event loop`) — not repro of prod V1.1 proof
- `prod_check.py`: **ALL CHECKS PASSED**
- `check_secrets.py`: FAIL on pre-existing FreeSWITCH TLS PEMs under `app/telephony/freeswitch/conf/tls/` (unchanged by this closure)
- Deploy: **none** — production stayed on `1803f819`

## FINAL VERDICT

**CONTROLLED CANARY LAUNCH READY**

Not COMMERCIAL LAUNCH READY because: payment auto-activates (`UPI_AUTO_ACTIVATE=1`), Jiya still has zero published value, Hands-Free marketing honesty gaps remain, deliverable-ready email intentionally gated, offsite backup not re-proven in this run.
