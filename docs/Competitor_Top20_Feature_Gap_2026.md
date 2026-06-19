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

> **⚠️ STATUS UPDATE (2026-06-19 docs-audit):** Is backlog ke ~saare free-stack P0/P1 items ab **BUILT + routed + mounted** hain (modules doc-date ke baad ship hue, list update nahi hui — code se grep-verified, evidence `docs/DOCS_AUDIT_2026_06_19.md`). Naya kaam mat samjho — sirf neeche 3 items genuinely OPEN, woh bhi **DLT/telephony-blocked** (build nahi): #5 live human transfer, SMS-DLT live send, RCS rich-cards. Baaki sab parity (§3) me move ho chuke. Examples: #1 `brand_frames.py` · #2 `business_card.py` · #3 `magic_resize.py` · #4 `review_to_post.py` · #6 `/api/voiceai/ask` · #7 `speed_to_lead.py`.

### P0 (high-impact, free-stack, abhi buildable)
1. **Branded frames + daily-post feed** (AdBanao signature, 4.5M users) — PIL compositor: client logo+naam+phone auto-overlay festival/daily templates pe → per-client roz ready post (download/1-click WA). Pieces hain (brand_kit, festivals, templates, ai_image) — sirf frame engine + daily feed missing.
2. **Digital business card** (AdBanao/Thryv) — `/b/{slug}/card` page + .vcf download + QR. mini_site extension, ~1 din.
3. **Magic resize / multi-format export** (Canva/Predis) — 1 design → square/story/banner/WA-status sizes (PIL).
4. **Review→post marketing** (SocialPilot/NiceJob) — 5★ review → branded poster auto-draft. Reviews + poster gen dono hain, glue missing.
5. **Live human transfer w/ context** (voice — ≥4 competitors) — AI call me "owner se baat karwao" → Exotel connect-leg transfer + Hinglish summary whisper. Advanced tier ka biggest missing piece.
6. **"Ask AI" over call/campaign data** (Vodex Ask-AI) — NL command bar ko call transcripts/qualifications/campaign stats pe extend karo.
7. **Speed-to-lead SLA metric + auto-engage** (Privyr/Podium "<2 min") — inquiry→first-touch time measure + dashboard badge "2-min me jawab"; AUTO_CALLBACK + lead_alerts already hain, ek unified pipeline + metric banao. Marketing copy gold.
8. **Client content-approval workflow** (agency-grade) — draft → client portal/WA approve link → status=approved → ready queue. Portal hai, approval loop missing.
9. **Snapshots / niche-setup clone** (GHL signature) — FDE deploy ko formalize karo: saved snapshot JSON (journeys+cadence+calendar+widget+mini-site config) → naya client = 1-click apply.
10. **Lead distribution round-robin** — client ke staff me leads auto-assign (NeoDove/TeleCRM core). Confirmed missing.

### P1 (differentiating, moderate effort)
11. **AI-search/GEO visibility report** (Birdeye early-mover) — "ChatGPT/AI me aapka business dikhta hai?" free-LLM probe → score+tips. Lead magnet #3 banao (audit, site-audit ke baad).
12. **Local grid rank tracker** (Synup $5/loc) — existing rank tracker ko 3×3 geo-grid (Places locationBias, cost-capped).
13. **India listings presence score** — Justdial/Sulekha/IndiaMART/Google presence checklist-audit (auto-sync ToS-blocked; report+guide enough). GBP-audit me section add.
14. **Cold-email spintax/A-B + per-variant stats** (Smartlead) — outreach templates me variants + reply-rate tracking.
15. **Telecaller gamification leaderboard** (NeoDove) — dialer dispositions → daily leaderboard card.
16. **Trackable proposals** (Privyr) — proposal/short-link pe view-pixel → "client ne proposal khola" alert.
17. **WhatsApp sticker pack + GIF maker** (AdBanao) — PIL/webp, viral feature, low effort.
18. **Repeat-service reminders** (NiceJob) — customer CRM me service-due cycles (AC/pest/salon) → wish-draft pattern reuse.
19. **Long-video→clips repurposing** (Simplified/Predis) — ffmpeg scene-cut+subtitles, HEAVY → worker-only, opt-in (qa-job lesson).
20. **Connected-call billing + competitor price-compare section** — pricing page copy (Vodex framing + MyOperator anchor). 1 ghanta.

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
