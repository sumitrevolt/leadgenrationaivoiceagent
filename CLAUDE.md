# Project Memory — leadgenrationaivoiceagent

## User Preferences (IMPORTANT)
- **Language: ALWAYS reply in Hinglish (Hindi + English mix, Roman script).** User ne explicitly bola hai — har jawab Hinglish me hi dena hai.
- Concise aur direct rakho. Zyada formatting / verbosity nahi.

## Project Context
- "LeadGen AI Voice Agent" — FastAPI based B2B lead-gen + AI voice agent platform.
- Stack: Lead scrapers (Google Maps, IndiaMart, JustDial, LinkedIn), AI voice agent (free STT Vosk/Whisper, free TTS EdgeTTS, Gemini/Vertex LLM), telephony Twilio + Exotel.
- 20 niches configured (solar, real estate, dental, HVAC, interior, study abroad, etc.).
- Integrations: WhatsApp, HubSpot, Google Sheets, Email.
- `.env` me Twilio/Exotel keys abhi placeholder hain — live calling configured nahi.

## User's Goal / Business Model
- Chhoti companies ko AI voice agent bechna (takibot-style) — agent unke potential customers ko call karke unke business ke hisab se leads laaye.
- User "free calls" chahta hai. Reality: AI brain ~free ho sakta hai, lekin telephony (PSTN) per-minute paid hai.
- Recommended pitch: client ko "per qualified lead" charge karo (₹200–500/lead), "free calls" mat bolo.

## Key Facts Established
- Dograh (open-source, self-hosted Vapi/Retell alternative, BYOK) platform layer free karta hai, lekin telephony nahi.
- Telephony (real phone ring) ka cost ~₹0.50–0.80/min India me — yeh research chal raha hai ki koi free solution hai kya.

## Production Hardening (2026-06-06, commits 16eb3d2 + 2ae1c62)
- Tests: 61/61 pass (Windows venv, Python 3.11.9). Frontend: tsc+vite build green.
- Fixed: data.py trailing null-bytes; stale __pycache__ serving old bytecode (500 on /api/data/niches); logger UnicodeEncodeError on cp1252 console (UTF-8 forced); JWT secret ab settings.jwt_secret_key se (admin.py + auth_deps.py dono); CSP ab jsDelivr/Google Fonts/inline allow karta hai; Permissions-Policy me microphone=(self) — web-call demo ke liye zaroori; Docker me frontend/ COPY hota hai ab; deploy_vps.sh ab APP_ENV=production + JWT_SECRET_KEY + CORS_ORIGINS set karta hai aur re-deploy pe secrets preserve karta hai.
- New scripts: `scripts/prod_check.py` (deploy se pehle chalao — parse/pycache/import/route/config checks), `scripts/run_tests.bat`, `scripts/smoke_test.bat` (port 8923), `scripts/build_frontend.bat`, `scripts/final_verify.bat` (push+prodcheck+pytest).
- Deploy target: Hostinger VPS (72.61.245.204, domain leadsgenai.in) via deploy_vps.sh (git pull from GitHub main). Telephony abhi skip (simulation mode).
- **LIVE DEPLOYED (2026-06-06, commit 507677d): VPS ab APP_ENV=production me chal raha hai** — https://leadsgenai.in/health = environment:production, /docs disabled, niches API 200, web-call page live. Deploy ke baad ek aur bug mila+fixa: cloud-logging init bina GCP creds ke har logger pe retry karke startup MINUTES tak block karta tha (logger.py me attempted-flag up-front + creds check). VPS ops ke liye `.claude/skills/hostinger-deploy/SKILL.md` padho — Git ka ssh.exe (C:\PROGRA~1\Git\usr\bin\ssh.exe) + id_rsa key use karna, Windows OpenSSH broken hai. Redeploy: scripts/fix_push_redeploy.bat pattern (pytest → push → VPS pull+restart).

