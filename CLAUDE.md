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

## Environment Gotchas (IMPORTANT for Claude sessions)
- **Sandbox mount STALE ho jata hai** file-tool edits ke baad — edited files bash se truncated dikhti hain. Windows side (Read/Write/Edit tools + Desktop Commander) hi source of truth hai. Verification hamesha Windows pe karo (bats run karke log files Read karo).
- Sandbox git index nahi padh sakta (version mismatch) — git operations Desktop Commander + Windows git (C:\PROGRA~1\Git\cmd\git.exe) se karo.
- .bat files me npm/git jaise .cmd tools ko `call` ke saath invoke karo warna batch wahi terminate ho jata hai. `timeout /t` non-interactive me fail hota hai — `ping -n N 127.0.0.1` use karo.
- Desktop Commander one-liner quoting mangle karta hai — complex commands .bat file me likh ke chalao, output log file me redirect karke Read karo.
