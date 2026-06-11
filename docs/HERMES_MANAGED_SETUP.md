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

## Security rules (IMPORTANT)
1. **Managed Hermes ko VPS ka SSH/root access MAT do** — autonomous agent + prod root = ek bhool me site down.
   Advise-only rakho; commands khud chalao ya mujhse (Claude) chalwao.
2. Admin password rotate karo (chat me aa chuka hai).
3. nexos.ai credits negative hue to Hermes chup ho jaata hai — balance Docker Manager → Projects me dikhta hai.
