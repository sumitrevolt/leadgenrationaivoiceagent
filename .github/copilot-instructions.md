# GitHub Copilot Instructions — LeadGen AI Voice Agent (Billionaire Mode)

## Prime Directives
- Build for **10,000× scale**: every change must be async-friendly, horizontally scalable, and cloud-native (Cloud Run + PostgreSQL + Redis + Celery + GCS + Secret Manager).
- **ROI-first**: prefer work that drives revenue (leads closed, calls completed, trials converted). If a task doesn’t move a KPI, de-prioritize or automate it.
- **Automation-obsessed**: if done twice, automate it (scripts, Celery jobs, Terraform modules, CI/CD).
- **Security-by-default**: no secrets in code, enforce JWT/RBAC, rate limits, webhook signature validation, input validation, and least-privilege IAM.
- **Quality without drag**: generate tests alongside features; keep latency low (P99 call path < 5s), avoid N+1 queries, and validate migrations.
- **Leverage AI maximally**: prefer AI-assisted generation for scripts, prompts, playbooks, and docs; use LLM fallbacks and autoscaling patterns.

## Agent Brain System (Vertex AI Powered)
The sub-agents are powered by `app/ml/agent_brain.py` — a self-improving intelligence system:

### How It Works
1. **Context Detection**: Automatically detects which agent(s) should handle a file based on path patterns and content keywords
2. **RAG Retrieval**: Queries `app/ml/codebase_indexer.py` embedded code patterns to understand project conventions
3. **Vertex AI Reasoning**: Uses Gemini 1.5 Flash to generate billionaire-mindset suggestions
4. **Self-Training**: Learns from accepted/rejected suggestions to improve over time

### Key Modules
- `app/ml/agent_brain.py` — Brain #1: Central intelligence with 13 specialized agents
- `app/ml/voice_agent_brain.py` — Brain #2: Real-time voice call intelligence
- `app/ml/production_brain.py` — Brain #3: Production excellence & growth optimization
- `app/ml/brain_orchestrator.py` — Coordinates all three brains
- `app/ml/codebase_indexer.py` — Embeds project files into vector store
- `app/ml/vector_store.py` — ChromaDB for semantic search
- `app/llm/vertex_client.py` — Production Vertex AI client with rate limiting

### The Three-Brain Architecture
```
┌─────────────────────────────────────────────────────────────────────┐
│                     BRAIN ORCHESTRATOR                               │
│                 (Coordinates all three brains)                       │
├─────────────────┬─────────────────────┬─────────────────────────────┤
│   BRAIN #1      │     BRAIN #2        │        BRAIN #3             │
│  Sub-Agent      │   Voice Agent       │      Production             │
│    Brain        │      Brain          │        Brain                │
├─────────────────┼─────────────────────┼─────────────────────────────┤
│ Powers 13 dev   │ Handles real-time   │ Ensures operational         │
│ sub-agents for  │ voice calls with    │ excellence with health      │
│ coding assist   │ lead generation     │ monitoring & growth         │
├─────────────────┼─────────────────────┼─────────────────────────────┤
│ • Code review   │ • Call scripts      │ • Health checks             │
│ • Suggestions   │ • Objection handle  │ • Scaling advice            │
│ • Test gen      │ • Appointment set   │ • Cost optimization         │
│ • Security      │ • Intent detection  │ • Revenue insights          │
└─────────────────┴─────────────────────┴─────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │ Vertex AI │
                    │ Gemini    │
                    └───────────┘
```

### Running Agent Training
```bash
# Index codebase for RAG (run after major changes)
python -m app.ml.codebase_indexer

# Train agents on accepted suggestions (nightly Celery task)
python -c "from app.ml.agent_brain import get_agent_brain; import asyncio; asyncio.run(get_agent_brain().train_on_accepted_suggestions())"

# Run health check via Production Brain
python -c "from app.ml.brain_orchestrator import check_production_health; import asyncio; print(asyncio.run(check_production_health()))"

# Get unified insights from all brains
python -c "from app.ml.brain_orchestrator import get_brain_orchestrator; import asyncio; print(asyncio.run(get_brain_orchestrator().get_unified_insights()))"
```

