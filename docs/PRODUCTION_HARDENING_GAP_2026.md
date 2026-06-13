# Production Hardening — Spec Gap Analysis & Roadmap (2026-06)

**Status:** Proposed · **Date:** 2026-06-13 · **Author:** Fable 5 (architecture review) · **Decider:** Sumit

Yeh document tumhare 12-requirement / 96-acceptance-criteria production-hardening spec ko **current codebase ke against** map karta hai. Maqsad: blindly 96 cheezein build karna NAHI — balki dekhna **kya already hai, kya adhoora, kya missing, aur kya bahar-se blocked** (paisa/paperwork/approval), phir sahi order me chalna.

## Legend
- ✅ **DONE** — built + live
- 🟡 **PARTIAL** — code hai par gated/incomplete/inactive (flag ya wiring chahiye)
- 🔴 **GAP** — nahi bana; **Claude free me bana sakta**
- ⛔ **BLOCKED** — paisa (2nd server/region/CDN), ya external (DLT/KYC/Cloudflare/Meta approval) — Claude akela nahi kar sakta

## Executive summary
Single-VPS, Docker-composed, free-stack platform ke liye **application-layer hardening ~70% already मौजूद hai** (rate-limiting, RBAC+2FA, circuit-breaker LLM failover, Prometheus/Grafana/Loki/Alertmanager/Gatus, PgBouncer, pg_backup+restore-drill+offsite-mail, dunning/recon/GST invoicing, consent-ledger, DND fail-closed, self-heal cron). 

**Asli gaps do buckets me hain:** (1) **infra-redundancy** (HA/failover/multi-region/clustering/CDN) — ye fundamentally **paisa** maangta (single VPS architecture); (2) **regulatory/telephony** (DLT, multi-carrier, KYC) — **external paperwork**. Jo Claude free me kar sakta hai wo Phase-1 me niche listed hai.

---

## Requirement 1 — Security Infrastructure Hardening
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Rate limiting on AI endpoints per tier | 🟡 PARTIAL | `app/api/ratelimit.py` per-IP rate-limit + `/api/ai/*` admin-gated (commit 1af2f25). **Gap:** per-client-TIER limits. Action: tier-aware limiter (free). |
|2| Authn token + RBAC | ✅ DONE | JWT (`admin.create_access_token`/`decode_token`), `require_admin`/`require_super_admin`, team RBAC (`rbac.py`, 8 modules). |
|3| WAF (SQLi/XSS/CSRF) | ⛔ BLOCKED | SQLAlchemy ORM = SQLi-safe; FastAPI escaping. True WAF = **Cloudflare** (guide `docs/INFRA_HARDENING_GUIDE.md`, needs CF account/perms). |
|4| DDoS protection <30s | ⛔ BLOCKED | Caddy basic + in-app rate-limit. Real DDoS = Cloudflare/edge (external). |
|5| TLS1.3 + AES-256 at-rest | 🟡 PARTIAL | TLS via Caddy (✅ in-transit). **At-rest AES-256:** Postgres volume disk-level nahi. Action: enable LUKS/pg TDE OR document scope. |
|6| Secrets mgmt (replace .env) | 🔴 GAP | Abhi `.env` (gitignored). Action: **SOPS+age** (guide ready) ya Infisical — Claude wire kar sakta (free, SOPS). |
|7| Security event logging + alerts | 🟡 PARTIAL | `AuditLog` + `log_audit` + Alertmanager email. **Gap:** dedicated security-event stream + suspicious-pattern alerts. |
|8| Session timeout + token rotation | 🟡 PARTIAL | JWT expiry + 2FA TOTP (gated `ADMIN_TOTP_SECRET`). **Gap:** refresh-token rotation + idle-timeout. |

