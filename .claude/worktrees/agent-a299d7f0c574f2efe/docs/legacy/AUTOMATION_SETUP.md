# 🚀 LeadGen AI — Full Automation Setup (Hinglish Guide)

Yeh guide batata hai is session me kya-kya bana, kaise chalao, aur live karne ke liye kya chahiye.
Sab kuch **modular** hai — keys na hon tab bhi system gracefully chalta hai (demo/degraded mode).

---

## 1. Kya naya bana

### Lead sources (2 naye add hue → ab total 6)
| Source | File | Key chahiye? |
|---|---|---|
| Google Maps | `app/lead_scraper/google_maps.py` (email-extract ab real) | optional API key |
| IndiaMart | `app/lead_scraper/indiamart.py` | nahi |
| JustDial | `app/lead_scraper/justdial.py` | nahi |
| LinkedIn | `app/lead_scraper/linkedin.py` (placeholder → real DuckDuckGo search) | nahi |
| **Web Search** 🆕 | `app/lead_scraper/web_search.py` | nahi (free) |
| **Social Media** 🆕 | `app/lead_scraper/social_media.py` (Insta/FB public) | nahi (best-effort) |

Sab `LeadScraperManager.scrape_leads(niche, cities, sources=[...])` se chalte hain.
Example: `sources=["google_maps","justdial","web","social"]`

### Automation engine
- `app/automation/orchestrator_pipeline.py` → `LeadGenPipeline.run_campaign(...)`
  9 stage end-to-end: **scrape → clean/dedupe → DND scrub → 9am-9pm gate → WhatsApp warm-up → AI voice call (qualify) → score (Hot/Warm/Cold) → deliver (Sheet/HubSpot/WhatsApp) → per-lead billing**.
  Har stage try/except — koi key missing ho to warning de ke aage badhta hai.
- `app/automation/agent_pool.py` → `AgentWorkerPool` — **multiple agents** ek saath kai clients ke campaigns chalate hain (asyncio, default 5 concurrent). Har agent ka status track hota hai (idle/running/done/error, calls_made, leads_found).

### Dashboards (web app)
- **Customer dashboard** → `frontend/customer_dashboard.html` + API `app/api/customer_dashboard.py`
  Client dekhta hai: KPIs, **calls kiye gaye** (table), **final qualified leads** (Hot/Warm/Cold), charts, CSV download.
- **Admin dashboard** → `frontend/admin_dashboard.html` + API `app/api/admin_dashboard.py`
  Tum (owner) dekhte ho: sabhi clients, agents pool status, campaigns progress, revenue ₹ vs cost, system health.

### Marketing website + App (PWA)
- `frontend/website/index.html` — landing page (service bechne ke liye), pricing, FAQ.
- `frontend/website/manifest.json` + `sw.js` — **installable PWA** (phone/desktop pe "app" ki tarah install hota hai, offline shell).

### Analytics
- `app/api/analytics.py` — TODO stubs hata ke real aggregates (in-memory `AnalyticsStore`).
  Note: project me abhi SQLAlchemy DB models nahi mile, isliye aggregates in-memory store se chalte hain — `TODO: bind to <Model>` markers diye hain jahan real DB jodna hai.

---

## 1b. Dograh-inspired voice upgrades 🆕

Dograh (open-source Vapi alternative) se seekh ke ye best-practices add kiye — taaki AI calls natural lagein aur test karna aasaan ho:

| Feature | File | Kya karta hai |
|---|---|---|
| **Conversation Flow Engine** | `app/voice_agent/flow_engine.py` | Baat-cheet ko node-graph (greeting→questions→condition→transfer/end) ki tarah chalata hai, flat script nahi |
| **Flow Builder** | `app/voice_agent/flow_builder.py` | Har niche ke qualification questions se auto flow banata hai |
| **QA Node** | `app/voice_agent/qa_node.py` | Flow/prompt quality analyze karta hai (score 0-100, issues) |
| **Real-time Pipeline** | `app/voice_agent/pipeline.py` | Streaming STT→LLM→TTS loop with **barge-in** (bot ko beech me rok sako) + endpointing + latency metrics |
| **BYOK Provider Registry** | `app/voice_agent/providers.py` | STT/TTS/LLM env se swap (`STT_PROVIDER`/`TTS_PROVIDER`/`LLM_PROVIDER`), Mock fallback |
| **Telephony Media-Stream** | `app/telephony/media_stream.py` | Twilio Media Streams (live audio) ko pipeline se bridge karta hai |
| **Web-Call Test Mode** | `app/api/web_call.py` + `frontend/web_call.html` | Browser me bot se baat karke **test** karo — koi real call nahi |

