---
name: spec
description: Vague feature idea ko concrete, build-ready spec banao — why/user, existing-code check (duplicate-route grep), data-model + API + flag + tests + success-metric, ban-safe defaults. Use when user bole "spec likho", "is feature ka plan banao", "ye idea concrete karo", ya `plan-then-build` se pehle scope nail karna ho.
---

# Skill: spec
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
- Build karne se PEHLE
- "Spec likho is feature ke liye"
- Vague idea ko concrete plan banana
- `/plan-then-build` ke saath

---

## Phase 1: "Why" Samjho

User se poocho (ek ek karke):
1. **Kaun use karega?** — "39 builtin niches mein se kaunsa user? Client? Admin? End customer?"
2. **Ab kya karte hain?** — "Is kaam ke bina kya manually karte hain?"
3. **Success kaise dikhega?** — "Feature kaamyab hua to kya metric change hoga?"

---

## Phase 2: Existing Code CHECK (PEHLE)

```bash
# Kya route pehle se hai?
grep -n "@router\." app/api/marketing.py | grep -i "KEYWORD"
grep -rn "KEYWORD" app/ --include="*.py" | head -10

# Related modules
ls app/marketing/ app/platform/ app/billing/
```

**RULE (CLAUDE.md gotcha):** Naya feature add karne se pehle existing routes dekho — duplicate banane se pehle yeh step MANDATORY hai.

---

## Phase 3: Technical Interrogation

1. **Data model:** Kya naya DB column/table chahiye? Ya existing table mein fit hoga?
2. **API endpoints:** GET ya POST? Auth required? Rate limit?
3. **Gated hai?** — Naya flag chahiye? `FEATURE_NAME=1` default OFF pattern follow karo.
4. **Scheduler integration?** — `team_scheduler` mein job add karna hai?
5. **Side effects:** Kyun koi auto-send/auto-delete nahi karna chahiye by default? (ban-safe pattern)

---

## Phase 4: Spec Draft

```markdown
# Spec: [FEATURE NAME]
Date: YYYY-MM-DD
Author: Claude + Sumit

## Problem
[1-2 sentences: kaun, kya problem, kya consequences]

## Solution
[High-level approach — what we build, what we DON'T build]

## Scope (MVP)
- [Included: 3-5 bullet points]
- OUT OF SCOPE: [explicit exclusions]

## API Design
- `POST /api/growth/feature` (admin, rate-limited 30/60s)
- `GET /api/growth/feature` (admin)
- Request: `{param1: str, param2: int}`
- Response: `{ok: bool, result: dict}`

## Data Store
- File: `data/feature.jsonl` (OR Postgres table: `feature_table`)
- Key fields: [list]

## Env Flag
- `FEATURE_NAME=1` (default OFF, gated, never-raise)

## Tests
- `tests/test_feature.py`: [test cases list]

## Success Metric
- [What number changes when this works?]

## Deploy Notes
- Image rebuild needed? [yes — naya route/code = `docker compose build app` + `up -d --no-deps app`; code image me BAKED] (2026-07-05)
- Env flag enable karna hai? [yes/no]
```

---

## Phase 5: Quality Gate

Spec review karo:
- [ ] Duplicate route nahi banaya?
- [ ] Fail-open pattern hai?
- [ ] Ban-safe hai (no auto-send/auto-publish)?
- [ ] Test cases likhay?
- [ ] AUTOMATION_FLAGS list update?
- [ ] prod_check fail nahi karega?

Agar sab pass → spec ko `docs/specs/FEATURE_YYYYMMDD.md` mein save karo.

---

## Phase 6: File + Execute

```bash
mkdir -p docs/specs
# spec file save karo
```

User se poocho: **"Spec approve hai? Build karein?"**
Agar haan → `plan-then-build` skill invoke karo.
