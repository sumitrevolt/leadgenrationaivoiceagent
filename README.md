# LeadGen AI

FastAPI SaaS for small Indian local businesses. **Live: https://leadsgenai.in** (Hostinger VPS, Mumbai).

Two separate products, sold as distinct SKUs:

| Product | What it is | Price |
|---|---|---|
| **AI Automated Marketing** | Done-for-you social-media + local-lead marketing (programmatic content, posting, lead capture, CRM follow-up) | Main ₹1,999/mo · Combo/Advanced ₹5,999/mo |
| **AI Voice Calling Agent** | Standalone full AI telecaller (inbound auto-callback + DLT-gated outbound) | Flat per niche-band: A ₹4,999/mo · B ₹9,999/mo · C ₹19,999/mo |

Money path: free lead magnets (`/audit`, `/site-audit`, `/demo`) + pSEO + auto email-outreach → inquiry → `/pricing` → `/start` → **manual UPI** (owner-confirmed) → subscription + top-up minute packs. Manual UPI is the **canonical** and only payment rail (owner-verified).

The entire AI stack runs on **free providers only** (no paid STT/TTS/LLM).

---

## Products

### 1. AI Automated Marketing
- AI social media content (posts/reels copy, Hinglish-optimised) per the client's niche
- Programmatic SEO + mini-sites (`/b/{slug}`)
- Lead capture widget + Hot Queue (`/app/inbox`) for follow-up
- AI email/WhatsApp outreach (ban-safe: cold WhatsApp OFF, 1-click human send)
- Plans:
  - `main` ₹1,999/mo
  - `advanced` ₹5,999/mo (includes AI-callback feature, 500 min)
  - `growth` ₹2,999 (legacy hidden)
  - ₹0 7-day trial (marketing-lite)
  - Annual = 10x monthly (2 months free)
  - Top-ups: 100/250/500 min = ₹1,499/₹3,499/₹5,999

### 2. AI Voice Calling Agent
- Full AI telecaller: STT → LLM → TTS over real phone calls (Vobiz India SIP)
- Compliance-gated: DND scrub (**fail-closed**), TRAI window 9am–7pm, AI disclosure at call start, consent ledger, DLT for cold outbound, 90-day recording retention
- Standalone pricing per niche band: `voice_a_monthly` ₹4,999 · `voice_b_monthly` ₹9,999 · `voice_c_monthly` ₹19,999

---

## Architecture

```
Internet ──> Caddy (host, TLS leadsgenai.in) ──> leadgen_app :8000 (FastAPI)
                                                    ├── Postgres leadgen_db (via PgBouncer :6432)
                                                    ├── Redis leadgen_redis :6379 (Broker + state)
                                                    ├── Qdrant :6333 (RAG: single kb_main, namespaced)
                                                    ├── leadgen_worker (Celery) + leadgen_scheduler
                                                    ├── FreeSWITCH + WS voice stream (L16/16k)
                                                    └── Obs stack (Prometheus/Grafana/Loki/...)
```

- Backend: FastAPI (async), domain routers in `app/api/` (split by domain), engines in `app/platform/`, voice in `app/voice_agent/` + `app/telephony/`, billing in `app/billing/`
- Frontend: server-rendered HTML in `frontend/` (marketing site, Mission Control `/app/automation`, HQ `/app/office`, 4 dashboards)
- Agents: coordinator / dag_engine / process_engine / self_improve loops in `app/agents/`, governed harness in `app/agents/harness/` (INERT by default)

## AI Stack (all free)

| Component | Provider |
|---|---|
| LLM (primary) | Mistral `mistral-small-latest` |
| LLM (fallback) | Groq · Cerebras · NVIDIA NIM · SambaNova · OpenRouter |
| Voice-scoped LLM | Gemini (9-key rotation pool) |
| STT | Groq `whisper-large-v3` (primary) · Gemini audio (fallback) |
| TTS | EdgeTTS `hi-IN-SwaraNeural` (free) |
| Images/video | Pollinations |
| Embeddings | fastembed `multilingual-e5-small` |
| Telephony | Vobiz (India SIP) · Twilio (international fallback) |
| Email | Hostinger SMTP/IMAP (`admin@leadsgenai.in`) |
| Prospecting | Google Maps Places (New) |
| Web search | SearXNG (self-host) |
| Push | ntfy (self-host) |
| WhatsApp | Meta Cloud + own WAHA :3111 |
| Payments | **Manual UPI only** (`UPI_VPA`) |

## Deploy

Single canonical deploy entrypoint: **`scripts/deploy_vps.sh`** (mandatory `APP_VERSION=<sha>`, `/health.version` gate, 5-service skew check). Full runbook: `memory/playbooks.md`.

Manual: `git push origin main` → SSH to VPS → `cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &` → poll `/tmp/dep.log`.

`docker-compose.vps.yml` is the **only** production compose file. `Dockerfile.lock` is the only build input.

## Quick Start (dev, Windows, py3.12)

```bash
python -m venv .venv
.venv\Scripts\pip install --no-deps -r requirements.lock.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
*Note: Run dev is [UNVERIFIED locally] — import verified via prod_check.*

- Tests (targeted): `.venv\Scripts\python.exe -m pytest tests/test_billing_truth_2026.py -q`
- Full suite: `scripts\run_tests.bat` (then read `pytest_run.log`)
- Lint: `.venv\Scripts\python.exe -m ruff check app`
- Verify gate: `.venv\Scripts\python.exe scripts\prod_check.py` and `scripts\check_secrets.py`

## Repo map

```
app/            FastAPI backend (routers, engines, voice, billing, agents)
frontend/       Server-rendered HTML (marketing site + app dashboards)
alembic/        DB migrations (DB_CREATE_ALL=0 → Alembic-only in prod)
tests/          pytest suite
scripts/        Deploy + ops (deploy_vps.sh = canonical deploy)
docs/           Architecture, ADRs (docs/adr/), runbooks, context
memory/         Decisions/backlog/incidents/playbooks (append-only)
monitoring/     Prometheus rules, gatus synthetic checks
deploy/         Non-production compose + scheduler config
docker-compose.vps.yml   CANONICAL production stack
Dockerfile.lock          CANONICAL build input
```

## Compliance

- TRAI/telecom: DND scrub **fail-closed**, AI disclosure at call start, promo window 9am–7pm, consent-ledger opt-out, no foreign trunks for India-domestic, cold auto-calls require DLT
- DPDP Act 2023: purpose limitation, data minimisation, consent basis, 90-day recording retention, purge API + Grievance Officer in `/privacy`, strict customer isolation
- Secrets: `.env` only (gitignored), never committed

## Docs

- Operating manual: `CLAUDE.md` / `AGENTS.md` (byte-identical)
- Loop ledger: `progress.md`
- Architecture + ADRs: `docs/`
- Knowledge base: `memory/` (`memory/INDEX.md` first)

## License

Proprietary — All Rights Reserved.