## Requirement 2 — Infrastructure High Availability
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Auto-failover ≤30s | ⛔ BLOCKED | Single VPS. Needs 2nd node. |
|2| Load balancing multi-instance | ⛔ BLOCKED | `WEB_CONCURRENCY` multi-worker ✅ (single host); multi-INSTANCE LB needs 2nd server. |
|3| Blue-green zero-downtime | 🔴 GAP | Deferred (ADR noted). Claude can script Coolify/compose blue-green on single host (partial). |
|4| Auto-route to healthy | ⛔ BLOCKED | Needs LB + 2nd node. |
|5| Staging mirrors prod | ✅ DONE | `docker-compose.staging.yml` (alt DB+Redis+:8001, automation OFF). |
|6| Auto-scaling (cpu/mem/req) | ⛔ BLOCKED | Single VPS — no horizontal scale without cloud/2nd node. |
|7| Geo-redundancy multi-region | ⛔ BLOCKED | Paisa + 2nd region. |
|8| DB clustering + replication | ⛔ BLOCKED | Single Postgres. Needs replica node (spend). PITR script ready (`pg_pitr_enable.sh`). |

> **ADR-HA (below):** single-VPS pe true HA possible nahi — decision needed: spend on 2nd node/managed DB, ya "graceful-degradation + fast-restore" posture rakho.

## Requirement 3 — Monitoring & Observability
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Real-time metrics all components | ✅ DONE | Prometheus + Grafana + `/metrics`. |
|2| Distributed tracing | 🟡 PARTIAL | `observability_otel.py` + Tempo container, **gated `ENABLE_OTEL`; otel pkgs image me NAHI**. Action: add pkgs to lock + rebuild (free). |
|3| Business-metric alerts | 🟡 PARTIAL | Alertmanager email + `ops_watchdog`+`revenue_digest`. **Gap:** revenue-drop/conversion-fail specific rules. |
|4| Anomaly notify ≤60s | 🟡 PARTIAL | Watchdog hourly (not <60s) + ntfy push. Action: tighten critical-path alert cadence. |
|5| Centralized logging + retention | ✅ DONE | Loki container. |
|6| SLA tracking + availability reports | 🟡 PARTIAL | Gatus + Uptime-Kuma (synthetic). **Gap:** formal SLA report. |
|7| External-dep monitoring | 🟡 PARTIAL | `telephony_readiness`, `llm_metrics`, `deliverability_monitor`, `integration_health`. **Gap:** payment-gateway uptime probe. |
|8| Baselines + trend analysis | 🟡 PARTIAL | Grafana trends. **Gap:** automated capacity baselines. |

## Requirement 4 — Data Protection & Disaster Recovery
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Daily backup + PITR | ✅/🟡 | `pg_backup.sh` nightly cron ✅; PITR `pg_pitr_enable.sh` (dry-run, needs --apply). |
|2| Geo-separate encrypted backups | 🟡 PARTIAL | `offsite_email_backup.py` (Hostinger mail, separate infra) ✅; R2/B2 rclone hook **ready-not-active** (needs creds). |
|3| Monthly DR test + procedures | ✅ DONE | `pg_restore_drill.sh` monthly cron (`0 3 1 * *`). |
|4| Restore ≤4h on corruption | 🟡 PARTIAL | Restore-drill proves capability; no formal 4h runbook SLA. |
|5| 7-year retention | 🔴 GAP | Abhi 30d (pg_backup) + 7d (data tarball). Action: long-term archival tier (R2 lifecycle) — needs offsite creds. |
|6| Continuous replication RPO≤1h | 🟡 PARTIAL | Nightly = RPO ~24h. WAL-PITR gets RPO low (needs --apply). True replica = 2nd node (spend). |
|7| Backup verification | ✅ DONE | restore-drill = integrity check. |
|8| Granular restore (client/table) | 🟡 PARTIAL | pg_dump full; selective = manual. Action: per-table dump script (free). |