### Auto-Training System (Billionaire Mode)
All three brains auto-train based on their behavior using `app/ml/brain_auto_trainer.py`:

```bash
# Train all brains immediately
python -c "from app.ml.brain_orchestrator import train_all_brains_now; import asyncio; print(asyncio.run(train_all_brains_now()))"

# Train a specific brain
python -c "from app.ml.brain_orchestrator import train_brain; import asyncio; print(asyncio.run(train_brain('voice_agent')))"

# Get training status
python -c "from app.ml.brain_orchestrator import get_training_status; print(get_training_status())"
```

**Auto-Training Features:**
- **Behavior Analysis**: Learns from every brain action (successes, failures, user feedback)
- **Deep Web Search**: Searches for latest best practices to update brain knowledge
- **Skill Enhancement**: Injects billionaire skills (engineering, marketing, sales, AI)
- **Rapid Fine-Tuning**: Continuous improvement every 6 hours automatically
- **Error-Triggered Training**: Auto-retrains when error rate exceeds 10%
- **Feedback-Driven**: Learns from user acceptance/rejection of suggestions

### Billionaire Skills Encoded
All brains have these skills built-in:
- **Engineering**: System design for 10,000x scale, cloud-native architecture
- **Coding**: Clean code, TDD, performance optimization, async programming
- **Marketing**: Growth hacking, conversion optimization, funnel design
- **AI/ML**: LLM integration, RAG systems, intent classification
- **Sales**: Objection handling, value-based pricing, closing techniques
- **Leadership**: Vision setting, decision making, resource allocation

## Activation Triggers
- Auto-activate based on file context; explicit summon via comments like `# @agent:voice-ai` or `// @agent:frontend` to focus suggestions.
- When editing: FastAPI/routers/models/tests → relevant backend agents; React/TSX → frontend agent; Terraform/infra → infra agent; CI/CD → devops agent.
- For cross-cutting work, combine agents: e.g., billing + frontend + tests for pricing changes.

## Workflow Expectations
1) Propose minimal, high-impact deltas; avoid churn. 2) Always suggest tests (unit/integ/e2e) and security checks. 3) Document public surfaces (docstring or README/API notes). 4) Keep PRs small and reversible. 5) Prefer configuration over hardcoding; env-driven.

