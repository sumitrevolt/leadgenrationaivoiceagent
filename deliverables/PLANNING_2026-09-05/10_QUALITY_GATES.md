# Quality Gates — LeadGen AI (definitions + enforcement)

> **Source:** consolidates `docs/AGENT_WORK_RULES.md`, `docs/AGENT_LOOP_PROMPT_MASTER.md`, `docs/RACI_MATRIX.md`. **Owner:** qa-test-engineer (R), Sumit (A), code-reviewer (C).

## Gate levels

| Level | Name | Blocking? | When |
|---|---|---|---|
| G0 | Pre-commit (local) | NO (advisory) | Before push |
| G1 | PR CI | YES | Every PR |
| G2 | Main CI (gate job) | **YES** | Every push to main |
| G3 | Pre-deploy (release-gate) | **YES** | Before deploy |
| G4 | Post-deploy (smoke) | YES (auto-rollback) | T+0 to T+5min |
| G5 | Hourly canary | NO (alert) | Every hour |

---

## G0 — Pre-commit (local, advisory)

| Check | Tool | Threshold |
|---|---|---|
| Lint | ruff | 0 errors |
| Format | ruff format | matches style |
| Type hint check | mypy (incremental) | no new errors |
| Secret scan | detect-secrets | 0 hits |
| Coverage delta | coverage.py | no drop > 1% on touched |

**Enforcement:** `pre-commit` hook. Failing pre-commit = warning, not block; PR CI will catch.

---

## G1 — PR CI (every PR)

| Gate | Tool | Threshold | Blocking? |
|---|---|---|---|
| Lint | ruff check | 0 errors | YES |
| Secret scan | detect-secrets + gitleaks | 0 hits | YES |
| Syntax | python -m py_compile | all files | YES |
| SAST (Python) | bandit | 0 high/critical | YES |
| SAST (cross-lang) | CodeQL | 0 high/critical | YES |
| Dep CVE | pip-audit | 0 critical | YES |
| Image CVE | trivy-action | 0 critical | YES |
| Unit tests | pytest | 100% pass | YES |
| Integration tests | pytest --splits 4 | 100% pass | YES |
| Coverage | coverage.py | ≥ 80% touched | YES |
| Contract (billing) | pytest -q tests/test_billing_truth_2026.py | 100% pass | **YES** |
| Runtime-data ratchet | scripts/skill_evals + ratchet | 0 net-new UNDECLARED | **YES** |
| Prod check | python scripts/prod_check.py | all checks pass | **YES** |
| Gate A (sketch) | pr-factory-gate-a | advisory | NO |
| LLM eval (advisory) | llm-eval.yml (deterministic-only) | 100% pass | NO |

**Owner-blocking gates:** lint, secrets, billing, runtime-data, prod_check, dependency CVE (critical), pytest.

**PR auto-merge**: only Dependabot PRs (`auto-merge.yml`); all human/AI PRs require explicit owner merge.

---

## G2 — Main CI (every push to main)

Same as G1 PLUS:

| Gate | Tool | Threshold | Blocking? |
|---|---|---|---|
| Skill quality | scripts/skill_evals/check_repo_skills.py | 0 new/modified skills without owner review | YES |
| Synthetic voice canary | scripts/synthetic_vobiz_canary.py | green (or skip if kill-switch ON) | YES |
| Migration dry-run | scripts/migration_dry_run.py | clean | YES (when migrations change) |
| Image build | docker build | success | YES |

**Release-gate (depends on G2):** green = proceed to deploy (if DEPLOY_ENABLED).

---

## G3 — Pre-deploy (release-gate)

| Gate | Tool | Threshold |
|---|---|---|
| G2 all green | (from G2) | required |
| CHANGELOG updated | grep CHANGELOG.md | last commit has entry |
| ADR added (if needed) | grep docs/ADR-*.md | if schema/migration/RBAC change |
| Deploy packet | deliverables/DEPLOY_PACKET_*.md | exists for this release |
| Owner sign-off | (manual) | Sumit `deploy` / `ship` |

**If any G3 fails:** block deploy; RCAs required.

---

## G4 — Post-deploy (5-min auto-smoke)

| Check | URL/command | Threshold |
|---|---|---|
| `/health/ready` | GET /health/ready | 200, < 1s |
| Dashboard sample | GET /api/dashboard/sample | 200, JSON valid |
| Billing truth inline | pytest -q tests/test_billing_truth_2026.py | green |
| Voice canary | synthetic Vobiz call | green or kill-switched |
| Runtime-data ratchet | scanner | 0 net-new UNDECLARED |
| First tenant dashboard | end-to-end check | 200, < 1.5s p95 |

**If G4 fails:** auto-rollback to previous image, auto-page Sumit, RCA within 60 min.

---

## G5 — Hourly canary

| Check | Source | Threshold |
|---|---|---|
| API health | GET /health/ready (5 endpoints) | 100% pass |
| Synthetic voice canary | Vobiz DID | call completes, audio OK |
| Synthetic payment | Razorpay sandbox | webhook received |
| Synthetic WhatsApp | WAHA sandbox | message echoed |
| Disk + memory | VPS metrics | < 70% utilization |
| DB connection | pgbouncer | < 50 used of 100 |

**Owner-page:** if any check fails 2 consecutive hours → page Sumit.

---

## SLO targets

| Path | p50 | p95 | p99 | Error rate |
|---|---|---|---|---|
| `/api/dashboard/*` | < 200ms | < 800ms | < 1.5s | < 0.1% |
| `/api/voice/*` | < 100ms | < 400ms | < 800ms | < 0.5% |
| `/api/admin/*` | < 500ms | < 1.5s | < 3s | < 0.1% |
| Webhook handlers | < 50ms | < 200ms | < 500ms | < 0.05% |
| Worker task | < 1s dispatch | < 5s | < 30s | < 0.5% |

