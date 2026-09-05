# Architecture — LeadGen AI (high-level + low-level, M6–M9 state)

> **Source:** consolidates `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_BLUEPRINT.md`, `docs/UNITY_VIRTUAL_OFFICE_ARCHITECTURE.md`, `docs/FINAL_INFORMATION_ARCHITECTURE.md`. Diagrams are Mermaid (renders inline on GitHub + in our preview panel).
> **Last updated:** 2026-09-05 (post-M5, pre-M6)

## High-level system architecture

```mermaid
flowchart LR
    Customer((Customer<br/>Nagpur SMB)) -->|Web/Phone| LB
    Owner((Founder<br/>Sumit)) -->|Admin/OS| LB

    subgraph Edge["Public edge"]
      LB[VPS reverse proxy<br/>Nginx + TLS]
    end

    subgraph App["App tier (Docker Compose)"]
      API[FastAPI :8000]
      Worker[Celery worker<br/>+ beat scheduler]
      Beat[Celery beat<br/>cron loop]
      NextUI[Next.js :3000]
    end

    subgraph Data["Data tier"]
      PG[(Postgres<br/>ledger + auth)]
      Redis[(Redis<br/>cache + broker)]
      Qdrant[(Qdrant<br/>vector store)]
      Disk[(JSONL stores<br/>data/*.jsonl)]
    end

    subgraph LLM["LLM tier"]
      GPT[GPT-Swara flagship<br/>voice + reply]
      Groq[Groq fallback]
      Gemini[Gemini keys]
    end

    subgraph Telephony["Telephony tier"]
      Vobiz[Vobiz DID<br/>+ SIP trunk]
      Smartflo[Smartflo CDR<br/>webhook]
      WAHA[WAHA<br/>WhatsApp]
    end

    LB --> API
    LB --> NextUI
    API --> PG
    API --> Redis
    API --> Qdrant
    API --> Disk
    Worker --> PG
    Worker --> Redis
    Worker --> LLM
    Worker --> Telephony
    Beat --> Worker
    NextUI --> API
```

---

## Container architecture (Docker Compose on Hostinger VPS)

```mermaid
flowchart TB
    subgraph VPS["Hostinger VPS :72.61.245.204"]
      N[Nginx<br/>reverse proxy<br/>TLS termination]

      subgraph Compose["docker compose"]
        App[app<br/>FastAPI :8000]
        Worker[worker<br/>Celery]
        Beat[beat<br/>Celery cron]
        UI[ui<br/>Next.js :3000]
        Redis[redis:7-alpine]
        PG[postgres:16-alpine<br/>data volume]
      end

      subgraph Sidecars["Sidecar containers"]
        OTel[otel-collector<br/>optional]
        Prom[prometheus<br/>optional]
        Backup[backup-cron<br/>pg_dump nightly]
      end

      N --> App
      N --> UI
      App --> Redis
      App --> PG
      Worker --> Redis
      Worker --> PG
      Beat --> Worker
    end

    Backup -.->|nightly dump| S3[(S3-compatible<br/>off-site)]
```

---

## Request flow (typical tenant dashboard load)

```mermaid
sequenceDiagram
    participant U as Tenant (browser)
    participant N as Nginx
    participant UI as Next.js
    participant A as FastAPI
    participant DB as Postgres
    participant R as Redis
    participant L as LLM (if needed)

    U->>N: GET /dashboard
    N->>UI: serve static or SSR
    UI->>A: /api/dashboard/data
    A->>R: GET cache:tenant:{id}:dash
    alt cache hit
      R-->>A: cached JSON
    else cache miss
      A->>DB: SELECT tenant cohort
      DB-->>A: rows
      A->>R: SET cache (TTL 60s)
    end
    A-->>UI: JSON
    UI-->>U: render dashboard
    Note over U,L: < 800ms p95 budget
```

---

## Voice call flow (Vobiz DID → Swara → customer)

