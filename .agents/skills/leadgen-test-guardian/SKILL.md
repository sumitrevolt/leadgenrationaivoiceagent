---
name: leadgen-test-guardian
description: Testing discipline enforce karo — unit/integration/route-smoke/Celery-task/scheduler/E2E tests, Docker health-checks, regression tests, production-readiness gates. Use jab test add/review karna ho ya "fix done" bolne se pehle proof chahiye.
---

# LeadGen Test Guardian

> Enterprise audit skill. Har fix ko PROOF chahiye. `test-driven-development`/`verify-ship` = workflow; **yeh = risk-matched coverage gate** (P1 revenue/auth/billing/automation/email/voice-compliance priority). Pehle `context-first`.

## Mission
Test-depth ko risk se match karo. Bina proof "done" mat bolo.

## Repo truth (verify loop)
- **Pre-flight**: `python scripts/prod_check.py` (parse/import/route/config + automation-gaps + cross-path). Route-count note karo.
- **Tests**: `scripts\run_tests.bat` → phir **`pytest_run.log` Read karo** (console truncate hota, log = truth). ~80+ green. Full pytest `team_pulse` area pe HANG ho sakta → targeted suite: `.venv\Scripts\python.exe -m pytest tests\test_X.py -q`.
- **Billing/pricing/route touch** → `test_billing_truth_2026.py` zaroor.
- **Cross-path parity**: `scripts/cross_path_audit.py` (final_integration_check me wired).
- **Voice change** → `scripts/agent_tester.py` (free scorecard: double/empty/repeat/long/slow).
- **Slash**: `/verify` (prod_check + targeted + check_secrets). DeepEval CI eval-gate (F.3).

## Required coverage
Pricing-truth + plan-gates · public routes + critical APIs · P1 customer journey · UPI activation + entitlement · content-gen + lead-capture · Celery task-registration + beat-schedule · email caps + provider fail-fast · voice compliance-preflight · auth/RBAC/tenant-isolation.

## Workflow
1. Changed behavior + affected contracts identify.
2. Smallest reliable test-level chuno: unit / integration / route-smoke / E2E / worker / scheduler / Docker-health.
3. Bug clear ho to regression test fix ke saath/pehle.
4. Targeted tests pehle, phir broader (jab shared behavior badla).
5. Commands + pass/fail + residual-risk report.

## Release gate
Fix "complete" tabhi jab relevant tests run hue ya "tests kyun nahi chal sakte" clearly stated. Green ke bina done MAT bolo.

## Output
Test matrix · commands run · failures+fixes · residual risk · readiness /100.

## Related repo skills (duplicate mat banao)
`test-driven-development` + `tdd-contract-first` (TDD) · `verify-ship` (deploy gate) · `verification-before-completion` (done-gate) · `pairwise-test-design` (case design) · har `leadgen-*` skill ka "tests" section yahan converge hota.