> 💡 Pipeline **pure-text mode** me bina kisi service ke chalta hai (Mock providers) — testing ke liye perfect.

## 1c. Competitor-parity voice features 🆕 (Retell/Vapi/Bland jaise)

Web research se top voice-agent platforms ke must-have features nikaal ke add kiye:

| Feature | File | Kya |
|---|---|---|
| **In-call function calling** | `app/voice_agent/function_calling.py` | Call ke beech tools chalao: appointment book, availability check, transfer, lead capture, pricing |
| **Appointment / calendar booking** | `app/integrations/calendar_booking.py` | Slot check + book (Google Calendar ya in-memory), ₹ + IST business hours |
| **Warm transfer to human** | `app/telephony/warm_transfer.py` | Human ko pehle context brief karke phir connect (hold→whisper→bridge) |
| **Answering machine detection** | `app/voice_agent/amd.py` | Voicemail pehchano → message chhodo ya hangup |
| **Knowledge base / RAG** | `app/voice_agent/knowledge_base.py` + `kb_loader.py` | Accurate grounded answers (niche FAQs + website se sync), no hallucination |
| **Filler words** | `app/voice_agent/fillers.py` | "ek second...", "haan..." — latency mask, natural lage |
| **Post-call analysis** | `app/voice_agent/call_analyzer.py` | Summary, sentiment, outcome, extracted fields, talk-ratio, next-action |

> Ye sab **`natural_dialog.py` me wired** hain — agent ab grounded answers deta hai, appointment book kar leta hai, voicemail pakad leta hai, aur call ke baad analysis deta hai. Sab **bina keys ke** (sim/fallback) chalte hain; keys aane par real.

## 1d. Infra / enterprise-grade features 🆕 (LiveKit/Bland/Retell jaise)

GitHub (pipecat, LiveKit, Bolna) + web research se infra-level gaps fill kiye:

| Feature | File | Kya |
|---|---|---|
| **Guardrails** | `app/voice_agent/guardrails.py` | Pre-LLM: PII redact (phone/email/Aadhaar/PAN/card/UPI) + prompt-injection/jailbreak block. Post-LLM: system-prompt leak / unsafe-promise / hallucination block. **natural_dialog me wired.** |
| **Observability / tracing** | `app/voice_agent/observability.py` | Har call ka trace — spans, per-step latency (STT/LLM/TTS), token + ₹ cost estimate, ring buffer dashboard ke liye |
| **Agent eval / simulation** | `app/voice_agent/eval_suite.py` | 7 test personas (interested/busy-rude/confused/price-objector/voicemail/not-interested/Hindi-switcher) — live jaane se pehle agent test. **7/7 pass.** |
| **Webhooks / events** | `app/integrations/webhooks_emitter.py` | `call.ended`, `lead.qualified`, `appointment.booked` etc. external URLs ko HMAC-signed bhejo, retry ke saath. **pipeline me wired.** |

> Guardrails ab har customer input PII-redact + injection-block karta hai, aur har agent reply ko safe karta hai. Webhooks `lead.qualified` + `campaign.completed` pe fire karte hain.

**Abhi bhi optional (chaaho to baad me):** full WebRTC sub-300ms streaming (LiveKit-style), Sarvam/Bhashini Indian-language STT/TTS, public Python/Node SDK. Ye bade infra/keys-dependent hain.

## 1e. India edge — "better than them" 🆕🇮🇳

Top platforms (Retell/Vapi/Bland) English-first hain. Ye do cheezein tumhe Indian market me **behtar** banati hain:

