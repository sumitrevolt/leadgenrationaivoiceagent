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

## Paid Tiers (`app/marketing/packages.py`, public `/api/marketing/packages`)
- **Starter ₹999/mo** — marketing only (posts, GBP audit, reviews, posters, WhatsApp). No calling.
- **Growth ₹2,499/mo** — + unlimited posters, content calendar, competitor, lead-form, monthly report.
- **Advanced ₹5,999/mo** — Growth + AI voice (inquiry call in 2-min, qualification, appointments, missed-call callback, 50 weekly follow-ups, 500 min/mo). **Yahi unique tier** (Dhanda/AdBanao/Predis ke paas nahi).
- (Prices = LIVE `packages.py` truth: 999/2499/5999. Landing + JSON-LD schema isi se match.)
- **Launch NOW possible**: marketing tiers + inbound callbacks ko DLT/telephony NAHI chahiye. Sirf Advanced voice cold-calling DLT pe atki.

## Live Infra
- VPS **72.61.245.204** (Mumbai, Ubuntu 24.04, Docker). App `/opt/leadgen`, systemd `leadgen` (uvicorn :8000). Caddy proxy (Traefik conflict — hostinger-deploy skill dekho). DB SQLite `/opt/leadgen/leadgen.db`. Qdrant docker `127.0.0.1:6333`.
- Key pages: `/` landing · `/audit` (public GBP-audit = **#1 lead magnet**) · `/blog` (programmatic SEO) · `/b/{slug}` (per-client mini-site+booking) · `/app/marketing` (19 tabs) · `/app/clients` · `/app/outreach` · `/app/team` · `/app/test-call` (FREE voice tuning) · `/app/admin` · `/app/customer`. Legal: `/privacy /terms /refund`. SEO: `/robots.txt /sitemap.xml` (dynamic).
- `/mcp` MCP server mounted (Platform/Data/Agents tools).

## AI Stack (all free, `app/voice_agent/free_ai.py` multi-provider chain)
- **LLM**: Cerebras `gpt-oss-120b` (WORKING, free-unlimited) → groq → xai(no credits) → openrouter → Gemini. (Gemini quota PER MODEL.)
- **STT**: Groq `whisper-large-v3` (**needs GROQ_API_KEY — abhi MISSING = weak link**) → Gemini audio → local faster-whisper (Hindi weak).
- **TTS**: EdgeTTS `hi-IN-SwaraNeural` (`edge-tts>=7.2.0` zaroori, warna 403).
- **RAG**: Qdrant single `kb_main` collection, per-niche namespaces (`niche:` + `client:<id>`).
- **RAG upgrades (optional, OFF default)**: `agentic_rag.py` (CRAG self-correct retrieve→grade→rewrite→generate over KB, NO new dep, `USE_AGENTIC_RAG=1`) + `graph_rag.py` (LightRAG knowledge-graph, `USE_LIGHTRAG=1`, lightrag-hku installed on VPS). Both opt-in/defensive, vector KB ke SAATH. Doc: `docs/RAG_KnowledgeGraph_Agentic.md`.
- **Automation/marketing helpers (installed on VPS, opt-in/defensive)**: `structured.py` (Instructor typed LLM JSON; sync `extract` + async `aextract`; **WIRED into `post_generator` via `USE_STRUCTURED_CONTENT=1`**), `seo_tools.py` (advertools SEM+RSA), `web_extract.py` (trafilatura; **WIRED into prospector email-extract, ACTIVE**), `to_markdown.py` (MarkItDown any file/URL→markdown, installed), `deep_extract.py` (Crawl4AI deep crawl→markdown, OPTIONAL/heavy + trafilatura fallback). agentic_rag voice me NAHI wired (latency). Docs: `docs/Automation_Marketing_Repos.md`, `docs/RAG_KnowledgeGraph_Agentic.md`.
- **Voice brain**: `telecaller_brain.py` (KB-grounded, ACP pattern, ≤2 sentences/1 question) + `niche_scripts.py`. Tuning FREE web-call pe; phone = final verify only.
- **Turn-taking upgrade (optional, OFF default)**: `turn_detector.py` — Silero VAD gate READY (`USE_SILERO_VAD=1` + `pip install silero-vad` + 5-line wire in `vobiz_stream.py`), Smart Turn v3 = NEXT (semantic end-of-turn, via pipecat). Plan: `docs/Efficiency_Repos_Integration.md`.
- **QA**: koi bhi voice change ke baad `scripts/agent_tester.py` chalao (free scorecard: double/empty/repeat/long/slow).

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
- Per-client: `clients_store.py` (onboard) + `auto_content.py` (daily content queue, 1-click copy/PNG/wa-send; auto-publish needs Meta API — blocked) + `mini_site.py` (`/b/{slug}`) + referral/evergreen.
- **Auto client onboarding (done-for-you, NEW)**: `app/marketing/onboarding.py` — client add hote hi auto-setup: **website → KB seed** (`deep_extract`→`KnowledgeBase` + LightRAG, ns `client:<id>`, dormant tools ab live) + first content pack (`data/client_packs/<id>.html`) + `setup_done`. Hourly sweep, **gated `AUTO_ONBOARD=1`**, defensive.

## Active Blockers / USER-ACTION pending (env-unset = dormant, graceful skip)
- **DLT**: individual request REJECTED → user ko **Udyam (MSME, FREE, udyamregistration.gov.in)** cert se Proprietorship re-apply. (Udyam cert ready hai.) DLT sirf cold-calling (Advanced) ke liye.
- **GROQ_API_KEY**: ✅ **SET** (live setup-audit confirmed) → STT "hearing" weak-link **RESOLVED**. (Memory pehle galti se 'missing' kehti thi; `scripts/setup_status.py` ne pakda.)
- **Vobiz telephony**: trial ~khatam. Recharge → trial number auto-remove → DID kharido → `VOBIZ_CALLER_ID=+91<DID>` (.env VPS+local) + restart. Streaming ₹0.65/min, raw-SIP ₹0.45. Cost ladder: Plivo ₹0.60 → Vobiz ₹0.45 → operator-direct ₹0.30-0.40 → VNO.
- **UPI_VPA** (payment modal dormant tak set na ho). **NOTIFY_EMAIL** (inquiry alerts).
- **Future (EXTERNAL-BLOCKED — user paperwork/approval, Claude build nahi kar sakta)**: missed-call callback (Vobiz DID + inbound webhook), GBP API auto-post (Google 60-din approval), Meta/FB-IG auto-posting (app-review). In par token mat jalao jab tak unlock na ho.

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
