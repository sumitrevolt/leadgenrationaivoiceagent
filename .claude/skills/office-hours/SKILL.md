---
name: office-hours
description: "Kya yeh worth building hai?" — naya feature/idea ko 6 startup forcing-questions (demand, status-quo pain, specific user, narrowest wedge, evidence, future-fit) se challenge karo aur build/validate/skip recommend karo. Use when user bole "idea hai kya karein", "ye banana worth hai", "office hours chahiye", ya kisi naye feature ko scope karne se PEHLE (`/plan-ceo-review`/`/plan-eng-review` se pehla step).
---

# Skill: office-hours
**Adapted from gstack by Garry Tan (YC). MIT License.**

## When to invoke
Jab user bole:
- "Kya yeh worth building hai?"
- "Is feature ke baare mein sochna hai"
- "Idea hai, kya karein?"
- "Office hours chahiye"
- Naya product feature scope karne se PEHLE

`/plan-ceo-review` ya `/plan-eng-review` se PEHLE use karo.

## Phase 1: Context Gather karo

```bash
git branch --show-current
git log --oneline -10
cat CLAUDE.md | head -50
```

User ka current product context pado: Marketing SaaS + Voice Agent, 39 builtin niches, FastAPI/Python, live at leadsgenai.in.

## Phase 2: 6 Forcing Questions (Startup Mode)

**Ek ek karke poochho** (sab ek saath mat). Jab tak jawab na aaye agle pe mat jao.

### Q1 — Demand Reality
> "Kya koi paise dene ko taiyaar tha PEHLE se, sirf tum bana sako is feature ke liye? Haan/nahi, aur woh kaun tha?"

(Agar nahi: yeh feature kisi ki zarurat nahi solve kar raha — pause karo.)

### Q2 — Status Quo Pain
> "Abhi log yeh kaam KAISE karte hain bina is feature ke? Kya woh kuch use karte hain? Spreadsheet? Manual call? Kuch aur?"

(Agar kuch nahi karte: pain real nahi hai.)

### Q3 — Desperate Specificity
> "Ek specific user ka naam/description do jo is feature ke bina roz 30+ minute waste karta hai. Uski exact frustration kya hai?"

(Vague "chhote businesses" = reject. Ek specific niche, ek specific problem.)

### Q4 — Narrowest Wedge
> "Yeh feature ka SMALLEST possible version kya hai jo real value dega ek user ko? Matlab 1 niche, 1 city, 1 use case."

(Jo pehle ship ho sake, woh — baaki sab baad mein.)

### Q5 — Observation Evidence
> "Tune KHUD dekha hai ki users is problem se struggle karte hain? Kab? Kahan? Support ticket, call recording, kuch evidence?"

(Assumption pe mat chalo — evidence chahiye.)

### Q6 — Future Fit (2026 India context)
> "1 saal baad, jab AI tools aur saste ho jayenge, yeh feature tab bhi defensible rahega? Ya koi bhi copy kar sakta hai?"

---

## Phase 3: Premise Challenge

User ke response ke baad, challenge karo:

1. **Reframe karo** — "Tune 'daily briefing' bola, par jo describe kiya woh actually 'AI chief of staff' hai. Yeh difference matter karta hai kyunki..."
2. **Hidden assumptions nikalo** — 3 assumptions jo user ne nahi boli par jo true honi chahiye is feature ke kaam karne ke liye
3. **Cheapest alternative** — "Kya yeh koi existing tool/WhatsApp group/Excel se solve ho sakta hai ₹0 mein?"

---

## Phase 4: Alternatives (MANDATORY)

3 alternative approaches do:
1. **Build karo** (ab, full, as-is)
2. **Validate first** (cheapest possible version — even manual/fake backend)
3. **Don't build** (kya existing feature se jugaad ho sakta hai?)

Har alternative ke liye: effort estimate, user impact (1-10), revenue potential.

---

## Phase 5: Recommendation + Design Doc Save

Decision recommendation do:
- **BUILD NOW** (agar Q1-Q6 sab strong)
- **VALIDATE FIRST** (agar 2-3 questions weak)
- **SKIP / DEPRIORITIZE** (agar demand not proven)

Agar BUILD: brief design doc banao:
```
docs/design/FEATURE_NAME_YYYYMMDD.md
```
Include: Problem, User (specific), Solution, MVP scope, Success metric.

---

## Important Rules
- Sab questions Hinglish mein poochho
- Generic "local businesses ke liye helpful hoga" = push back karo
- Revenue impact of each decision frame karo (₹ terms mein)
- Context yaad rakho: DO alag products (Marketing = main, Voice = standalone — koi bundle framing NAHI), 39 builtin niches, live pipeline numbers `/app/admin` se lo (CLAUDE.md me count nahi)
