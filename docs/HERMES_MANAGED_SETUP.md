# Managed Hermes (Hostinger) — LeadsGenAI Infra-Handler Setup

**Instance:** `blanchedalmond-peafowl-208582` → https://blanchedalmond-peafowl-208582.hstgr.cloud
(hPanel → Applications → Hermes Agent). Yeh Hostinger-MANAGED hai — hamare VPS ke containers se alag.

> NOTE: Hamare platform ke ANDAR bhi ek "Hermes 🛰️" staff agent hai (`app/platform/infra_handler.py`,
> hourly scan + score). DONO complementary hain: in-app Hermes = automated monitoring;
> Managed Hermes = conversational infra-ops assistant jisse aap baat kar sakte ho.

## Step 1 — Login (sirf aap)
Dashboard kholo, admin username + password se login. **Password chat me share hua tha —
setup ke baad ROTATE kar lena** (Hermes settings me change password).

## Step 2 — LLM provider
- Agar VPS purchase ke saath **nexos.ai credits** liye the to key auto-filled hogi — kuch nahi karna.
- Warna Settings → Providers me apna key daalo (OpenAI-compatible: Groq bhi chalega —
  base URL `https://api.groq.com/openai/v1`). Bina key Hermes tasks run NAHI karega.

## Step 3 — Role prompt (paste-ready)
Hermes CLI/chat me yeh paste karo (ya system-prompt/identity setting me daalo):

```
Tum LeadsGenAI (leadsgenai.in) ke INFRASTRUCTURE HANDLER ho. Hinglish me jawab do, concise.

STACK FACTS:
- FastAPI app, Docker pe Hostinger KVM-4 VPS (Mumbai). Containers: leadgen_app (:8000),
  leadgen_db (Postgres), leadgen_redis, leadgen_worker/scheduler (Celery), pgbouncer,
  observability stack (Prometheus/Grafana/Alertmanager/Loki/Uptime/Gatus).
- Public health: https://leadsgenai.in/health aur /health/ready (db+redis status JSON).
- Public status page: https://leadsgenai.in/status
- In-app monitoring already hai: Hermes staff agent (hourly infra score), Kavya (ops watchdog),
  Tara (telephony readiness), dead-man switch, self-heal cron. Tum unka DUPLICATE nahi —
  tum mere conversational ops-assistant ho: diagnose, explain, runbook suggest.

TUMHARA KAAM:
1. Jab main health/error/downtime ke baare me poochun — pehle https://leadsgenai.in/health/ready
   fetch karke REAL state batao, phir diagnosis.
2. Runbook steps suggest karo (docker logs/restart commands) — par EXECUTE sirf tab jab main
   explicitly bolun, aur kabhi bhi destructive (rm/prune/down) commands khud mat chalana.
3. Deploy issues pe: repo = github.com/sumitrevolt/leadgenrationaivoiceagent, deploy =
   git pull + docker compose -f docker-compose.vps.yml build app + up -d --force-recreate.
   Naye page-routes pe HARD RELOAD yaad dilana.
4. Weekly mujhse poochho: backups offsite gaye? disk %? CI green hai?

BOUNDARIES (hamesha):
- Mere VPS pe tumhara SSH/exec access NAHI hai aur nahi hona chahiye — sirf advise karo.
- Secrets/passwords kabhi store ya repeat mat karo.
- Koi bhi paid action (recharge, purchase) sirf suggest karo, karo mat.
```

## Step 4 — (Optional) Telegram connect
Hermes Settings → Connectors → Telegram link karo, taaki phone se hi infra sawal pooch sako.

## 1-MAHINA VALUE PLAN (plan kharida hai — poora nichodo)

> Funda: Managed Hermes wahi kaam kare jo HAMARA stack nahi karta — background research,
> external watch, Telegram-se-ops. Jo hamara platform already karta hai (content, posts,
> monitoring alerts) us pe iske credits MAT jalao. FREE/sasta model use karo (Step 2 —
> Groq key = ₹0; nexos credits plan me mile hon to wo).

### Week 1 — Setup + infra assistant
1. Step 1-3 upar (login, Groq key, role prompt) + Telegram connect.
2. Test: "leadsgenai.in/health/ready fetch karke batao sab healthy hai?"
3. Scheduled daily task paste karo:
```
Roz subah 9 baje IST: https://leadsgenai.in/health/ready aur https://leadsgenai.in/status
fetch karo. Agar kuch unhealthy/slow dikhe to mujhe Telegram pe turant batao,
warna sirf "✅ sab healthy" ek line. Koi action khud mat lena.
```

### Week 2 — Competitor watch (background, jo hum manually nahi karte)
```
Har Somvaar yeh karo aur mujhe summary do (Hinglish, 10 lines max):
1. predis.ai/pricing, dhanda.app, adbanao.com pe koi pricing/feature change?
2. Google pe "AI telecaller India pricing" ke naye players/offers?
3. caller.digital aur myoperator.com pe voice-AI pricing change?
Sirf CHANGES batao — purani cheez repeat mat karo. Source link ke saath.
```

### Week 3 — Lead research assistant (drafts only, send hum karte hain)
```
Task: Pune/Nashik/Nagpur ke 20 solar installation companies dhundo jinki website
nahi hai ya bahut purani hai. Har ek ka: naam, city, phone (public listing se),
website-status. Table me do. Yeh main apne CRM me import karunga.
DISCLAIMER: koi contact/outreach khud mat karna — sirf research.
```
(Output CSV jaisa aaye to hum `/api/growth/prospects/import` me daal denge.)

### Week 4 — Content/SEO research (hamare generators ke liye raw material)
```
"AI marketing for [niche] India" type 10 blog-topic ideas do jo Google me
low-competition + high-intent hain, har ek ke saath 3 H2 subheadings.
Niches: solar, real estate, coaching classes, dental clinics.
```

### Mahine ke end pe decide
- Agar Telegram-ops + competitor-watch ki aadat ban gayi aur credits free-tier me
  chal rahe → renew socho. Warna cancel — in-app stack sab zaroori kaam karta hai.

## Security rules (IMPORTANT)
1. **Managed Hermes ko VPS ka SSH/root access MAT do** — autonomous agent + prod root = ek bhool me site down.
   Advise-only rakho; commands khud chalao ya mujhse (Claude) chalwao.
2. Admin password rotate karo (chat me aa chuka hai).
3. nexos.ai credits negative hue to Hermes chup ho jaata hai — balance Docker Manager → Projects me dikhta hai.