**SLO breach** = P2 incident; auto-page if sustained > 5 min.

---

## Error budget

- **Monthly error budget**: 99.9% availability = 43.83 min/month downtime
- **Burn rate alerts**: 2× burn = warn, 5× burn = freeze deploys
- **Freeze**: at 50% budget consumed in first week → 1-week deploy freeze
- **Reset**: end of month, error budget refills

---

## Coverage requirements

| Path | Min coverage | Why |
|---|---|---|
| Billing | 100% | Revenue |
| Auth + RBAC | 100% | Security |
| DPDP | 100% | Compliance |
| Voice | 90% | Quality + cost |
| Marketing | 80% | Revenue |
| Platform | 85% | Cross-cutting |
| Integrations | 70% | Adapter code |

**Coverage drop > 1% on touched files** = PR blocked. Must justify (`# pragma: no cover` requires ADR + reason).

---

## Performance budgets

| Action | Budget |
|---|---|
| API endpoint response | < 800ms p95 |
| DB query | < 100ms p95 |
| Worker task | < 30s p99 |
| Webhook handler | < 200ms p95 |
| Image build | < 5 min |
| Deploy | < 3 min |
| Smoke verify | < 5 min |
| Total lead time (commit → prod) | < 4 hours |

**Budget breach** = review in retro; charter amendment if persistent.

---

## Security gates

| Gate | Tool | Frequency | Blocking? |
|---|---|---|---|
| SAST (Python) | bandit | per PR | YES |
| SAST (CodeQL) | GitHub CodeQL | per PR | YES |
| Dep audit | pip-audit | per PR | YES (critical) |
| Image scan | trivy | per PR | YES (critical) |
| DAST | zap-baseline | weekly | YES (high/critical) |
| Auth bypass test | custom | per PR | YES |
| Tenant isolation test | custom | per PR | YES |
| IDOR probe | custom | per PR | YES |
| Pentest | external | quarterly | advisory |

**Critical CVE in production** = P0 incident, 24h SLA.

---

## Compliance gates

| Gate | Check | Owner | Blocking? |
|---|---|---|---|
| DPDP consent | Onboarding flow includes explicit consent | compliance-engineer | YES |
| DPDP purge | Customer deletion is 8-step idempotent | compliance-engineer | YES |
| Recording retention | Voice recordings ≤ 90 days auto-cleanup | compliance-engineer | YES |
| Audit log integrity | HMAC chain unbroken | compliance-engineer | YES |
| Pricing disclosure | Pricing in T&C matches `packages.py` | billing-engineer | YES |
| DLT compliance | All voice templates DLT-registered before send | telephony-engineer | YES |

---

## Owner-gating gates (separate from automated)

| Action | Owner word |
|---|---|
| Push to remote | `push` |
| Trigger deploy | `deploy` / `ship` / `go` / `M{n}` |
| Outbound bulk send | `send` |
| Refund / chargeback | `refund <amount>` |
| Pricing change | `price <change>` |
| Feature flag flip | `arm <flag>` |
| Voice arm | `arm voice <tenant>` |
| Customer deletion | `purge <tenant>` |
| Charter amendment | `amend <charter>` |
| Emergency rollback | `rollback <sha>` |

**Enforcement:** CI/scripts verify owner trigger word before action; auto-reject if missing.

---

## Quality gate summary table

| Gate | Blocking? | Owner | Failure response |
|---|---|---|---|
| Pre-commit | NO (advisory) | developer | Fix before push |
| Lint (CI) | YES | staff-engineer | Fix or exempt |
| SAST | YES | security-engineer | Fix or risk-accept |
| Dep CVE | YES (critical) | sre-engineer | Patch or pin |
| Test pass | YES | qa-test-engineer | Fix |
| Coverage | YES | qa-test-engineer | Add tests or exempt |
| Contract (billing) | **YES** | billing-engineer | Fix or stop |
| Runtime-data ratchet | **YES** | platform-engineer | Fix or stop |
| Prod check | **YES** | sre-engineer | Fix or stop |
| Release-gate | **YES** | Sumit | Sign-off or stop |
| Post-deploy smoke | YES | sre-engineer | Auto-rollback |
| Hourly canary | NO (alert) | sre-engineer | Triage within 1h |
| SLO breach | YES (freeze) | sre-engineer | Page + freeze |
| Owner-gate (deploy) | **YES** | Sumit | Block deploy |
| DPDP | **YES** | compliance-engineer | Fix |

---

## Quality gate review cadence

- **Daily**: SRE reviews failed gates; triage within 24h
- **Weekly**: code-reviewer reviews gate failures; pattern analysis
- **Per sprint**: lead reviews SLO burn + error budget; mid-sprint adjustment if needed
- **Quarterly**: full quality review; gate threshold tuning; charter amendment if needed

---

## Anti-patterns (gates we will NOT relax)

1. ❌ Skip prod_check because it's "flaky" (fix the flakiness)
2. ❌ Allow runtime-data debt to grow "temporarily" (ratchet is BLOCKING)
3. ❌ Disable billing-truth test "just this once" (it's the source of revenue truth)
4. ❌ Bypass DPDP purge for "trusted" customers (always idempotent 8-step)
5. ❌ Loosen coverage for "non-critical" code (use ADR + exemption, not exception)
6. ❌ Auto-merge non-Dependabot PRs (always owner merge)
7. ❌ Deploy without smoke (auto-rollback is the backstop, but smoke is the front-line)
8. ❌ Freeze owner-gating because of urgency (15-min pause to verify never costs more than a botched deploy)