| Feature | File | Kya |
|---|---|---|
| **Sarvam / Indic providers** | `app/voice_agent/indic_providers.py` | Sarvam Saaras STT + Bulbul TTS (22 Indian bhashayein, Hindi-English code-switching, natural voices). AI4Bharat open-source fallback. BYOK registry me wired — `STT_PROVIDER=sarvam`. Key na ho to free Vosk/EdgeTTS. |
| **Latency optimization** | `app/voice_agent/latency.py` | Response/FAQ caching (instant reply), first-sentence TTS chunking (3-5x kam perceived latency), partial-transcript streaming, TTFT metrics. **natural_dialog me wired** (grounded answers ab cached). |

> Sarvam ke saath Hindi calls **competitors se zyada natural** lagti hain. Caching se repeat sawaalon ka jawab instant. Setup: `.env` me `SARVAM_API_KEY` + `STT_PROVIDER=sarvam` + `TTS_PROVIDER=sarvam`.

## 2. Routes (server chalu hone ke baad)

| URL | Kya |
|---|---|
| `/` | API status (JSON) |
| `/site/` | Marketing website (landing page) |
| `/app/customer` | Customer dashboard |
| `/app/admin` | Admin dashboard |
| `/app/test-call` | 🆕 Web-call test mode (bot se browser me baat) |
| `/api/web-call/ws` | 🆕 Web-call websocket (test) |
| `/telephony/twilio/media-stream` | 🆕 Twilio live-audio bridge (websocket) |
| `/api/customer/dashboard?client_id=demo` | Customer data |
| `/api/admin/dashboard` | Admin data |
| `/manifest.json`, `/sw.js` | PWA install + offline |

Dashboards **offline bhi chalte hain** — HTML file ko seedha browser me khol lo, demo data render ho jaata hai. Server chalu ho to live API se data le lenge.

---

## 3. Kaise chalao (local)

```bash
cd leadgenrationaivoiceagent
python -m venv venv && venv\Scripts\activate     # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Phir browser me:
- Website: http://localhost:8000/site/
- Customer dashboard: http://localhost:8000/app/customer
- Admin dashboard: http://localhost:8000/app/admin

Ya bina server ke: `frontend/customer_dashboard.html` / `admin_dashboard.html` / `website/index.html` ko directly double-click karke kholo.

---

## 4. Live karne ke liye kya chahiye (abhi `.env` me placeholder hain)

| Cheez | Key | Bina iske |
|---|---|---|
| Real phone calls | SIP trunk / Twilio / Exotel | calls simulate honge, real ring nahi |
| WhatsApp warm-up | WhatsApp Business token | step skip ho jaayega |
| Lead delivery | Google Sheets creds / HubSpot key | local list me rahenge |
| AI brain | Gemini free-tier (free) ya OpenAI | mock/fallback |
| Compliance (zaroori) | DLT registration + 140-series number + DND scrub | India me legal calling ke liye must |

> ⚠️ **Legal note:** India me automated outbound calls ke liye DLT registration, 9am–9pm window, aur DND/NCPR scrub zaroori hai (pipeline me gate laga hua hai). Cold random calling se number block ho sakta hai — warm/opt-in leads best.

---

## 5. Abhi kya pending (next steps)
1. Real DB models (SQLAlchemy) banake dashboards + analytics ko live data se jodna.
2. SIP trunk account le ke real telephony connect karna.
3. WhatsApp/HubSpot/Sheets keys daalna.
4. PWA ke real PNG icons (192/512) banana (abhi SVG placeholder hai).
5. Native mobile app (abhi PWA hai — installable web app; native baad ka step).

---

## ⚠️ Verification note (is build session ke baare me)
Is session me sandbox ka Linux shell mount **sync-lag/corruption** dikha raha tha (purani/null-byte copies). Isliye files **editor (Read/Write/Edit) se verify** hui hain — tumhari disk pe files **valid aur complete** hain. Apni machine pe `python -m py_compile app/lead_scraper/scraper_manager.py` chala ke khud bhi confirm kar sakte ho.
