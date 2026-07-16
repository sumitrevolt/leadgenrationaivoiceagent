# Customer Plan Delivery Audit — AI Marketing Automation ₹1,999

**Date:** 2026-07-17  
**Auditor role:** Production Delivery Auditor + Marketing Agency Operations Admin  
**Tenant under test:** Jiya Makeover Studio (`jiya-makeover` / billing alias `d79d690f61b3`)  
**Plan:** AI Marketing Automation — ₹1,999/mo (starter)  
**Mode:** Audit-only (no silent fixes; no outbound sends; no CRM/social mutations)  
**Code-reviewer:** [evidence honesty review](d05ae8fd-7322-45c2-8855-b51a314a01e4)

---

## 1. Executive verdict

**FINAL VERDICT: D. PRICING PROMISE EXCEEDS PRODUCTION CAPABILITY**

Platform tooling and many customer-portal Studio tools are real and deployed. Jiya is a paid, onboarded customer with a live mini-site and a bank of **draft** creatives. That is **not** the same as receiving the marketed service levels:

- Public page sells **roz** posts ready **~7 AM**, **Hands-Free Automations (20)**, **AI video ads every ~5 days**, and **CRM sync / webhooks** as included capabilities.
- Production evidence for Jiya shows **3 content-generation days in July (not daily)**, **12/12 queue items still `draft`**, **24 approvals open ~125h with SLA breaches**, **0 social jobs for Jiya**, **1 video stuck `pending`**, and a **monthly report file that is tiny and not ledger-acknowledged**.
- `delivery_state=delivered` on the client record is a **stale field**. Live Product One computation: **stage=`approval_pending`**, **deliverable_completion_pct=50**. Code wins.

Operational shape is also close to **C (tools available, service not fully delivered)**. Pricing-truth risk forces **D**.

**Evidence confidence:** High for provenance + Jiya queue/ledger/flags + public pricing/minisite browser. Medium for authenticated customer-portal interiors (login/OTP required — admin must enter). Low for per-engine Hands-Free tenant run proofs (flags ON, per-customer artifacts mostly UNVERIFIED).

### Explicit answers

1. **Is Jiya receiving everything she pays ₹1,999 for?** **No.**
2. **Overdue this month:** daily posts since last gen gap; publish proof; usable video cadence; honest 4 branded posters (not festival-padded); monthly report as customer-visible completed deliverable; clearance of stale approvals; GBP audit score artifact.
3. **Code/UI-only / not real service delivery:** most Hands-Free items (draft engines), CRM/webhooks without client creds, A/B variations (unproven), team round-robin (unconfigured), social auto-publish (`SOCIAL_AUTOPOST` unset → MOCK path), video “ready to share”.
4. **Automations with recent prod execution proof (Jiya-scoped):** `product_one_health` approval reminders + SLA breach events (ledger); content generation on 2026-07-11/14/15; video_ad row created 2026-07-12 (failed to become ready). Platform social/Postiz proven elsewhere historically — **not** for Jiya social jobs (0).
5. **Hide/clarify immediately:** Hands-Free “auto” framing; roz/~7AM SLA; video every ~5 days; CRM sync as automatic; “4 posters” counting; any implication of auto social publish.
6. **Before next paying customer:** fix daily content reliability; approval→share loop working; stop poster padding; regenerate quality-controlled first-week pack; honest pricing copy; onboarding checklist that blocks “fully activated” until GBP/social/VPA/CRM optional states are explicit.
7. **Agency-standard gaps:** monthly strategy doc, QC gate before customer sees drafts, account-manager ageing dashboard that drives action (not only reminders), engagement/attribution reporting, missed-delivery recovery SLA.

---

## 2. Production provenance

| Layer | Value | Evidence |
|---|---|---|
| Local HEAD | `aab11f1934e30275df582a8af623ee3afbd7b713` | `git rev-parse HEAD` |
| origin/main | same SHA | `git rev-parse origin/main` |
| VPS `/opt/leadgen` git | `aab11f19…` | SSH probe |
| `/health` | `version=aab11f19`, `environment=production`, healthy | `curl https://leadsgenai.in/health` |
| App images | `leadgen_app/worker/scheduler/worker_heavy/worker_video` → `:aab11f19` | `docker ps` |
| Staging skew | `leadgen_app_staging` → `42b8c1c0f708` (not prod path) | noted; not customer-serving |
| Activation | `ready_for_first_paid_customer=true`, `blocker_count=0` | `/api/activation/summary` |
| Graphify | query hit `auto_content`, `product_one_delivery`, `delivery_ledger`, studio | `graphify query … --budget 800` |

**Conclusion:** Local, origin, prod git, and serving app images are **aligned** on `aab11f19`. Audit conclusions apply to currently running production.

---

## 3. Customer delivery score (Jiya)

