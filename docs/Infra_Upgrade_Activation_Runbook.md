# Infra Upgrade — Activation Runbook (June 2026)

> Companion to `Infra_BestStack_GapAnalysis_2026-06.md`. Saari additive cheezein **code/config ban chuki** hain aur **OFF-by-default** hain (prod untouched). Ye doc batata hai har ek ko ON kaise karna + kaunse creds chahiye.
> **Order of safety:** sab gated — env set karne tak koi behavior change nahi.

---

## Status snapshot

| Gap | Kya banaya (is repo me) | Activate karne ko chahiye | Status |
|---|---|---|---|
| G1 LLM observability | `app/observability_llm.py` + wired in `app/llm/structured.py` | `ENABLE_LLM_OBS=1` + OTel/Langfuse endpoint | ✅ code done, dormant |
| G2 Cloudflare edge | `docker-compose.edge.yml` (cloudflared) | Cloudflare account + Tunnel token + DNS | ⏳ creds |
| G3 PostHog | `app/analytics/posthog_client.py` + `app/middleware/analytics_inject.py` | PostHog Cloud key + 1-line middleware register | ⏳ creds |
| G4 Secrets (SOPS) | **PEHLE SE THA** (`.sops.yaml` + `scripts/sops_*`) | real `age` public key | ✅ already in repo |
| G5 VPS rebuild | `deploy/ansible/site.yml` + inventory | Ansible install + SSH | ✅ code done |
| G6 Offsite backup | `deploy/offsite/rclone.conf.example` + `scripts/backup_offsite_check.py` (pg_backup.sh already wired) | R2/B2 bucket + keys → `RCLONE_REMOTE` | ⏳ creds |
| G7 LiteLLM cache | `docker-compose.edge.yml` (litellm) + `deploy/litellm/config.yaml` | `LITELLM_MASTER_KEY` (keys already in .env) | ✅ code done, optional |
| G8 Eval CI | `.github/workflows/llm-eval.yml` + `evals/promptfooconfig.yaml` | (optional) `CEREBRAS_API_KEY` GH secret | ✅ advisory live |

---

## G1 — LLM observability (HIGHEST value)
1. `pip install langfuse` (ya sirf OTel jo already hai).
2. `.env`:
   ```
   ENABLE_LLM_OBS=1
   ENABLE_OTEL=1
   OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317        # Tempo (already)
   # ya Langfuse cloud-free: https://cloud.langfuse.com/api/public/otel
   ```
3. Recreate app. Bas — `structured.py` ke calls ab trace honge.
4. **Voice path bhi capture karne ke liye** (jab confirm kare `free_ai.chat` ka call-site), wrap karo:
   ```python
   from app.observability_llm import llm_span
   with llm_span("chat", model=model, provider=provider) as obs:
       resp = await client.chat.completions.create(...)
       obs.record(prompt_tokens=..., completion_tokens=..., output_preview=resp_text)
   ```

## G2 — Cloudflare (free WAF/DDoS/CDN + origin hide)
1. Cloudflare account → domain `leadsgenai.in` add (nameservers point) → Zero Trust → **Tunnels** → create → public hostname `leadsgenai.in` → service `http://localhost:8000` (ya Caddy).
2. Tunnel **token** copy → `.env`: `CLOUDFLARE_TUNNEL_TOKEN=eyJ...`
3. `docker compose -f docker-compose.edge.yml --profile edge up -d`
4. Verify site via Cloudflare; phir origin firewall me sirf Cloudflare IPs allow (ya tunnel-only → 80/443 band).
- **Premium:** Pro $25/mo = full managed WAF rules (traffic bade tab).

## G3 — PostHog (web analytics + session replay + flags, free)
1. PostHog Cloud → free project → **project API key** (`phc_...`).
2. `.env`: `POSTHOG_API_KEY=phc_xxx` + `POSTHOG_HOST=https://us.i.posthog.com`
3. `pip install posthog` (server-side events ke liye).
4. **Frontend auto-inject** — `main.py` app-factory me middleware-stack ke END me ek line:
   ```python
   from app.middleware.analytics_inject import PostHogInjectMiddleware
   app.add_middleware(PostHogInjectMiddleware)
   ```
   (Key unset = middleware turant passthrough, zero overhead. Isliye abhi register karna bhi safe hai.)
5. Server-side events: `from app.analytics import posthog_client as ph; ph.capture(client_id, "lead_qualified", {...})`.

## G4 — SOPS secrets (ALREADY in repo)
- `.sops.yaml` + `scripts/sops_setup.sh|sops_encrypt_env.sh|sops_decrypt_env.sh` pehle se hain. Bas activate: `bash scripts/sops_setup.sh` → public key `.sops.yaml` me daalo → `bash scripts/sops_encrypt_env.sh` → `.env.sops` commit. (Naya kuch banane ki zaroorat nahi.)

## G5 — Ansible VPS rebuild (DR)
1. Control machine: `pip install ansible`
2. `cp deploy/ansible/inventory.ini.example deploy/ansible/inventory.ini` → fill host/key.
3. `.env` box pe ho (ya SOPS-decrypt step uncomment).
4. `ansible-playbook -i deploy/ansible/inventory.ini deploy/ansible/site.yml`
- Dead VPS → naya box → ye playbook → ~15min me wapas live.

## G6 — Offsite backup (activate dormant)
1. **Backblaze B2** (10GB free) ya **Cloudflare R2** (10GB free, zero egress) bucket banao → keys.
2. `cp deploy/offsite/rclone.conf.example ~/.config/rclone/rclone.conf` → keys bharo → `rclone lsd r2:` test.
3. `.env`: `RCLONE_REMOTE=r2:leadgen-backups` → agli raat pg_backup.sh khud offsite karega.
4. Freshness sensor cron: `0 5 * * * python3 scripts/backup_offsite_check.py >> /var/log/leadgen_backup.log 2>&1` (stale > 36h → ntfy alert).

## G7 — LiteLLM semantic cache (optional — Groq-TPD pain ke liye)
1. `.env`: `LITELLM_MASTER_KEY=sk-<random>` (keys already set).
2. `docker compose -f docker-compose.edge.yml --profile gateway up -d`
3. In-network endpoint: `http://litellm:4000` (OpenAI-compatible). free_ai.py PRIMARY rehne do; LiteLLM ko cache/experiment layer ki tarah aazma.

## G8 — Eval CI (advisory, already live)
- `.github/workflows/llm-eval.yml` PR/weekly pe chalta (non-blocking). `evals/promptfooconfig.yaml` me apne real prompts/asserts bharo. Assertions chalane ke liye GH repo secret `CEREBRAS_API_KEY` add karo. Build kabhi RED nahi hoga.

---

## Recommended activation order (free, high-ROI first)
**G6** (offsite, 10min) → **G2** (Cloudflare free) → **G1** (Langfuse cloud-free) → **G3** (PostHog) → **G5** (Ansible) → **G8** (fill evals) → **G7** (only if TPD pain).
