# PRD — Product Requirements Document

> **Product:** LeadGenAI (leadgenrationaivoiceagent) · **Owner:** Sumit · **Updated:** 2026-06-20
> **Truth:** Pricing = `app/marketing/packages.py` · Niches = `app/niches.py` (39 builtin)

---

## 1. Vision

Chhote Indian local businesses ke liye **affordable AI SaaS** — marketing automation (MAIN) + optional AI voice telecaller (standalone). Free AI stack; revenue via manual UPI + SaaS tiers.

---

## 2. Products (DO NOT bundle in marketing)

| Product | Audience | Core value | Entry price |
|---------|----------|------------|-------------|
| **AI Automated Marketing** | Local SMB (salon, clinic, solar, etc.) | Content, mini-site, lead capture, GBP, campaigns | Starter ₹1,199/mo |
| **AI Voice Calling Agent** | Businesses needing outbound/inbound calls | Full AI telecaller, niche scripts, CRM push | Band A ₹4,999/mo |

Advanced Marketing tier includes voice as **one feature** (500 min/mo) — not a bundle USP.

---

## 3. User personas

| Persona | Goal | Primary UI |
|---------|------|------------|
| **Platform owner (Sumit)** | Revenue, ops, deploy | `/app/admin`, `/app/automation`, `/app/ops` |
| **Marketing client** | Posts, leads, reviews | `/app/customer`, `/app/marketing` |
| **Voice client** | Calls, qualification | `/app/customer`, `/app/test-call` |
| **End consumer** | Inquiry, booking | `/b/{slug}`, `/audit`, `/pricing` |
| **Sales prospect** | Compare, signup | `/`, `/compare`, `/start`, `/voice-agent` |

---

## 4. Feature matrix (shipped)

### Marketing (Product 1)

| Feature | Tier | Module / route |
|---------|------|----------------|
| AI social posts + hashtags + branded frames | Starter+ | `post_generator`, `brand_frames`, `/app/customer/marketing` |
| Festival calendar + tyohar/offer posts | Starter+ | `festivals.py`, `auto_content.py` |
| GBP audit + review reply drafts | Starter+ | `marketing_tools`, `review_kit.py` |
| 4 posters/mo + WhatsApp content pack + UPI QR | Starter+ | `poster`, `whatsapp_campaign`, marketing tabs |
| Post approval + customer portal + GST invoices | Starter+ | `content_approval`, `customer_auth`, `gst_invoice` |
| AI image + Complete Post + A/B variations | Growth+ | `ai_image.py`, `post_generator` |
| Content calendar + scheduler + festival auto-schedule | Growth+ | `content_schedule.py` |
| Competitor analysis + sentiment/hashtag research | Growth+ | marketing tabs |
| Mini-site + booking + bio/card | Growth+ | `mini_site.py`, `/b/{slug}` |
| Web lead widget + AI chatbot | Growth+ | `embed_widget.py`, `chatbot.py` |
| Reactivation + WhatsApp drip + review kit | Growth+ | `reactivation`, `drip`, `review_engine.py` |
| Team lead routing + CRM sync + webhooks | Growth+ | `lead_distribution`, `crm_sync`, `customer_webhooks` |
| Ads/reels drafts + catalog + referral + monthly report | Growth+ | marketing tabs |
| AI voice callback (inbound) + 500 min/mo | Advanced | `vobiz_stream`, `usage.py` |
| Lead qualification + booking + follow-ups + transcripts | Advanced | `call_qualifier`, `calendar_booking` |
| Speed-to-lead SLA + post-call qualify | Advanced | `speed_to_lead`, `call_qualifier` |

### Voice (Product 2)

| Feature | Status | Blocker |
|---------|--------|---------|
| Web-call tuning | LIVE | `/app/test-call` |
| Phone outbound (Vobiz) | Code-ready | DLT + DID recharge |
| Post-call qualify | Wired | `AUTO_QUALIFY_CALLS=1` |
| Minute metering | LIVE | `usage.py` |

### Platform

| Feature | Status |
|---------|--------|
| 15+ AI staff automation | LIVE (Celery beat) |
| Customer webhooks (HMAC) | Wired, `CUSTOMER_WEBHOOKS=1` |
| MCP-as-product | `/api/mcp-product/v1/*` |
| Multi-tenant white-label | Middleware, fail-open |
| Admin revenue / timeline / health | Wired, flags `REVENUE_TRENDS` etc. |

---

## 5. Key user flows

### 5.1 Acquisition → paid (Marketing)

```
/audit or /pricing → signup (/start) → UPI pay (manual) → admin activate → /app/login → dashboard
```

### 5.2 Client lead capture

```
Visitor → /b/{slug} or widget → POST /api/public/inquiry → lead_alerts + optional callback + CRM hooks
```

### 5.3 Outbound growth (platform self)

```
niche_prospector → lead_scoring → auto_outreach email → reply_agent triage → sales_pipeline
```

### 5.4 Voice call (when telephony unlocked)

```
queue_call → compliance (DND, 10–7, AI disclosure) → vobiz_stream → post_call_hooks → qualify → CRM
```

---

## 6. Roadmap & priorities

### P0 — Revenue now (₹0 code cost)

| Item | Owner | Status |
|------|-------|--------|
| UPI_VPA live | User | ✅ Set on VPS |
| First paid marketing client | Sales | Open |
| Speed-to-lead + round-robin | Eng | ✅ Shipped |

### P1 — After DLT/Vobiz

| Item | Notes |
|------|-------|
| Voice cold-calling go-live | Udyam → DLT → Vobiz DID |
| Missed-call callback | Vobiz inbound webhook |
| TRAI verbal consent confirm | Spec: `TRAI_CONSENT_CONFIRM_SPEC.md` |

### P2 — Dashboard / ops polish

| Item | Ref |
|------|-----|
| Revenue time-series | `REVENUE_TRENDS=1` |
| Client activity timeline | `CLIENT_TIMELINE=1` |
| godfiles refactor merge | branch `refactor/godfiles-2026-06-20` |

### WON'T (external-blocked)

GBP API auto-post · Meta auto-post · HA second server · R2 offsite (until creds/approval)

Full backlog: [`PRIORITIZED_BACKLOG.md`](PRIORITIZED_BACKLOG.md) · [`ADVANCEMENT_ROADMAP_2026.md`](ADVANCEMENT_ROADMAP_2026.md)

---

## 7. Non-functional requirements

| NFR | Target |
|-----|--------|
| Uptime | Single VPS + self-heal cron; `/health/ready` db+redis |
| AI cost | $0 marginal (free provider chain + circuit breaker) |
| Compliance | TRAI/DND/AI-disclosure gates **never disabled** |
| Security | RBAC, IDOR closed on billing, webhook signatures fail-closed |
| Data | Postgres + nightly pg_dump; Redis for queue/state |

---

## 8. Success metrics (KPIs)

See [`KPI_DASHBOARD_SPEC.md`](KPI_DASHBOARD_SPEC.md). North-star: **first ₹ revenue → repeatable acquisition → voice unlock**.

---

## 9. Out of scope (explicit)

- Paid STT/TTS/LLM (user decision: free-only)
- WhatsApp bulk auto-send (ban risk)
- JustDial/IndiaMART auto-scrape (ToS)
- Razorpay (removed 2026-06-18)
