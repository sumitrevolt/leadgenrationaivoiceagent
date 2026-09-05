# RACI Matrix — LeadGen AI (M6–M9, formal extension)

> **Legend:** **R** = Responsible (does the work) · **A** = Accountable (owner of outcome, single A per row) · **C** = Consulted (gives input) · **I** = Informed (kept in loop)
> **Source-of-truth:** this matrix extends `docs/RACI_MATRIX.md` (existing) — names of AI roles map to `docs/AI_WORKFORCE.md` Tier 1 + Tier 2. When in doubt, the AI Workforce doc wins.
> **Owner:** every row has **exactly one A**. If multiple A's appear, that's a governance bug — escalate via `OWNER-SCOPE-AMEND-NNN`.

## Role roster

| Tag | Role | Owner of | Skills | Scope |
|---|---|---|---|---|
| **Sumit** | Founder / owner | All external actions + first 10 deals + first annual/agency deal | — | Sole R/A on gate |
| **staff-engineer** | Senior dev (WRITE) | All non-test code | `app/**`, scripts | R on implementation |
| **qa-test-engineer** | QA (WRITE tests/) | Test coverage + harness | `tests/**` | R on tests |
| **code-reviewer** | Code review | Pre-ship adversarial review | read-only | R on review |
| **security-auditor** | AppSec | auth/payment/telephony | read-only | R on security sign-off |
| **database-architect** | DB | schema/migration/queries | read-only | R on DB design |
| **frontend-ux-engineer** | UI craft | all visible pages | read-only | R on UX review |
| **infra-doctor** | DevOps | VPS/Docker/Celery/observability | read-only | R on infra review |
| **agent-workflow-auditor** | Agent governance | loops/cost/eval | read-only | R on agent audit |
| **harness-conformance-auditor** | Harness score | C-01..C-15 controls | read-only | R on maturity |
| **mcp-engineer** | MCP | /mcp + A2A + Arya | read+write (MCP only) | R on MCP |
| **revenue-strategist** | CSO/growth | ROI/roadmap | read-only | R on revenue decisions |
| **ops-engineer** | Runtime ops | tenant-facing automation | scripts/UI | R on ops |
| **sre-engineer** | SRE | observability/on-call | infra/observability | R on SLOs |
| **sales-engineer** | Sales OS | outreach/reply/closing | sales flows | R on sales |
| **cs-engineer** | Customer success | health/churn/cohort | CS loops | R on CS |
| **closing-engineer** | Deal close | booked-call → paid | scripts/UI | R on closing |
| **outreach-engineer** | Outreach | lead generation | scripts/UI | R on outreach |
| **reply-engineer** | Reply agent | WhatsApp/email reply | prompts/flows | R on reply |
| **telephony-engineer** | Voice/SIP/DLT | Vobiz/Smartflo/DLT | telephony code | R on telephony |
| **ml-engineer** | ML/LLM | model selection, eval, fine-tune | ml/ | R on ML |
| **data-engineer** | Data/BI | cohort/dashboard/SQL | data/ | R on data |
| **billing-engineer** | Billing truth | packages/UPI/Razorpay | billing/ | R on billing |
| **frontend-engineer** | UI build | components, pages | Next.js | R on UI build |
| **platform-engineer** | Platform | auth/middleware/rbac | platform/ | R on platform |
| **compliance-engineer** | DPDP/SOC2 | consent/purge/audit | compliance/ | R on compliance |

---

## 1. Engineering workstream

| Activity | Sumit | staff-engineer | qa-test-engineer | code-reviewer | security-auditor | database-architect | frontend-ux-engineer | infra-doctor |
|---|---|---|---|---|---|---|---|---|
| Feature implementation | **A** | **R** | **I** | **C** (peer review) | **C** if auth/payment/telephony | **C** if schema change | **C** if UI change | **C** if infra change |
| Bug fix | **A** | **R** | **I** | **C** | **C** | **C** | **C** | **C** |
| Test coverage | **A** | **C** | **R** | **C** | **C** | — | — | — |
| Code review (pre-ship) | **A** | **I** | **I** | **R** | **C** | **C** | **C** | **C** |
| Security audit | **A** | **I** | **I** | **I** | **R** | — | — | **C** |
| DB schema design | **A** | **C** | — | **C** | **C** | **R** | — | — |
| UI design | **A** | **C** | — | **C** | — | — | **R** | — |
| Infra change | **A** | **C** | — | **C** | — | — | — | **R** |
| Migrations | **A** | **R** | **I** | **C** | **C** | **R** | — | **C** |
| Performance regression | **A** | **C** | **I** | **C** | — | **C** | **C** | **R** |

## 2. Operations workstream

| Activity | Sumit | ops-engineer | sre-engineer | platform-engineer | infra-doctor |
|---|---|---|---|---|---|
| Daily tenant ops | **A** | **R** | **I** | **C** | **C** |
| Incident response | **A** | **R** (detect) | **R** (mitigate) | **C** | **R** (root-cause) |
| Deploy (VPS) | **A/R** | **C** | **C** | **I** | **C** |
| Secrets / `.env` | **A/R** | **I** | **I** | **C** | **C** |
| Backup / DR | **A** | **I** | **R** | **I** | **C** |
| Health-check / uptime | **A** | **C** | **R** | **I** | **C** |
| Auto-scaling (VPS) | **A** | **I** | **R** | **C** | **C** |
| Cost / capacity | **A** | **I** | **R** | **I** | **C** |
| Logging / observability | **A** | **C** | **R** | **C** | **C** |
| On-call (24/7) | **A/R** | — | **R** (auto-page) | — | — |

