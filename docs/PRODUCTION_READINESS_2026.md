# Production-Readiness + Revenue Automation — Design Doc (2026-06-10)

> Deep web + GitHub research (June 2026) → gap analysis → build plan. System-design + ADR style.
> Built this session: GST invoicing · email warmup ramp · usage upsell alerts · annual pricing · Gatus synthetic monitoring.

## 1. Requirements
- **Functional**: revenue loop me invoicing missing (payment hota hai, invoice nahi banta); outreach cap static (warmup ramp nahi, bounce auto-pause nahi); Advanced clients ko 80%/100% minute-usage par upsell trigger nahi; annual plan pricing nahi; synthetic API checks nahi (Kuma = ping-style only).
- **Non-functional**: free-stack only, single VPS, solo founder, ban-safe (auto-send gated), never-raise, additive (zero behaviour change with flags OFF).
- **Constraints**: no paid services; Postgres+Redis+Celery LIVE; .env = secrets; FastAPI first-route-wins (dup routes danger).

## 2. Research findings (sources: SESSION_LOG / agent report)
- **GST invoice (Rule 46)**: 16 mandatory fields; unique sequential number ≤16 chars per FY (`INV/2026-27/NNN`); SAC for SaaS = **998313**; intra-state = CGST 9% + SGST 9%, inter-state = IGST 18%; composition scheme **not viable** (no inter-state supply allowed); GST registration mandatory only **>₹20L** services turnover — till then invoice WITHOUT tax lines ("GST not applicable — unregistered"); e-invoicing (IRP) threshold ₹5Cr AATO — irrelevant abhi.
- **Dunning benchmarks**: median recovery 47.6%, automated 60-80% (humara 0/3/7/14 on-pattern). Annual plan = "2 months free" (16.7%) most common; annual billing cuts churn ~27%. Usage-threshold upsell converts 20-40% vs 5-15% cold.
- **Cold-email warmup**: new domain ramp = wk1 3-10/day → wk2 10-25 → wk3 25-35 → wk4 35-50; bounce hard ceiling 2% (Google), auto-pause trigger **1.8%** (Smartlead/Instantly pattern); cold sends should move OFF primary domain eventually (secondary domain + inbox rotation). No free warmup pools exist 2026.
- **Zero-downtime deploy**: `wowu/docker-rollout` (MIT 2k★) best-fit but needs `container_name`/host-port removal + Caddy dynamic upstream; current `lb_try_duration 25s` covers most. **Decision: defer** (deploy gap already near-zero).
- **Alembic adoption (live DB)**: `alembic init` → autogenerate → empty first revision → `alembic stamp head`; expand→migrate→contract pattern; `lock_timeout` on DDL. **Decision: defer to dedicated pass** (invasive; models currently create_all-style — separate chat).
- **Secrets**: SOPS+age (free, ~30min) > Infisical (3 extra containers). **Decision: documented, user-action** (.env currently VPS-only = single point of loss; offsite email-backup partially mitigates).
- **Repos to borrow from**: Crater (invoice schema), full-stack-fastapi-template (Alembic/refresh-token), listmonk (bounce processing model), **TwiN/gatus** (Apache-2.0 10k★, 40MB RAM — YAML synthetic checks with body assertions + TLS expiry) → **adopted**.

## 3. What was built (this session)
| # | Feature | Module | Gate | Wiring |
|---|---------|--------|------|--------|
| 1 | GST invoice engine | `app/billing/gst_invoice.py` | `AUTO_INVOICE=1` (email send; record always) | `billing._provision_usage` hook (pay/renew → invoice); API `/api/growth/revenue/invoice*` |
| 2 | Email warmup ramp + bounce auto-pause | `app/platform/email_warmup.py` | `EMAIL_WARMUP=1` | `auto_outreach` dono cap-spots; API `/api/growth/outreach/warmup*` |
| 3 | Usage upsell alerts (80%/100%) | `app/billing/usage_alerts.py` | `USAGE_ALERTS=1` | digest job (team_scheduler); API `/api/growth/revenue/usage-alerts*` |
| 4 | Annual pricing (2 months free) | `packages.py` additive `price_inr_year` | — (data only) | public packages API (additive keys) |
| 5 | Gatus synthetic monitoring | `monitoring/gatus.yaml` + obs compose | opt-in compose | checks /health/ready body, key public APIs, TLS expiry |

Invoice design (Crater-schema thin port): sequential per-FY counter in `data/invoices.jsonl` (file_lock atomic), SAC 998313, supplier env (`GST_SUPPLIER_NAME/GST_GSTIN/GST_SUPPLIER_STATE_CODE/GST_SUPPLIER_ADDRESS`), recipient from clients_store (optional `gstin`,`state_code` fields), tax mode auto: GSTIN unset → unregistered bill (no tax lines); intra (state==supplier) → CGST+SGST; else IGST. HTML invoice brandable; email via existing `email_sender`.

Warmup design: start-marker auto-set on first gated run (`data/email_warmup.json`); ramp caps {wk1:5, wk2:15, wk3:25, wk4+:base}; `record_sent`/`record_bounce` rolling 7d; rate ≥1.8% → paused 24h + NOTIFY_EMAIL alert. Flag OFF = `effective_cap(base)==base` (zero change).

## 4. Trade-offs (ADR)
- **jsonl stores vs DB tables** for invoices/alerts: project-pattern consistency, zero migration; revisit at >5k invoices/yr (then Alembic + table).
- **Invoice at provision-hook vs per-webhook-event**: provision-hook = ek single choke-point (all gateways), amount derive from packages.py plan price (truth source) — webhook raw amount edge-cases (partial/top-up) me bhi consistent. Top-ups invoice nahi karte (sirf plan pay/renew).
- **Gatus vs more Kuma monitors**: Gatus = git-declared assertions on response BODY (`/health/ready` database+redis healthy) — Kuma yeh nahi karta; dono complementary.
- **Defer Alembic/docker-rollout/SOPS**: invasive vs additive batch discipline; documented above with adoption paths.

## 5. Revisit when
- >₹20L turnover → GSTIN registration → set `GST_GSTIN` env (tax lines auto-on).
- Secondary cold-email domain kharido → warmup restart (delete `data/email_warmup.json`) + inbox rotation build.
- > 2 paying clients on Advanced → usage alerts tune (top-up SKU?).
- Schema change needed → Alembic adoption pass (stamp head).
