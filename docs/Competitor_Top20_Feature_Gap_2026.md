# Top-20+ Competitor Deep Research + Feature Gap (2026-06-10)

> Scope: 26 competitors, 4 categories, deep web research (pricing pages + feature pages + 2026 reviews).
> Method: per-competitor full feature list → master checklist → leadsgenai.in ke ~500 routes se dedupe (grep-verified) → sirf GENUINE gaps niche.

## 1. Kaun research hua

| Category | Competitors |
|---|---|
| AI social/marketing (SMB) | Predis.ai, AdBanao, Dhanda (EZO), Simplified, SocialPilot, Canva Magic Studio, Jasper, Copy.ai |
| AI voice agents (India) | Vodex.ai, Toingg, Sarv SuperBot, Rezo.ai, Gnani.ai, MyOperator, Exotel GenAI/Ameyo XTRM |
| Lead-gen / CRM / outreach | GoHighLevel, Apollo.io, Smartlead, Instantly, Privyr, NeoDove, TeleCRM, AiSensy, Wati, Interakt |
| Local SEO / reputation | Birdeye, Podium, Synup, SOCi, Thryv, NiceJob |

## 2. Pricing intel (positioning ammo)

- Transparent INR pricing RARE hai — sirf MyOperator (AI agent **+₹10,000/agent/mo**) aur INR WhatsApp tools publish karte. Vodex $100/mo se. Birdeye $299/loc, Podium ~$500-800/mo, NiceJob $75/mo floor.
- **Humara Marketing ₹1,199 / ₹2,999 / ₹6,999** aur **Voice flat-band ₹4,999 / ₹9,999 / ₹19,999/mo** (band A/B/C) — MyOperator AI-Voice ₹10k+ se materially sasta. Landing copy me explicitly bolo.
- Patterns copy karne layak: credit add-on packs (topups ✅ hain), "connected calls only billed" framing (Vodex), non-expiring credits + free campaign team (Sarv), free-tier→audit funnel (Dhanda — humara /audit ✅).
- Dhanda = closest direct competitor (GBP audit + monthly GBP posts + AI review replies, ~₹999/mo) — no voice, no email outreach, no CRM. AdBanao = creative library only. **Marketing aur Voice ab alag products hain** (ADR-009) — bundle framing mat use karo.

## 3. Parity confirm (REBUILD MAT KARO — already live)

GBP audit, AI posts/caption/hashtags/carousel/meme/multilang-9, festival calendar+autoschedule, scheduler, brand kit, logo, jingles, photo→poster, bg-remove(rembg opt), faceless reels, template library, competitor analysis, review gen/monitor/AI-reply/widget, NPS, rank tracker (single-point), website+site audit, SEO pages/blog/IndexNow, trends/weather angles, WA campaigns(1-click)/widget-chat/chatbot/flows(gated)/catalog/payment-links/UPI-QR, booking+reminders, mini-site, embed widget, cadence sequences, email warmup+MX+deliverability, reply triage, /app/inbox + /app/conversations, dialer+dispositions, lead scoring+hot, prospect search/lists/CSV-import/email-finder, deals kanban, proposals, sales assistant+BANT team, journeys, dunning, lifecycle nurture, client health, GST invoices, topups, affiliate/loyalty, white-label tenant, client reports, client API keys, customer portal, voice (Hinglish KB-RAG, AMD, DND fail-closed, post-call qualifier, 42 niche scripts), memory vault+call prep, NL command bar, outbound webhooks, lead-in catcher, lead alerts, short links, PWA, status page.

## 4. GENUINE GAPS — build backlog

> **STATUS UPDATE (2026-06-22 launch audit):** P0 items **#1–#4, #6–#10** aur P1 **#11–#20** (except telephony-live) = **SHIPPED + LIVE** (grep + `frontend/explorer.html` + prod_check). **Marketing Product-1 launch = GO** (`/api/activation/summary` blocker_count=0).  
> **Genuinely OPEN (external/DLT only):** #5 live human transfer (`CALL_TRANSFER` coded, needs Vobiz DID+DLT) · SMS-DLT live send · RCS rich-cards · Meta/GBP auto-post (§EXTERNAL-BLOCKED).  
> **Do NOT rebuild:** `brand_frames.py` · `business_card.py` · `magic_resize.py` · `review_to_post.py` · `speed_to_lead.py` · `content_approval.py` · `client_snapshots.py` · `lead_distribution.py` · `campaign_variants.py` · `revenue_attribution.py`.

