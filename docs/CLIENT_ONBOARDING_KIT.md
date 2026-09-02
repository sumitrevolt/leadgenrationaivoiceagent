# Client Onboarding Kit — LeadGenAI

> **For:** Marketing + Voice clients after payment · **Admin tools:** `/app/clients`, FDE API, `/app/minisite-builder`
> **Auto path:** `AUTO_ONBOARD=1` → `app/marketing/onboarding.py`

---

## 1. Pre-onboarding (sales → signup)

| Step | Action | Owner |
|------|--------|-------|
| 1 | Plan chosen on `/pricing` | Client |
| 2 | Signup `/start` → account created | System |
| 3 | UPI payment + screenshot to WA | Client |
| 4 | Admin **Activate** plan (God Mode UPI panel) | Sumit |
| 5 | `POST /api/customer/auth/set-password` — login creds | Admin |

---

## 2. Day-0 setup checklist (Marketing)

| # | Task | How | Done when |
|---|------|-----|-----------|
| 1 | Client record + niche | Admin `/app/clients` | `client_id` exists |
| 2 | Business name, phone, city, website | Client form | KB seed input ready |
| 3 | Auto-onboard sweep | Hourly job or manual trigger | `setup_done=true` |
| 4 | KB seeded from website | `onboarding.py` → Qdrant `client:{id}` | RAG queries return content |
| 5 | Mini-site live | `/b/{slug}` | Public 200 |
| 6 | First content pack | `data/client_packs/{id}.html` | Client dashboard shows posts |
| 7 | Web widget snippet | Marketing tab "Web Widget" | `widget.js` on client site |
| 8 | Customer login sent | `/app/login` creds | Client can access portal |

**FDE one-shot:** `POST /api/growth/fde/deploy` {business_name, niche, city, brief}

---

## 3. Day-0 setup checklist (Voice add-on / Product 2)

| # | Task | Blocker |
|---|------|---------|
| 1 | Niche + band confirmed | `lead_band()` A/B/C |
| 2 | `VOBIZ_CALLER_ID` + DLT | User paperwork |
| 3 | Test web-call | `/app/test-call` (free) |
| 4 | 1 real phone test | After recharge |
| 5 | Post-call qualify ON | `AUTO_QUALIFY_CALLS=1` optional |

---

## 4. Client training (self-serve)

| Topic | Where |
|-------|-------|
| Dashboard KPIs | `/app/customer` |
| Marketing tools | `/app/marketing` (28 tabs) |
| Lead status edit | Customer dashboard inline PATCH |
| Team round-robin | Customer dashboard → routing section |
| WhatsApp 1-click send | Copy buttons (no bulk auto) |

**Video scripts (record locally):** 5×3-min Loom on: login → first post → widget install → lead inbox → WA send.

---

## 5. Deliverables by tier

> **Source of truth:** `app/marketing/packages.py` · Full bullets: `docs/PROJECT_HANDOFF.md` §2 · SOP: `docs/PRODUCT_HANDOFF_SOP.md` §1.3

### Trial ₹0 (7 din) — 11 items
5 AI posts (Hinglish) · 1 GBP audit · enquiry widget (+ AI chat) · mini-site preview · branded frames · customer portal 7d · WhatsApp basic pack · onboarding checklist · 1-click share · no payment · **no voice**

### Starter ₹1,199/mo — 15 items
Roz AI posts (39 niches) · branded frames · portal (roz ~7 baje, WA share) · festival calendar · tyohar posts · GBP audit + fixes · review reply drafts · 4 posters/mo · WhatsApp pack · UPI QR · hashtags · post approval · onboarding dashboard · GST invoices · marketing-only (no calling)

### Growth ₹2,999/mo — 18 items (Starter +)
Unlimited posters · AI image + Complete Post · A/B variations · calendar/scheduler · competitor · mini-site + booking · enquiry widget · AI chatbot · reactivation · WhatsApp drip · review kit · team routing · CRM + webhooks · ads/reels · catalog/referral · monthly report · 2FA

### Advanced ₹6,999/mo — 14 items (Growth + voice FEATURE)
AI voice callback (~2 min) · qualification · booking · missed-call (DID) · 500 min/mo · weekly follow-ups · transcripts · post-call qualify · speed-to-lead · multi-lingual · TRAI disclosure · unified portal · minute tracker

### Voice Band A–C (Product 2, alag)
Unlimited AI calls/niche — flat band pricing (`voice_packages.py`)

Pricing truth: `app/marketing/packages.py` · Voice: `voice_packages.py`

---

## 6. Support channels

| Channel | Contact |
|---------|---------|
| WhatsApp verify | `UPI_VERIFY_WA` env (default 8459012607) |
| Email | admin@leadsgenai.in |
| Grievance | `/privacy` DPDP officer |

---

## 7. Offboarding / pause

1. Admin pause client → status `paused`
2. `usage.py` blocks new calls if out of minutes
3. DPDP purge: consent ledger + `agent_memory` purge API (admin)

---

## 8. Internal references

- Sales talk track: [`Sales_Kit_Hinglish.md`](Sales_Kit_Hinglish.md)
- Marketing copy: [`Marketing_Kit_LeadGenAI.md`](Marketing_Kit_LeadGenAI.md)
- Sample client kit: [`page_kits/SAMPLE_client_Sharma_Solar_kit.md`](page_kits/SAMPLE_client_Sharma_Solar_kit.md)
