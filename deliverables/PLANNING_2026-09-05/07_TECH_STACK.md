# Tech Stack — LeadGen AI (justification + alternatives considered)

> **Decision date:** 2026-09-05 (current state). **Re-evaluation:** at M9 retro (end S6). **Owner:** Sumit (A), lead (R), all engineers (C).

## Backend

| Component | Chosen | Version | Justification | Alternatives considered |
|---|---|---|---|---|
| Web framework | **FastAPI** | 0.115+ | Async-native, OpenAPI auto-gen, Pydantic v2 for validation, fastest Python framework for I/O-bound, Python 3.12 | Flask (sync, slower), Django (heavier, ORM lock-in), Litestar (newer, smaller ecosystem), aiohttp (raw, no OpenAPI) |
| ORM | **SQLAlchemy 2** | 2.0+ | Async + sync parity, raw SQL escape hatch, Alembic integration, mature | Tortoise ORM (smaller community), Piccolo (newer), raw asyncpg (no migrations), Django ORM (Django-locked) |
| Migrations | **Alembic** | latest | Standard for SQLAlchemy, async-aware, autogenerate with manual review | yoyo-migrations (lighter), hand-rolled (no) |
| Background jobs | **Celery + Redis** | 5.x + 7 | Battle-tested, beat scheduler, rich canvas, Redis as broker + result backend | Dramatiq (newer, lighter), RQ (simpler, no canvas), Arq (async-native but young), Huey (smaller), APScheduler (in-process only) |
| Auth | **PyJWT + bcrypt** | latest | Stateless tokens, RBAC at middleware layer, no vendor lock-in | Auth0/Clerk (vendor), Keycloak (heavy, own infra), NextAuth (frontend-locked) |
| RBAC | **Custom (Role enum + middleware)** | n/a | Light, no external dep, owns matrix | Casbin (over-engineered for 6 roles), Oso (excellent but premium) |
| Validation | **Pydantic v2** | 2.x | Type-safe, fast (Rust core), integrates with FastAPI | Marshmallow (slower), attrs (less ergonomic) |
| HTTP client | **httpx** | 0.28+ | Async-native, mirror requests API | aiohttp (raw), requests (sync only) |

## Frontend

| Component | Chosen | Version | Justification | Alternatives considered |
|---|---|---|---|---|
| Framework | **Next.js** | 14+ | SSR + SSG, App Router (M6-ready), React 18+, Vercel-class DX | Remix (newer, smaller), SvelteKit (different framework), CRA (deprecated) |
| UI library | **React 18** | 18+ | Stable, Server Components for dashboards, broad talent | Solid.js (smaller community), Qwik (newer) |
| Styling | **Tailwind CSS** | 3.x | Utility-first, JIT, matches our design tokens (Archify) | CSS Modules (more code), Chakra UI (heavier), Material UI (over-design) |
| Components | **shadcn/ui + custom** | latest | Headless + owns CSS; matches Archify premium look | Material UI (heavy), Ant Design (heavy), custom (more dev time) |
| State | **TanStack Query + Zustand** | latest | Cache + server state vs client state split | Redux (over-engineered), Jotai (atom-only) |
| Forms | **react-hook-form + Zod** | latest | Type-safe, low re-render | Formik (older), final-form (declining) |

## Data tier

| Component | Chosen | Version | Justification | Alternatives considered |
|---|---|---|---|---|
| Primary DB | **Postgres 16** | 16.x | JSONB + JSONL-via-app pattern, mature, on-disk backups trivial | MySQL (weaker JSON), MongoDB (no transactions ACID by default) |
| Cache + broker | **Redis 7** | 7.x | Universal, well-supported, persistence options | KeyDB (Redis fork), DragonflyDB (newer) |
| Vector store | **Qdrant** | latest | Rust-native, on-disk HNSW, supports tenant isolation by collection | Pinecone (vendor, expensive), Weaviate (heavier), pgvector (limited) |
| JSONL stores | **On-disk (`data/*.jsonl`)** | n/a | Rebuildable, append-only, simple ops, owner-visible | SQLite (per-file overhead), Postgres JSONB (migration cost) |
| Search index | **Postgres FTS** | built-in | Cheaper than ES for our scale | Elasticsearch (overkill), Meilisearch (extra service) |

## LLM / AI

