**[CORRECTION] Ira ka gate — maine galat flag par decision maanga tha**

Follow-up check me do alag engine, do alag flag nikle:
- `JOURNEY_ENGINE` → `app/marketing/journeys.py:47` — event→action rules (`emit_event`). Code default `"0"`.
- `LIFECYCLE_NURTURE` → `app/marketing/lifecycle_nurture.py:52` — day-based drip. `run_due()` khud self-gated hai (`:232-234`, off par `{"enabled": False}` return).

Do baatein isse nikalti hain:
1. **Gate leak nahi hai** — `growth_optimizer.py:200` seedha `run_due()` bulata hai aur wo apne aap `LIFECYCLE_NURTURE` par ruk jaata hai. Growth beat se koi ungated journey fire nahi ho raha.
2. **Par wrapper par galat flag hai** — `run_ira()` (`staff.py:1390`) `JOURNEY_ENGINE` check karta hai aur phir `lifecycle_nurture.run_due()` chalata hai. Yani Ira ka path DONO flags maangta hai, jabki uska kaam sirf `LIFECYCLE_NURTURE` ka hai.

Isliye mera pichla Owner-action sawaal galat premise par tha. `JOURNEY_ENGINE` akela arm karne se Ira ka nurture sweep shuru NAHI hoga (`LIFECYCLE_NURTURE` phir bhi rokega) — aur wo ek bilkul alag engine (journeys.py ke event actions, customer-contact surface) arm kar dega. Do alag blast radius hain, ek decision me mat milaiye.

Recommendation list me #4: `run_ira()` ka gate `JOURNEY_ENGINE` se `LIFECYCLE_NURTURE` par theek karo — tabhi Ira ka heartbeat uske asli kaam se match karega.

Pichli triage ke baaki findings waise hi khade hain (beat me Ira/Raksha nahi, `EXPECTED_GAP_MIN` me nahi, silent flag-off return). Dono flags ki prod value maine ab bhi read nahi ki — upar sirf code defaults hain.

**Sudhra hua Owner next action:** decision `LIFECYCLE_NURTURE` par hai — nurture drip chalani hai ya off rehne deni hai? `JOURNEY_ENGINE` ko alag se, baad me dekhein. Flag main koi flip nahi karunga.