### P0 — ✅ SHIPPED (2026-06-11+, verified 2026-06-22)
1. **Branded frames + daily-post feed** — ✅ `brand_frames.py`, `/api/brand/frames/*`
2. **Digital business card** — ✅ `/b/{slug}/card` + `.vcf` + QR
3. **Magic resize** — ✅ `magic_resize.py`
4. **Review→post** — ✅ `review_to_post.py`
5. **Live human transfer** — ⏳ coded (`call_transfer.py`, `CALL_TRANSFER`); **BLOCKED**: Vobiz DID + DLT
6. **Ask AI over call data** — ✅ `/api/voiceai/ask`
7. **Speed-to-lead SLA** — ✅ `speed_to_lead.py` + clientops API + Boss digest
8. **Content-approval workflow** — ✅ `content_approval.py` + automation Approvals tab
9. **Snapshots / niche clone** — ✅ `client_snapshots.py` + `/api/clientops/snapshots`
10. **Lead round-robin** — ✅ `lead_distribution.py`

### P1 — ✅ SHIPPED (2026-06-11+, verified 2026-06-22)
11. **GEO visibility report** — ✅ `/api/localseo/geo-check`
12. **Grid rank tracker** — ✅ `grid_rank.py`
13. **India listings presence** — ✅ `listings_presence.py`
14. **Cold-email A/B + stats** — ✅ `outreach_variants.py` + `campaign_variants.py`
15. **Dialer leaderboard** — ✅ growth-tools tab
16. **Trackable proposals** — ✅ proposal tracking
17. **WA sticker + GIF** — ✅ shipped
18. **Repeat-service reminders** — ✅ `service_reminders.py`
19. **Video→clips** — ✅ `video_clips.py` (ffmpeg, worker-only)
20. **Pricing compare strip** — ✅ `/pricing` + `/compare`

### P0/P1 archive (original research text — historical)
<details>
<summary>Original gap descriptions (2026-06-10 research)</summary>

Original P0 list items 1–10 and P1 items 11–20 described competitor features that are now implemented. See git history for full spec text.

</details>

### P2 (baad me)
21. Inbox rotation / 2nd sending domain (Smartlead) — partially external (domain kharidna).
22. AI avatar/voiceover video (Pollinations video_url scaffold hai).
23. Funnel builder (mini-site layouts extension).
24. Customer gifting, video chat, voice biometrics, communities/courses — skip-able niche/enterprise.

### EXTERNAL-BLOCKED (user paperwork/approval — token mat jalao)
Meta FB/IG auto-publish + FB Lead Ads native + CTWA manager + Conversions API (app review) · GBP API posting (60-din approval) · WhatsApp Flows (Meta) · DLT (SMS+cold-call) · Exotel KYC+recharge · Truecaller Business (paid).

### SKIP (ToS/ban/illegal — kabhi nahi)
Privyr-style unofficial WA auto-responder on own number (ban) · Justdial/IndiaMART/LinkedIn auto-scrape · SERP organic scraping · foreign trunk calling.

## 5. Strategic takeaways
- 2026 direction = "AI agent jo KAAM kare, sirf draft nahi" (Birdeye BirdAI, Podium Jerry, SOCi Genius, GHL AI Employee) — humari 10-agent AI staff framing on-trend hai; demo me agents ko aur visible karo.
- Synup ka Agency-OS model (white-label + SMB lead credits + prospect audit reports as sales tool) humare reseller/partnership track ka template hai.
- Humara unique combo intact: koi competitor is price band me marketing automation + India-native voice stack nahi deta. P0 list close karne ke baad feature-parity story har category me "equal or better at 1/5th price" ho jayegi.

## 6. 2026-06-17 refresh (battlecard build)
- 5 head-to-head competitors web-reverified (June 2026): **MyOperator** AI module ₹10–20k/mo + ₹20k onboarding on ₹52k base (enterprise; 12k+ incl Amazon/Dominos/TCS). **Vodex.ai** = Bengaluru-HQ but US-collections-first, English, USD, pay-per-connected-call — India-domestic = foreign-trunk ILLEGAL (biggest landmine). **GoHighLevel** $97 platform + $97 AI Employee add-on (USD, agency, no native India/Hinglish/DLT). **Dhanda(EZO)** free+premium, GBP-only, ~59k installs/mo. **AdBanao** 4.5M users, 50L+ creative library = our honest template-scale gap.
- **Pricing note (truth):** Marketing **₹1,199 / 2,999 / 6,999** (`packages.py`). Voice = **flat monthly per niche-band** A/B/C **₹4,999 / 9,999 / 19,999** + free pilot 7d/50 calls (`voice_packages.py`). Per-qualified-lead counting **REMOVED** (2026-06-12).
- **Interactive battlecard asset:** `docs/LeadGenAI_Battlecard_2026-06-17.html` (standalone) + served in-app at `/app/battlecard` (admin sidebar → Sales).

## Sources
Predis/AdBanao/Dhanda/Simplified/SocialPilot/Canva/Jasper pricing+feature pages; Vodex/Sarv SuperBot/Rezo/Gnani/MyOperator/Exotel product pages; GHL/Apollo/Smartlead/Instantly/Privyr/NeoDove/TeleCRM/AiSensy/Wati/Interakt pricing pages; Birdeye/Podium/Synup/SOCi/Thryv/NiceJob pricing+platform pages (sab June 2026 fetched; detailed URLs research agents ke reports me).
