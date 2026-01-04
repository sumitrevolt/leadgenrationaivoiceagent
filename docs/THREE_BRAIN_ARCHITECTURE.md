# Three-Brain Architecture

## Overview

AuraLeads uses a **Three-Brain Architecture** powered by **Vertex AI (Gemini)** to create a self-improving, billionaire-mindset AI system. Each brain serves a distinct purpose and works together through the Brain Orchestrator.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     BRAIN ORCHESTRATOR                               │
│                 (app/ml/brain_orchestrator.py)                       │
├─────────────────┬─────────────────────┬─────────────────────────────┤
│   BRAIN #1      │     BRAIN #2        │        BRAIN #3             │
│  Sub-Agent      │   Voice Agent       │      Production             │
│    Brain        │      Brain          │        Brain                │
├─────────────────┼─────────────────────┼─────────────────────────────┤
│ agent_brain.py  │ voice_agent_brain.py│   production_brain.py       │
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

---

## Brain #1: Sub-Agent Brain

**File:** `app/ml/agent_brain.py`

**Purpose:** Powers 13 specialized development sub-agents that assist with coding.

### 13 Sub-Agents

| Agent | Context | Responsibilities |
|-------|---------|------------------|
| `@agent:voice-ai` | `app/voice_agent`, `app/telephony` | Call flows, ASR/TTS, barge-in |
| `@agent:leads` | `app/lead_scraper`, `app/automation` | Scraping, deduping, DND checks |
| `@agent:ml` | `app/ml`, `app/llm` | Models, RAG, A/B tests, training |
| `@agent:billing` | `app/billing` | Stripe/Razorpay, metering, invoices |
| `@agent:pricing` | `app/billing`, pricing pages | Plan packaging, upsells, trials |
| `@agent:growth` | `app/automation` | Activation loops, conversion |
| `@agent:integrations` | `app/integrations` | HubSpot, Zoho, webhooks |
| `@agent:security` | `app/middleware`, `app/auth_deps.py` | Auth, rate limits, validation |
| `@agent:backend` | `app/api`, `app/models` | FastAPI, SQLAlchemy, caching |
| `@agent:frontend` | `frontend/src` | React/TS, Tailwind, API typing |
| `@agent:infra` | `infrastructure/terraform` | Docker, Cloud Run, Terraform |
| `@agent:qa` | `tests/` | Unit, integration, e2e tests |
| `@agent:product` | `README.md`, `docs/` | DX, positioning, plan upsells |

### Usage

```python
from app.ml import get_agent_brain

brain = get_agent_brain()

# Detect relevant agents for a file
agents = brain.detect_agent("app/billing/subscription.py", code_content)
# Returns: [AgentRole.BILLING, AgentRole.PRICING]

# Generate a suggestion
suggestion = await brain.generate_suggestion(
    file_path="app/api/leads.py",
    content=code_content,
    cursor_position=150,
)
print(suggestion.suggestion)
```

### Self-Training

The brain learns from accepted/rejected suggestions:

```python
await brain.train_on_accepted_suggestions()
```

---

## Brain #2: Voice Agent Brain

**File:** `app/ml/voice_agent_brain.py`

**Purpose:** Handles real-time AI voice calls for lead generation.

### Features

- **Industry-Specific Scripts:** Real estate, solar, dental, insurance, general
- **13 Intent Detection Types:** Greeting, interested, objection, appointment, callback, etc.
- **Lead Temperature Scoring:** Hot, warm, cold, dead
- **Objection Handling:** Price, time, not interested, need to think, wrong person
- **Appointment Booking:** Date/time extraction and confirmation
- **RAG Integration:** Learns from successful conversations

### Call Flow

```
Start Call → Greeting → Customer Response → Intent Detection → Response Generation → Loop until appointment/end
```

### Usage

```python
from app.ml import get_voice_agent_brain

brain = get_voice_agent_brain()

# Start a call
state = await brain.start_call(
    call_id="call-123",
    lead_id="lead-456",
    lead_name="Rahul Sharma",
    lead_phone="+919876543210",
    industry="solar",
)

# Generate greeting
greeting = await brain.generate_greeting("call-123")
print(greeting.text)  # "Hi Rahul! This is Maya from AuraLeads..."

# Process customer speech
response = await brain.process_customer_speech(
    "call-123",
    "What's the price for this?"
)
print(response.text)  # Handles price objection
print(response.detected_intent)  # CallIntent.OBJECTION_PRICE

# End call
result = await brain.end_call("call-123", outcome="appointment")
```

### Industry Configurations

Each industry has custom:
- Greeting style
- Value proposition
- Common objection handles
- Appointment CTA

---

## Brain #3: Production Brain

**File:** `app/ml/production_brain.py`

**Purpose:** Ensures operational excellence, growth, and production readiness.

### Features

- **Health Monitoring:** API, Database, Redis, Celery, LLM, Telephony
- **Anomaly Detection:** Alerts for degraded/critical components
- **Scaling Recommendations:** CPU, memory, connection pool thresholds
- **Cost Optimization:** LLM token usage, infrastructure costs
- **Production Readiness:** 30+ security, reliability, scalability checks
- **Growth Insights:** AI-powered growth recommendations

### Health Checks

