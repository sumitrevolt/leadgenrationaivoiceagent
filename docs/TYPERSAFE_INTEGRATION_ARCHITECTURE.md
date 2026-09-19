# TypeSafe Integration Architecture — Decision-to-Output Chain

**Date**: 2026-09-19  
**Status**: Proposed (awaiting API key rotation)  
**Owner**: Sumit (Owner)

---

## Executive Summary

TypeSafe JEv is currently **INERT** (no API key) and only used in `agent_talent_pool.py` for creating 992 specialized talents from 31 base agents. This document proposes extending TypeSafe to a **decision→output→validation→execution** chain across all automation workflows.

---

## Current State

### TypeSafe Consumers (Audited)

| File | Usage | Status |
|------|-------|--------|
| `app/platform/typesafe_integration.py` | Core client + helpers | ✅ Ready |
| `app/platform/agent_talent_pool.py` | 992 talent specializations | ⚠️ INERT (no key) |
| `app/agents/skills.py` | Skill registry (no TypeSafe calls) | ⚠️ Unused |
| `app/agents/workers.py` | Worker orchestration (no TypeSafe calls) | ⚠️ Unused |

### Current Flow

```
Agent Talent Pool
├── 31 base agents (STAFF)
├── 32 specializations per agent
└── TypeSafe decides: "What should {role} specialize in at level {index}?"
    └── Result: specialization name + confidence score
```

**Problem**: TypeSafe only creates static talent definitions, not dynamic decisions for live workflows.

---

## Proposed Architecture

### 5-Layer Decision-to-Output Chain

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1: EVIDENCE (Live Data)                                   │
│   CRM, leads, customers, campaigns, GitHub, production metrics  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 2: TYPEsafe JEv (Intelligent Decisions)                   │
│   Lead classification, next action, content strategy,           │
│   risk detection, model routing, output validation              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3: OmniRoute + Agents (Output Generation)                 │
│   Emails, creatives, videos, code, WhatsApp, reports,           │
│   Swara responses, automations                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4: QUALITY GATES (TypeSafe + Deterministic Checks)        │
│   Accuracy, relevance, completeness, brand compliance,          │
│   customer data isolation, approval requirements                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 5: EXECUTION + FEEDBACK (Business Results)                │
│   Approved delivery, permitted publishing, CRM updates,         │
│   replies, bookings, collections, customer feedback             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### 1. Sales/Email Automation

**Current**: Generative model creates emails → manual send  
**Proposed**:

```python
# Decision (TypeSafe)
decision = typesafe_choice(
    "What is the optimal email strategy for this lead?",
    state={
        "lead_intent": lead.intent_score,
        "customer_context": lead.company_size,
        "previous_interactions": lead.history,
        "campaign_goal": "demo_booking"
    },
    criteria={
        "0": "Direct demo pitch",
        "1": "Value-first educational email",
        "2": "Social proof + case study",
        "3": "Urgency/scarcity approach",
        "4": "Personalized problem-solution"
    }
)

# Generation (Generative model)
email = generate_email(
    strategy=decision.value,
    lead_context=lead,
    tone="professional_friendly"
)

# Validation (TypeSafe + deterministic)
validation = typesafe_score(
    "How relevant is this email to the lead?",
    state={"email": email, "lead": lead},
    criteria=["not_relevant", "somewhat_relevant", "highly_relevant"]
)

if validation.value == "highly_relevant" and validation.confidence > 0.7:
    send_email(email, lead)
    log_execution(lead.id, "email_sent", decision.value, validation.confidence)
else:
    trigger_revision(email, lead, validation.value)
```

### 2. Swara Voice Agent

**Current**: Voice LLM generates responses → direct reply  
**Proposed**:

```python
# Decision (TypeSafe)
intent = typesafe_choice(
    "What is the caller's primary intent?",
    state={
        "transcript": conversation_history,
        "caller_context": caller_profile,
        "call_purpose": "lead_qualification"
    },
    criteria={
        "0": "Information seeking",
        "1": "Price inquiry",
        "2": "Demo request",
        "3": "Objection handling",
        "4": "Already qualified"
    }
)

# Generation (Voice LLM)
response = voice_llm.generate(
    intent=intent.value,
    context=conversation_history,
    style="concise_hinglish"
)

# Validation (TypeSafe)
quality = typesafe_score(
    "Is this response grounded in customer data?",
    state={"response": response, "customer_data": customer_profile},
    criteria=["not_grounded", "partially_grounded", "fully_grounded"]
)

if quality.value == "fully_grounded" and quality.confidence > 0.8:
    speak(response)
    log_call_outcome(caller.id, intent.value, quality.confidence)
else:
    fallback_to_knowledge_base()
```

### 3. Content/Video Generation

**Current**: Manual creation or basic automation  
**Proposed**:

