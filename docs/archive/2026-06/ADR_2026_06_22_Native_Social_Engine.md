# ADR 2026-06-22 — Native Social-Posting Engine (own stack)

**Status:** Accepted (scaffold shipped, gated `SOCIAL_ENGINE`, default OFF)
**Context owner:** LeadGen AI platform

## Context
AI video-ad cycle (aur baaki content) ko customer ke social accounts pe post karne ke
liye abhi **Postiz** (external) par dependency hai. Long-term production ke liye apna
**native social-posting engine** chahiye — control, cost, reliability, aur customer-data
apne paas. Tumhare paas pehle se **Postgres + Redis + Celery workers + AI staff** stack
hai, isliye "Redis queue / PostgreSQL / worker agents" reinvent nahi — **reuse** karenge.

## Decision
`app/social_engine/` package banaya — provider-adapter pattern + durable queue + token
vault. Postiz ek adapter ban gaya (external dependency optional fallback). Sab **gated
`SOCIAL_ENGINE` (default OFF)**, additive, never-raise.

## Architecture
```
video_ad_cycle / koi bhi caller
        │  enqueue_publish(client, media, caption, platforms)
        ▼
   store (durable)  ── JSONL primary + Postgres mirror (social_post_jobs)
        │  job: queued
        ├─► Celery task social_engine.drain  (Redis broker, worker agents)   ─┐
        └─► scheduler run_cycle → process_queue()  (guaranteed drain)         │
                          │  claim_pending → dispatch                         │
                          ▼                                                   │
                 registry → SocialProvider.publish(req, account)  ◄───────────┘
                          │   (token vault se per-client OAuth)
                          ▼
        Telegram · Meta(FB+IG) · GBP · LinkedIn · X · YouTube · Postiz
                          │
                  published | retry | dead | skipped(inert)
```
**Files:**
- `base.py` — `SocialProvider` ABC, `PublishRequest`/`PublishResult`.
- `vault.py` — per-client per-platform OAuth token, **Fernet encrypted-at-rest** (`SOCIAL_TOKEN_KEY`).
- `store.py` — durable job queue: **JSONL primary (fail-open) + Postgres mirror** (`social_post_jobs`), idempotent `ensure_tables()`.
- `providers.py` — adapters (neeche).
- `engine.py` — `enqueue_publish()`, `process_queue()` (claim → dispatch → retry/backoff/dead/skip).
- `tasks.py` — Celery `@celery_app.task social_engine.drain` (Redis). Scheduler bhi drain karta (worker.py boot edit nahi chahiye).

## Fits existing infra
- **Queue/transport:** Redis + Celery (`from app.worker import celery_app`) — pehle se live.
- **Persistence:** SQLAlchemy `Base` + `get_db_session` (PgBouncer/Postgres) — mirror table additive.
- **Worker agents:** Celery `leadgen_worker` + scheduler/beat — already running; drain dono se.
- **Resilience:** scheduler-driven drain = guaranteed even if Celery task unregistered (dead-man pattern).

## Per-platform integration + approval gates (har ek INERT until ready)
| Platform | Adapter | Approval / pre-req | Media |
|---|---|---|---|
| **Telegram** | live | none (BotFather token) | file upload, free ✅ |
| **Instagram** | Meta | Meta app-review + business verify; `instagram_content_publish` | **public video URL** (REELS container→publish) |
| **Facebook Page** | Meta | `pages_manage_posts`, `pages_read_engagement` | public URL / file |
| **Google Business** | GBP | GBP API access request + per-location OAuth (Google ne post-features restrict kiye — current status verify) | photo URL |
| **LinkedIn** | LinkedIn | Marketing/Community API **partner access** (sabse mushkil); `w_organization_social` | text live; video = registerUpload (activation pe) |
| **X (Twitter)** | X | OAuth + paid API tier (media) | text live; media activation pe |
| **YouTube** | YouTube | OAuth; resumable upload (heavy, worker) | activation pe wire |
| **Postiz** | Postiz | `POSTIZ_API_KEY` (multi-channel fallback) | upload+post |

> ⚠️ Har platform ka API version + permission **activation pe current docs se verify** karo
> (endpoints stable-ish, par platforms badalte). **Public media hosting** Meta/LinkedIn ke
> liye zaroori — reels file ko public URL pe serve karo (MinIO/S3 addon ya `/media/` route).

## Security
- OAuth tokens **Fernet-encrypted at rest** (`SOCIAL_TOKEN_KEY` urlsafe-b64 32B; warna `SECRET_KEY` se derive). Key unset = plaintext + loud warning (prod me key MANDATORY).
- Token plaintext kabhi log/commit nahi. Per-client isolation (`client_id|platform|account_ref`).

## Rollout phases
- **P0 (done):** scaffold — interface, vault, queue, providers (Telegram+Postiz live; baaki gated), engine, video_ad_cycle handoff, flag. Inert until `SOCIAL_ENGINE=1`.
- **P1:** public media hosting (reels → public URL) + `SOCIAL_ENGINE=1` + Telegram end-to-end prod test.
- **P2:** Meta app-review → IG+FB live (Indian local businesses ke liye highest value).
- **P3:** GBP API access → local-SEO posts. **P4:** LinkedIn partner → B2B niches. **P5:** X / YouTube.
- Har phase: provider creds → `vault.put(client, platform, token, account_ref)` → test ek client → roll out.

## Enablement (`.env`)
```
SOCIAL_ENGINE=1
SOCIAL_TOKEN_KEY=<fernet key>            # python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
# Telegram: TELEGRAM_BOT_TOKEN + client.telegram_chat_id
# Meta/GBP/LinkedIn/X/YouTube: per-client OAuth tokens vault me daalo (approval ke baad)
MEDIA_BASE_URL=https://leadsgenai.in/media   # public reel hosting (Meta/LinkedIn ke liye)
```

## Risks / tradeoffs
- Platform approvals = **external blockers** (weeks–months). Engine ready hai; activation unke baad.
- API drift → adapters me version pinned; activation pe verify.
- Public media hosting = naya requirement (Meta/LinkedIn URL-fetch karte).
- Postgres mirror best-effort; JSONL = source of truth (DB down pe queue chalta rahe).

## Verify
`python scripts/prod_check.py` · `pytest tests/test_social_engine.py -q` (logic harness: 12/12 pass).
