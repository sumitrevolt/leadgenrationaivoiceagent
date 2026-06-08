# Project Memory — leadgenrationaivoiceagent (LEAN working memory)

> **Token discipline (IMPORTANT):** Yeh file har turn load hoti hai — isliye SIRF lean working-memory rakho.
> Detailed dated history → `docs/SESSION_LOG.md` (auto-load NAHI hota). Naya milestone wahan append karo, yahan sirf 1-2 line update.
> Naya task = naya chat (memory persist karti hai). Heavy sub-agents kam — wahi token jalate hain.

## User Preferences
- **Hinglish (Roman script) me HI reply karo** — har baar. Concise + direct, kam formatting.
- Sab **free stack** — koi paid STT/TTS/LLM nahi (user decision). Phone-call paisa khaata hai → tuning FREE web-call pe.

## Product (current direction — MARKETING-FIRST pivot)
- Core = **"AI Automated Marketing"** (Dhanda-jaisa) for chhote local businesses. AI **voice agent = HELPER** (inquiry callback, lead qualification, follow-ups).
- FastAPI platform, **LIVE: https://leadsgenai.in** (Hostinger VPS Mumbai). Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
- **42 niches** (`app/niches.py`), categories: marketing / leadgen / both. API `/api/data/niches?tier=S|A|B`.
- **AI image generation (NEW)**: `app/marketing/ai_image.py` — Pollinations Flux. **GOTCHA: Pollinations ab anonymous pe 402 Payment Required** — `POLLINATIONS_TOKEN` env chahiye (auth.pollinations.ai free signup); bina token frontend graceful msg dikhata (`__imgErr`). `POST /api/marketing/ai-image` → image URL. SVG posters = reliable fallback. (Caption/hashtags bina token chalte.)
- **Predis-style combos (NEW)**: `POST /api/marketing/complete-post` (ek phrase → caption+hashtags+AI image one-shot, asyncio.gather) + `POST /api/marketing/post-variations` (N=2-4 variants, A/B). generate_post+ai_image compose karte.
- **Godmode marketing batch (NEW, WIRED in marketing.html)**: `/api/marketing/chatbot` (client-KB FAQ + lead-capture bot — `chatbot.py`, website/WA widget brain) · `/sentiment` (`sentiment.py` — reviews mood+themes) · `/hashtags` (`hashtags.py` — trending + best-time) · `/brand-logo` (AI logo, `ai_image.logo_url`). **Routes ~234; marketing.html ab 28 tabs** (+ Scheduler + Web Widget; pehle 26 — AI Image/Complete-Post/Variations/Chatbot/Sentiment/Hashtags/Logo etc. — JS `node --check` verified). VPS pe ab node v18 installed (`scripts/check_marketing_js.py`).
- **Content scheduler (NEW, Buffer-style)**: `app/marketing/content_schedule.py` — kisi khaas DATE ke liye post queue karo (Diwali/sale day). `POST /api/marketing/schedule` (add) · `GET /schedule` (list) · `POST /schedule/run` (manual prepare). Daily `content` job (07:00 IST) me `run_due()` wired → due items auto content-generate hoke `status=ready` (1-click human post; auto-publish Meta-blocked). Store `data/content_schedule.jsonl`. **UI: `/app/marketing` me "📅 Scheduler" tab (27th) — manual add + list + run + 1-click festival auto-schedule.** Verified: schedule→due→prepared real caption, JS node --check OK.
- **Festival → scheduler glue (NEW)**: `POST /api/marketing/festival-autoschedule` — EXISTING `app/marketing/festivals.py` calendar (`upcoming(days)`, Jun2026→Dec2027) ke festivals ko content_schedule me **dup-safe** queue → daily run_due auto-prepares. **CAUTION (galti se seekha)**: `festivals.py`/`/festivals`/`/festival-posts`, `review_replies.py`/`/review-reply`, `/ads-pack`, `/reels`, `/gbp-texts` aur unke UI tabs (Review Reply/Festivals/Ads/Reels) PEHLE se hain (~50 routes already). Maine in sabke duplicate module+route banaye the (festival_calendar/review_reply/ad_copy/gbp_post/reel_script.py) — FastAPI first-route-wins se prod `/festivals` shadow ho gaya tha → **sab revert+delete kiye**, sirf yeh ek glue endpoint naya rakha. **LESSON: naya marketing feature add karne se pehle `grep '@router' app/api/marketing.py` se existing routes dekho.**