| Component | Chosen | Justification | Alternatives |
|---|---|---|---|
| Flagship voice | **GPT-Swara** (custom fine-tuned GPT) | Hindi prosody, low-latency streaming | ElevenLabs (vendor, recurring), Play.ht (vendor), VALL-E (no API) |
| Fallback LLM | **Groq** (Llama 3.1 70B) | Lowest latency, free tier good | Together AI, Anyscale, OpenRouter |
| Backup | **Gemini** | Multi-modal, separate provider for failover | Claude (vendor, ethics review), Mistral |
| Eval | **LLM-as-judge (GPT-4)** | Catches subtle regressions; deterministic-only fallback for CI | RAGAS (specific to RAG), custom (time) |
| Embeddings | **OpenAI text-embedding-3-small** | Cost-effective, 1536d, broad support | Sentence-Transformers (self-hosted), Cohere (vendor) |

## Telephony / voice

| Component | Chosen | Justification | Alternatives |
|---|---|---|---|
| DID provider | **Vobiz** | Nagpur local DIDs available, competitive rates | Exotel (costly), Knowlarity (older), Ozonetel |
| SIP trunk | **Smartflo** | CDR webhooks, India-grade | Tata Tele, BSNL, Airtel IQ |
| WhatsApp | **WAHA (self-hosted)** | Direct WA Business API, no per-message fee at scale | Twilio (expensive), Gupshup (vendor), Interakt |
| Recording | **Vobiz + Smartflo native** | Compliance-grade, 90-day retention | Cloud-based (more cost) |

## Infrastructure

| Component | Chosen | Justification | Alternatives |
|---|---|---|---|
| VPS | **Hostinger (single, KVM 2)** | Cheap, India region, full root | DigitalOcean, Linode, AWS Lightsail, Hetzner |
| Container | **Docker Compose** | Single-VPS scale, simple ops | K8s (overkill at this size), bare-metal (no), Nomad (extra learning) |
| CI | **GitHub Actions** | Free tier generous, GHCR integrated, owner already onboarded | CircleCI, GitLab CI, Jenkins |
| Container registry | **GHCR** | Free for public, private repos included | Docker Hub (rate limits), ECR (AWS), GCR (GCP) |
| Secrets | **GitHub Actions secrets + VPS env** | Standard, owner-rotatable | HashiCorp Vault (overkill), Doppler (extra service) |
| Observability | **Sentry + Grafana + Prometheus (optional)** | Free tiers sufficient | Datadog (costly), New Relic (costly), Honeycomb (costly) |
| Backups | **pg_dump nightly → off-site S3** | Standard, owner-runnable | managed Postgres (vendor), WAL-G (heavier) |

## Dev / tooling

| Component | Chosen | Justification | Alternatives |
|---|---|---|---|
| Python | **3.12** | Stable, perf, async improvements | 3.13 (newer, some lib compatibility), 3.11 (older) |
| Lint | **ruff** | Fast, replaces flake8+isort+black | flake8 (slower), pylint (heavy), Black (separate) |
| Type check | **mypy strict (incremental)** | Catches drift | Pyright (faster), Pyre (FB-only) |
| Test | **pytest 7.4.4 + pytest-asyncio 0.23.4** | Standard, pinned for stability | unittest (verbose), nose (deprecated) |
| HTTP test | **httpx TestClient** | Async-native | requests (sync) |
| Mock | **unittest.mock + respx** | Standard + HTTP mock | vcr.py (recording-heavy) |
| E2E | **playwright** (selective) | Cross-browser, modern | Selenium (older), Cypress (JS-locked) |
| Load | **locust** | Python-native, simple | k6 (JS), JMeter (heavy) |
| Security | **bandit + pip-audit + Dependabot** | Standard | Snyk (costly), Trivy (broader scope, used) |

## Why NOT X (decisions we ruled out)

1. **Next.js over Remix** — owner familiarity with React, App Router is feature-complete.
2. **Postgres over MongoDB** — transactions + JSONB + lower ops cost.
3. **Celery over Dramatiq** — battle-tested, owner already knows it.
4. **Qdrant over Pinecone** — on-prem (DPDP), no per-vector $.
5. **WAHA over Twilio** — direct WA Business API, lower long-term cost.
6. **Vobiz over Exotel** — local DIDs, better pricing.
7. **GH Actions over Circle** — bundled with GitHub, free tier.
8. **Hostinger KVM 2 over DO/Linode** — India region, owner familiarity.

## Open reconsiderations (S5–S6)

- **Postgres 17** (when stable + tested in S5)
- **Redis 7.4** (security patches)
- **FastAPI 0.116** (incremental upgrade)

No major framework migrations in M6–M9. Re-evaluation at M9 retro.