| Metric | Value |
|---|---|
| Promised features (public starter) | **93** |
| Applicable (marketing-only) | **93** (no voice minutes in starter) |
| Matrix DELIVERED | **1** |
| Matrix AUTOMATED | **0** |
| Matrix READY_MANUAL | **51** |
| Matrix CONFIG_REQUIRED | **3** |
| Matrix PARTIAL | **35** |
| Matrix FAILED | **1** |
| Matrix UNVERIFIED | **2** |
| Product One setup % | **100** |
| Product One deliverable % | **50** |
| Stage (live) | `approval_pending` |
| Content queue | 12 items, **all draft** |
| Pending approvals | **24** (stale/urgent ageing) |
| Posts scheduled | **0** |
| Posts published (status field) | **1** (UNVERIFIED channel proof; social_jobs=0) |
| Social jobs (Jiya) | **0** |
| Video ads ready | **0** (1 pending) |
| Monthly report ledger | **0** reports events |
| Undelivered paid detector | **0** clients (`has_paid_evidence` True) |

**Score interpretation:** Roughly half of Product One core deliverables “done” by internal scorer — but that scorer **over-counts posters** and treats drafts as progress. Marketing-page 93-feature fulfillment is far lower when DELIVERED/AUTOMATED are required.

---

## 4. Full 93-feature promise matrix

Source of truth: `app/marketing/packages.py` `_STARTER_FEATURE_GROUPS` ↔ production `GET /api/marketing/packages` ↔ browser `/pricing` (counts 33+10+7+8+4+6+5+20). **0 duplicates** in flat list.