## Requirement 5 — Regulatory Compliance
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| TRAI voice (DLT/140/timing) | 🟡/⛔ | AI-disclosure ✅, 10am-7pm timing-gate ✅, compliance.py ✅. **DLT registration = user paperwork (Udyam)** ⛔; 140-series = operator. |
|2| DND before promo calls | ✅ DONE | `dnd_checker` fail-CLOSED (`compliance.py` blocks on unverified). |
|3| GDPR international | 🟡 PARTIAL | DPDP privacy page ✅, Grievance Officer ✅. **Gap:** GDPR-specific (EU) controls, geo-detection. |
|4| Block + alert on violation | ✅ DONE | ComplianceGate blocks (opted_out/dnd/timing) + events. |
|5| Audit trails | ✅ DONE | `AuditLog` + `consent_ledger`. |
|6| DSR automation (access/port/delete) | 🟡 PARTIAL | consent_ledger opt-out + retention. **Gap:** self-serve DSAR endpoint+fulfillment. Action: build (free). |
|7| Recording consent + retention | ✅ DONE | `consent_ledger` 90-day retention sweep (gated `RECORDING_RETENTION`). |
|8| Compliance reports | 🟡 PARTIAL | GSTR CSV ✅. **Gap:** TRAI/DPDP report generator. |

## Requirement 6 — Telephony Reliability
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Carrier failover (Vobiz/Plivo/Twilio) | 🟡 PARTIAL | Exotel active + Twilio handler + Vobiz; **multi-carrier auto-failover NOT wired**. Action: provider-router abstraction (free code; needs accounts to truly test). |
|2| DLT registration automation | ⛔ BLOCKED | DLT = user paperwork. |
|3| Call-quality monitor + routing | 🟡 PARTIAL | `telephony_readiness` ✅; quality-based routing 🔴. |
|4| Carrier failover ≤10s | 🔴 GAP | Needs #1 + 2nd carrier credits. |
|5| Cost/usage analytics per client | 🟡 PARTIAL | `lead_usage` + `exotel_account.balance()`. **Gap:** per-client cost report. |
|6| Voice quality + success-rate | 🟡 PARTIAL | `agent_tester` scorecard; live success-rate 🟡. |
|7| Real-time call status + webhook reliability | ✅ DONE | webhooks signature-verified + `call_state` Redis registry. |
|8| Call-volume limits + queuing | ✅ DONE | `queue_call` gate + `RedisCallStore` queue. |

## Requirement 7 — Financial Operations
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Revenue reconciliation | ✅ DONE | `payment_recon.py` (Razorpay vs invoices, gated). |
|2| Dunning / sub-recovery | ✅ DONE | `dunning.py` (day 0/3/7/14, gated). |
|3| Financial reports + analytics | ✅ DONE | `revenue_digest.py` weekly. |
|4| Auto recovery on fail | ✅ DONE | webhook payment_failed → dunning + 1-tap recovery links. |
|5| Fraud detection | 🔴 GAP | Action: velocity/dedupe fraud rules (free, basic). |
|6| Real-time payment status + notify | 🟡 PARTIAL | webhooks + ntfy. **Gap:** customer-facing status. ⚠️ **Razorpay API 401 — user must fix keys.** |
|7| Tax calc + compliance report | ✅ DONE | `gst_invoice.py` (Rule-46, CGST/SGST/IGST) + GSTR CSV. |
|8| Subscription lifecycle + renewals | ✅ DONE | `subscription.py` + `usage.activate_plan`/`reset_usage_period`. |

## Requirement 8 — Performance & Scalability
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Horizontal auto-scaling | ⛔ BLOCKED | Single VPS. |
|2| DB pooling + query opt | ✅ DONE | PgBouncer (session mode). |
|3| Redis clustering HA | ⛔ BLOCKED | Single Redis; cluster needs nodes. |
|4| Scale on spike ≤2min | ⛔ BLOCKED | Needs cloud/2nd node. |
|5| Mem/CPU per container | 🟡 PARTIAL | compose limits partial. Action: set resource limits (free). |
|6| CDN static + API cache | 🟡/⛔ | API cache (Redis 60s) ✅; CDN = Cloudflare (external). |
|7| Perf budgets + auto perf-test | 🔴 GAP | Action: lightweight load-test + budget gate in CI (free). |
|8| AI inference batch+cache | 🟡 PARTIAL | greeting-audio cache ✅; response cache 🟡. Action: LLM response cache (free). |