```python
# Decision (TypeSafe)
content_type = typesafe_choice(
    "What content format best serves this audience?",
    state={
        "audience_segment": audience,
        "campaign_goal": "brand_awareness",
        "platform": "whatsapp"
    },
    criteria={
        "0": "Short video (15-30s)",
        "1": "Image carousel",
        "2": "Single image + text",
        "3": "Voice note",
        "4": "Document/PDF"
    }
)

# Generation (Creative pipeline)
asset = generate_content(
    format=content_type.value,
    audience=audience,
    brand_assets=brand Guidelines
)

# Validation (TypeSafe + deterministic)
brand_check = check_brand_compliance(asset)
quality_score = typesafe_score(
    "How well does this content align with brand guidelines?",
    state={"asset": asset, "guidelines": brand_standards},
    criteria=["non_compliant", "partially_compliant", "fully_compliant"]
)

if brand_check.passed and quality_score.value == "fully_compliant":
    publish(asset, platform="whatsapp")
else:
    route_for_human_review(asset)
```

### 4. Bug/Task Classification (GitHub Automation)

**Current**: Manual triage or basic ML  
**Proposed**:

```python
# Decision (TypeSafe)
classification = typesafe_choice(
    "How critical is this bug and what routing is optimal?",
    state={
        "bug_description": issue.body,
        "affected_modules": affected_files,
        "customer_impact": impact_score,
        "sprint_status": current_sprint
    },
    criteria={
        "0": "P0-hotfix-immediate",
        "1": "P1-critical-next-sprint",
        "2": "P2-normal-backlog",
        "3": "P3-enhancement-future",
        "4": "Documentation-only"
    }
)

# Routing (Agent assignment)
assigned_worker = route_to_worker(
    classification=classification.value,
    modules=affected_files,
    availability=worker_status
)

# Execution (Agent fixes bug)
fix = assigned_worker.implement(
    issue=issue,
    classification=classification,
    constraints=blocking_gates
)

# Validation (Tests + TypeSafe)
test_result = run_targeted_tests(fix)
quality = typesafe_score(
    "Does this fix address the root cause without side effects?",
    state={"fix": fix, "original_bug": issue},
    criteria=["incomplete", "partial", "complete"]
)

if test_result.passed and quality.value == "complete":
    merge(fix)
    close_issue(issue, fix)
else:
    send_for_review(fix, quality.value)
```

---

## Implementation Priorities

### P0 (Immediate — After Key Rotation)

1. **Enable TypeSafe in production**
   ```bash
   # On VPS
   echo 'TYPESAFE_API_KEY=new_key_here' >> /opt/leadgen/.env
   docker compose -f docker-compose.vps.yml restart leadgen_app
   ```

2. **Smoke test integration**
   ```bash
   docker exec leadgen_app python -c "
   from app.platform.typesafe_integration import get_typesafe_client
   client = get_typesafe_client()
   resp = client.initialize()
   print(f'Enabled: {client.enabled}')
   print(f'Initialized: {resp.success}')
   "
   ```

3. **Add execution tracking**
   - Log every TypeSafe decision (input, output, confidence)
   - Link decisions to worker tasks and generated artifacts
   - Track execution outcomes (sent, booked, collected)

### P1 (Week 1)

4. **Integrate with email automation**
   - Add `typesafe_choice` before email generation
   - Add `typesafe_score` after generation for validation
   - Log decision→generation→validation→execution chain

5. **Add output quality gates**
   - Deterministic checks (no fake claims, brand compliance)
   - TypeSafe confidence scoring
   - Bounded retry loop for low-confidence outputs

### P2 (Week 2+)

6. **Extend to Swara voice agent**
   - Intent classification before response generation
   - Groundedness validation after response
   - Call outcome tracking

7. **Build dashboard**
   - Decision→output→result chain visualization
   - Confidence distribution over time
   - Execution success rate by workflow

---

## Key Metrics to Track

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Decision coverage** | >80% of automations use TypeSafe | % of workflows with JEv decision point |
| **Output quality** | >70% high-confidence approvals | % of generated outputs passing validation |
| **Execution rate** | >90% approved outputs executed | % of validated outputs sent/published |
| **Business outcome** | Track revenue/bookings per workflow | CRM integration for result tracking |
| **Cost efficiency** | <₰0.01 per decision | Token usage × pricing |

---

## Security Considerations

1. **API key rotation**: Current key shared in chat → **ROTATE IMMEDIATELY**
2. **Key storage**: Only in `/opt/leadgen/.env` (gitignored)
3. **No key in logs**: TypeSafe integration already filters keys
4. **Bounded usage**: 68K tokens/week = ~₰X cost (verify with new pricing)

---

## Next Steps

1. **Owner rotates TypeSafe API key** (console.typesafe.ai → API Keys → Regenerate)
2. **Set new key in production** (`/opt/leadgen/.env`)
3. **Verify integration** (smoke test above)
4. **Start P0 implementation** (execution tracking + email automation)

---

**Status**: Awaiting API key rotation  
**Canary**: 🐦 pelican