| ID | Category | Public promise | Frequency/quantity | Code | Deployed | Configured | Recent run | Real deliverable | Customer visible | Automation | Status | Evidence | Gap | Required action | Owner | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F001 | Core Marketing Automation | Roz AI social posts — Hinglish caption + hashtags (39 niches, aapki industry ke hisaab se) | daily | Y | Y | Y | 2026-07-11/14/15 only | 12 drafts (not daily) | Approvals queue | scheduler content job | **PARTIAL** | content_queue 12 all draft; JULY_POST_DAYS=3 of ~17 | Promise=roz; actual=3 days; all draft not published | Fix daily content for paying clients + close approval SLA | Engineering+Ops | P0 |
| F002 | Core Marketing Automation | Branded post frames — aapka logo + business naam har post pe | on-demand | Y | Y | PARTIAL | brand poster draft | PARTIAL quality | Y | daily content | **PARTIAL** | Decision pack: placeholder phone on poster; mini-site brand OK | Brand frames quality/phone accuracy | Regenerate branded assets with real phone/logo | Ops | P0 |
| F003 | Core Marketing Automation | Customer portal — 1-click copy + WhatsApp/Insta share (roz subah ~7 baje content ready) | daily | Y | Y | Y | portal 200 | drafts visible path | Y | claim ~7am | **PARTIAL** | Portal routes live; 7am readiness NOT proven (items at 10:57Z / 03:30Z) | ~7 AM SLA unmet/unproven | Measure IST ready-by-7 metric + alert | Engineering | P0 |
| F004 | Core Marketing Automation | Festival calendar auto — Diwali, Holi, Rakhi, Independence Day sab covered | on-demand | Y | Y | Y | Rath Yatra festival items | 3 festival drafts | Y | auto_content festivals | **PARTIAL** | festival types in queue 2026-07-14/15 | Duplicates; quality vs calendar promise | Dedupe festival generation | Engineering | P1 |
| F005 | Core Marketing Automation | Tyohar/offer posts — sale day ke liye ready creatives + captions | on-demand | Y | Y | Y | campaign draft | 1 campaign draft | Y | daily content | **PARTIAL** | Local Offer Campaign in queue; decision pack city mismatch Mumbai vs Nagpur | Wrong locality in copy | Regenerate Nagpur-correct offer creatives | Ops | P0 |
| F006 | Core Marketing Automation | Google Business Profile audit (0–100 score) + top 5 fix suggestions | on-demand | Y | Y | N | none for Jiya | N | Studio gbp-tips | manual | **CONFIG_REQUIRED** | gbp_suggestions deliverable=pending; next_action asks GBP link | GBP not linked / no score artifact | Capture GBP URL in setup; run audit | Customer+Ops | P1 |
| F007 | Core Marketing Automation | Google reviews ke Hinglish reply drafts — copy-paste, rating bachao | on-demand | Y | Y | PARTIAL | none auto | N | Studio review-reply | REVIEW_MONITOR=1 but no Jiya proof | **READY_MANUAL** | review_replies deliverable=pending | No review-reply artifacts in queue/ledger | Seed review templates + monitor | Ops | P1 |
| F008 | Core Marketing Automation | 4 branded posters/mo — naam, phone, offer ke saath (SVG, print-ready) | monthly | Y | Y | Y | poster+festival counted | claim 4/4 padded | Y | daily content | **PARTIAL** | product_one counts poster\|festival; queue poster=1 festival=3; poster phone defect | Promise=4 branded posters/mo; only 1 true poster type | Stop counting festival text as poster; regenerate 4 SVG posters | Engineering+Ops | P0 |
| F009 | Core Marketing Automation | WhatsApp content pack — broadcast messages + status updates ready | on-demand | Y | Y | Y | 2026-07-11 whatsapp draft | 1 WA draft (malformed historically) | Y | content job | **READY_MANUAL** | whatsapp_pack=done; WHATSAPP_AUTO_SEND=0; decision pack truncated text | Not broadcast-ready quality; auto-send OFF by design | Regenerate clean WA pack; keep 1-click human send | Ops | P1 |
| F010 | Core Marketing Automation | Lead capture widget — 1-line script, form seedha dashboard me | on-demand | Y | Y | PARTIAL | embed 200 | snippet available | Studio website-widget + /b/.../embed | none | **READY_MANUAL** | HTTP embed:200; leads=0 in ledger | Widget may not be installed on customer site | Confirm paste on Jiya website | Customer+Ops | P1 |
| F011 | Core Marketing Automation | AI website chatbot — FAQ + lead capture (widget mode) | on-demand | Y | Y | PARTIAL | UNVERIFIED | UNVERIFIED | widget-chat API | none | **READY_MANUAL** | embed_widget/chatbot code + public route | No Jiya chatbot conversation proof | Smoke widget-chat for slug | Ops | P2 |
| F012 | Core Marketing Automation | CRM sync (Zoho/HubSpot) + programmable webhooks (lead/call events) | on-demand | Y | Y | N | none | N | send-to-crm API | CRM_SYNC=1 platform; per-client creds unknown | **CONFIG_REQUIRED** | CRM_SYNC=1; CUSTOMER_WEBHOOKS=1; no Jiya crm_sync proof | Needs Zoho/HubSpot tokens + webhook URL | Collect CRM creds or CLARIFY as optional | Customer | P0 |
| F013 | Core Marketing Automation | WhatsApp drip nurture — naye leads ko spaced follow-up messages | on-demand | Y | Y | PARTIAL | UNVERIFIED | draft engines | Studio followup | CADENCE/LIFECYCLE flags ON; send OFF | **PARTIAL** | Hands-free flags ON; WHATSAPP_AUTO_SEND=0 draft-not-send | Advertised drip vs ban-safe drafts | CLARIFY pricing: draft packs not auto-send | Product | P0 |
| F014 | Core Marketing Automation | Database reactivation — purane customers ke liye win-back campaigns | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio win-back | WINBACK_ENGINE=1 | **PARTIAL** | Flag ON; no Jiya winback artifact proven | No customer DB reactivation run evidence | Run winback draft cycle for Jiya | Ops | P1 |
| F015 | Core Marketing Automation | Competitor analysis + monthly marketing report — kya chala, kya nahi | monthly | Y | Y | PARTIAL | report file 1702B | file exists status pending | partial | CLIENT_REPORTS=1 | **PARTIAL** | d79d690f61b3_2026-07.html 1702 bytes; ledger reports=0; monthly_report pending | Tiny report + no ledger event | Regenerate report + write ledger event; email if entitled | Engineering | P0 |
| F016 | Core Marketing Automation | Referral tools + Ads copy pack + Reels script drafts | on-demand | Y | Y | Y | studio tools | on-demand only | Y | manual | **READY_MANUAL** | referral/ads/reel-script studio tools | No auto monthly pack delivery proven | Deliver monthly creative pack to approvals | Ops | P1 |
| F017 | Core Marketing Automation | UPI Scan & Pay QR card — counter/display ke liye branded | on-demand | Y | Y | PARTIAL | UNVERIFIED | UNVERIFIED | Studio upi-qr | manual | **READY_MANUAL** | upi-qr tool exists | Needs customer VPA | Collect UPI VPA; generate card | Customer+Ops | P2 |
| F018 | Core Marketing Automation | Mini-site `/b/aapka-slug` — bio link + digital visiting card + booking page (ek link sab kuch) | on-demand | Y | Y | Y | browser 200 | live mini-site | Y public | onboard seeded | **DELIVERED** | Browser https://leadsgenai.in/b/jiya-makeover 200; brand+booking form | Services pills generic | Enrich services catalogue | Ops | P2 |
| F019 | Core Marketing Automation | Appointment booking page — customer khud calendar slot book kare, aapko auto-confirmation | on-demand | Y | Y | PARTIAL | form on mini-site | enquiry form | Y | BOOKING_REMINDERS=1 unverified runs | **PARTIAL** | Booking section on mini-site; calendar lock claim unproven | True calendar slot booking vs enquiry form | Verify booking store writes; CLARIFY if enquiry-only | Product | P1 |
| F020 | Core Marketing Automation | AI image generation + Complete Post one-shot — caption + hashtags + AI image ek click me | on-demand | Y | Y | Y | UNVERIFIED Jiya run | UNVERIFIED | Studio complete-post/ai-image | manual | **READY_MANUAL** | Studio tools wired | No image artifact pinned to Jiya ledger | Generate Complete Post for Jiya as proof | Ops | P2 |
| F021 | Core Marketing Automation | AI video ads (Reels/Shorts) — har ~5 din naya video ready, SAB niches ke liye, 1-click share (koi extra charge nahi) | ~every 5 days | Y | Y | Y flag | 2026-07-12 pending | 1 pending video no path | N usable | VIDEO_AD_CYCLE=1 | **FAILED** | video_ads.jsonl status=pending path=null; not every ~5 days ready | Cadence+share promise unmet | Debug video render; deliver shareable MP4 | Engineering | P0 |
| F022 | Core Marketing Automation | Har post pe 1-click WhatsApp/copy share — approve karke seedha bhejo (aap control me; auto-post/bulk-send nahi, ban-safe) | on-demand | Y | Y | Y | approval path | copy/share UI | Y | ban-safe manual | **READY_MANUAL** | Promise itself says auto-post/bulk-send nahi; 24 pending approvals | Share only after approve; backlog | Clear approval backlog with Jiya | Ops+Customer | P0 |
| F023 | Core Marketing Automation | Content calendar + scheduler — mahine bhar ka plan + festival auto-schedule | monthly | Y | Y | Y | UNVERIFIED schedule runs | calendar drafts | Y | content_schedule.run_due | **PARTIAL** | posts_scheduled=0 | Scheduler not advancing to scheduled/published | Wire approved->scheduled->publish path | Engineering | P1 |
| F024 | Core Marketing Automation | Post variations A/B — ek idea se 2–4 alag versions, jo chale wo chuno | on-demand | Y | Y | Y | UNVERIFIED | UNVERIFIED | Studio | manual | **UNVERIFIED** | A/B variations claimed; no Jiya A/B artifacts found | No variation IDs in queue | Prove A/B generator for one topic | Engineering | P2 |
| F025 | Core Marketing Automation | Review kit — khush customer ko Google review, naraz ko private feedback (rating bachao) | on-demand | Y | Y | Y | UNVERIFIED | UNVERIFIED | Studio review-request | manual | **READY_MANUAL** | review-request tool | No sent review-request proof | Generate kit + share with Jiya | Ops | P2 |
| F026 | Core Marketing Automation | Team lead routing — members round-robin + WhatsApp handoff, koi lead miss nahi | on-demand | Y | Y | N | none | N | routing config APIs | none | **CONFIG_REQUIRED** | RoutingConfigIn exists; no team members proven for Jiya | Needs team setup | Configure team or CLARIFY | Customer | P2 |
| F027 | Core Marketing Automation | Product/service catalog + UPI payment links — share karo, customer wahi se pay kare | on-demand | Y | Y | PARTIAL | UNVERIFIED | UNVERIFIED | Studio service-menu/whatsapp-catalog | manual | **READY_MANUAL** | tools exist; mini-site services generic | Catalogue not populated with real prices | Load real services+UPI links | Customer+Ops | P1 |
| F028 | Core Marketing Automation | Hot leads dashboard — score ke hisaab se priority leads upar, pehle kisko call karein | on-demand | Y | Y | PARTIAL | leads=0 | empty | AI Inbox / pipeline | none | **PARTIAL** | ledger leads=0 | No hot leads yet; scoring UI may be empty | Drive traffic to mini-site/widget | Ops+Customer | P1 |
| F029 | Core Marketing Automation | Per-client blog page — programmatic SEO, Google pe organic reach badhao | on-demand | Y | Y | Y | blog 200 | blog surface live | Y public | seo_blog daily unverified for Jiya | **PARTIAL** | HTTP /b/jiya-makeover/blog 200 | Content quality/quantity unverified | Verify post count+indexability | Ops | P2 |
| F030 | Core Marketing Automation | Sentiment + hashtag research — kya trend kar raha, kaunsa tone chal raha | on-demand | Y | Y | Y | UNVERIFIED | UNVERIFIED | Studio hashtags/sentiment | manual | **READY_MANUAL** | studio tools | No research artifact in ledger | Run hashtag+sentiment once | Ops | P3 |
| F031 | Core Marketing Automation | Customer 2FA (TOTP) login security — account safe rakho | on-demand | Y | Y | UNVERIFIED | UNVERIFIED | UNVERIFIED | login security | n/a | **UNVERIFIED** | TOTP code present in codebase (not live-tested this audit) | No browser 2FA proof without customer login | Customer enables 2FA; smoke test | Customer+Security | P2 |
| F032 | Core Marketing Automation | Post approval workflow — publish se pehle aapki OK (portal me) | on-demand | Y | Y | Y | approval_reminded x63 | 24 pending open | Y | product_one_health + CONTENT_APPROVAL_AUTO=1 | **PARTIAL** | 24 pending ~125h; SLA breached; auto-approve flag ON but backlog remains | Workflow not converting to approved/published | Investigate CONTENT_APPROVAL_AUTO behavior + customer notify path | Engineering | P0 |
| F033 | Core Marketing Automation | GST invoice download portal se | on-demand | Y | Y | PARTIAL | invoice row exists | invoice present fields sparse | billing API | n/a | **PARTIAL** | gst invoice for d79d690f61b3 created_at 2026-07-05; number/amount null in probe | Download UX + Rule-46 fields need verify | Customer download smoke with auth | Billing | P1 |
| F034 | Content & Creative | Carousel maker — Instagram multi-slide carousel posts (SVG ready) | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F035 | Content & Creative | Meme generator — niche-relevant Hinglish memes, viral-ready | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F036 | Content & Creative | Testimonial poster — customer review → branded poster + caption | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F037 | Content & Creative | Content repurpose — 1 topic/blog → 7 alag formats (post/reel/thread…) | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F038 | Content & Creative | Reel/Ad voiceover script — Hinglish VO record karne ke liye ready | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F039 | Content & Creative | YouTube metadata — title + tags + description optimized | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F040 | Content & Creative | Instagram 9-grid planner — cohesive feed layout | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F041 | Content & Creative | Story highlights planner — categories + cover ideas | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F042 | Content & Creative | Regional language post — caption Hindi/Marathi/Tamil/Telugu… me convert | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F043 | Content & Creative | Evergreen post ideas — kabhi bhi repost-able content bank | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F044 | Local SEO & AI Discovery | Get-Found-by-AI (AEO) — ChatGPT/Gemini/Perplexity pe dikhne ka checklist | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F045 | Local SEO & AI Discovery | Schema markup generator — LocalBusiness JSON-LD (Google rich results) | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F046 | Local SEO & AI Discovery | FAQ page builder — website ke liye ready Q&A | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F047 | Local SEO & AI Discovery | 'Service in city' SEO pages — local search ke liye landing pages | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F048 | Local SEO & AI Discovery | Listings / NAP consistency check — directories pe naam/phone/address audit | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F049 | Local SEO & AI Discovery | DIY rank-check guide — Google ranking khud track karne ka tareeka | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F050 | Local SEO & AI Discovery | Conversion tracking setup — GA4 / Meta pixel / UTM checklist | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F051 | Leads & Conversion | AI Inbox — saari inquiries intent + urgency ke hisaab se sorted | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F052 | Leads & Conversion | Lead magnet builder — free guide/checklist se leads capture | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F053 | Leads & Conversion | Speed-to-lead instant reply — naya lead aate hi ready message | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F054 | Leads & Conversion | Ad budget planner — niche + goal ke hisaab se daily ad spend suggestion | daily | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F055 | Leads & Conversion | Lost-lead reasons + fix — kyu convert nahi hua, kaise sudhaarein | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F056 | Leads & Conversion | Newsletter builder — monthly email newsletter ka plan + content outline | monthly | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F057 | Leads & Conversion | Quote / estimate draft — inquiry se professional price quote | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F058 | Leads & Conversion | ROI calculator — spend vs revenue estimate dikhaao | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F059 | Reviews & Reputation | Bad-review rescue — naraz review ka polite damage-control reply | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F060 | Reviews & Reputation | Reviews widget — website pe Google reviews showcase | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F061 | Reviews & Reputation | Case study generator — customer success story (social-proof content) | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F062 | Reviews & Reputation | NPS / CSAT survey builder — customer feedback survey ready | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F063 | Sales & Retention | Objection handler — 'mehenga hai / sochta hoon' ka best reply | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F064 | Sales & Retention | Loyalty program design — points + rewards gamified plan | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F065 | Sales & Retention | Coupon generator — code + expiry + WhatsApp text | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F066 | Sales & Retention | Customer reminders — appointment/renewal/payment ke auto messages | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F067 | Sales & Retention | Complaint recovery flow — angry customer ko wapas khush karna | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F068 | Sales & Retention | UGC request kit — customers se photo/video testimonials maango | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F069 | Planning & Coaching | AI Growth Coach — har hafte 3 high-impact action suggestions | weekly | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F070 | Planning & Coaching | Next-Best-Action — aaj kya karna hai, priority task list | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F071 | Planning & Coaching | Daily Owner Brief — business ka ek-nazar daily summary | daily | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F072 | Planning & Coaching | Customer avatar — ideal buyer profile + targeting guidance | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F073 | Planning & Coaching | Best time to post/call/message — niche-wise optimal timing | on-demand | Y | Y | PARTIAL | UNVERIFIED | N | Studio/portal tool | manual_on_demand | **READY_MANUAL** | Studio _TOOLS route exists; customer portal shell /app/customer* | No Jiya-specific recent run artifact proven this audit | Generate once for Jiya + attach ledger proof | Ops | P2 |
| F074 | Hands-Free Automations | Appointment/booking reminders — booking se pehle auto WhatsApp/SMS reminder (no-show kam) | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F075 | Hands-Free Automations | Repeat-service due reminders — 'aapki service due hai' auto recurring nudge | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F076 | Hands-Free Automations | Naye Google review pe auto AI reply-draft — review aate hi ready jawab | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F077 | Hands-Free Automations | Brand & review mention monitoring (weekly) — net pe aapke naam ka zikr + reply drafts | weekly | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F078 | Hands-Free Automations | Local Google rank tracking (weekly) — aapki keywords ki ranking auto-track + report | weekly | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F079 | Hands-Free Automations | Birthday/anniversary auto-wishes — customers ko personalized wish draft | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F080 | Hands-Free Automations | Monthly customer newsletter — har mahine email newsletter auto-draft | monthly | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F081 | Hands-Free Automations | Cold-lead auto win-back — thande pade leads ko wapas laane ke drafts | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F082 | Hands-Free Automations | Multi-channel follow-up cadence — WhatsApp+email+SMS sequenced auto-advance | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F083 | Hands-Free Automations | Lifecycle nurture journeys — inquiry→engaged→loyal event-based auto-drafts | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F084 | Hands-Free Automations | Hot-lead instant alert — naya high-intent lead aate hi turant aapko notify | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F085 | Hands-Free Automations | Sales deal auto next-action — har deal ka agla step auto-suggest | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F086 | Hands-Free Automations | Signup→paid nurture — naye signup ko paying customer banane ki auto-sequence | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F087 | Hands-Free Automations | Email deliverability auto-watch — aapki emails spam me na jaayein (SPF/DMARC/blacklist auto-check) | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F088 | Hands-Free Automations | Har inquiry auto-log + source attribution — kaunsa lead kahan se aaya, timeline auto-record | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F089 | Hands-Free Automations | Weekly AI-staff work report — 'is hafte aapki AI team ne kya kiya' auto-summary | weekly | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F090 | Hands-Free Automations | Evergreen content auto-repost — purane top posts auto-freshen + re-queue | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F091 | Hands-Free Automations | NPS/CSAT auto-survey — customer satisfaction survey periodic auto-draft | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F092 | Hands-Free Automations | Stale-inquiry auto-followup — 24h koi reply nahi → auto nudge draft | automated/recurring (claimed) | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |
| F093 | Hands-Free Automations | Roz-subah Owner Brief auto-tayar — naye leads + ready content + aaj ke kaam, bina click | daily | Y | Y | FLAGS_ON | platform flags ON; Jiya tenant runs UNVERIFIED | draft-not-send expected | mostly admin/draft stores | event/scheduler draft engines | **PARTIAL** | Prod flags for hands-free mostly =1; WHATSAPP_AUTO_SEND=0; pricing presents as auto | Advertised hands-free vs draft-only ban-safe reality | CLARIFY/BETA on pricing; prove per-engine Jiya runs | Product+Ops | P0 |

