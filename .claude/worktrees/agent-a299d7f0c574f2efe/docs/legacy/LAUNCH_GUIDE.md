# 🚀 LAUNCH GUIDE — LeadGen AI Voice Agent (Hinglish)

Ye guide tumhe **zero se live** le jaata hai. 3 phase: (A) local test bina kisi paise/key ke,
(B) free keys ke saath real AI, (C) ek SIP trunk laga ke pehli real call.

> Sab commands project folder (`leadgenrationaivoiceagent`) ke andar se chalana.

---

## PHASE A — Local test (₹0, koi key nahi)

### 1. Python + deps
```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```
> Jaldi test ke liye sirf core deps chahiye to: `pip install -r requirements-core.txt`

### 2. .env banao
```bash
copy .env.example .env           # Windows  (Mac/Linux: cp .env.example .env)
```
`.env` me kam se kam ye set karo (free local):
```
DATABASE_URL=sqlite:///./leadgen.db
APP_ENV=development
DEBUG=true
```

### 3. Demo data seed karo (SQLite)
```bash
python scripts/seed_demo_data.py
```
Isse ~10 clients, 6 agents, 8 campaigns, 26 leads, 40 calls demo data ban jaata hai —
dashboards isse populate ho jaate hain.

### 4. Server start karo
```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Browser me kholo
- Website:            http://localhost:8000/site/
- Customer dashboard: http://localhost:8000/app/customer
- Admin dashboard:    http://localhost:8000/app/admin
- **Bot se baat karo (test):** http://localhost:8000/app/test-call

> Dashboards bina server ke bhi chalte hain — `frontend/*.html` ko seedha browser me kholo.

### 6. Agent ko personas pe test karo (eval)
```bash
python -m app.voice_agent.eval_suite
```
7 test personas (interested, busy-rude, confused, price-objector, voicemail,
not-interested, Hindi-switcher) pe agent ka pass/fail report milega.

---

## PHASE B — Free AI brain (Gemini + optional Sarvam)

### Gemini (free tier — recommended LLM)
1. https://aistudio.google.com se free API key lo.
2. `.env` me:
```
GEMINI_API_KEY=your_key_here
DEFAULT_LLM=gemini
LLM_PROVIDER=gemini
```
Ab `/app/test-call` pe agent ka jawab **bahut zyada natural** ho jaayega (rule-based se LLM mode).

### Sarvam (best Hindi voice — tumhara India edge, optional)
1. https://www.sarvam.ai se API key lo.
2. `.env` me:
```
SARVAM_API_KEY=your_key
STT_PROVIDER=sarvam
TTS_PROVIDER=sarvam
DEFAULT_LANGUAGE=hi-IN
```
Key na ho to free Vosk/EdgeTTS chalega (Hindi thoda kam natural).

---

## PHASE C — Real calls (paid telephony)

> ⚠️ Yahan se per-minute kharcha lagta hai (~₹0.40–0.80/min). India ke liye Plivo/Exotel sasta.

### 1. SIP trunk account
- **Plivo / Exotel / FreJun** me sign up karo, ek DID number lo.
- `.env` me (telephony section):
```
TELEPHONY_PROVIDER=sip          # ya exotel / twilio
SIP_HOST=...
SIP_USERNAME=...
SIP_PASSWORD=...
SIP_DID=+91XXXXXXXXXX
```
Key na ho to system **simulation mode** me chalta hai (logs me dikhega, real ring nahi).

### 2. ⚖️ Compliance (India — zaroori, ignore mat karna)
- **DLT registration** karao (principal entity + headers).
- Sirf **140-series** number se commercial calls.
- Sirf **9 AM – 9 PM** (pipeline me gate laga hai).
- **DND/NCPR scrub** on rakho (pipeline karta hai).
- Best: **opt-in / warm leads** — random cold calling pe number block + penalty ka risk.

### 3. Ek campaign chalao
```python
from app.automation.orchestrator_pipeline import LeadGenPipeline
import asyncio
pipe = LeadGenPipeline()
asyncio.run(pipe.run_campaign(
    client_id="client-1", niche="solar",
    cities=["Pune"], sources=["justdial","web"],
    max_leads=20, channels=["whatsapp","voice"],
))
```

---

## 💸 Business model reminder (mat bhulna)
Client ko **"free calls" mat becho** — **"per qualified lead ₹200–500"** becho.
Per-call cost (~₹1–2) us hi client ki payment se cover hota hai → 80% margin.
(Detail: `LeadGen_Costing_Model.xlsx`)

---

## 🆘 Common issues
- `ModuleNotFoundError` → `pip install -r requirements.txt` dobara.
- DB error on seed → `DATABASE_URL=sqlite:///./leadgen.db` set hai na confirm karo.
- Port busy → `--port 8001`.
- Agent robotic lag raha → Gemini key daalo (Phase B).
- Hindi voice kam natural → Sarvam key daalo (Phase B).

Sab features ka detail: `AUTOMATION_SETUP.md`.
