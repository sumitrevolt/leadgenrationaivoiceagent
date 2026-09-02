# Hostinger Managed Hermes Agent — Setup + Usage Guide

> **Naming**: Hostinger ke product ka naam bhi "Hermes Agent" hai (collision-warning).
> Project me **"Hermes 🛰️"** = humara internal `app/platform/infra_handler.py` (infra watchdog).
> Yahan jis cheez ki setup hai = **Hostinger Managed Hermes** (cloud coding-agent, Gemini-powered).
> Code/docs me iss external service ko **`hostinger_hermes`** prefix se refer karte hain to disambiguate.

## What it is

Hostinger Managed Hermes ek hosted coding-agent hai (cloud Claude-Code jaisa):
- **Sandbox**: 10GB persistent disk, CLI + App UI access, `Open App` button + `Command line (CLI)`.
- **AI**: User-provided **Gemini API key** (Google AI Studio, free tier kaafi for small tasks).
- **Plan**: "Managed Hermes" — expiry monitor karo (current: 2026-07-11).
- **Use case for this project**: 14th AI staff member — **Apprentice Dev** role.

## Why we wired it (decision log)

`code_upgrader` (Vikram 🛠️) abhi sirf patches **propose** karta hai (`data/code_patches.jsonl`)
— koi entity unhe **apply** nahi karta. Manual approval ke baad woh patches "approved" status
me pade rehte hain. Hostinger Hermes wahi missing executor hai:

- Phase 1 (read-only, **active**): Daily project-health report via email — koi write risk nahi.
- Phase 2 (gated `HERMES_HANDOFF=1`, **future**): Approved patches uthao → branch banao → tests
  run → draft PR. Human merge approve karega.

Phase 2 wiring abhi **default OFF** hai — flag visible hai `/api/growth/infra/flags` me.

## Phase 1 Setup (one-time, ~10 min)

### Step 1 — Hostinger Hermes dashboard se ek baar