### Promise inventory hygiene

- **Overlaps:** Core “Referral tools + Ads copy + Reels” bundles three Studio tools into one bullet; Hands-Free repeats several Core themes (newsletter, win-back, NPS, owner brief).
- **Vague:** “Competitor analysis + monthly marketing report” combines research tool + report SLA.
- **Misleading vs ban-safety:** Hands-Free items read as auto-send; code/docs intentionally **draft-not-send** (`WHATSAPP_AUTO_SEND=0`).
- **Combo page** on `/pricing` correctly separates Voice ₹5,999 — starter remains marketing-only. Hot-leads copy still says “pehle kisko **call** karein” inside marketing plan (clarify).

---

## 5. Jiya current-month entitlement and delivery ledger

### Entitlement (Product One template + package promises)

| Entitlement | Promised | Actual (July 2026 evidence) | Verdict |
|---|---|---|---|
| Daily social posts | ~1/day from ~7 AM IST | Generation days 11,14,15 only; 5 `post` drafts total | **OVERDUE / PARTIAL** |
| 12 social captions/posts bank | ≥12/mo | Status 11/12 in_progress; drafts only | **NEAR / not delivered** |
| 4 branded posters/mo | 4 SVG posters | Scorer 4/4 via poster+festival; true `poster` type=1; phone defect | **MISCOUNTED** |
| Festival creatives | calendar-driven | 3 Rath Yatra festival drafts (dup risk) | **PARTIAL** |
| WhatsApp pack | usable pack | 1 draft; historical truncate/markdown issues | **NEEDS REGEN** |
| AI video ~5 days | shareable video | 1 pending, no path | **FAILED** |
| Monthly report | customer-visible | HTML 1702B exists; ledger reports=0; status pending | **PARTIAL/WIRING** |
| Publish proof | scheduled/published | posts_scheduled=0; social_jobs=0 | **MISSING** |
| Approvals SLA | timely customer OK | 24 pending; 125h; sla_breached | **BREACHED** |

