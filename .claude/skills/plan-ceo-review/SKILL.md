# Skill: plan-ceo-review
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- Bada feature ya product direction decide karna hai
- "CEO review chahiye"
- Scope challenge chahiye
- `/office-hours` ke baad, `/plan-eng-review` se pehle

---

## Step 0: Mode Select karo

Pehle poochho user se: **"Ab hum kahan hain?"**

| Mode | Context | Approach |
|------|---------|----------|
| **EXPANSION** | Product-market fit mil gayi, grow karna hai | Scope bado, resources add karo |
| **SELECTIVE** | Kuch working, kuch nahi | Kill weak bets, double down on strong |
| **HOLD** | Revenue pressure, consolidate karo | Feature freeze, tech debt, reliability |
| **REDUCTION** | Survival mode | Cut everything non-essential |

**Current reality check (run karo):**
```bash
# Live stats
python -c "
from app.platform.clients_store import get_all_clients
from app.platform.prospects_store import ProspectStore
import asyncio
# Check pipeline
print('Check admin dashboard for real numbers')
"
# Simpler: check CLAUDE.md for pipeline stats
grep -E "prospects|clients|MRR|revenue" CLAUDE.md | tail -10
```

---

## Step 1: 10-Star Product Challenge

Gstack's CEO question: **"What would 10/10 be?"**

Current product score karo (1-10) on:
1. **Speed to first value** — Client signup se pehla result kitni der mein?
2. **Revenue per client** — Kya current pricing right hai?
3. **Automation depth** — Kitna hands-off hai client ke liye?
4. **India-fit** — Hinglish, UPI, WhatsApp, DLT — kitna native?
5. **Competitive differentiation** — Jo competitor nahi deta, woh kya hai?

---

## Step 2: Scope Challenge (4 questions)

Proposed feature/plan ke liye:

1. **"Agar sirf EK cheez ship kar sako is sprint mein, woh kya hogi aur kyun?"**

2. **"Kya yeh feature EXISTING clients ke liye valuable hai, ya sirf future clients attract karega?"**
   - Existing clients = immediate revenue impact
   - Future clients only = marketing bet, low priority unless funnel broken

3. **"Kya yeh 3 mahine mein ₹X more MRR laega? Kaise?"**
   - ₹0 impact features = always lowest priority

4. **"Kya yeh feature bina yeh hue launch ho sakta tha?"**
   - Agar haan → scope cut karo, MVP se shuru karo

---

## Step 3: 10-Section Review

**Har section ke liye: [✅ Strong / ⚠️ Weak / ❌ Missing]**

1. **Problem clarity** — Ek sentence mein problem?
2. **User specificity** — Named person / specific niche?
3. **Revenue path** — Direct ₹ impact kaise?
4. **MVP scope** — Smallest version defined?
5. **Anti-features** — Kya explicitly OUT of scope hai?
6. **Success metric** — Measurable in 2 weeks?
7. **Existing reuse** — Kya pehle se kuch rebuild nahi karna?
8. **Risk/blocker** — DLT, external API, user action needed?
9. **Rollback plan** — Kya gated/safe hai?
10. **Hinglish/India-fit** — Copy aur UX local hai?

---

## Step 4: Decision

```
## CEO Review Decision

Mode: [EXPANSION / SELECTIVE / HOLD / REDUCTION]

Score: [X/10]

Decision: [BUILD NOW / VALIDATE FIRST / DEFER / KILL]

Reasoning: [2-3 sentences]

Approved scope:
- [Feature A — include]
- [Feature B — include]
- [Feature C — CUT, reason]

Next step: /plan-eng-review se architecture review karo
```