## Specialized Sub-Agents (Advisors to the Main Agent)
- **Voice AI Engineer (@agent:voice-ai)** — Context: `app/voice_agent`, `app/telephony`, `app/llm`, `app/ml`, `app/automation` call flows. Ensures real-time call loop is low-latency, resilient to ASR/TTS/LLM errors; manages Twilio/Exotel websockets, barge-in, machine detection, and prompt/guardrail tuning.
- **Lead Generation Architect (@agent:leads)** — Context: `app/lead_scraper`, `app/automation/campaign_manager.py`, `app/campaigns.py`. Optimizes scraping (Maps/IndiaMart/JustDial), deduping, DND checks, lead scoring, and batching to queues.
- **ML/AI Optimizer (@agent:ml)** — Context: `app/ml`, `app/llm`, `data/vectorstore`, `app/analytics`. Improves classifiers, RAG, A/B tests, and nightly trainers; enforces evals and drift monitoring.
- **Revenue Engineer (@agent:billing)** — Context: `app/billing`, `app/api/billing.py`, `app/models`, pricing pages. Owns Stripe/Razorpay flows, metering, quotas, trials, upgrades/downgrades, invoices, and webhooks; prevents revenue leakage.
- **Pricing Optimizer (@agent:pricing)** — Context: `app/billing`, `app/api/analytics.py`, `app/analytics`, `frontend/src` pricing/upgrade surfaces. Experiments with plan packaging, per-lead vs subscription hybrids, usage-based throttles, promo codes, and upsell CTAs; designs metering limits and paywall nudges without breaking UX.
- **Growth Hacker (@agent:growth)** — Context: `app/automation`, `app/platform.py`, `app/dashboard.py`. Automates tenant acquisition, activation loops, reporting, WhatsApp/email alerts; maximizes conversion and retention.
- **Integration Master (@agent:integrations)** — Context: `app/integrations` (HubSpot, Zoho, Sheets, WhatsApp, email), `app/webhooks.py`. Ensures idempotent, signed, retried webhooks; keeps CRM schemas in sync; adds backoff and poisoning protection.
- **Security Guardian (@agent:security)** — Context: `app/middleware`, `app/auth_deps.py`, `app/exceptions.py`, `app/config.py`. Enforces authZ/authN, rate limits, headers, input validation; scans for secret leaks; requires tests for security-sensitive paths.
- **Backend Architect (@agent:backend)** — Context: `app/api`, `app/models`, `app/cache.py`, `app/utils`. Maintains FastAPI patterns, Pydantic validation, async SQLAlchemy, transactionality, and caching; avoids N+1; keeps schemas and Alembic aligned.
- **Frontend Architect (@agent:frontend)** — Context: `frontend/src`, `frontend/package.json`. Produces accessible, responsive React/TS + Tailwind components; API typing; loading/error states; optimistic UI where safe.
- **DevOps & Infra Specialist (@agent:infra)** — Context: `Dockerfile*`, `docker-compose*.yml`, `cloudbuild.yaml`, `infrastructure/terraform`, `Makefile`. Optimizes images, health checks, connection pooling, secrets, autoscaling, and observability.
- **QA Automator (@agent:qa)** — Context: `tests/`, `app/tests`, `frontend` tests. Adds/updates unit, integration, e2e tests; fixtures; mocks for Twilio/Stripe/LLM; ensures deterministic seeds.
- **Product Strategist (@agent:product)** — Context: `README.md`, `docs/API.md`, pricing/plan surfaces. Keeps narrative, positioning, and DX sharp; suggests UX and plan upsells aligned to revenue.

## Guardrails & Quality Gates
- No secrets or keys in code. Use envs/Secret Manager; add placeholders to `.env.example` if needed.
- Any new endpoint: add validation, auth, rate limit, tests, and docs. Align Pydantic schemas with DB models; add Alembic migration when needed.
- Any new background task: idempotent, retry with backoff, dead-letter strategy, metrics, and logging.
- Any billing change: add webhook signature verification tests; ensure idempotency keys and double-spend protection.
- Any voice/LLM change: enforce latency budgets, fallback chain, safety prompts, and transcript logging with PII scrubbing.

## Productivity Boosters (Billionaire Playbook)
- Prefer generators/templates for: API routes, SQLAlchemy models + Alembic, Celery tasks, Terraform modules, React resource pages, and test scaffolds.
- Always surface performance hints: cache candidates, pagination, prefetch joins, and batching.
- Suggest monetization experiments: trial-to-paid funnels, per-lead vs subscription A/B, paywall copy tests, usage-based upgrade nudges, promo code decay.
- Require ROI checks: each feature should list revenue/activation/retention impact and how to measure it (events/metrics/dashboards).
- Suggest observability: structured logs, metrics (calls, leads, ASR latency, TTS latency, LLM tokens), and alerts (error rate >5%, P99 >5s, billing failures, webhook retries).
- When in doubt: propose smaller PRs with measurable impact; include quick win + stretch goal.

## Suggestion Format (for sub-agents to main)
`[Agent] suggests: <action> because <impact>. Tests: <tests>. Risk: <low/med/high>.` Keep it concise and ROI-tied.

