> Verbatim worked decision scenarios: 5 concrete goals mapped to the right loop, with setup commands. See SKILL.md for the decision tree.

## 5 Decision Scenarios

### Scenario 1: "Scrape Pune daily for 30 days"

**Analysis**:
- Daily recurring? ✓ YES
- Now-goal? No
- Workflow with gates? No
- → **Use SELF-IMPROVE LOOP**

**Setup**:
```bash
# Enable loop (runs daily)
SELF_IMPROVE_LOOP=1

# Self-improve picks "prospector.scrape" action daily
# Monitor: python scripts/selfimprove_audit.py --last-run
```

---

### Scenario 2: "I need a cold-email strategy for Pune solar TODAY"

**Analysis**:
- Daily recurring? No
- Now-goal? ✓ YES (need it today)
- Workflow with gates? No
- → **Use COORDINATOR** (sequential or advanced)

**Execution**:
```bash
# Draft (safe)
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Pune solar cold-email strategy: 5 emails, subsidy angle"
  }'

# Review output, iterate if needed, then manually send
```

---

### Scenario 3: "Auto-generate and send blog posts weekly (with approval)"

**Analysis**:
- Daily recurring? Weekly (not daily, but repeating)
- Now-goal? No
- Workflow with gates? ✓ YES (generate → **APPROVE** → publish)
- → **Use PROCESS-ENGINE**

**Setup**:
```bash
# Define workflow: content.generate → BREAKPOINT (human review) → publish
# Run weekly via scheduler
curl -X POST http://localhost:8000/api/growth/process/start \
  -d '{"process_id": "weekly_blog"}'

# At breakpoint: human reviews, approves
curl -X POST http://localhost:8000/api/growth/process/run/{id}/approve
```

---

### Scenario 4: "Design 30-day growth strategy + learn from outcomes"

**Analysis**:
- Daily recurring? No
- Now-goal? ✓ YES (need strategy now)
- Workflow with gates? No (but needs quality + learning)
- → **Use COORDINATOR ADVANCED MODE**

**Execution**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate-advanced \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "30-day Q3 growth plan: channels, cities, niches",
    "quality_bar": 0.8,
    "max_iterations": 3
  }'
# Loop runs 1-3 iterations until 0.8 score, learns from reflection
```

---

### Scenario 5: "Real-time customer chat support"

**Analysis**:
- Daily recurring? Yes (ongoing support)
- Now-goal? ✓ YES (customer waiting)
- Workflow with gates? No (real-time)
- → **Use CHATBOT** (human agent + AI co-pilot)

**Execution**:
- Customer opens chat
- AI suggests responses (context from KB + conversation)
- Human reviews + modifies
- Human sends (or AI auto-sends if confidence high)