### Ledger snapshot

- Events total: **92**
- Notable counts: `approval_reminded` **63**, `sla_breached` **5**, `post_approved` **5**, `post_published` **1**, `video_ready` **1** (vs video row still pending — treat carefully), `integration_failed` **4**, `reports` **0**
- Last event: `2026-07-16T09:06:42Z` approval_reminded
- `value_delivered` summary flag True vs live stage approval_pending — **do not trust single field**

### Next 7-day delivery schedule (recommended operational plan)

| Day | Action |
|---|---|
| D0 | QC regenerate Jiya pack (phone/city/dedupe); clear obsolete drafts |
| D1 | Customer approval session (target ≤5 priority posts) |
| D2 | Manual publish/share proof for ≥2 posts; log proof |
| D3 | Force video render or disable claim; deliver WA pack clean |
| D4 | GBP link + audit score; regenerate report with ledger event |
| D5 | Verify daily content job produced IST-morning drafts |
| D6-7 | Agency weekly summary to customer; freeze Hands-Free pricing copy |

---

## 6. Automation execution matrix

### Daily content / social

`Trigger(scheduler content ~07–09 IST)` → `Preconditions(paid/active clients)` → `Task(auto_content.run_daily_content)` → `Provider(free LLM + SVG frames)` → `Output(content_queue drafts)` → `Approval(content_approvals)` → `Delivery(1-click share / SOCIAL_ENGINE)` → `Logging(delivery_ledger + AutomationLog)` → `Retry/DLQ(job wrapper)` → `Escalation(product_one_health SLA)`

