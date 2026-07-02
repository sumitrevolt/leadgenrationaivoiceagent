---
name: enterprise-readiness-audit
description: Master enterprise-grade SaaS audit — 12-domain scored matrix (security, tenant-isolation, DR, SLO, secrets, DPDP, capacity, migrations, supply-chain, billing-truth, compliance, support-ops) with per-domain skill dispatch. Use jab "enterprise grade hai kya", full platform audit, investor/customer due-diligence prep, ya quarterly deep-review chale.
---

# Enterprise Readiness Audit (12-domain, scored, dispatch-based)

> Orchestrator skill. `production-ready` = LAUNCH gate (bech sakte hain?); **yeh = ENTERPRISE gate (bade customer/due-diligence survive karega?)**. Har domain apni specialist skill pe dispatch hota — yahan sirf matrix + verdict. Pehle `context-first`.

## 12-domain matrix (score /10 each, evidence mandatory)
| # | Domain | Dispatch skill | Pass bar |
|---|---|---|---|
| 1 | Security & RBAC | `leadgen-security-rbac` | zero missing-auth on customer/admin routes |
| 2 | Tenant isolation | `tenant-isolation-audit` | zero cross-tenant leak paths, wrong-tenant tests green |
| 3 | DR & backups | `dr-restore-drill` | restore PROVEN <90d old, RTO measured |
| 4 | Reliability SLO | `slo-error-budget` | SLOs defined + burn alerts live + budget tracked |
| 5 | Secrets | `secrets-rotation` | inventory current, no key >90d without review |
| 6 | Data retention/DPDP | `data-retention-dpdp` | deletion runbook proven, 90d recording purge live |
| 7 | Capacity | `load-capacity-testing` | ceiling measured, headroom ≥40% at peak |
| 8 | DB migrations | `db-migration-safety` | last 3 migrations followed expand-contract + rollback |
| 9 | Supply chain | `supply-chain-security` | pip-audit clean of exploitable HIGH, images <90d |
| 10 | Billing truth | `leadgen-billing-upi` | packages.py↔plans↔tests aligned, GST rule-46 |
| 11 | Voice/comms compliance | `leadgen-voice-compliance` | TRAI gates INTACT (DND fail-closed, 9am–7pm, AI-disclosure) |
| 12 | Ops & incident | `prod-incident-triage` + `observability-ops` | runbooks current, alerts actionable, heartbeats green |

## Run modes
- **Quick (1 session)**: har domain 10-min evidence pull (koi deep fix nahi) → matrix + top-5 gaps → prioritized queue banao.
- **Deep (multi-session)**: domain-per-session, specialist skill full run, fixes SHIP karo (decide-and-ship — analysis pe mat ruko), har session SESSION_LOG entry.
- **Due-diligence prep**: matrix + evidence links ek doc me (`docs/`) — customer/investor security-questionnaire ka ready answer bank.

## Scoring honesty rules
- Evidence ke bina score = 0 us domain me ("hona chahiye" ≠ "hai"). prod_check/final_integration_check PASS ≠ domain pass (improvement ≠ broken lesson).
- Single-VPS reality accept karo — 99.99% HA ka natak score inflate mat kare; measured 99.5% with proven restore > claimed 99.99% with nothing.
- Score <6 kisi domain me = us domain ki skill IMMEDIATELY dispatch, matrix report ke baad.

## Verdict format
Overall /120 → **Enterprise-ready ≥96 with NO domain <6**. Output: matrix table + top-5 gap list (effort × risk ranked) + shipped-this-session list + next-session queue.

## Related repo skills
`production-ready` (launch gate) · `executive-council` (strategic trade-offs) · `llm-council-decision` (ambiguous go/no-go) · saare 12 dispatch skills upar.
