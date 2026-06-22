# 🌐 DEPLOY GUIDE — LeadGen AI ko live karna (Hinglish)

Goal: project ko internet pe live karna taaki dashboards, web-call, aur telephony
webhooks public HTTPS URL pe chalein. Do raaste — **Railway (sabse aasaan)** ya
**Render**. Dono tumhare `Dockerfile` se deploy karte hain.

---

## ⭐ Option 1 — Railway (recommended, sabse aasaan)

### Steps
1. Code ko **GitHub** pe push karo (agar nahi hai):
   ```bash
   git init && git add . && git commit -m "deploy"
   git branch -M main
   git remote add origin https://github.com/<tumhara-user>/leadgen-voice.git
   git push -u origin main
   ```
   > ⚠️ `.env` push mat karna! `.gitignore` me hona chahiye (check karo).

2. https://railway.app pe jao → **New Project** → **Deploy from GitHub repo** → apna repo chuno.
   - Railway `railway.json` + `Dockerfile` khud detect karega.

3. **Database add karo:** project me **+ New** → **Database** → **PostgreSQL**. (Redis bhi: **+ New → Redis**.)

4. **Environment variables** set karo (web service → Variables):
   ```
   APP_ENV=production
   DEBUG=false
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   SECRET_KEY=<koi-lamba-random-string>
   GEMINI_API_KEY=<tumhari-gemini-key>
   DEFAULT_LLM=gemini-2.5-flash
   LLM_PROVIDER=gemini
   TELEPHONY_PROVIDER=simulation
   TIMEZONE=Asia/Kolkata
   WORKING_HOURS_START=09:00
   WORKING_HOURS_END=21:00
   ```
   (Sarvam/SIP keys baad me jab chahiye.)

5. **Background worker** (scraping/calling jobs ke liye) — **+ New → Empty Service** → same repo →
   Settings → **Start Command**:
   ```
   celery -A app.worker worker --loglevel=info --concurrency=2
   ```
   Same DATABASE_URL + REDIS_URL variables iss service me bhi daalo.

6. **Public domain:** web service → Settings → **Generate Domain** → `https://xxx.up.railway.app` milega.

7. **DB tables + seed** (ek baar): web service → Settings → ek baar run karo
   (ya Railway shell se): `python scripts/seed_demo_data.py`
   > Production me usually `alembic upgrade head` use karo migrations ke liye.

### Test
- `https://<your-domain>/health` → healthy
- `https://<your-domain>/app/customer` , `/app/admin` , `/app/test-call`
- `/app/test-call` pe bot se baat karo — Gemini se live natural jawab.

**Cost:** ~$5/month (₹420) base + thoda usage. Postgres/Redis included.

---

## Option 2 — Render (blueprint se one-click)

1. Code GitHub pe (upar jaisa).
2. https://render.com → **New** → **Blueprint** → repo chuno.
   - `render.yaml` already bana hua hai — web + worker + Postgres + Redis sab define hai.
3. Deploy ke baad **Environment** me `GEMINI_API_KEY` (aur Sarvam/SIP baad me) daalo — ye `sync:false` hain isliye dashboard se daalne padte hain.
4. Domain Render khud deta hai (`https://xxx.onrender.com`).
> Free plan spin-down ho jaata hai (telephony ke liye bura) — **Starter (~$7/mo)** always-on ke liye.

---

## Option 3 — VPS (Hetzner/DigitalOcean) — jab SIP self-host karo

`docker-compose.prod.yml` already hai. VPS pe:
```bash
git clone <repo> && cd leadgenrationaivoiceagent
cp .env.example .env   # values bharo
docker compose -f docker-compose.prod.yml up -d
```
Phir **Caddy/Nginx** se HTTPS + domain laga do. Cheapest always-on (~₹700/mo), aur
yahan Asterisk/SIP bhi same box pe chala sakte ho.

---

## ✅ Live jaane ke baad checklist
1. **Telephony:** Exotel/Plivo SIP account + number → `.env`/host vars me `TELEPHONY_PROVIDER` + SIP keys. Webhook URL = `https://<your-domain>/telephony/twilio/media-stream`.
2. **DLT/TRAI registration** (India — outbound ke liye mandatory).
3. **Sentry DSN** daalo (error monitoring — code ready).
4. **Custom domain** (optional) → host ke DNS settings me.
5. Pehli **real test call** apne hi number pe.

> Detail features: `AUTOMATION_SETUP.md` | Local test: `LAUNCH_GUIDE.md` | Costing: `LeadGen_Costing_Model.xlsx`