- **Website lead-capture widget (NEW, Growth-tier deliverable)**: `app/marketing/embed_widget.py` — client apni KISI BHI website pe ek `<script>` line paste kare → floating "Enquiry" button + form (Calendly/Tally-jaisa). **CORS-free**: form ek iframe me HAMARE origin se serve hota (`GET /b/{slug}/embed`), injector JS `GET /b/{slug}/widget.js` (dono `main.py` me, `/b/{slug}` ke paas). Submit → existing `POST /api/public/inquiry` + `source_slug` → lead auto client se link hoke dashboard me. Admin snippet: `GET /api/marketing/embed-snippet?slug=`. UI: "🔌 Web Widget" tab (28th). Verified LIVE: widget.js 200 (application/javascript), embed 200 (posts to /inquiry, real client `sharma-solar-7b6f`).

## Paid Tiers (`app/marketing/packages.py`, public `/api/marketing/packages`)
- **Starter ₹999/mo** — marketing only (posts, GBP audit, reviews, posters, WhatsApp). No calling.
- **Growth ₹2,499/mo** — + unlimited posters, content calendar, competitor, lead-form, monthly report.
- **Advanced ₹5,999/mo** — Growth + AI voice (inquiry call in 2-min, qualification, appointments, missed-call callback, 50 weekly follow-ups, 500 min/mo). **Yahi unique tier** (Dhanda/AdBanao/Predis ke paas nahi).
- (Prices = LIVE `packages.py` truth: 999/2499/5999. Landing + JSON-LD schema isi se match.)
- **Launch NOW possible**: marketing tiers + inbound callbacks ko DLT/telephony NAHI chahiye. Sirf Advanced voice cold-calling DLT pe atki.

