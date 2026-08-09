# Book Sources — Automation Opportunity Discovery (LeadGen)

> Evidence tiers (har principle ka source level clearly marked):
> - **DIRECT** = publisher/author metadata, official ToC/sample/preview inspected
> - **AUTHOR-SUMMARY** = author/publisher/companion-site summaries
> - **SECONDARY** = reputable reviews/commentary
> - **SYNTHESIS** = FreeBuff's independent distillation
> - **ADAPTATION** = LeadGen-specific application written by FreeBuff
>
> Copyright: koi full chapter, distinctive prose, checklist, template, diagram ya
> lengthy quotation reproduce NAHI kiya gaya. Books = teachers (principles), text
> donors nahi. Koi licence relicense nahi karta book material. Full 18-book ledger:
> `docs/research/BOOK_SOURCES_LEDGER.md`; decision matrix: `docs/research/SKILL_OVERLAP_MATRIX.md`.

## Selected sources (8) — principle → skill section map

### 1. The Goal — E. Goldratt & J. Cox, North River Press (30th Anniversary Ed., ISBN 978-0884271956) — DIRECT (publisher/catalog metadata + ToC)
- **Principle (SYNTHESIS):** throughput = constraint se bounded; bottleneck ke aage naya work push karna throughput nahi badhata, WIP badhata hai.
- **Adaptation (ADAPTATION):** `SKILL.md §1 Pre-flight` — pehle repo ka current constraint confirm karo (mid-funnel Hot Queue + dialer sprint) tabhi naya top-funnel loop socho. §3 Score me "Revenue impact" axis ka justification.

### 2. Accelerate — N. Forsgren, J. Humble, G. Kim, IT Revolution (2018, ISBN 978-1942788331) — DIRECT (publisher metadata + author summaries)
- **Principle (SYNTHESIS):** delivery capability ko deployment frequency, lead time, change-failure rate, MTTR se measure karo; change-failure rate ek prime signal hai.
- **Adaptation (ADAPTATION):** `SKILL.md §6 Measure + Kill` — success metric pehle define, `dlq:failed_tasks` weekly inspect = change-failure evidence; weekly ops review = Accelerate's cadence pattern.

### 3. The Lean Startup — E. Ries, Crown Business (2011, ISBN 978-0307887894) — DIRECT (publisher metadata + author summaries)
- **Principle (SYNTHESIS):** build-measure-learn loop; validate before scaling; "automate the proven".
- **Adaptation (ADAPTATION):** `SKILL.md §2 Discover` step 4 (5-10 manual repetitions pehle) + `§5 Run` (smallest vertical slice, canary first) + `§6` kill-fast, no sunk cost.

### 4. Running Lean — A. Maurya, O'Reilly (2012, ISBN 978-1449305178) — DIRECT (publisher metadata + author summaries)
- **Principle (SYNTHESIS):** problem/solution fit documentation, 1-page canvases, evidence before scaling.
- **Adaptation (ADAPTATION):** `SKILL.md §2 Discover` — 1-page process map = "canvas" for automation (steps → owner → data → gate); ye map hi contract hai.

### 5. The Phoenix Project — G. Kim, K. Behr, G. Spafford, IT Revolution (2013, ISBN 978-0988262591) — DIRECT (publisher metadata + author summaries)
- **Principle (SYNTHESIS):** four work types (business project, internal, change, **unplanned**); unplanned work pehle fix karo, automate mat karo; flow improvement = work-type triage.
- **Adaptation (ADAPTATION):** `SKILL.md §2` step 2 work-type triage; unplanned = pehle fix.

### 6. The Checklist Manifesto — A. Gawande, Metropolitan Books (2009, ISBN 978-0805091748) — DIRECT (publisher metadata + author summaries)
- **Principle (SYNTHESIS):** checklists expert settings me discipline + failure reduction dete hain; verification step kabhi skip nahi.
- **Adaptation (ADAPTATION):** `SKILL.md §1` pre-flight checklist (5 items, kabhi skip nahi) + `§8` self-verification commands.

### 7. The E-Myth Revisited — M. Gerber, HarperCollins (ISBN 978-0887307287) — DIRECT (publisher metadata + author summaries) — **SECONDARY weight only**
- **Principle (SYNTHESIS):** founder ko systems par kaam karna chahiye, systems me nahi; owner time = highest-value input.
- **Adaptation (ADAPTATION):** `SKILL.md §3` "Owner-time saved" axis — owner manual work = high score, agent/automation = lower.

### 8. Traction / EOS — G. Wickman, BenBella (ISBN 978-0978531899) — DIRECT (publisher metadata + author summaries) — **SECONDARY weight only**
- **Principle (SYNTHESIS):** fixed operating cadence (weekly/quarterly) + accountability for execution follow-through.
- **Adaptation (ADAPTATION):** `SKILL.md §6` fixed weekly ops review (KEEP / KILL / SCALE / FIX) + output contract (10-field) = accountability artifact.

## Rejected in this skill's scope (covered by existing skills) — summary

| Book | Existing owner skill |
|---|---|
| DDIA (Kleppmann) | `leadgen-automation-reliability`, `integration-engineering` |
| Release It! (Nygard) | `error-handling-patterns`, `leadgen-automation-reliability` |
| Predictable Revenue (Ross/Tyler) | `cold-email`, `prospecting`, `revops` |
| 1-Page Marketing Plan (Dib) | `marketing-plan`, `conversion-optimization` |
| Mom Test (Fitzpatrick) | `customer-research` |
| Obviously Awesome (Dunford) | `product-marketing` |
| Don't Make Me Think (Krug) | `design-review` |
| Made to Stick (Heath) | `copywriting`, `hinglish-copywriting` |
| Hooked (Eyal) | `onboarding`, `churn-prevention` |
| Customer Success (Mehta et al.) | `churn-prevention`, `revops` |

## FreeBuff synthesis statement

Yeh skill 8 books ke principles ka **independent re-expression** hai — project-specific
procedures (`opportunity matrix`, `work-type triage`, `canary → kill`, `10-field output
contract`) FreeBuff ne LeadGen ke actual runtime (Hot Queue, `AUTOMATION_FLAGS`,
`dlq:failed_tasks`, `automation_health.EXPECTED_GAP_MIN`, owner-gate model) ke hisaab se
likhe hain. Koi book ka structure, prose, checklist, ya template copy nahi hua.