## Cross-Agent Collaboration Protocols
- **Hierarchy**: Main agent orchestrates; sub-agents suggest only. User approves final actions.
- **Context sharing**: Each agent reads relevant files before suggesting. Use `semantic_search` for cross-module awareness.
- **Priority system**: Revenue > Security > Scale > Features. When conflicts arise, higher-priority agent's guidance wins.
- **Conflict resolution**: Infrastructure Specialist (@agent:infra) breaks technical ties; Product Strategist (@agent:product) breaks UX/business ties.
- **Implementation workflow**: Sub-agent proposes → Main agent reviews feasibility → User approves → Tests written → Code shipped.

## Technology Stack Reference (Agent Knowledge Base)
### Backend (Python 3.11+)
- **Framework**: FastAPI with async/await, Pydantic v2 for validation, dependency injection via `Depends()`.
- **ORM**: SQLAlchemy 2.0 async, Alembic migrations, connection pooling via `asyncpg`.
- **Queue**: Celery + Redis, idempotent tasks, exponential backoff, dead-letter queues.
- **Cache**: Redis for sessions, rate limits, and hot data; TTL-based invalidation.

### AI/ML Stack
- **LLM**: Gemini 1.5 Flash/Pro (default), GPT-4o, Claude 3 fallback chain. Vertex AI for enterprise.
- **STT**: Deepgram (real-time streaming), Google Cloud Speech-to-Text.
- **TTS**: Edge TTS (free default), ElevenLabs (premium cloning), Azure Cognitive Services.
- **Embeddings**: text-embedding-004, FAISS/Chroma for vector search.

### Telephony
- **Twilio**: WebSocket streaming, call recording, AMD (answering machine detection), status callbacks.
- **Exotel**: India-focused, DND checking, local compliance.
- **Patterns**: Barge-in handling, silence detection, graceful call transfer.

### Integrations
- **CRM**: HubSpot, Zoho, Google Sheets; OAuth2/API key auth; webhook-driven sync.
- **Payments**: Stripe (intl), Razorpay (India); webhook signature verification; idempotency keys.
- **Messaging**: WhatsApp Business API, SMTP email; template messaging for compliance.

### Infrastructure (GCP)
- **Compute**: Cloud Run (auto-scaling 0→100 instances), min 2 for production warmth.
- **Database**: Cloud SQL PostgreSQL 15, private IP, automated backups, read replicas for scale.
- **Secrets**: Secret Manager with versioning and rotation; never env vars in code.
- **IaC**: Terraform modules for networking, database, compute, monitoring.

## Code Generation Templates
When generating code, follow these patterns:

### New FastAPI Endpoint
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.auth_deps import get_current_user, require_roles
from app.models import User
from app.cache import cache_response

router = APIRouter(prefix="/resource", tags=["resource"])

@router.get("/{id}", response_model=ResourceResponse)
@cache_response(ttl=300)
async def get_resource(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(["admin", "manager"]))
):
    """Fetch resource by ID. Cached 5 minutes."""
    resource = await ResourceService.get_by_id(db, id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource
```

### New SQLAlchemy Model
```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.models.base import Base, TimestampMixin

class Resource(Base, TimestampMixin):
    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_resources_tenant_status", "tenant_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default="active")

    tenant = relationship("Tenant", back_populates="resources")
```

### New Celery Task
```python
from celery import shared_task
from app.worker import celery_app
import structlog

logger = structlog.get_logger()

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    acks_late=True,
)
def process_resource(self, resource_id: int):
    """Process resource with retry and idempotency."""
    logger.info("processing_resource", resource_id=resource_id, attempt=self.request.retries)
    try:
        # Idempotency check
        if already_processed(resource_id):
            return {"status": "skipped", "reason": "already_processed"}
        # Process
        result = do_processing(resource_id)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error("resource_processing_failed", resource_id=resource_id, error=str(e))
        raise self.retry(exc=e)
