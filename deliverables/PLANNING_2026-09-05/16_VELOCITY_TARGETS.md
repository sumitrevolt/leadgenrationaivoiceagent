# Velocity Targets — LeadGen AI

> **Source:** `docs/KPI_DASHBOARD_SPEC.md`, sprint history (60-day baseline), WBS estimates. **Owner:** lead-engineer (R), Sumit (A), qa-test-engineer (C).
> **Definition:** **Velocity = Engineer-Days (ED) of completed work per sprint**, normalized by sprint length (10 working days).
> **Target:** 14 ED/sprint baseline; 18 ED on Advanced UI sprint (S4); trending up to 16 ED by M9.

---

## Why velocity, not story points or hours?

| Metric | Pros | Cons (for our setup) |
|---|---|---|
| Story points | Relative effort | Inflate over time; team of AI + solo owner can't self-calibrate consistently |
| Hours logged | Concrete | Inflated when AI works "off-hours"; doesn't reflect output |
| Engineer-days (ED) | Concrete, calibration-friendly, comparable to staffing norms | Needs explicit task sizing discipline |
| **ED/cycle time / defect density** | Hybrid | More inputs = more drift |

**Decision:** use **ED delivered per sprint** as primary, with cycle time + defect density as quality-adjusted overlay.

---

## Velocity targets per sprint

| Sprint | Theme | Planned (ED) | Stretch (ED) | Floor (ED) | Velocity index | Notes |
|---|---|---|---|---|---|---|
| **S1** | M6 starter — first 5 deals | 14 | 16 | 10 | 1.0 | Calibration sprint; expect ~70% realization |
| **S2** | M6 scale — outreach automation | 14 | 16 | 10 | 1.0 | Reply-agent v2 + scaling pressure |
| **S3** | M7 CS — health + churn + D7 gate | 14 | 15 | 9 | 1.0 | Statistical noise on early D7 cohort |
| **S4** | M8 Advanced UI — tier-aware dashboard | 18 | 20 | 12 | 1.0 | Largest sprint; Combo upgrade + voice console |
| **S5** | M9 SKU — Annual + Agency + Razorpay | 11 | 13 | 8 | 1.0 | All-hour-glue-sprint |
| **S6** | M9 close + retro + M10 plan | 11 | 12 | 8 | 1.0 | Mostly retro + first annual/agency closing |
| **Total 90-day charter** | | **82 ED** | 92 | 57 | | |

---

## Realistic velocity curve (learning curve ramp)

Even with an AI-staff augment, the team is in **calibration mode for the first sprint** and gets faster over time:

```
Sprint   Realization   Actual ED    Cumulative learning factor
S1       70%           9.8          1.0
S2       80%          11.2          1.07
S3       85%          11.9          1.13
S4       90%          16.2          1.20
S5       95%          10.5          1.23
S6       100%         11.0          1.25
                                          (final cumulative ~ 70.6 ED)
```

**Total 90-day realized ED:** ~71 (vs. 82 planned = 0.87 velocity index)

**Why not 1.0?**

| Constraint | Realization penalty |
|---|---|
| AI-staff new to codebase (week 1) | -20% sprint 1 |
| Owner-gating queue (Sumit attention rate-limited) | -10% sprints 2-6 |
| Compliance + review overhead (M6 → M9) | -8% sprints 3-6 |
| Calendar noise (Indian holidays, Sumit holidays, festivity weeks) | -5% sprints 5-6 |

**Cumulative effect:** 80–87% realization on long horizon is realistic.

---

## Per-task-type velocity benchmarks

