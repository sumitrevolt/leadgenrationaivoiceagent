# TASKS — Competitor Feature-Gap Backlog (2026-06-10)

> Source: `docs/Competitor_Top20_Feature_Gap_2026.md` (26 competitors deep research).
> Rule: build se pehle `grep '@router' app/api/*.py` — duplicates already dedupe kiye, par double-check karo.

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
- [ ] DEPLOY batch (/ship; HARD RELOAD — naya page-route /b/{slug}/card) + live smoke naye public endpoints
- [ ] Voice pipeline me detect_transfer_intent wiring (hot-path safe keyword check)
- [ ] Scheduler hooks: digest me speed-to-lead line, proposal-opened alert, pending-approvals reminder
- [ ] UI tabs: frames daily-feed + card + approvals (marketing.html/growth-tools pattern)

## P1 — next
- [ ] AI-search/GEO visibility report (lead magnet #3)
- [ ] Local 3×3 grid rank tracker (Places locationBias, cost-capped)
- [ ] India listings presence score in GBP audit (Justdial/Sulekha/IndiaMART checklist)
- [ ] Cold-email spintax/A-B + per-variant reply stats
- [x] Telecaller leaderboard (✅ built in P0 batch)
- [x] Trackable proposals (✅ built in P0 batch)
- [x] WA sticker pack (✅ built; GIF maker pending)
- [ ] Repeat-service reminders (customer CRM cycles)
- [ ] Long-video→clips (ffmpeg, WORKER-ONLY — qa-job lesson)
- [ ] Pricing page: competitor price-compare + "connected calls only" framing (copy, 1hr)

## P2 / blocked
- [ ] Inbox rotation + 2nd domain (USER: domain kharido)
- [ ] AI avatar video (Pollinations video_url scaffold)
- EXTERNAL-BLOCKED: Meta publish/Lead-Ads/CTWA/CAPI, GBP API, WA Flows approval, DLT, Exotel KYC, Truecaller
- SKIP FOREVER: unofficial WA auto-responder, Justdial/IndiaMART/LinkedIn scrape, SERP scrape

## Pehle se pending (carry-over)
- [ ] USER: Razorpay API keys 401 fix (dashboard regenerate) — pehla paid customer se pehle ZAROORI
- [ ] USER: Razorpay webhook register + RAZORPAY_WEBHOOK_SECRET
- [ ] USER: UPI_VPA set · Exotel key rotate · DLT via Udyam · Cloudflare token perms