## Web-Call Bot LLM Fix (2026-06-06, commits cb2bec0 → 0678fa7)
- Bot echo-mode bug ka root cause 3-layered tha: (1) VoicePipeline me text-respond method hi nahi — web_call ab pipeline tabhi use karta jab method ho, warna LLMBrain (runtime-fail pe bhi brain fallback); (2) **Gemini free-tier quota PER MODEL hoti hai** — gemini-2.5-flash sirf 20 req/day, khatam ho gayi thi → DEFAULT_LLM ab `gemini-2.5-flash-lite` (sabse zyada free quota); (3) llm_brain ka ML-optimization code BrainOptimizer/FeedbackLoop ke asli signatures se mismatch tha (ConversationContext fields, agent_type/industry args, sync get_best_response) — ab aligned, "ML-optimized prompt" path live chal raha hai.
- Echo reply dikhe toh: `journalctl -u leadgen | grep -i ResourceExhausted` → quota issue = model switch in /opt/leadgen/.env. Per-model probe: `env PYTHONPATH=/opt/leadgen DEFAULT_LLM=<model> .venv/bin/python scripts/llm_probe.py`. Live ws test: `.venv/bin/python scripts/ws_test.py` (VPS pe).

## Top 25 Niches + Pricing (2026-06-06, commit 845adb0 — research-finalized)
- Deep web research (5 parallel agents + adversarial verification) se **top 25 niches final** — app/niches.py me tier (S/A/B), target_type (b2c/b2b/both), b2b_client, end_customer, avg_ticket_inr, pricing_inr (qualified_lead min-max, appointment min-max, monthly_starter) ke saath.
- **Two-tier model ab explicit hai**: Tier-1 = hum niche ke businesses ko client banate hain (B2B); Tier-2 = client ka agent uske end-customers ko call karta hai (target_type batata hai B2C ya B2B). B2C-reachable niches: 19/25.
- S-tier (pehle becho): real_estate, real_estate_luxury, studying_abroad, home_loans, solar_residential, solar_commercial, insurance, coaching. API: `/api/data/niches?tier=S` ya `?target_type=b2c`.
- Pricing bands (research-backed): low-ticket ₹150–800/QL, mid ₹300–1,500/QL, high ₹800–6,000/QL; appointments 2–5x; RE site-visit benchmark ~₹7,500. Hamari cost ~₹120–270/QL → 60-80% margin. Monthly starters ₹8K–25K (agency retainers ₹15–50K se neeche).
- Key market facts: Gemini-type AI call ₹14–18/contact vs human ₹55–70; India me koi bhi AI player "leads delivered" package nahi bechta (gap); TRAI: 140-series + DLT + DND scrub + 10am-7pm + AI disclosure mandatory, penalty ₹10L (CONFIRMED).
- Full data: `Niche_Pricing_Research.xlsx` (4 sheets: niches, competitor pricing, India CPL benchmarks, strategy). Rebuild: `scripts/build_xlsx.bat`.
- Dropped old niches (low suitability): financial_advisors, corporate_law (→ca_legal), event_management (→hotels_mice), architects, franchise_consultants, software_dev, gym_equipment, medical_equipment, packaging, logistics_3pl. KB/flow lookups `.get()` fallback se safe.

## Per-Client 2-Agent Auto-Provisioning (2026-06-06, commit 0187a69)
- **Har naya client bante hi system 2 agents auto-create karta hai**: DATA agent (role="data" — business profile + niche facts KB me seed, namespace `client:<id>`) + LEADS agent (role="leads" — end-customer calling, niche ke target_type ke hisab se). Code: `app/platform/agent_provisioner.py` (idempotent; `resolve_niche_key` loose industry strings ko NICHES key me map karta hai, fallback "general").
- API (admin auth): `POST /api/platform/clients` (create+provision), `POST /api/platform/clients/{id}/provision-agents` (backfill, idempotent), `GET /api/platform/clients/{id}/agents`. Agent model me `role` column — `_apply_schema_upgrades()` in models/base.py startup pe ALTER karta hai (SQLite/PG safe).
- Web-call dropdown ab `/api/data/niches` se 25 niches dynamically load karta hai (S/A/B grouped, static fallback). Flows/KB pehle se NICHES-generic the — sab 25 auto-supported (VPS verified: 25 namespaces, 8 chunks each).
- Tests 76/76 (15 naye: niche registry/flows/API filters/provisioning/idempotency/niche-resolution). VPS live-verified: seeded client pe 2 agents + KB seed + idempotent re-run.