## Requirement 9 — Quality Assurance
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Automated integration tests | 🟡 PARTIAL | ~68 test files; **full-suite offline-hangs (network tests)** — targeted suites green. Action: hermetic network-mock layer (free, valuable). |
|2| Load testing | 🔴 GAP | Action: Locust/k6 script (free). |
|3| Chaos engineering | 🔴 GAP | Action: basic container-kill chaos script (free). |
|4| Validate journeys on deploy | 🟡 PARTIAL | prod_check + smoke. **Gap:** full journey suite in deploy gate. |
|5| Contract testing | ✅ DONE | `test_billing_truth_2026` (pricing contract). |
|6| Security/pentest automation | 🟡 PARTIAL | `check_secrets.py` + `cso-audit` skill. **Gap:** automated pentest (ZAP). |
|7| Telephony call testing | 🟡 PARTIAL | `agent_tester.py` free scorecard. |
|8| Perf regression per release | 🔴 GAP | Action: perf-regression gate (free). |

## Requirement 10 — Operational Excellence
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Deploy pipelines + rollback | ✅ DONE | CI `deploy-vps.yml` (gated, auto-rollback) + `vps_deploy_fable.sh`. |
|2| Runbooks | 🟡 PARTIAL | `.claude/skills` (leadgen-ops/hostinger-deploy/incident) + `fable-operating-manual`. **Gap:** formal runbook index. |
|3| Incident mgmt + escalation | 🟡 PARTIAL | `ops_watchdog` + `incident-response` skill + email/ntfy alert. **Gap:** auto-escalation tiers. |
|4| Status page auto-update | ✅ DONE | `/status` + Gatus + Uptime-Kuma. |
|5| Health checks + self-healing | ✅ DONE | `automation_health` dead-man + `vps_selfheal.sh` (*/10 cron) + compose healthchecks. |
|6| Capacity planning recs | 🟡 PARTIAL | Hermes infra-handler + Grafana. **Gap:** automated recommendations. |
|7| Config mgmt + IaC | 🟡 PARTIAL | docker-compose (declarative) + `.env`. **Gap:** full IaC (Ansible/Terraform). |
|8| Docs + knowledge base | ✅ DONE | CLAUDE.md + SESSION_LOG + docs/ + 60 skills + KB ingest. |

## Requirement 11 — AI Infrastructure Reliability
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| AI rate-limit + quota per provider | ✅ DONE | `free_ai` circuit-breaker (escalating cooldown, TPD-aware) + `/api/ai` limiter. |
|2| Provider failover ≤5s | ✅ DONE | `free_ai` multi-provider chain (Cerebras→Groq→...→Gemini). |
|3| AI latency + success tracking | ✅ DONE | `llm_metrics.py` per-provider. |
|4| AI response caching | 🟡 PARTIAL | greeting/audio cache; general response cache 🔴 (free to add). |
|5| Output quality + circuit breakers | ✅ DONE | circuit-breaker + critic (MAR) in coordinator. |
|6| Cred rotation + monitoring | 🟡 PARTIAL | metrics ✅; auto-rotation 🔴. |
|7| Request queuing + batch | 🟡 PARTIAL | process_engine/self_improve queues; LLM batch 🟡. |
|8| AI usage ToS compliance | 🟡 PARTIAL | free-tier ToS-aware; formal tracking 🔴. |