| Check | Result |
|---|---|
| Scheduler registration | YES (`team_scheduler` content job) |
| Actual Jiya daily runs | **NO** — only 3 July days with items |
| Queue routing | drafts created |
| Worker availability | images healthy on aab11f19 |
| Publish provider | `SOCIAL_ENGINE=1`, `dry_run=false`, but **`SOCIAL_AUTOPOST` unset → MOCK path** (`app/tasks/reporting.py`) |
| Idempotency | ledger keys / approval ids present |
| False-success risk | **HIGH** if dry_run were true (currently false); MOCK autopost can look “ok” without channel post; `approval_reminded status=success` while backlog grows |
| Tenant context | content_queue keyed by `jiya-makeover` |

### Video ads

`VIDEO_AD_CYCLE=1` → `video_ad_cycle.run_cycle` (rides content job) → Jiya row `pending` since 2026-07-12 → **no shareable output**.

### Hands-Free engines

Flags ON in prod for booking reminders, review monitor, newsletter, winback, lifecycle, cadence, owner brief, etc. **Promise language = auto customer outcomes. Implementation = mostly draft generation + ban-safe no auto-send.** Per-Jiya successful customer-visible outputs for these 20: **UNVERIFIED / PARTIAL**.

### Approval / health

Hourly `product_one_health` **is executing** (ledger proof). That proves monitoring, not marketing delivery.