## Custom Niches Runtime Support (2026-06-06, commit 5641405)
- **Koi bhi NAYA niche runtime pe add ho sakta hai** — `POST /api/data/niches` (admin; sirf `name` zaroori, baki defaults), `DELETE /api/data/niches/{key}` (builtin 25 protected, 403). Persistence: `data/custom_niches.json` (gitignored, VPS-local), mtime-based auto-reload (multi-worker safe).
- Custom niche turant SAB jagah kaam karta hai: flows (generic builder), KB (auto-seed on create), agent provisioning (`resolve_niche_key` loose match), web-call dropdown ([custom] tag, tier "C"). VPS-verified e2e: add → flow 7 nodes → resolve "ev charging" → remove.
- `app/niches.py` API: `add_custom_niche(name, ...)`, `remove_custom_niche(key)`, `refresh_custom_niches()`, `_BUILTIN_KEYS` frozen. Tests 80/80 (4 naye custom-niche tests).

## Architecture Stack Research (2026-06-06) — docs/Architecture_Research_RAG_Agents_MCP.md
- **Decided stack (research-backed)**: LangGraph 1.x supervisor (multi-agent orchestration, "graph wala" — 126k stars) + Qdrant single-collection payload-partitioned per-niche RAG (collection-per-niche MAT — Qdrant official guidance) + multilingual-e5-small ONNX embeddings (Hinglish) + Pipecat (voice, Phase 3) + fastapi_mcp (platform ko MCP server banao). GraphRAG/CrewAI/AutoGen/ADK skip (reasons doc me). LightRAG sirf future bade client-docs ke liye.
- Roadmap: P1 Qdrant RAG + fastapi_mcp → P2 LangGraph supervisor (data/leads agents as nodes) → P3 Pipecat telephony → P4 LightRAG.

## P1+P2 IMPLEMENTED + LIVE (2026-06-06, commit 0d6ce9d) — VPS verified
- **Qdrant RAG live**: `_QdrantIndex` in knowledge_base.py — single `kb_main` collection, payload `{namespace,text,source}`, fastembed multilingual-e5-small (e5 prefixes), backend chain Qdrant→Chroma→keyword (QDRANT_URL empty = disabled). VPS: docker container `qdrant` (port 127.0.0.1:6333, /opt/qdrant_storage), store+retrieve verified.
- **LangGraph supervisor live**: app/agents/supervisor.py — rule-based supervisor → data_agent (KB-grounded via client:/niche ns) | leads_agent (NICHES pitch/questions se outreach plan), dono LLMBrain/Gemini call karte. `POST /api/agents/run` (admin), `GET /api/agents/status`. AsyncSqliteSaver checkpointer data/agent_graph.db. VPS pe dono routes Gemini results de rahe.
- **fastapi_mcp live**: `/mcp` pe Platform/Data/Agents endpoints MCP tools — "MCP server mounted" log VPS pe. Claude ab platform-admin ban sakta hai.
- Deploy gotcha: deploy_vps.sh ka pip fallback naye deps skip kar sakta hai — fix: `.venv/bin/pip install langgraph langgraph-checkpoint-sqlite langchain-core fastapi-mcp qdrant-client fastembed` explicitly + restart. Old langchain==0.1.6/langchain-openai pins VPS se uninstall kar diye (codebase me unused the). Windows venv pe bhi naye deps install needed for tests (scripts/p12_install_test.bat).
- Smoke: scripts/vps_agents_test.py (VPS pe PYTHONPATH ke saath). DC long-installs ke liye: launcher bat pattern (`start /min cmd /c`) + log poll — DC ~60s pe process kill kar deta hai warna.