```python
from app.ml import get_production_brain

brain = get_production_brain()

# Run health checks
health = await brain.run_health_checks()
# Returns: {api: HEALTHY, database: HEALTHY, redis: HEALTHY, ...}

# Get production readiness score
readiness = await brain.run_production_readiness_check()
print(f"Score: {readiness['overall_score']}%")
# Returns: security, reliability, scalability, observability, deployment checks
```

### Optimization Recommendations

```python
from app.ml.production_brain import SystemMetrics

metrics = SystemMetrics(
    cpu_utilization=85,
    api_p99_latency_ms=4000,
    llm_cost_today_usd=15,
)

recommendations = await brain.analyze_metrics(metrics)
for rec in recommendations:
    print(f"[{rec.priority}] {rec.title}: {rec.action_required}")
```

### Growth Insights

```python
insights = await brain.get_growth_insights()
print(insights)
# {
#   "growth_score": 7,
#   "key_metric_to_improve": "conversion_rate",
#   "top_3_growth_actions": [...],
#   "revenue_opportunity": "2-3x MRR with optimization",
#   "bottleneck": "Lead quality"
# }
```

---

## Brain Orchestrator

**File:** `app/ml/brain_orchestrator.py`

**Purpose:** Coordinates all three brains and provides unified access.

### Usage

```python
from app.ml import get_brain_orchestrator

orchestrator = get_brain_orchestrator()

# Route request to appropriate brain automatically
response = await orchestrator.route_request("health_check", {})

# Get unified insights from all brains
insights = await orchestrator.get_unified_insights()

# Pre-deployment coordination
deploy_check = await orchestrator.coordinate_brains("pre_deployment", {})
print(deploy_check["ready_to_deploy"])  # True/False
```

### Convenience Functions

```python
from app.ml.brain_orchestrator import (
    ask_sub_agent,
    start_voice_call,
    check_production_health,
    get_growth_insights,
)

# Quick code suggestion
suggestion = await ask_sub_agent("app/api/leads.py", code)

# Quick voice call
call = await start_voice_call("call-1", "lead-1", "John Doe")

# Quick health check
health = await check_production_health()

# Quick growth insights
insights = await get_growth_insights()
```

---

## Weekly Training Schedule

All three brains are trained/checked weekly via the Training Scheduler:

```python
# Runs every Sunday at 3 AM IST
async def _run_weekly_training():
    # Brain #1: Train on accepted code suggestions
    await agent_brain.train_on_accepted_suggestions()
    
    # Brain #2: Learn from successful calls
    await voice_brain.train_on_successful_calls()
    
    # Brain #3: Production health & growth check
    await prod_brain.run_production_readiness_check()
    await prod_brain.get_growth_insights()
```

---

## File Structure

```
app/ml/
├── __init__.py              # Exports all brains
├── agent_brain.py           # Brain #1: Sub-Agent Brain
├── voice_agent_brain.py     # Brain #2: Voice Agent Brain
├── production_brain.py      # Brain #3: Production Brain
├── brain_orchestrator.py    # Orchestrator
├── codebase_indexer.py      # RAG indexer for Brain #1
├── vector_store.py          # ChromaDB for all brains
├── training_scheduler.py    # Weekly training
└── ...
```

---

## Environment Variables

```bash
# Vertex AI (required for brains)
GOOGLE_CLOUD_PROJECT=your-project-id
VERTEX_AI_LOCATION=us-central1

# Vector Store
CHROMA_DB_PATH=data/vectorstore

# Training
TRAINING_SCHEDULE_ENABLED=true
```

---

## Metrics & Observability

### Brain Health Dashboard

```python
health = await orchestrator.get_all_brain_health()
# {
#   "sub_agent": {"status": "idle", "requests_handled": 150, "avg_response_ms": 250},
#   "voice_agent": {"status": "active", "requests_handled": 500, "avg_response_ms": 180},
#   "production": {"status": "idle", "requests_handled": 50, "avg_response_ms": 100},
# }
```

### Key Metrics

| Metric | Target | Brain |
|--------|--------|-------|
| Code suggestion latency | <500ms | #1 |
| Voice response latency | <300ms | #2 |
| Appointment booking rate | >5% | #2 |
| Production readiness | >95% | #3 |
| Alert resolution time | <30min | #3 |

---

## Best Practices

1. **Always use the orchestrator** for cross-brain operations
2. **Run codebase indexer** after major code changes
3. **Monitor brain health** via dashboard data
4. **Review weekly training reports** for improvements
5. **Check production readiness** before deployments

---

## Troubleshooting

### Brain Not Responding

```python
# Check brain health
health = await orchestrator.get_all_brain_health()
print(health["sub_agent"]["status"])  # Should be "idle" or "busy"
```

### Vertex AI Errors

```bash
# Check credentials
gcloud auth application-default print-access-token

# Verify quota
gcloud compute quotas list --filter="metric:aiplatform"
```

### Vector Store Issues

```python
# Re-index codebase
from app.ml import get_codebase_indexer
indexer = get_codebase_indexer()
await indexer.index_codebase(force=True)
```

---

## Billionaire Mindset

The Three-Brain Architecture embodies billionaire principles:

- **10,000× Scale:** Each brain is designed for massive scale
- **ROI-First:** Production Brain prioritizes revenue metrics
- **Automation:** Weekly self-training without human intervention
- **Self-Improvement:** Learns from every call and code review
- **Operational Excellence:** Continuous health monitoring

> "Think like a billionaire, act like a billionaire" — The brains do exactly that.