## 3. Product & feature workstream

| Activity | Sumit | sales-engineer | cs-engineer | closing-engineer | outreach-engineer | reply-engineer | frontend-engineer |
|---|---|---|---|---|---|---|---|
| Pricing change | **A/R** | **C** | **C** | **C** | — | — | **I** |
| New product SKU | **A/R** | **C** | **C** | **C** | — | — | **I** |
| Sales OS (M6) | **A** | **R** | — | **C** | **C** | **C** | **C** |
| Customer success (M7) | **A** | — | **R** | — | — | — | **C** |
| Advanced UI (M8) | **A** | — | **C** | — | — | — | **R** |
| Outreach batches | **A** | **C** | — | — | **R** | **C** | — |
| Reply agent coaching | **A** | **C** | — | — | — | **R** | — |
| Closing script | **A** | **C** | — | **R** | — | — | — |
| Tenant onboarding | **A** | **R** | **C** | **C** | — | — | **C** |
| Feature gating (tier) | **A** | **C** | **C** | **C** | — | — | **R** |

## 4. Telephony & voice

| Activity | Sumit | telephony-engineer | ml-engineer | infra-doctor | sre-engineer |
|---|---|---|---|---|---|
| DLT paperwork | **A/R** | **C** | — | — | — |
| Vobiz/Smartflo cutover | **A** | **R** | — | **C** | **C** |
| Voice kill-switch arm/disarm | **A/R** | **I** | — | **C** | **I** |
| Swara voice quality eval | **A** | **C** | **R** | — | — |
| Voice synthetic canary | **A** | **C** | **C** | **C** | **R** |
| Voice fine-tune (post-M9) | **A** | **C** | **R** | — | — |

## 5. Data, ML & analytics

| Activity | Sumit | data-engineer | ml-engineer | agent-workflow-auditor | harness-conformance-auditor |
|---|---|---|---|---|---|
| Cohort reports | **A** | **R** | **C** | **I** | — |
| Health score model | **A** | **R** | **C** | — | — |
| Churn detector | **A** | **R** | **C** | — | — |
| ML eval (LLM-as-judge) | **A** | **C** | **R** | **C** | **C** |
| Agent cost / loop governance | **A** | **I** | **C** | **R** | **C** |
| Harness maturity score | **A** | **I** | **C** | **C** | **R** |

## 6. Billing & payments

| Activity | Sumit | billing-engineer | security-auditor | compliance-engineer |
|---|---|---|---|---|
| Pricing truth | **A** | **R** | **C** | **C** |
| UPI flow | **A** | **R** | **C** | **C** |
| Razorpay integration | **A** | **R** | **C** | **C** |
| Refund / dispute | **A/R** | **C** | **C** | **C** |
| Plan change UI | **A** | **R** | **C** | — |
| Annual recurring billing | **A** | **R** | **C** | **C** |

## 7. Compliance & legal

| Activity | Sumit | compliance-engineer | security-auditor | revenue-strategist |
|---|---|---|---|---|
| DPDP consent flow | **A/R** | **R** | **C** | **I** |
| DPDP purge (right-to-erasure) | **A/R** | **R** | **C** | — |
| SOC2 control mapping (M10) | **A** | **R** | **C** | **I** |
| Recording retention (voice) | **A** | **R** | **C** | — |
| Audit log integrity (HMAC) | **A** | **R** | **C** | — |
| Pricing-disclosure compliance | **A** | **C** | — | **R** |

## 8. Owner-gating (always A = Sumit, R varies)

| Activity | Sumit | Primary R | Trigger word |
|---|---|---|---|
| `git push` to remote | **A/R** | code-reviewer (review) → staff-engineer (push mechanics) | owner: `push` |
| `gh workflow run deploy-vps.yml` | **A/R** | sre-engineer (gate) | owner: `deploy` / `ship` / `go` / `M{n}` |
| Outbound WhatsApp / Email bulk | **A/R** | ops-engineer (queue) | owner: `send` |
| Refund / chargeback | **A/R** | billing-engineer | owner: `refund` |
| Pricing change | **A/R** | revenue-strategist (propose) → billing-engineer (apply) | owner: `price <change>` |
| Skill flag flip (`COMBO_PRODUCT=1` etc.) | **A/R** | platform-engineer | owner: `arm <flag>` |
| DLT arm (`VOICE_LAUNCH_KILL=0` for new tenant) | **A/R** | telephony-engineer | owner: `arm voice <tenant>` |
| Customer deletion / DPDP purge | **A/R** | compliance-engineer (purge) | owner: `purge <tenant>` |
| Charter / scope amendment | **A/R** | lead (propose) | owner: `amend <charter>` |
| Emergency rollback | **A/R** | sre-engineer | owner: `rollback <sha>` |

---

## Decision rules

1. **Single A per row.** If two agents both want A, escalate to lead for tiebreak; record in `OWNER-SCOPE-AMEND-NNN`.
2. **Sumit is always A on owner-gating rows.** Even if delegate is automated (CI checks), owner signs-off before action.
4. **C is non-blocking by default** unless the consulted agent says BLOCK; in which case R pauses and lead arbitrates.
5. **I is informational.** No work blocked by I; recording only.
6. **AI agents may act as R in dev-time without further approval** for non-owner-gating work (test, lint, refactor within scope).
7. **AI agents NEVER act as A.** A is the owner or an explicit delegate the owner named (e.g. Sumit-as-sole-A in this charter).

> **Audit:** every entry must be traceable to a `15_OWNER_GATING_PROTOCOL.md` event log; reconciliation quarterly.