## Telephony Cheapest-Legal Research (2026-06-07)
- **Free+unlimited+legal PSTN exist nahi karta.** Best discovery: **WhatsApp Business Calling API** — India me business-initiated voice calls GA, ~₹0.40–0.60/min sirf ANSWERED calls, inbound FREE, **NO DLT/140 needed** (data call), connect rate ~78% vs PSTN ~22%. Consent template zaroori (1 req/24h, 2/week) — warm leads ke liye, cold-calling nahi.
- Sasta "unlimited": FreJun ₹1,149–1,699/user/mo unlimited India (FUP, sales-dialer); Smartflo ₹500-700/channel + ₹0.30-0.50/min; Exotel ₹0.30-0.50/min volume pe; Twilio ~₹0.63/min.
- DLT setup: ₹5,900 one-time (kisi ek operator DLT portal pe) + 140-number ~₹1-3K/mo (Exotel etc.). TCCCPR: violations = 2-saal blacklist tak.
- Phases: Demo ₹0-500/mo (web-call + WA inbound) → First clients ₹4-8K/mo (Smartflo/FreJun + DLT + WA) → Scale ₹20-40K/mo (Exotel volume ₹0.30-0.40/min).
- **AVOID (illegal)**: SIM box/GSM gateway (criminal, raids), personal unlimited SIM + auto-dialer (FUP: >300min/day ya 100 unique nos/week = disconnect + blacklist).
- **FreJun vs Smartflo verdict (2026-06-07)**: FreJun "unlimited" ₹1,349-1,699/user = sirf HUMAN dialer seats, AI bot allowed NAHI (unka AI product = Teler: ₹800/channel × min 10 = ₹8K/mo fixed + ₹0.30/min — sirf >26K min/mo pe sasta). **Pilot winner: Plivo Zentrunk** (self-serve, ₹0.60/min, ₹250/number, NO minimums, media-streams AI-friendly). **Scale winner: Tata Smartflo** ₹700/channel + ₹0.30/min (sales-route, SIP, DLT-native). @2K min/mo: Smartflo ~₹1.1-1.6K, Plivo ~₹1.45K, Teler ₹8.6K. Exotel Voicebot Applet (websocket) proven but retail ₹0.80-1/min.

## P3 DECISION (2026-06-07): Khud ka telephony stack + service resell
- **User ne decide kiya: khud ka stack banayenge AUR white-label service bhi bechenge.** Full plan: `docs/P3_Own_Telephony_Stack_Plan.md` — FreeSWITCH (Docker) + Pipecat + Plivo Zentrunk trunk (pilot ₹0.60/min) → operator direct (₹0.30-0.40 @scale). White-label ₹10-25K/mo positioning (Synthflow $2K/mo gap). Minutes-resale ka legal check (VNO/OSP) pending.
- **User action items (blockers): Plivo account, DLT ₹5,900, 140-number, WhatsApp Business app.** Implementation next session: FreeSWITCH compose → pipecat module → web-call transport proof → Plivo e2e.
- **Trunk final research (2026-06-07): Vobiz.ai naya contender** — ₹0.45/min std (₹0.65 streaming), self-serve console.vobiz.ai, AI-first (Bolna ecosystem), India-native Airtel/Jio/VIL trunks, DLT-ready. Plan: **Plivo pilot (proven ₹0.60) + Vobiz parallel trial** — Pipecat SIP pe ₹0.45 confirm hua toh switch. DPIIT-recognized ho toh Exotel startup free credits bhi. **Foreign trunks (Twilio/Telnyx/Vonage) India domestic ke liye ILLEGAL (ILD toll-bypass, DLT impossible) — production me kabhi nahi.** Scale: Smartflo ₹0.30-0.50.
- **USER FINAL DECISION (2026-06-07): TEENO EK SAATH karne hain — (1) leads-business + (2) khud ka telephony stack + (3) white-label service resell.** Scope-creep warning di gayi thi, user ne conscious decision liya hai parallel chalane ka. Claude ka kaam: teeno tracks ka code/infra/ops sambhalna, user: sales+paperwork. Build order phir bhi pragmatic rakhna (trunk pilot → FreeSWITCH+Pipecat → white-label metering).

## Environment Gotchas (IMPORTANT for Claude sessions)
- **Sandbox mount STALE ho jata hai** file-tool edits ke baad — edited files bash se truncated dikhti hain. Windows side (Read/Write/Edit tools + Desktop Commander) hi source of truth hai. Verification hamesha Windows pe karo (bats run karke log files Read karo).
- Sandbox git index nahi padh sakta (version mismatch) — git operations Desktop Commander + Windows git (C:\PROGRA~1\Git\cmd\git.exe) se karo.
- .bat files me npm/git jaise .cmd tools ko `call` ke saath invoke karo warna batch wahi terminate ho jata hai. `timeout /t` non-interactive me fail hota hai — `ping -n N 127.0.0.1` use karo.
- Desktop Commander one-liner quoting mangle karta hai — complex commands .bat file me likh ke chalao, output log file me redirect karke Read karo.