1. Hostinger dashboard → Hermes Agent → **Change AI model** section me apni Gemini API key paste karo.
   Get key from [aistudio.google.com](https://aistudio.google.com) (free tier OK).
2. **Open App** button click karo (browser me Hermes interface khulega) ya **Command line (CLI)** se SSH.

### Step 2 — Inside Hermes sandbox (one-time bootstrap)

```bash
# Hermes ki CLI ya app me yeh paste karo
curl -fsSL https://raw.githubusercontent.com/sumitrevolt/leadgenrationaivoiceagent/main/scripts/hostinger_hermes_bootstrap.sh | bash
```

Ya manual:
```bash
git clone https://github.com/sumitrevolt/leadgenrationaivoiceagent.git ~/leadgen
cd ~/leadgen
bash scripts/hostinger_hermes_bootstrap.sh
```

Bootstrap script ye karta hai:
- Repo clone (or pull latest)
- Python venv setup (lean — sirf `httpx` + `requests` + stdlib)
- `~/.hermes/config.env` me SMTP/notify creds save karne ki template likhta hai
- Pehla `hostinger_hermes_daily_report.py` test-run

### Step 3 — Credentials in Hermes sandbox

`~/.hermes/config.env` file me bharo:
```
# Email recipient for daily reports (default: admin@leadsgenai.in)
NOTIFY_EMAIL=admin@leadsgenai.in

# SMTP creds (Hostinger mail — same as main project)
SMTP_HOST=smtp.hostinger.com
SMTP_PORT=465
SMTP_USERNAME=admin@leadsgenai.in
SMTP_PASSWORD=<paste from main .env>

# Optional: ntfy push (for instant alerts on broken health)
NTFY_URL=https://ntfy.leadsgenai.in
NTFY_TOPIC=<from main .env>
NTFY_TOKEN=<from main .env>
```

### Step 4 — Schedule the daily report

Hermes CLI me cron set karo (sandbox cron available hai):
```bash
# Add to ~/.hermes/cron.txt or crontab -e
30 9 * * *  cd ~/leadgen && bash scripts/hostinger_hermes_daily_report.sh >> ~/hermes_daily.log 2>&1
```

Ya manually run karke test karo:
```bash
cd ~/leadgen && python3 scripts/hostinger_hermes_daily_report.py
```

## What it reports daily

Email subject: `[Hermes] LeadGen daily health YYYY-MM-DD`

Body sections:
1. **Git state** — current HEAD, commits behind/ahead, last 5 commits.
2. **prod_check.py** — route count, import OK/FAIL, env loaded.
3. **External health** — `https://leadsgenai.in/health` + `/health/ready` status.
4. **Test summary** — `pytest -q --ignore=tests/test_phase3_voice.py` quick run (non-hanging subset).
5. **Recent prod-down patterns** — checks for known issues (stale .pyc, scheduler boot-grace,
   event-loop blocks per CLAUDE.md prod-down lessons).
6. **TODO/stub audit** — `scripts/loop_audit.py` hits, only NEW since last report (delta-only).
7. **Pending code-upgrader patches** — count of `proposed` patches in `data/code_patches.jsonl`
   (read via repo clone — Hermes doesn't write).

## Phase 2 (gated, future) — `HERMES_HANDOFF=1`

When trust is established (Phase 1 stable ≥1 week), enable Phase 2:

1. **GitHub deploy key** — Hermes sandbox me ssh key generate karo, public key GitHub
   repo `Settings → Deploy keys → Add new` me **read+write** ke saath add karo.
   ```bash
   ssh-keygen -t ed25519 -C "hostinger-hermes-handoff" -f ~/.ssh/hermes_deploy
   cat ~/.ssh/hermes_deploy.pub  # paste this in GitHub
   ```
2. Enable flag in main project `.env`:
   ```
   HERMES_HANDOFF=1
   ```
3. Run `hostinger_hermes_handoff.py` (will be added in Phase 2):
   - Pulls `data/code_patches.jsonl` (status=approved)
   - For each: creates branch `hermes/patch-<id>` → applies patch → runs tests
   - If green: pushes branch + opens **draft PR** via `gh` CLI
   - Marks status `applied` in jsonl
4. Human reviews draft PR + merges manually.

**Safety**: Draft PR (not auto-merge), branch protection on `main`, tests must pass.
Worst case = bad PR sitting in your inbox.

## What it WILL NOT do (by design)

- ❌ SSH into production VPS (no `72.61.245.204` access)
- ❌ Push to `main` directly (always branch + draft PR)
- ❌ Run anything on production (sandbox-isolated)
- ❌ Modify `.env`, `secrets/`, or `monitoring/alertmanager_smtp_pass`
- ❌ Auto-deploy or trigger CI workflows
- ❌ Touch domain logic agents (Rohan/Isha/Swara stack)

## Cost

- Hostinger Managed Hermes plan: as paid (expires 2026-07-11)
- Gemini API: free tier ~15 RPM, ~1500 RPD = plenty for daily report + small patches
- SMTP send: Hostinger mail (already paid for `admin@leadsgenai.in`)

## Verify it's working

After Step 4, you should receive a daily email by ~09:35 IST. If not:

```bash
# In Hermes sandbox
cd ~/leadgen
python3 scripts/hostinger_hermes_daily_report.py --dry-run  # prints report, no email
```

If `--dry-run` works but no email arrives → check SMTP creds in `~/.hermes/config.env`.

## When to disable / pause

- If Hostinger Hermes plan expires, daily report just stops (no production impact).
- If Phase 2 produces a bad PR: close PR, no harm done. Investigate, fix `code_upgrader`
  proposal logic, or revoke Hermes deploy key from GitHub repo settings.
- Permanently: just stop the Hostinger plan; nothing in main project depends on it.

---

# Conversational ops-assistant usage (merged from HERMES_MANAGED_SETUP, 2026-06-20)

> Upar wala = automated daily-report setup. Yeh section = Hermes ko **conversational infra-ops assistant** ki tarah use karna (chat/Telegram se diagnose-explain-runbook).
> NOTE: In-app **Hermes 🛰️** (`app/platform/infra_handler.py`, hourly score) + Kavya/Tara monitoring alag hain — yeh external Managed Hermes unka conversational complement hai, DUPLICATE nahi.

## Role prompt (paste-ready — Hermes identity/system-prompt me daalo)

```
Tum LeadsGenAI (leadsgenai.in) ke INFRASTRUCTURE HANDLER ho. Hinglish me jawab do, concise.

STACK FACTS:
- FastAPI app, Docker pe Hostinger KVM VPS (Mumbai). Containers: leadgen_app (:8000),
  leadgen_db (Postgres), leadgen_redis, leadgen_worker/scheduler (Celery), pgbouncer,
  observability (Prometheus/Grafana/Alertmanager/Loki/Uptime/Gatus).
- Public health: https://leadsgenai.in/health aur /health/ready (db+redis JSON). Status: /status
- In-app monitoring already hai (Hermes hourly score, Kavya watchdog, Tara telephony, self-heal cron).
  Tum unka DUPLICATE nahi — conversational ops-assistant: diagnose, explain, runbook suggest.

TUMHARA KAAM:
1. Health/error/downtime poochne pe — pehle /health/ready fetch karke REAL state, phir diagnosis.
2. Runbook steps suggest karo (docker logs/restart) — EXECUTE sirf explicit bolne pe; destructive
   (rm/prune/down) khud KABHI mat chalao.
3. Deploy: repo github.com/sumitrevolt/leadgenrationaivoiceagent; deploy = git pull +
   docker compose -f docker-compose.vps.yml build app + up -d --force-recreate. Naye page-routes pe HARD RELOAD yaad dilana.
4. Weekly poochho: backups offsite gaye? disk %? CI green?

BOUNDARIES: VPS pe SSH/exec access NAHI (sirf advise) · secrets kabhi store/repeat mat karo ·
paid action (recharge/purchase) sirf suggest, karo mat.
```

**(Optional) Telegram:** Hermes Settings → Connectors → Telegram → phone se infra sawal pooch sako.

## 1-month value plan (plan kharida hai to poora nichodo)
> Funda: Managed Hermes wahi kaam kare jo HAMARA stack nahi karta — background research, external watch, Telegram-ops. Jo platform already karta (content/posts/monitoring) us pe credits MAT jalao. FREE model (Groq key = ₹0).

- **Week 1 — infra assistant:** role prompt + Telegram + daily task "9 baje /health/ready + /status fetch karke unhealthy ho to Telegram pe batao, warna ✅ ek line. Action khud mat lena."
- **Week 2 — competitor watch:** har Somvaar predis.ai/dhanda.app/adbanao.com + "AI telecaller India pricing" + caller.digital/myoperator pricing-changes (sirf CHANGES, source link).
- **Week 3 — lead research (drafts only):** city-wise no-website businesses → naam/city/phone/website-status table → `/api/growth/prospects/import`. Outreach khud mat karna.
- **Week 4 — content/SEO research:** low-comp high-intent blog topics + H2s (niches: solar/real-estate/coaching/dental).
- **Month-end decide:** aadat bani + credits free-tier me → renew; warna cancel (in-app stack sab zaroori kaam karta).

## Security rules
1. Managed Hermes ko VPS ka **SSH/root access MAT do** (autonomous agent + prod root = ek bhool me site down). Advise-only.
2. Admin password rotate karo (chat me aa chuka tha).
3. nexos.ai/Gemini credits khatam = Hermes chup; balance Docker Manager → Projects me dikhta.
