# TASKS — Competitor Feature-Gap Backlog (2026-06-10)

> Source: `docs/Competitor_Top20_Feature_Gap_2026.md` (26 competitors deep research).
> Rule: build se pehle `grep '@router' app/api/*.py` — duplicates already dedupe kiye, par double-check karo.

## ✅ PRODUCTION-READINESS AUDIT (2026-06-14) — deep live scan done
**Verdict: system HEALTHY, loops in loop, sab agents kaam kar rahe. Lone blocker = Razorpay (user-action).**
- ✅ **Automation loops ALL firing**: growth/ops/reply_triage/watchdog/onboard/qa/trainer `last_ok=true`; `overdue=[]`, `never_ran=[]`, celery queue 0. Hermes infra **100/100**.
- ✅ **Pipeline flowing**: 936 prospects (432 email), 309 cadence-enrolled, 122 reply-drafts, **5 hot leads** (DB, threshold 60 — code already tuned 70→60 kyunki cold leads cap ~68).
- ✅ **Persona pack (140 agency-agents) wired into 3 core engines**: ads-pack (ppc/paid-social), sales-team deep-dive (discovery/outreach/objection), post_generator (social-media-strategist). skill_pack **202 skills** LIVE.
- ✅ **Fixed this session**: (1) Celery backlog 8347→0 (self_improve_tick accumulation, purged); (2) content-feedback `best_themes` DEAD loop (galat kwarg `limit`+indexing → ab chalega); (3) `gap_check.py` KeyError('provider').
- ⚠️ **Flags OFF (mostly intentional)**: CRM_SYNC (per-client creds chahiye), NEWSLETTER_ENGINE, WINBACK_ENGINE, CLIENT_REPORTS, BRAND_PULSE, TEAM_REPORT — content/use-case ready hone par ON.
- 🚨 **#1 BLOCKER (USER): Razorpay 401 "Authentication failed"** — LIVE-confirmed. 0 invoices, koi revenue possible nahi. Fix: dashboard se keys regenerate → `.env` update → `up -d --no-deps app` → webhook register (`/api/billing/webhooks/razorpay` + `RAZORPAY_WEBHOOK_SECRET`). Pehla paid customer se pehle ZAROORI.
- **Naya agent NAHI chahiye** — 14-staff roster + loops comprehensive aur healthy hain. Aur agent = bloat.

## P0 — ✅ BUILT 2026-06-11 (commit pending deploy — /ship)
- [x] Branded frames + daily-post feed (`brand_frames.py`, /api/brand/frames/*)
- [x] Digital business card `/b/{slug}/card` + .vcf + QR (`business_card.py`)
- [x] Magic resize (`magic_resize.py`, /api/brand/resize)
- [x] Review→post (`review_to_post.py`, /api/brand/review-post)
- [x] Voice human transfer w/ context (`call_transfer.py`, gated CALL_TRANSFER) — voice-pipeline intent wiring PENDING
- [x] "Ask AI" over call data (`call_insights.py`, /api/voiceai/ask)
- [x] Speed-to-lead metric (`speed_to_lead.py`) — dashboard badge + digest hook PENDING
- [x] Client content-approval workflow (`content_approval.py`)
- [x] Snapshots capture/apply (`client_snapshots.py`)
- [x] Lead round-robin (`lead_distribution.py`)
- [x] BONUS P1: WA sticker pack · trackable proposals · dialer leaderboard

### P0 follow-ups
- [x] DEPLOYED 2026-06-11 ✅ — 550 routes live, smoke all-200, geo-check LIVE-proven, flags SERVICE_REMINDERS+OUTREACH_AB ON
- [ ] CALL_TRANSFER ON karna ho to: callers me flow_state["owner_phone"] set + Exotel KYC pehle
- [x] Voice pipeline detect_transfer_intent wiring (pipeline.py run_turn, gated) — NOTE: callers ko flow_state["owner_phone"] dena hota
- [x] Scheduler hooks: digest speed-to-lead Boss-event, watchdog proposal-opened sweep, content service-reminders
- [x] UI tabs: growth_tools 11→17 (frames/card/approvals/speed+board/ask-AI/localseo+)
- [x] ffmpeg — image me pehle se tha (Dockerfile.lock), live verified 7.1.4

## P1 — ✅ BUILT 2026-06-11 (pending deploy)
- [x] AI-search/GEO visibility report (`geo_visibility.py`, public /api/localseo/geo-check)
- [x] Local 3×3 grid rank tracker (`grid_rank.py`, cost-capped)
- [x] India listings presence score (`listings_presence.py`, checklist — no scraping)
- [x] Cold-email spintax/A-B (`outreach_variants.py`, gated OUTREACH_AB)
- [x] Telecaller leaderboard (✅ built in P0 batch)
- [x] Trackable proposals (✅ built in P0 batch)
- [x] WA sticker pack + GIF maker (✅ dono built)
- [x] Repeat-service reminders (`service_reminders.py`, gated SERVICE_REMINDERS)
- [x] Long-video→clips (`video_clips.py`, background-thread, ffmpeg VPS pe install karna)
- [x] Pricing page compare strip + connected-calls line

## P2 / blocked
- [x] Inbox rotation code (`OUTREACH_MAILBOXES` JSON, gated) — USER: 2nd domain/mailbox kharido tab ON
- [x] AI avatar video (`avatar_video.py` — POLLINATIONS_API_KEY pe chalti)
- EXTERNAL-BLOCKED: Meta publish/Lead-Ads/CTWA/CAPI, GBP API, WA Flows approval, DLT, Exotel KYC, Truecaller
- SKIP FOREVER: unofficial WA auto-responder, Justdial/IndiaMART/LinkedIn scrape, SERP scrape

## Pipeline Review actions (2026-06-12 — score 31/100, detail: SESSION_LOG)
- [x] Junk-deal guard: reply_agent bulk-sender skip + deal sirf known-prospect (commit 5a2a41f) + 2 junk deals (PayU/Instamojo) VPS se removed
- [x] Prospect store hygiene: created_at/updated_at in _append + mark/set bumps (5a2a41f)
- [ ] USER/DAILY: human dialer sprint — 421 phone-only prospects, `/app/dialer` se 20-30 calls/din (top niches: home_loans 48 · real_estate 43 · solar 39); battlecard landmines use karo
- [ ] Email-finder enrich run on ~289 phone-only prospects (`POST /api/growth/prospects/find-email` batch) — sendable pool 132 → 250+ target
- [ ] USER: 1 "replied" prospect ko follow-up (store me single garam lead)
- [ ] Reply intent classifier tune — 63/79 drafts "other" (junk guard ke baad re-measure karo, fir prompt improve)
- [ ] Sales-team auto deep-dives ko hot DB leads (score 70+) pe target karna (abhi sab Grade C aa rahe)
- [ ] Inbound watch: /compare SEO + channel-experiment outcomes feed karte raho (2-4 hafte)

## Pehle se pending (carry-over)
- [ ] USER: Razorpay API keys 401 fix (dashboard regenerate) — pehla paid customer se pehle ZAROORI
- [ ] USER: Razorpay webhook register + RAZORPAY_WEBHOOK_SECRET
- [ ] USER: UPI_VPA set · Exotel key rotate · DLT via Udyam · Cloudflare token perms