```mermaid
sequenceDiagram
    participant C as Customer
    participant V as Vobiz
    participant SF as Smartflo (CDR)
    participant A as FastAPI
    participant W as Worker
    participant L as GPT-Swara

    C->>V: dial Nagpur local DID
    V->>SF: SIP → Smartflo
    SF->>A: /webhook/smartflo (call started)
    A->>W: enqueue handle_call()
    W->>L: stream first-turn prompt
    L-->>W: TTS audio chunk
    W-->>V: WebSocket audio
    V->>C: audio out
    loop dialogue
      C->>V: speech
      V->>A: stream audio in
      A->>L: STT + reasoning
      L-->>A: response
      A->>V: TTS stream
    end
    C->>V: hang up
    V->>SF: call ended
    SF->>A: /webhook/smartflo (CDR)
    A->>W: enqueue store_cdr()
    W->>DB: INSERT cdr + recording
```

---

## Console event dispatcher flow (M2/M5)

```mermaid
flowchart LR
    Emit[Emit site<br/>e.g. voice_launch] -->|emit_console_event| Disp[console_dispatcher]
    Disp -->|JSONL append| Store[(data/console_events/<tenant>.jsonl)]
    Beat[staff-console-drain-5min] -->|drain| Store
    Beat -->|dispatch| Handlers[HANDLERS ring]
    Handlers --> WAHA
    Handlers --> SMTP
    Handlers --> Analytics
```

---

## Customer data isolation (per-tenant boundary)

```mermaid
flowchart TB
    Req[HTTP request] --> MW[tenant_scope middleware]
    MW -->|extract tenant_id from JWT| Ctx[request.ctx.tenant_id]
    Ctx --> ORM[ORM query filter<br/>always tenant_id = ctx]
    ORM --> DB[(Postgres + JSONL)]
    Ctx --> Cache[Redis key prefix<br/>tenant:{id}:*]
    Ctx --> Vector[Qdrant collection<br/>tenant_{id}]
    Note[Every query path<br/>MUST flow through tenant_scope] -.-> MW
```

**Invariant:** every read/write MUST pass `tenant_scope` middleware. ORM raw SQL without filter is a P0 bug.

---

## Observability layer

```mermaid
flowchart LR
    App[FastAPI + Worker] -->|stdout JSON| Loki[Loki / log files]
    App -->|OTel| OTelC[OTel collector]
    OTelC --> Prom[Prometheus]
    OTelC --> Tempo[Tempo]
    App -->|exceptions| Sentry[Sentry]
    Prom --> Graf[Grafana]
    Loki --> Graf
    Tempo --> Graf
    Sentry --> Owner[Owner on-call alert<br/>Sumit]
    Graf --> Owner
```

---

## Module organization (FastAPI app)

```
app/
├── main.py                 # FastAPI app + middleware + routers
├── api/                    # HTTP routes (1406 ops)
│   ├── product_consoles.py # 8 EVENT_SLOTS — single source of truth
│   ├── revenue_sprint.py
│   ├── admin_*.py          # admin endpoints (RBAC-gated)
│   └── ...
├── automation/             # Console dispatcher, schedulers
│   ├── console_dispatcher.py  # M2 durable contract
│   ├── console_events.py
│   └── ...
├── agents/                 # AI staff agents (28 of them)
│   ├── sales_team.py
│   ├── reply_agent.py
│   └── ...
├── billing/                # Billing truth
│   ├── subscription.py
│   ├── packages.py         # Tier matrix
│   └── ...
├── marketing/              # Marketing automation
├── platform/               # Cross-cutting (auth, runtime-data, RBAC)
│   ├── runtime_data_authority.py
│   ├── runtime_data_allowlist.py
│   ├── runtime_data_manifest.py
│   └── ...
├── telephony/              # Vobiz, Smartflo, voice
│   ├── vobiz_stream.py
│   ├── smartflo_*.py
│   └── voice_*.py
├── voice_agent/            # GPT-Swara integration
├── ml/                     # Models, vector store
├── integrations/           # WhatsApp (WAHA), email, HubSpot, Google
├── api/                    # REST + MCP routes
├── middleware/             # tenant_scope, RBAC, OTel
└── ...
```