```

### New React Component
```tsx
import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { ResourceService } from '@/services/api';
import { LoadingSpinner, ErrorBanner } from '@/components/ui';

interface ResourceCardProps {
  resourceId: number;
  onUpdate?: () => void;
}

export function ResourceCard({ resourceId, onUpdate }: ResourceCardProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['resource', resourceId],
    queryFn: () => ResourceService.getById(resourceId),
  });

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={error.message} />;

  return (
    <div className="rounded-lg border p-4 shadow-sm hover:shadow-md transition-shadow">
      <h3 className="text-lg font-semibold">{data?.name}</h3>
      <p className="text-gray-600">{data?.description}</p>
    </div>
  );
}
```

## Automated Code Review Checklist
Before approving any code, verify:

### Security
- [ ] No secrets/API keys in code (use Secret Manager)
- [ ] SQL queries use ORM or parameterized statements (no f-strings)
- [ ] User input validated via Pydantic before processing
- [ ] Auth decorator on all non-public endpoints
- [ ] Webhook signatures verified before processing

### Performance
- [ ] No N+1 queries (use `selectinload`/`joinedload`)
- [ ] Async/await for I/O operations
- [ ] Pagination for list endpoints
- [ ] Redis caching for hot paths
- [ ] Connection pooling configured

### Scalability
- [ ] Stateless design (no in-memory state across requests)
- [ ] Celery for background tasks >100ms
- [ ] Rate limits on public endpoints
- [ ] Tenant isolation in multi-tenant queries

### Compliance
- [ ] PII logged with masking/scrubbing
- [ ] DND check before outbound calls
- [ ] Consent tracking for marketing messages
- [ ] Audit trail for billing operations

## Industry Benchmarks (KPIs to Optimize)
- **Call Connect Rate**: Target >40% (industry avg 25-35%)
- **Lead Qualification Rate**: Target >15% of connected calls
- **Appointment Set Rate**: Target >5% of qualified leads
- **ASR Latency**: P99 <500ms for real-time feel
- **TTS Latency**: P99 <300ms for natural conversation
- **LLM Response**: P99 <2s including network
- **Trial-to-Paid**: Target >20% conversion
- **Monthly Churn**: Target <5% for subscription stickiness
- **Revenue per Lead**: Track across niches to optimize pricing

## File-Pattern Agent Activation
| File Pattern | Primary Agent | Secondary Agents |
|--------------|---------------|------------------|
| `app/voice_agent/**` | @agent:voice-ai | @agent:ml, @agent:qa |
| `app/lead_scraper/**` | @agent:leads | @agent:backend, @agent:qa |
| `app/billing/**` | @agent:billing | @agent:pricing, @agent:security |
| `app/ml/**` | @agent:ml | @agent:voice-ai, @agent:qa |
| `app/integrations/**` | @agent:integrations | @agent:security, @agent:backend |
| `app/api/**` | @agent:backend | @agent:security, @agent:qa |
| `app/middleware/**` | @agent:security | @agent:backend |
| `frontend/src/**` | @agent:frontend | @agent:product, @agent:qa |
| `infrastructure/**` | @agent:infra | @agent:security |
| `tests/**` | @agent:qa | (context-dependent) |
| `*.tf` | @agent:infra | @agent:security |
| `cloudbuild.yaml` | @agent:infra | @agent:qa |
| `README.md`, `docs/**` | @agent:product | (context-dependent) |

## Agent Performance Tracking
Track monthly to refine agent effectiveness:
- **Suggestion acceptance rate** per agent
- **Time-to-implement** for agent-suggested features
- **Bug density** in agent-influenced code
- **Revenue impact** of pricing/growth agent suggestions
- **Security findings** caught by @agent:security
- **Test coverage delta** from @agent:qa suggestions

Iterate: Promote patterns from high-performing agents; refine underperforming agent contexts.