---

## 7. Customer portal / browser findings

| Surface | HTTP | Finding |
|---|---|---|
| `/pricing` | 200 | Live 93-feature accordion matches packages.py; ₹1,999 marketing-only badge |
| `/b/jiya-makeover` | 200 | Real branded mini-site; Call/WhatsApp/Enquiry; Nagpur; booking+review forms |
| `/b/jiya-makeover/card` | 200 | Digital card route up |
| `/b/jiya-makeover/blog` | 200 | Blog surface up |
| `/b/jiya-makeover/embed` | 200 | Widget embed up |
| `/app/customer` `/app/customer/marketing` | 200 | Shell loads; **authenticated data not exercised** (OTP/password = human) |
| Approvals UX | UNVERIFIED browser-auth | API/status show 24 pending — customer action bottleneck |

**Not done (policy):** no password/OTP entry; no approve/reject; no WhatsApp send; no social publish; no CRM write.

---

## 8. Admin cockpit findings

| Surface | HTTP | Finding |
|---|---|---|
| `/app/delivery-command-center` | 200 | UI present: customers KPIs, pipeline, automation logs, automation runs, DLQ filters |
| Data panels | auth-gated | Requires admin Bearer token paste — **metrics not loaded in unauthenticated browser** |
| Backend APIs | present | `/api/admin/delivery-cockpit`, `/delivery-logs`, `/automation-logs` |
| SSH truth | available | Used as primary evidence for Jiya when UI auth blocked |

---

## 9. Agency-standard gap analysis

| Capability | State | Notes |
|---|---|---|
| 1. Client onboarding | **Partial** | Setup 100% checks; brand/social flags true; quality of assets still weak |
| 2. Monthly strategy | **Missing** | No evidenced monthly theme/campaign brief for Jiya |
| 3. Content QC | **Partial/weak** | Decision pack found phone placeholder, city mismatch, duplicate captions |
| 4. Account management | **Partial** | Cockpit+reminders exist; 125h approvals show weak human follow-through |
| 5. Performance measurement | **Missing/weak** | No engagement/attribution proof; leads=0 |
| 6. Customer communication | **Partial** | Approval emails sometimes logged; weekly/monthly narrative weak |
| 7. Service reliability | **Partial** | Ledger+SLA events exist; missed daily recovery not evidenced |
| 8. Compliance/safety | **Strong intent** | WA auto-send OFF; tenant isolation tested in suite; DPDP gates intact |
| 9. Retention/growth | **Partial** | Health/SLA tooling; no churn/CSAT loop proven for Jiya |

**Sell confidence:** Do **not** sell as full-service agency autopilot until QC + daily SLA + approval loop + honest pricing are fixed.

---

## 10. Pricing-page truth risks

| Claim | Risk | Recommendation |
|---|---|---|
| Roz posts ~7 AM | Material unmet | **CLARIFY** → “Daily drafts targeted mornings; portal shows ready queue” or fix SLA |
| Hands-Free Automations (20) | Reads as auto-send | **CLARIFY/BETA** → “Auto-drafts; human send” |
| AI video every ~5 days | Failed for Jiya | **HIDE_TEMPORARILY** until render proven |
| CRM sync Zoho/HubSpot | Config required | **CLARIFY** optional integration |
| 4 branded posters/mo | Padded metric | **CLARIFY** definition; fix scorer |
| Auto social publish implication | MOCK without SOCIAL_AUTOPOST | **KEEP** ban-safe wording already on F022; reinforce elsewhere |
| No extra charge video | Free stack OK; delivery fail | Keep free claim; fix delivery |
| Hot leads “…call karein” | Voice bleed on marketing plan | **CLARIFY** remove call verb |
| Calling on Combo only | OK | **KEEP** |

---

## 11. Top launch blockers (P0)

1. Daily content SLA not met for paying Jiya (3 days ≠ roz).
2. Approval backlog 24 / SLA breached — blocks all downstream delivery.
3. Poster entitlement honesty (festival padded + wrong phone).
4. Video cadence promise failing (`pending` no asset).
5. Social publish path MOCK for customers (`SOCIAL_AUTOPOST` unset) while SOCIAL_ENGINE on — false confidence.
6. Monthly report not ledger-complete / not customer-closed.
7. Pricing Hands-Free + roz + video claims exceed evidenced capability.