| Task type | Average ED | Median cycle time | Defect density |
|---|---|---|---|
| UI feature (medium) | 1.5 | 3 days | 0.5 bugs/feature |
| UI feature (large) | 3.0 | 5 days | 1.5 bugs/feature |
| Backend feature (medium) | 1.0 | 2 days | 0.3 bugs/feature |
| Backend feature (large) | 2.5 | 4 days | 1.0 bugs/feature |
| Migration (with ADR) | 1.5 | 3 days | 0.2 bugs/migration |
| Bug fix (small) | 0.3 | 1 day | N/A |
| Bug fix (medium, root cause) | 0.8 | 2 days | N/A |
| Infra / deploy workflow | 1.0 | 3 days | 0.2 bugs |
| Compliance evidence + test | 1.0 | 2 days | 0.1 bugs |
| Doc update (charter/plan) | 0.3 | 0.5 day | N/A |
| Test refactor | 0.5 | 1 day | 0.2 bugs |

These are per-task ED estimates based on the 60-day baseline + WBS calibration.

---

## Cycle-time targets (per PR)

| PR size | Target PR cycle time | Definition |
|---|---|---|
| Small (≤ 50 lines) | < 24h | first commit → merge |
| Medium (≤ 200 lines) | < 3 days | |
| Large (≤ 500 lines) | < 7 days | |
| XL (≥ 500 lines) | MUST SPLIT | exception: Sumit override |

**Cycle-time SLA breach** = code-reviewer paged.

---

## Quality-adjusted velocity

Velocity without quality = feature factory. **Quality-adjusted velocity** weights:

| Quality dimension | Weight | Target |
|---|---|---|
| Test coverage delta on touched | 0.20 | ≥ 0% (no drop) |
| G1 / G2 gate pass rate | 0.15 | ≥ 95% |
| P0 incidents per sprint | 0.25 | 0 |
| P1 incidents per sprint | 0.10 | ≤ 1 |
| Defect leakage (caught post-deploy) | 0.20 | ≤ 1% |
| Production smoke (G4) pass rate | 0.10 | ≥ 95% |

**Quality-adjusted velocity** = raw ED × Σ (weight × score)

| Score | Description |
|---|---|
| 1.0 | meets target |
| 0.8 | within tolerance |
| 0.5 | amber (mid-sprint review triggered) |
| 0.0 | fail (sprint retro + RCA) |

**Quality-adjusted target:** maintain ≥ 0.90 across all sprints.

---

## Velocity tracking dashboard (auto-built, Grafana)

| Panel | Source | Refresh |
|---|---|---|
| ED completed per sprint | WBS + git + delivery log | end-of-sprint |
| Velocity index per sprint | planner | end-of-sprint |
| Cycle time per PR | GitHub | live |
| Quality gates pass rate | CI | live |
| Defect leakage per sprint | incident log | live |
| Quality-adjusted velocity | derived | end-of-sprint |
| Burndown per sprint | WBS + kanban | live |
| Cumulative charter completion | WBS + delivery | live |
| Owner-gate latency | gate log | live |
| Mid-sprint risk realization | risk register | live |

---

## Sprint-on-sprint comparability

| Sprint | ED planned | ED actual | Velocity | Index | Quality-adjusted | Trend |
|---|---|---|---|---|---|---|
| S1 | 14 | TBD | TBD | TBD | TBD | initial |
| S2 | 14 | TBD | TBD | TBD | TBD | - |
| S3 | 14 | TBD | TBD | TBD | TBD | - |
| S4 | 18 | TBD | TBD | TBD | TBD | - |
| S5 | 11 | TBD | TBD | TBD | TBD | - |
| S6 | 11 | TBD | TBD | TBD | TBD | - |

**Index trends:**
- ≥ 1.0 → Sprint goal exceeded
- 0.85–0.99 → On-target (yellow if < 0.85)
- < 0.85 → Mid-sprint review triggered
- < 0.70 → Charter amendment triggered

---

## Velocity-aligned milestones (revenue + product)

| Charter milestone | Velocity gate | Velocity at risk gate |
|---|---|---|
| M6 close | 10 paid logos, ≥ 14 ED/sprint completed | < 0.85 mid-sprint |
| M7 close | D7 ≥ 50%, 18 paid logos | < 0.85 mid-sprint |
| M8 close | First Combo upgrade, ≥ 16 ED/sprint | < 0.80 mid-sprint |
| M9 close | MRR ≥ ₹1.5L, first Annual + Agency | < 0.75 mid-sprint |

