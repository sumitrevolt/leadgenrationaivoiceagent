---
description: Kisi module ke tests expand karo — untested branches/edge-cases target karke, project pytest gotchas ke saath.
---
# /test-expand — coverage expand loop (LeadGen AI tailored)

Naya engine/feature ship hua par tests thin hain? Yeh loop chalao. Detail skills: `tdd-contract-first`, `llm-error-analysis`.

## Steps
1. **Target chuno**: `$ARGUMENTS` ka module (e.g. `app/billing/usage.py`) ya last commit ke changed `app/` files.
2. **Coverage dekho**: `.venv\Scripts\python.exe -m pytest tests\test_X.py --cov=app.module --cov-report=term-missing -q` (pytest-cov na ho to: code padh ke branches manually list karo — error paths, gates, fallbacks).
3. **Gap classes (is codebase ke real patterns)**:
   - **Gated flags**: flag OFF = zero behaviour change assert + flag ON path.
   - **Fail-open/never-raise**: dependency missing/exception pe graceful return (billing fail-open, tenant fail-open jaise).
   - **Boundary**: quota 0/exact-cap/topup-expire, period watermark missing (backward-compat), dedupe keys.
   - **LLM fallback**: provider error → static fallback chalta hai (sales_team pattern).
   - **Price-locks**: pricing change = `test_billing_truth` style contract test SAATH.
4. **Likho existing pattern me**: same file me append ya naya `tests/test_<feature>.py`; conftest already scheduler/automation OFF force karta — network calls mock karo (CI hang lesson).
5. **Verify**: targeted run green + poora `scripts\run_tests.bat` regression (pytest_run.log Read karo). ⚠️ Windows py3.11 me pytest-timeout flag NAHI — ini-keys pyproject me hain, addopts me mat daalo.

Output: naye test code blocks + 1-line "kya cover hua" summary. Coverage % measurably badhna chahiye.

`$ARGUMENTS`: module path ya feature naam.

*Adapted from luongnv89/claude-howto (MIT) — project test-infra gotchas ke saath.*