---

## 12. Recommended additions

- Entitlement ledger UI: promised vs delivered counts for month.
- Pre-publish QC gate: phone/city/dedupe/prohibited claims.
- Missed-day catch-up job for paid clients.
- Customer notification when drafts ready (WhatsApp/email) with deep link.
- Per-customer automation run attribution (`client_id` on jobs).
- Agency monthly strategy note template auto-attached to report.

---

## 13. Recommended promise clarifications

| Feature area | Action |
|---|---|
| Hands-Free group | **CLARIFY** as auto-draft / human-approve |
| Daily ~7 AM | **CLARIFY** or **KEEP** only after metric green |
| Video ads | **HIDE_TEMPORARILY** |
| CRM/webhooks | **CLARIFY** setup required |
| Team routing | **CLARIFY** |
| Mini-site/portal/studio tools | **KEEP** |
| Ban-safe 1-click share | **KEEP** (accurate) |

---

## 14. Seven-day remediation plan

1. **Day 1:** Pricing copy patch proposals (no auto-apply without approval) + regenerate Jiya QC pack.
2. **Day 2:** Approval working session; publish/share ≥2 proofs.
3. **Day 3:** Poster scorer fix + 4 real SVG posters.
4. **Day 4:** Video pipeline debug or hide claim.
5. **Day 5:** Report rebuild + ledger `weekly_report`/`monthly` event.
6. **Day 6:** Daily content job verification for Jiya with IST timestamp proof.
7. **Day 7:** Re-audit matrix deltas; gate next customer onboarding checklist.

---

## 15. Thirty-day agency maturity plan

Week 1: delivery truth + pricing honesty.  
Week 2: QC + strategy briefs.  
Week 3: measurement (leads/bookings/reviews MoM).  
Week 4: retention loops (CSAT, renewal, health).  
Exit criteria: ≥90% applicable Core promises DELIVERED/AUTOMATED for Jiya for a full calendar month with browser+ledger proof.

---

## 16. Evidence appendix

### Commands / probes

- `curl.exe https://leadsgenai.in/health` → version aab11f19
- `curl.exe https://leadsgenai.in/api/activation/summary` → ready, blockers 0
- `curl.exe https://leadsgenai.in/api/marketing/packages` → 93 features
- SSH `docker exec leadgen_app python /tmp/jiya_probe.py` → status/queue/ledger/flags
- Browser: `/pricing`, `/b/jiya-makeover`, `/app/delivery-command-center`
- Graphify: delivery subsystem BFS from `auto_content` / `product_one_delivery`
- Prior docs: `docs/PRODUCT_ONE_DELIVERY_MAP.md`, `docs/DELIVERY_OS_AUDIT.md`, `docs/JIYA_CONTENT_DECISION_PACK_2026-07-15.md`
- Code-reviewer pass: agent `d05ae8fd-7322-45c2-8855-b51a314a01e4`

### Flags observed (names only)

`SOCIAL_ENGINE=1`, `social_engine.json dry_run=false`, `VIDEO_AD_CYCLE=1`, `CLIENT_REPORTS=1`, `AUTO_DELIVER_VALUE=1`, `CRM_SYNC=1`, `CUSTOMER_WEBHOOKS=1`, hands-free engines mostly `=1`, `WHATSAPP_AUTO_SEND=0`, `SOCIAL_AUTOPOST` empty, `CONTENT_APPROVAL_AUTO=1`.

### Explicitly UNVERIFIED (do not invent)

- Authenticated customer portal click-paths
- Admin cockpit live KPI numbers (token required)
- Channel connection of Jiya Instagram/Facebook tokens
- True destination of the single `post_published` ledger event
- Content of 1702-byte monthly HTML beyond existence/size
- Per Hands-Free engine last success for Jiya
- TOTP 2FA enabled state for Jiya login

### Audit constraints honored

- No silent code fixes
- No secrets printed
- No real WA broadcast / social publish / CRM mutation / payment
- Tenant focus = Jiya only

---

## Loop Engineer 9-field block

- **Goal:** Evidence-based ₹1,999 plan delivery audit for Jiya + pricing truth
- **Inspected:** packages.py, Product One delivery, content queue, ledger, flags, pricing/minisite/cockpit browser, graphify, prior delivery docs, code-reviewer
- **Problems Found:** daily SLA miss; approval SLA; poster padding; video pending; MOCK social autopost; report ledger gap; Hands-Free overclaim
- **Changed:** docs only — `docs/audits/customer_plan_delivery_audit_2026-07-17.md` (no product code)
- **Tests Run:** not applicable for audit-only; live probes + browser instead
- **Verification Evidence:** SHA aab11f19 aligned; Jiya probe JSON; pricing 93; mini-site 200
- **Risks:** Selling next customer on current public copy = trust/chargeback risk
- **Remaining:** Auth-gated portal deep browser with human OTP; fix loop after approval
- **Next Highest Priority:** Pricing clarifications + Jiya QC/approval catch-up (P0)