---

## Velocity anti-patterns (will distort measurement)

1. ❌ **Re-sizing tasks in middle of sprint** — backwards-looking measurement only
2. ❌ **Counting exploration/R&D as ED** — exploration is overhead, not deliverable
3. ❌ **Skipping retro to "save time"** — retro is what improves the next velocity
4. ❌ **Inflating ED estimates to hit plan** — sustainability beats optics
5. ❌ **Confusing activity (commits) with delivery (deployed + used)** — only delivered + used counts
6. ❌ **Skipping quality gates to "ship faster"** — quality-adjusted velocity catches this
7. ❌ **Blaming the AI for slow sprints** — calibration takes 3 sprints, accept it
8. ❌ **Comparing to a 4-engineer team velocity** — AI-staff + solo founder has its own curve

---

## Velocity by AI-staff tier (granular)

The 11 subagents + 24 staff agents have different velocity profiles. Track per tier:

| Tier | Count | Avg ED/week | Notes |
|---|---|---|---|
| Tier 1: dev-time subagents | 11 | 3-5 ED each | Code, test, doc-heavy |
| Tier 2: platform AI-staff (24) | 24 | 1-3 ED each | Specialised, narrower scope |
| **Total AI-staff capacity** | 35 agents | ~80-100 ED/week theoretical | Realistic realized: ~20-30 ED/week |

**Why realized ≠ theoretical:**

| Drag factor | Effect |
|---|---|
| Coordination overhead | -10% |
| Context-switching between tenants | -15% |
| Sequential dependencies (need human in middle) | -10% |
| Production safety review | -10% |
| Bug-fix and rework (residual defects) | -5% |

**Realistic AI-staff weekly realized: ~22 ED/week** (= ~12 ED/sprint of pure AI-staff output)
Plus **Sumit: ~3 ED/week** (architecture, decisions, escalation)
**Total realized: ~14-16 ED/sprint** — matching the plan.

---

## Velocity retrospective (per-charter)

End of every charter (90 days), run this:

| Question | Answer |
|---|---|
| Did we hit planned velocity? | Yes / No + Δ% |
| Where did we over-deliver? | <list> |
| Where did we under-deliver? | <list> |
| Quality-adjusted velocity? | ≥ 0.90? |
| Owner-attention spent vs. budget? | hrs / hrs |
| What changed in the team's velocity curve? | learning factor |
| Plan correction for next charter? | scope / schedule / hiring / tools |
| Should charter continue? | YES / NO / AMEND |

The retrospective is held by Sumit + lead-engineer + 2 domain owners. Output: **Charter Amend Document v2**, archived to `deliverables/CHARTER_AMEND_*`.

---

## Velocity first-90-days lessons learned (target)

1. **Calibration matters more than speed** — S1 is the calibration sprint. Don't optimize.
2. **Quality-adjusted beats raw** — sprint S3 with 0 P0 incidents beats S2 with 14 ED + 2 P0s.
3. **Owner attention is the real ceiling, not AI capacity** — 22h/sprint budget is the binding constraint.
4. **Long-tail bug-fix ED eats velocity** — design for less rework, not more speed.
5. **Compliance + review overhead is fixed cost** — accept it; don't try to "automate it away" by skipping.
6. **Mid-sprint velocity dips = signal** — investigate, don't "recover" by cutting tests.

---

## Velocity auto-collection (cron + scripts)

| Script | Cadence | Output |
|---|---|---|
| `scripts/velocity_collector.py` | end-of-day | Daily ED tally + projection |
| `scripts/cycle_time_collector.py` | end-of-week | Cycle time histogram |
| `scripts/defect_density_collector.py` | end-of-sprint | Defect density trend |
| `scripts/quality_adjusted_velocity.py` | end-of-sprint | Quality-adjusted score |
| `scripts/owner_gate_latency.py` | end-of-week | Gate latency histogram |
| `scripts/charter_burndown.py` | live | WBS-vs-delivered burndown |

All scripts output JSON → Grafana + WBS database + weekly email digest.
