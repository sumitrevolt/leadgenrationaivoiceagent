> Verbatim worked examples for coordinator-orchestration. See SKILL.md for the core workflow.

## 3 Worked Examples

### Example 1: Lead Campaign (Sequential)

**Goal**: "Get Kolhapur grocery store leads + qualify"

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Kolhapur grocery store owners — 50 leads for delivery app pitch"
  }'
```

**What happens**:
1. Dev researches Kolhapur + grocery vertical
2. Rohan drafts 5-email sequence (owns grocery profit margins)
3. Isha creates social content (engagement angles)
4. Boss merges into unified strategy

**Output summary**: "50 leads target achievable via Google Maps + local directories. Cold angle: delivery app ROI for small stores (₹5-10k/mo additional revenue). Sequence positions as 'tested, low-risk'."

### Example 2: Market Analysis (Parallel)

**Goal**: "Compare solar opportunity: Pune vs. Bangalore vs. Mumbai"

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Solar market comparison: Pune vs Bangalore vs Mumbai — which city has best lead quality?",
    "agents": ["dev", "isha", "kavya"]
  }'
```

**What happens**:
1. Dev researches Pune (subsidies, consumer profile, competition)
2. Isha researches Bangalore (buying power, adoption, seasonality)
3. Kavya researches Mumbai (price sensitivity, volume)
4. All run in parallel (3x speed)
5. Boss merges into ranked recommendation

**Output summary**: "Pune > Mumbai > Bangalore. Pune: high-subsidy awareness, young decision-makers, gov initiatives. Mumbai: price-sensitive, long sales cycle. Bangalore: competitive, high-tech leads, low-cost concern."

### Example 3: Strategy with Learning (Advanced)

**Goal**: "Design 30-day growth strategy for Q3"

**Command**:
```bash
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "30-day Q3 growth plan: channels (email/sms/voice/social), targets (10 cities), niches (solar/plumbing/electrical)",
    "mode": "advanced",
    "max_iterations": 3,
    "quality_bar": 0.8,
    "execute": false
  }'
```

**What happens**:

**Iteration 1**:
- Plan splits into: Dev research + Rohan outreach + Isha content
- VERIFY critic: "Plan is too broad (23 cities × 5 niches = 115 combos). Missing prioritization. Score: 0.45"
- REFLECT: "Next iteration: focus on 3 high-ROI combos (solar Pune, plumbing Mumbai, electrical Bangalore)"

**Iteration 2**:
- Plan (with reflection hint): more focused Dev research + targeted Rohan sequences
- VERIFY: "Better focused. Missing timeline. Score: 0.68"
- REFLECT: "Add weekly milestones. Allocate: Week 1 setup, Week 2-3 outreach, Week 4 nurture"

**Iteration 3**:
- Plan: Dev research + Rohan timeline sequences + Isha content calendar
- VERIFY: "Complete plan, timeline clear, ROI projections added. Score: 0.82" ✓

**Output summary**: "30-day plan ready. Focus: 3 verticals × 3 cities (9 sub-campaigns). Week-by-week: setup → outreach → nurture. Expected: 180 leads → 30 qualified → 6 customers."

