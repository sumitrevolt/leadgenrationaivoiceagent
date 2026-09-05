# Milestone Reporting — LeadGen AI

> **Source:** `docs/RACI_MATRIX.md`, `docs/KPI_DASHBOARD_SPEC.md`, sprint plan cadence. **Owner:** lead-engineer (R), Sumit (A), qa-test-engineer (C).
> **Format:** every milestone (per-sprint + per-charter + per-incident) follows the **R.O.B.N.** template: **R**esults / **O**ngoing / **B**lockers / **N**ext.

---

## Reporting cadence (multi-tier)

| Report type | Cadence | Author | Audience | Auto-generated? |
|---|---|---|---|---|
| **Daily standup digest** | Daily 10:00 IST | lead-engineer | Sumit | YES (cron + auto-compile) |
| **Sprint review report** | Fri 17:00 IST (per sprint) | lead-engineer + qa-test-engineer | Sumit + customer-facing | YES (template + filled) |
| **Sprint retro packet** | Fri 17:30 IST (per sprint) | lead-engineer | Sumit | YES (template) |
| **Milestone close packet** | Per milestone (M6, M7, M8, M9) | lead-engineer | Sumit + stakeholders (optional) | YES |
| **Charter retro** | End of M9 + per charter | lead-engineer | Sumit + investors (when applicable) | YES |
| **Incident report** | Per P0/P1 incident, within 24h | sre-engineer | Sumit + stakeholders | Template + manual fill |
| **Compliance audit report** | Quarterly (post-SOC2) | compliance-engineer | external auditor | YES |
| **Customer-facing changelog** | Per release | marketing-engineer | customers | YES (auto from git log) |

---

## R.O.B.N. template (mandatory for sprint reviews + milestone close)

Each report has 4 sections:

### R — Results (completed + measured)
### O — Ongoing (in-flight + ETA)
### B — Blockers (risks realized + mitigations)
### N — Next (next steps + ownership)

---

## Sprint Review Report — Template

```markdown
# Sprint Review — Sprint N (YYYY-MM-DD to YYYY-MM-DD)

**Theme:** <sprint theme>
**Velocity index:** <actual/planned> = <X.XX>
**Owner-gating actions used:** <N>

---

## R — Results

| Task ID | Title | Owner | Status | Evidence |
|---|---|---|---|---|
| ... | ... | ... | ✅ done | link/artifact |

**Definition of Done achieved:**
- [x] <criterion 1>
- [x] <criterion 2>
- [x] <criterion 3>

**Key metrics:**
- Velocity: <X ED> / <Y ED planned> = <X.XX>
- Quality gates: G1–G5 green count = <N>/5
- Test coverage delta: <+X.X%> on touched
- PR cycle time median: <X hours>
- Production smoke (last deploy): ✅ / ❌

---

## O — Ongoing (carried over to next sprint)

| Task ID | Title | % complete | ETA | New owner |
|---|---|---|---|---|
| ... | ... | <XX%> | YYYY-MM-DD | ... |

---

## B — Blockers (active + mitigated)

| Risk ID | Realized? | Mitigation in place | Owner | Status |
|---|---|---|---|---|
| R-XXX-NNN | yes/no | <mitigation> | <owner> | resolved/active |

**Incidents during sprint:** <count> — <summary>

---

## N — Next (next sprint focus)

| Priority | Task | Estimated ED | Owner |
|---|---|---|---|
| 1 | ... | <X> | ... |
| 2 | ... | <X> | ... |
| 3 | ... | <X> | ... |

**Owner-gating actions planned for next sprint:** <count>
```

---

## Milestone Close Packet — Template (per M-number)

```markdown
# Milestone Close — M{N} (YYYY-MM-DD → YYYY-MM-DD)

**Theme:** <milestone North Star>
**Charter objective:** <which charter objective>
**Total charter ED:** <planned> / <actual>

---

## Strategic outcomes

| Charter objective | Target | Achieved | Δ |
|---|---|---|---|
| O-1 | <target> | <value> | +/- |
| O-2 | <target> | <value> | +/- |
| O-3 | <target> | <value> | +/- |

**Critical metrics (per charter success criteria):**

| KPI | Target | Actual | Verdict |
|---|---|---|---|
| CAC blended | < ₹400 | ₹XXX | PASS/FAIL |
| LTV/CAC | > 6 | X.XX | PASS/FAIL |
| D7 retention | > 50% | XX% | PASS/FAIL |
| P0 outages | 0 | X | PASS/FAIL |
| Defect leakage | < 1% | X.X% | PASS/FAIL |
| MTTR (P0/P1) | < 30 min | X min | PASS/FAIL |

---

## Sprint-by-sprint recap

| Sprint | Theme | Planned (ED) | Actual (ED) | Velocity | Owner-gates |
|---|---|---|---|---|---|
| S1 | ... | 14 | XX | X.XX | 4 |
| S2 | ... | 14 | XX | X.XX | 3 |
| ... | ... | ... | ... | ... | ... |

---

## Owner-gating audit

| Action | When | Outcome | Time-to-decision |
|---|---|---|---|
| <push/deploy/etc.> | <date> | <OK/FAIL> | <X min> |
| ... | ... | ... | ... |

---

## Risk realized vs mitigated

| Risk ID | Description | Realized? | Impact | Mitigation effectiveness |
|---|---|---|---|---|
| R-XXX | ... | yes/no | <£/>/time | effective/partial/ineffective |

---

## Customer outcomes (if any)

- New paid logos: <count>
- Upgrades (Starter → Combo): <count>
- Annual signed: <count>
- Agency pilots: <count>
- Churn this period: <count> (target < X)

---

## Lessons learned (top 5)

1. ...
2. ...
3. ...
4. ...
5. ...

---

## Next milestone (M{N+1}) preview

- Focus: ...
- Critical gate: ...
- Owner-gating actions expected: <count>

---

## Appendix: evidence attachments

- Sprint review packets: <links>
- Deploy packets: <links>
- Incident RCAs: <links>
- Compliance packets: <links>
- Charter amendments: <links>
```