## Requirement 12 — Customer Data Security & Privacy
| # | Criteria | Status | Current / Action |
|---|----------|--------|------------------|
|1| Encryption at-rest + in-transit | 🟡 PARTIAL | In-transit ✅ (TLS). At-rest = R1#5. |
|2| Data anonymization | 🔴 GAP | Action: PII-masking util for analytics/test (free). |
|3| Retention policy enforcement | 🟡 PARTIAL | consent_ledger recording-retention ✅; general data-retention 🔴. |
|4| Breach response ≤15min | 🔴 GAP | Action: breach-detection alert + runbook (free, partial). |
|5| RBAC data access + audit | ✅ DONE | team RBAC + AuditLog. |
|6| Auto DSAR fulfillment | 🟡 PARTIAL | = R5#6. |
|7| Secure deletion + verify | 🟡 PARTIAL | consent retention delete (gated); verified-deletion 🟡. |
|8| Data lineage tracking | 🔴 GAP | Action: source-tagging (utm_source exists partly) — extend (free). |

---

## Scorecard (rough)
- ✅ DONE: ~30 criteria (≈31%) — app-layer security, RBAC, LLM resilience, monitoring core, financial ops, compliance core, self-heal.
- 🟡 PARTIAL: ~38 (≈40%) — exists, needs flag-flip/wiring/pkg.
- 🔴 GAP (Claude-buildable, free): ~14 (≈15%).
- ⛔ BLOCKED (spend/external): ~14 (≈14%) — HA/multi-region/clustering/CDN/DLT/Cloudflare.

## Roadmap (priority order)

### Phase 1 — Claude free, high-value, low-risk (DO NEXT)
1. **Secrets mgmt (SOPS+age)** [R1#6] — biggest security win, free.
2. **OTel traces live** [R3#2] — add otel pkgs to `requirements.lock.txt` + rebuild.
3. **Tier-aware rate limiting** [R1#1] — per client-tier limits.
4. **DSAR + data-retention + anonymization** [R5#6, R12#2/3/8] — privacy bundle, free.
5. **Hermetic test network-mock layer** [R9#1] — fixes full-suite hangs (real value).
6. **LLM response cache + per-table backup + resource limits** [R11#4, R4#8, R8#5].
7. **Load/perf/chaos test scripts** [R9#2/3/8] — k6 + container-kill.
8. **Multi-carrier provider-router abstraction** [R6#1] — code now, accounts later.

### Phase 2 — flag-flip / config (cheap)
- Activate offsite R2/B2 backups (needs creds), PITR `--apply`, business-alert rules, 2FA enforce, breach-detection alerts.

### Phase 3 — needs spend / external (your decision)
- **HA bucket** [R2 all, R8#1/3/4, R4#6 true-replica]: 2nd VPS/node + managed Postgres replica + load balancer. **OR** accept "single-node + fast-restore + Cloudflare edge" posture (cheaper).
- **Cloudflare** [R1#3/4, R8#6]: WAF + DDoS + CDN (free CF tier covers a lot — needs CF account + DNS move).
- **DLT/KYC/multi-carrier credits** [R5#1, R6#2/4]: paperwork + recharge.

## Key Architecture Decision — HA posture (ADR)
**Context:** Spec R2 demands zero-SPOF (failover/LB/multi-region/clustering). Current = single VPS (Mumbai), Docker-composed, free-stack.

**Decision needed:** True HA = **recurring spend** (2nd node + managed DB + LB ≈ several thousand ₹/mo). Alternatives:

| Option | Cost | RTO/RPO | Effort |
|--------|------|---------|--------|
| A. Stay single-node + harden restore (PITR, self-heal, Cloudflare edge) | ~free | RTO ~min (restart), RPO ~1h (PITR) | Low (Claude) |
| B. 2-node active-passive + managed Postgres replica + LB | ₹₹₹/mo | RTO ~30s, RPO ~0 | Med (setup + spend) |
| C. Full cloud (managed k8s/Cloud Run) multi-region | ₹₹₹₹/mo | RTO ~0 | High (re-platform) |

**Recommendation:** **Option A now** (Claude does Phase-1/2 + Cloudflare edge — gets ~80% of the safety for ~0 cost), **Option B when revenue justifies** (pehla paying customer ke baad). Option C abhi over-engineering.

**Consequences:** A me single-node failure pe ~minutes downtime (self-heal/restart) — acceptable for current scale; revenue-blocking SPOF (Razorpay/DLT) infra se zyada important hain abhi.
