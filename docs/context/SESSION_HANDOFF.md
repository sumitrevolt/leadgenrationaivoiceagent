# SESSION_HANDOFF — 2026-08-17 (DSH/admin/inbox/automation audit slice)

## Status
**LOCAL VERIFIED, DEPLOY PENDING.** This slice addresses the audit list's highest code-fixable items without arming DSH flags and without touching frozen Swara/voice paths. DSH authority is still not claimed promotion-ready until a bounded production canary proves capability submission after deploy.

## Changed files in this slice
- `app/platform/workforce_runtime/free_ai_proxy.py` — authoritative DSH runs force OpenAI `tool_choice` to `dsh_capability_submit` when the submit tool is exposed, preventing LLM 200 + prose-only/no-submit turns.
- `app/api/agents.py` — anonymous `/api/agents/status` keeps basic LangGraph availability but no longer exposes internal `workforce_runtime` provider/allowlist/frozen counts; admins still receive it.
- `frontend/admin_dashboard.html` — one Logout button, auth-only privileged controls (`Hot Queue`, `Add Customer`, manual call card) hidden until `/api/admin/me` auth boot succeeds, 15s bounded dashboard timeout, and horizontal overflow clamp.
- `frontend/inbox.html` — Hot Queue tab count/label uses server `summary.total_open` and scope (`Boss queue`/`Admin pending`) instead of loaded-item length.
- `frontend/automation.html` — today tab autoloads Production Launch Status and failure paths replace stuck loader/placeholders with honest fallback text.
- `tests/test_dsh_workforce_runtime.py`, `tests/test_agent_stack.py`, `tests/test_inbox_frontend.py` — updated/added regression coverage.
- `tests/test_admin_dashboard_auth_ui.py`, `tests/test_automation_mission_control_frontend.py` — new frontend contract tests.
- `progress.md` — Loop Run ledger appended.

## Verification evidence
- First targeted pytest failed once due to missing `asyncio` import in the new DSH unit test; fixed before final verification.
- `pytest tests/test_dsh_workforce_runtime.py tests/test_agent_stack.py tests/test_admin_dashboard_auth_ui.py tests/test_inbox_frontend.py tests/test_automation_mission_control_frontend.py -q --tb=short` → **54 passed**.
- `scripts/prod_check.py` → **ALL CHECKS PASSED**; 1322 routes checked; API.md 1344 ops in sync.
- `scripts/check_secrets.py` → **OK**, no secrets detected across 16 changed files.
- `scripts/check_html_js.py` → **JS_OK**.

## Safety notes
- `DSH_RUNTIME_ENABLED`, `DSH_SHADOW_ENABLED`, allowlist/promotion flags were not armed locally or in prod by this slice.
- Legacy/direct executor remains real operational authority until post-deploy DSH canary proves capability submission and owner gates retirement.
- Swara/voice issues from the audit (opener claim, typed-mode mic privacy, guarantee refusal) were not edited because Swara/voice is frozen; require explicit Owner gate.
- No Stripe/Razorpay restoration, paid AI provider, cold/bulk WhatsApp auto-send, or compliance weakening.
- Existing unrelated dirty files/surfaces were not reviewed as part of this slice: `app/api/dsh_internal.py`, `tests/test_platform_pitch_flow.py`, `tests/test_universal_pitch.py`, `docs/evidence/DSH_LIVE_ISSUES_20260817.md`.

## Next
If Owner asks: commit/push/deploy via canonical `scripts/deploy_vps.sh` with explicit `APP_VERSION=<sha>`, verify `/health.version`, smoke anonymous `/api/agents/status`, admin dashboard, inbox, automation page, then run a bounded DSH canary with runtime flags armed only for the canary and restored OFF immediately.