---

## Layer boundaries

1. **API tier** (`app/api/`): thin — receives HTTP, validates, dispatches. No business logic.
2. **Domain tier** (`app/agents/`, `app/billing/`, `app/marketing/`): business logic, transactional scripts.
3. **Platform tier** (`app/platform/`): cross-cutting concerns — auth, RBAC, runtime-data, observability, MCP.
4. **Integration tier** (`app/integrations/`, `app/telephony/`, `app/voice_agent/`): external systems — adapters only, never domain logic.
5. **Data tier**: Postgres, Redis, Qdrant, JSONL. All writes flow through runtime-data allowlist gate.

---

## Cross-cutting patterns

- **Runtime-data allowlist**: every JSONL write to `data/*.jsonl` MUST be bound to a `runtime_data_allowlist_entries.py` entry. UNDECLARED → BLOCKING in CI. Source: `app/platform/runtime_data_allowlist.py`.
- **Tenant scope middleware**: every request MUST carry tenant_id; raw SQL without filter is a P0. (`. `app/middleware/tenant_scope.py`.)
- **Voice kill-switch**: `VOICE_LAUNCH_KILL=1` blocks all voice dispatch. Owner-gated arm.
- **Console event dispatcher**: durable envelope between product consoles and worker. (M2; `app/automation/console_dispatcher.py`.)
- **Owner-gating protocol**: external actions (push, deploy, outbound sends, payments, refunds) require explicit owner approval. (See `15_OWNER_GATING_PROTOCOL.md`.)
- **DPDP purge**: 8-step idempotent purge before customer deletion. (`app/platform/dpdp.py`.)
- **MCP gate**: `/mcp` endpoint mounted only with token + RBAC. (`app/api/mcp.py`.)

---

## Architecture decision log (ADRs)

See `docs/ADR-*.md` for individual decisions. Top-level:
- **ADR-001**: repo cleanup (2025)
- **ADR-104**: deploy runbook (2026)
- **ADR-150**: owner_os coordination hub (2026-08-04)
- **ADR-154**: platform.workforce_memory hub (2026-08-03)
- **ADR-158/161**: memory_governance (do-not-remember + audit, 2026-08-05)
- **ADR-177**: marketing.gsc_rankings (2026-08-11)
- **ADR-009**: COMBO product gate (2026)

ADR template: context → options → decision → consequences. New ADRs required for: new external integration, schema change > 1 table, RBAC change, feature flag add/remove.

---

## Performance budgets

| Path | p50 | p95 | p99 | SLA breach = P2 |
|---|---|---|---|---|
| `/api/dashboard/*` | < 200ms | < 800ms | < 1.5s | > 2s |
| `/api/voice/*` | < 100ms | < 400ms | < 800ms | > 1s (call quality risk) |
| `/api/admin/*` | < 500ms | < 1.5s | < 3s | > 4s |
| Webhook handlers | < 50ms | < 200ms | < 500ms | > 1s (replay risk) |
| Worker task dispatch | < 1s | < 5s | < 30s | > 60s (queue depth risk) |

Enforced via Grafana SLO board (CC-004). Breach auto-pages Sumit.

---

## Capacity targets (M9 end)

| Metric | Target | Buffer |
|---|---|---|
| Active tenants | 50 | 100 (auto-scale pre-empt at 70%) |
| Daily voice calls | 500 | 1000 |
| Daily WhatsApp messages | 5000 | 10000 |
| Daily LLM API calls | 20000 | 50000 |
| Daily UPI transactions | 100 | 500 |
| Storage (Postgres) | 50 GB | 100 GB |
| Storage (JSONL) | 20 GB | 50 GB |
| Storage (Qdrant) | 5 GB | 10 GB |
| Bandwidth | 1 TB / mo | 3 TB / mo |

Capacity review at end of S4; pre-emptive upgrade if approaching target.