---

## Daily Standup Digest — Template (auto-generated)

```markdown
# Daily Standup — YYYY-MM-DD

**On-call:** <agent>
**Open PRs:** <count> (oldest: <X hours>)
**Open incidents:** <count>

---

## Yesterday (auto-collected from git + state)

- Merged: <PR list>
- Opened: <PR list>
- Deploys: <deploy list>
- Incidents resolved: <count>

## Today (per AI agent)

- Agent A: <tasks> — ETA <time>
- Agent B: <tasks> — ETA <time>
- ...
- Sumit queue: <N actions waiting>

## Risks active (R-MIT-OPEN count: N)

| Risk | Owner | Status |
|---|---|---|
| R-VOICE-001 | ... | mitigated / active / escalating |

## Quality gates (last 24h)

- G1 PR CI: <X>% green
- G2 main CI: <X>% green
- G4 post-deploy smoke: <X>% green (last 7d)
- G5 hourly canary: <X>% green (last 24h)

---
```

**Frequency:** every day 10:00 IST, posted to Sumit (Telegram/WhatsApp/email) and pinned to `deliverables/DAILY/YYYY-MM-DD.md`.

---

## Incident Report — Template (within 24h)

```markdown
# Incident Report — INC-YYYY-MM-DD-NNN

**Severity:** P0 / P1 / P2 / P3
**Duration:** HH:MM → HH:MM (HH:MM total)
**Customer impact:** <count> tenants, <revenue> at risk
**Detection:** <auto/manual>, time to detect <X min>
**Mitigation:** <auto/manual>, time to mitigate <X min>
**Resolution:** <time to resolve>

---

## Timeline (UTC)

- HH:MM — <event>
- HH:MM — <event>
- HH:MM — <page sent>
- HH:MM — <rollback/fix>
- HH:MM — <all clear>

---

## Root cause (5 Whys)

1. Why: ...
2. Why: ...
3. Why: ...
4. Why: ...
5. Why (root): ...

---

## Customer communication

- Status page updated at HH:MM
- Customer emails sent at HH:MM
- All-clear at HH:MM

---

## Action items (RCA follow-up)

| ID | Action | Owner | Due | Status |
|---|---|---|---|---|
| RCA-001 | ... | ... | YYYY-MM-DD | open |
| ... | ... | ... | ... | ... |

---

## What went well

- ...

## What didn't

- ...

## What we'll change

- ...
```

---

## Reporting distribution

| Report | Sumit | Lead | Staff-eng | Platform-eng | QA | Other |
|---|---|---|---|---|---|---|
| Daily standup | ✅ | ✅ | ✅ | ✅ | ✅ | opt-in |
| Sprint review | ✅ | ✅ | ✅ | ✅ | ✅ | customer-facing subset |
| Sprint retro | ✅ | ✅ | ✅ | (selected) | ✅ | (selected) |
| Milestone close | ✅ | ✅ | ✅ | ✅ | ✅ | stakeholders |
| Incident (P0/P1) | ✅ | ✅ | ✅ | ✅ | ✅ | (auto-page) |
| Compliance quarterly | ✅ | ✅ | | ✅ | | external auditor |

---

## Reporting discipline (non-negotiable)

1. **Daily standup ALWAYS auto-posts** (even if nothing to report) — silence = noise
2. **Sprint review on Friday at 17:00 IST or that sprint is OFFICIAL amber** — never skip
3. **Incident report within 24h** — late = RCA-blocking = charter-blocking
4. **Milestone close packet within 5 working days of milestone close** — sets up next charter
5. **Compliance evidence packet attached to every release** — audit trail non-negotiable

---

## Anti-patterns (reporting we will NOT do)

1. ❌ Reports that summarize only what went well — report R.O.B.N. as-is
2. ❌ Burying blockers at the bottom — first thing in the report
3. ❌ Reporting numbers without context (e.g. "10 incidents" without saying 0 were customer-facing)
4. ❌ Reporting "active work" without % complete and ETA
5. ❌ Hidden owner-gating queue — visible always
6. ❌ Skipping the daily digest on Sundays (low activity ≠ zero activity)
7. ❌ Inline external incident communication without status page update
8. ❌ "Retro will happen later" — happens Friday, period