## Live Infra
- VPS **72.61.245.204** (Mumbai, Ubuntu 24.04, Docker). App `/opt/leadgen`, systemd `leadgen` (uvicorn :8000). Caddy proxy (Traefik conflict — hostinger-deploy skill dekho). DB SQLite `/opt/leadgen/leadgen.db`. Qdrant docker `127.0.0.1:6333`.
- Key pages: `/` landing · `/audit` (public GBP-audit = **#1 lead magnet**) · `/blog` (programmatic SEO) · `/b/{slug}` (per-client mini-site+booking) · `/app/marketing` (26 tabs) · `/app/clients` · `/app/outreach` · `/app/team` · `/app/test-call` (FREE voice tuning) · `/app/admin` · `/app/customer`. Legal: `/privacy /terms /refund`. SEO: `/robots.txt /sitemap.xml` (dynamic).
- `/mcp` MCP server mounted (Platform/Data/Agents tools).

## AI Stack (all free, `app/voice_agent/free_ai.py` multi-provider chain)
- **LLM**: Cerebras `gpt-oss-120b` (WORKING, free-unlimited) → groq → xai(no credits) → openrouter → Gemini. (Gemini quota PER MODEL.) **Circuit-breaker (NEW)**: provider 429/quota/queue pe 60s cooldown (`_LLM_COOLDOWN_UNTIL` in `free_ai.py`) → burst me dead provider skip, auto-reopen. Verified: Cerebras 429 burst → Groq instant fallback, chat 'OK'.
- **STT**: Groq `whisper-large-v3` (**needs GROQ_API_KEY — abhi MISSING = weak link**) → Gemini audio → local faster-whisper (Hindi weak).
- **TTS**: EdgeTTS `hi-IN-SwaraNeural` (`edge-tts>=7.2.0` zaroori, warna 403).
- **RAG**: Qdrant single `kb_main` collection, per-niche namespaces (`niche:` + `client:<id>`). Embedder **multi-model fallback** `_EMBED_CANDIDATES` (e5-small unsupported tha → `paraphrase-multilingual-MiniLM-L12-v2` dim-384; fastembed version-proof, REAL dim auto-detect, collection recreate on mismatch). backend=qdrant semantic verified (`scripts/check_rag.py`).
- **RAG upgrades (optional, OFF default)**: `agentic_rag.py` (CRAG self-correct retrieve→grade→rewrite→generate over KB, NO new dep, `USE_AGENTIC_RAG=1`) + `graph_rag.py` (LightRAG knowledge-graph, `USE_LIGHTRAG=1`, lightrag-hku installed on VPS). Both opt-in/defensive, vector KB ke SAATH. Doc: `docs/RAG_KnowledgeGraph_Agentic.md`.
- **Automation/marketing helpers (installed on VPS, opt-in/defensive)**: `structured.py` (Instructor typed LLM JSON; sync `extract` + async `aextract`; **WIRED into `post_generator` via `USE_STRUCTURED_CONTENT=1`**), `seo_tools.py` (advertools SEM+RSA), `web_extract.py` (trafilatura; **WIRED into prospector email-extract, ACTIVE**), `to_markdown.py` (MarkItDown any file/URL→markdown, installed), `deep_extract.py` (Crawl4AI deep crawl→markdown, OPTIONAL/heavy + trafilatura fallback). agentic_rag voice me NAHI wired (latency). Docs: `docs/Automation_Marketing_Repos.md`, `docs/RAG_KnowledgeGraph_Agentic.md`.
- **Voice brain**: `telecaller_brain.py` (KB-grounded, ACP pattern, ≤2 sentences/1 question) + `niche_scripts.py`. Tuning FREE web-call pe; phone = final verify only.
- **Turn-taking (Phase-3 WIRED, OFF default, commit 8aab2c3)**: `turn_detector.py` `SileroSpeechGate`/`SmartTurnDetector` ab **`vobiz_stream.py`** (16k) + **`phone_stream.py`** (8k, `sample_rate=8000`) me rms-check pe wired (Silero noise/echo filter), aur **`pipeline.py`** me `confirm_end_of_turn()` (silence-timer + Smart Turn semantic combine — mid-sentence pause pe nahi tokta). Enable: `USE_SILERO_VAD=1`(+`pip install silero-vad`) / `USE_SMART_TURN=1`(+pipecat). Bina dep/flag = graceful RMS/silence fallback (zero behaviour change, gates `None` lautate). Tests `tests/test_phase3_voice.py`.
- **QA**: koi bhi voice change ke baad `scripts/agent_tester.py` chalao (free scorecard: double/empty/repeat/long/slow).
- **Phase-2 (2026-06-09, FREE-only, commit 38ec980)**: `agents/supervisor.py` `route_for_task` ab **semantic** — `semantic_route_for_task()` async free-LLM (`free_ai.chat`) se data_agent/leads_agent classify, keyword router = zero-latency fallback; `supervisor_node` async. `LatencyOptimizer` (`latency.py`) me **pre-synth greeting AUDIO cache** — `cache_audio`/`get_cached_audio`/`has_cached_audio`/`presynthesize_greetings(tts, {niche:text})` + `build_niche_greetings()` (Hinglish) → sub-300ms TTFT. `prospector._append` ab DB me bhi `Lead` likhta (`_persist_prospect_to_db`, best-effort, dedupe-by-phone) → dashboards ka `_build_from_db` (customer+admin dono me PEHLE se DB-first + jsonl-fallback) ab real leads dikhayega. **Sarvam (paid STT/TTS) jaan-bujhke OFF** — `indic_providers.py` adapters opt-in hi rehte (free EdgeTTS/Groq default; user: NO paid services). Tests `tests/test_phase2_upgrades.py` 8/8, import no-circular.

## AI Staff Team (product framing) — `app/platform/team.py` + `team_scheduler.py`
8 staff: Boss(Manager) · Swara(Telecaller) · Dev(Data) · Rohan(Leads) · Arjun(QA) · Meera(Trainer) · Kavya(Ops) · Isha(Marketing). Events → `agent_events` table. Dashboard `/app/team`.
**Auto-schedule (IST)**: 06:30 blog · 07:00 content(self+clients) · 08:30 digest · 09:30 scrape/prospect · 10:30 email outreach+followups · hourly Kavya health · 02:30 Arjun QA · 03:00 Meera trainer · 15-min growth-pulse (`growth_engine.py`) · hourly reply-triage (`reply_agent.py`, REPLY_AGENT) · hourly ops-watchdog (`ops_watchdog.py`, OPS_WATCHDOG → email-alert Sumit on critical) · hourly auto-onboard sweep (`onboarding.py`, AUTO_ONBOARD) · ~04:00 backups.
**Scalable multi-agent (optional, OFF default)**: `app/agents/staff_supervisor.py` — langgraph-supervisor over STAFF roster (auto-scales, dynamic). Deps VPS pe installed. Enable: `USE_LANGGRAPH_SUPERVISOR=1` + CEREBRAS/GROQ key. Existing rule-based `supervisor.py` + scheduler untouched. Detail: SESSION_LOG.

## Outbound/Growth (working)
- **Email outreach LIVE**: Hostinger SMTP `admin@leadsgenai.in` (`smtp.hostinger.com:465`). `AUTO_EMAIL_OUTREACH=true` → Rohan roz 10:30 auto-sends personalized Hinglish cold-emails + Day-3/Day-7 followups. Cap 25/day. (`app/platform/auto_outreach.py`; Resend/Brevo API fallback in `email_api.py`.)
- **Google Maps API LIVE** (Places API New; legacy textsearch DENIED). Prospector real phones+reviews (cap `PROSPECT_MAX_LOOKUPS=60`/run). OSM Overpass fallback (no key).
- **Lead-gen quality (competitor-grade, LIVE)**: `email_verify.py` (email-validator syntax+**MX**) **WIRED into `auto_outreach._valid_email`** → sirf deliverable emails bhejte (bounce<2%, sender-rep safe; `OUTREACH_VERIFY_MX=1`). `phone_validate.py` (phonenumbers E.164/mobile). Self + client campaigns. **Email auth (SPF/DKIM/DMARC) ALL SET + verified** (Hostinger auto; DMARC `rua` reporting added via Hostinger DNS API). Doc: `docs/LeadGen_Competitor_Repos.md`.
- **DNS via Hostinger API**: `scripts/hostinger_dns.py` (get/validate/put/delete/fix; `HOSTINGER_API_TOKEN` in .env, DNS-scoped; **browser UA header zaroori warna Cloudflare err-1010**). GOTCHA: Hostinger PUT `overwrite=false` = ADD (not replace) → duplicate ban sakta; single record ke liye `fix` (delete+put). `overwrite=true` KABHI nahi (zone me A/NS/www bhi — partial overwrite = site down).
- **AI reply triage (closes the outreach loop, NEW)**: `app/platform/reply_agent.py` — IMAP (`imap.hostinger.com`, SMTP creds reuse) se replies → free_ai intent classify (interested/objection/unsubscribe/…) → prospect status (interested→hot, unsub→dead) → Hinglish draft (`data/reply_drafts.jsonl`, 1-click send) + Rohan/Swara event. Hourly scheduled, **gated `REPLY_AGENT=1`**, auto-send OFF (ban-safe). Smartlead SmartAgents ka free equivalent.
- **WhatsApp = 1-click human send** (bulk auto = ban). Inbound funnel auto (`/audit`, landing form → `data/inquiries.jsonl`).
- **WhatsApp campaign (Track-4, NEW, commit d290f9d)**: `app/marketing/whatsapp_campaign.py` — `send_campaign`/`send_one` DEFAULT = ban-safe 1-click links; **sirf `WHATSAPP_AUTO_SEND=1` + official Cloud API creds** (`whatsapp_business_token`+`phone_number_id`, existing `integrations/whatsapp.py` graph.facebook.com) pe spaced auto-send. **baileys/unofficial NAHI** (number-ban). Bina flag/creds = inert (links). Opt-in, loud warnings.
- **Booking API (Track-2, NEW)**: `app/api/booking.py` — `/api/booking/slots`·`/book`·`/cancel` existing `integrations/calendar_booking.py` (Google Calendar ya sim-mode business-hours) ke upar (Calendly-lite). Customer LOGIN portal `/app/login` abhi nahi (auth surface — next).
- **Track-3 status**: form/inquiry auto-callback PEHLE se hai (`public_site._auto_callback` → `telephony_vobiz.start_stream_call`, gated `AUTO_CALLBACK_INQUIRY`); missed-call callback Vobiz-DID pe blocked. `CallRequest.call_type` (default promotional; `transactional` for consented callbacks → `queue_call` compliance looser gate) NEW. (Redundant `auto_callback.py` banaya tha → deleted.)
- **Track-1 (Silero/Smart Turn)**: code WIRED (Phase-3); enable = `pip install silero-vad`(heavy torch ~1GB)+`USE_SILERO_VAD=1` + FREE web-call test — prod pe install carefully karna (auto nahi kiya, OOM risk).
- Per-client: `clients_store.py` (onboard) + `auto_content.py` (daily content queue, 1-click copy/PNG/wa-send; auto-publish needs Meta API — blocked) + `mini_site.py` (`/b/{slug}`) + referral/evergreen.
- **Auto client onboarding (done-for-you, NEW)**: `app/marketing/onboarding.py` — client add hote hi auto-setup: **website → KB seed** (`deep_extract`→`KnowledgeBase` + LightRAG, ns `client:<id>`, dormant tools ab live) + first content pack (`data/client_packs/<id>.html`) + `setup_done`. Hourly sweep, **gated `AUTO_ONBOARD=1`**, defensive.

## LIVE-ENABLED flags (2026-06-08, smoke-verified)
- **REPLY_AGENT · OPS_WATCHDOG · AUTO_ONBOARD · USE_STRUCTURED_CONTENT** = sab ON in `/opt/leadgen/.env` (systemd `EnvironmentFile` → os.getenv lagta hai). Smoke: watchdog ok, onboard 1 real client (website→KB), structured post (Cerebras 429 burst → Groq fallback worked). `.env.bak` backup. Status: `python scripts/setup_status.py`. Rollback: restore `.env.bak`.
- Still OFF (reason): USE_LIGHTRAG (LLM-heavy), USE_SILERO_VAD/SMART_TURN (deps+wiring), USE_LANGGRAPH_SUPERVISOR/USE_AGENTIC_RAG (not wired = no-op).

## Active Blockers / USER-ACTION pending (env-unset = dormant, graceful skip)
- **DLT**: individual request REJECTED → user ko **Udyam (MSME, FREE, udyamregistration.gov.in)** cert se Proprietorship re-apply. (Udyam cert ready hai.) DLT sirf cold-calling (Advanced) ke liye.
- **GROQ_API_KEY**: ✅ **SET** (live setup-audit confirmed) → STT "hearing" weak-link **RESOLVED**. (Memory pehle galti se 'missing' kehti thi; `scripts/setup_status.py` ne pakda.)
- **Vobiz telephony**: trial ~khatam. Recharge → trial number auto-remove → DID kharido → `VOBIZ_CALLER_ID=+91<DID>` (.env VPS+local) + restart. Streaming ₹0.65/min, raw-SIP ₹0.45. Cost ladder: Plivo ₹0.60 → Vobiz ₹0.45 → operator-direct ₹0.30-0.40 → VNO.
- **UPI_VPA** (payment modal dormant tak set na ho). **NOTIFY_EMAIL** (inquiry alerts).
- **Future (EXTERNAL-BLOCKED — user paperwork/approval, Claude build nahi kar sakta)**: missed-call callback (Vobiz DID + inbound webhook), GBP API auto-post (Google 60-din approval), Meta/FB-IG auto-posting (app-review). In par token mat jalao jab tak unlock na ho.

## Telephony (production-hardened, commit 310e141, 2026-06-09)
- `telephony/webhooks.py` ab `/api/webhooks` pe MOUNTED (main.py) — Twilio/Exotel voice+status callbacks. POST routes signature-verified (Depends `verify_twilio_signature`/`verify_exotel_signature` from `app/api/webhooks.py`). Module **lazy-init** (VoiceAgent/CallManager import pe instantiate nahi → mount se startup crash nahi). Sentry FastApiIntegration global = errors auto-capture.
- **AMD**: Twilio `AnsweredBy` machine/voicemail/fax → `AnsweringMachineDetector` se voicemail-drop (`AMD_LEAVE_VOICEMAIL=1`, sirf `machine_end_beep`) ya seedha hangup (credit bachao).
- **DND fail-CLOSED (TRAI)**: `dnd_checker` me `verified` flag (lookup fail/non-200 = `verified=False`); `compliance.py` promotional call ko `dnd_lookup_failed` reason se **BLOCK** karta jab DND verify na ho (₹10L safe). Transactional unaffected (DND skip).
- **Exotel make_call**: ab hamesha valid destination `Url` (app_id→Url, warna webhook_url, warna ValueError) — connect-validation error fix; CallManager `exotel_app_id`+status-webhook pass karta.
- **Distributed call state** (`telephony/call_state.py` RedisCallStore): call_queue + active-call registry Redis me (multi-worker stateless scaling); Redis na ho to **local in-memory fallback** (single-worker unchanged). Live `CallContext` worker-local (serialize nahi hota). **Async enrich** (`tasks/scraping.py` httpx.AsyncClient+gather, strict 3s) + `/metrics` DB counts ab Redis me **60s cached**. Tests 8/8 (`tests/test_telephony_upgrades.py`), import OK (257 routes, no circular). `/api/webhooks/health` live = provider twilio.

## SaaS reselling stack (Phase-3, commit a98a389, FREE/additive)
- **Minute metering+enforcement**: `app/billing/usage.py` — BillingRecord = ledger (no balance col), to USAGE-ledger: `record_call_usage(client_id, duration)` post-call hook (`CallManager.handle_call_completed`, best-effort, client_id ← context/client_name) TELEPHONY line (quantity=min) likhta; `minutes_used_this_period`/`minutes_remaining`/`has_minutes` (PLAN_MINUTES advanced=500). Enforcement: `CallRequest.client_id` + `queue_call` `has_minutes` gate → 0-min pe block (`out_of_minutes_<id>`). **Fail-OPEN** (no client_id/non-calling plan/error → block nahi).
- **Multi-tenant white-label**: `app/middleware/tenant.py` `TenantBrandingMiddleware` (mounted in `middleware/__init__`) — Host `agency.leadsgenai.in` → slug `agency` → `clients_store.get_by_slug` branding → `request.state.tenant`. `customer_dashboard /dashboard` `DashboardResponse.branding` set (reseller UI). **FAIL-OPEN** (apex/reserved/unknown → None, normal). Tests `tests/test_phase3_billing_tenant.py` 8/8.
- **BUGFIX**: `tasks/scraping.py` `filter(not Lead.phone_verified)` → `.is_(False)` (Python `not`-on-Column TypeError; verify_phone_numbers ab kaam karega).

## Legal (CONFIRMED)
- TRAI: 140-series + DLT + DND scrub + 10am-7pm + AI disclosure mandatory, penalty ₹10L. Foreign trunks (Twilio/Telnyx/Vonage) India-domestic = ILLEGAL.
- Pure minutes-resale bina license = Telegraph Act violation. Legal resale = **SaaS bundle** (DLT/140 CLIENT ke naam) — industry standard.
- WhatsApp bulk auto-send = number ban. Cold auto-calls bina DLT = ₹10L risk → sirf inbound auto-callback.

## Skills (`.claude/skills/` — workflow invoke karo, re-derive mat karo)
`leadgen-start` (session bootstrap + token discipline) · `leadgen-ops` (verify→test→push→deploy loop) · `hostinger-deploy` (VPS gotchas) · `marketing-feature` (naya marketing feature add karne ka pattern) · `niche-onboarding` · `run-campaign` · `test-agent` · `voice-agent-kb` · `deploy`.

## Deploy loop (detail → `leadgen-ops` + `hostinger-deploy` skills)
1. `python scripts/prod_check.py` → 2. `scripts\run_tests.bat` (**pytest_run.log Read karo**, ~80+ green) → 3. Windows git `C:\PROGRA~1\Git\cmd\git.exe` push (bat ke andar) → 4. VPS pull+restart via **Git ka ssh** `C:\PROGRA~1\Git\usr\bin\ssh.exe -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204` → verify `/health` = `environment:production`.
- **Hard reload** (purana code load ho to): `systemctl stop leadgen; pkill -9 -f uvicorn; rm -rf __pycache__; systemctl start leadgen` → alag SSH call se `is-active` verify (pkill blip se EXIT_255 aata hai par service aa jaati).

## Critical Env Gotchas
- **Sandbox mount STALE** ho jata hai file-tool edits ke baad → Windows side (Read/Write/Edit, Desktop Commander) = source of truth. Verify Windows pe (bat chala ke log Read karo).
- Sandbox **git index unreadable** → Windows git via Desktop Commander.
- Windows **OpenSSH broken** → Git ka ssh.exe use karo.
- `.bat`: npm/git `.cmd` ko `call` ke saath; `timeout /t` fail → `ping -n N 127.0.0.1`. DC one-liner quoting mangle → complex cmd `.bat` me likho, output log me, log Read karo. SSH command me `&`/`<` quoting todta (EXIT_9009) → smoke `.py` file me likho, ssh se `python scripts/x.py`.
- **Bade multi-file edits same file pe parallel mat do** — file truncate ho jati hai.
- **Secrets kabhi committed file/CLAUDE.md/scripts me mat likho — sirf .env** (gitignored).

## History & Research
- Full dated history: **`docs/SESSION_LOG.md`**. Research: `docs/Architecture_Research_RAG_Agents_MCP.md`, `docs/P3_Own_Telephony_Stack_Plan.md`, `docs/Marketing_Kit_LeadGenAI.md`, `docs/Sales_Kit_Hinglish.md`, `docs/THREE_BRAIN_ARCHITECTURE.md`, `docs/API.md`. Pricing: `Niche_Pricing_Research.xlsx`.
