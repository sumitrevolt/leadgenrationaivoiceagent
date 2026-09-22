# Telegram vault runtime persistence

## Goal

Make Admin Key Manager secrets restart-persistent on the existing external runtime-data mount and let Telegram egress consume the rotated Notify credential without copying its value into code, docs, logs, or URLs.

## Risk tier

High-risk (secrets + production runtime). Rollback: restore the prior Key Manager path and keep Telegram env-token resolution authoritative; no database/data migration and no production deploy in this session. Before any later deploy, copy the existing encrypted envelope—not plaintext—from the running container into the external runtime-data `secrets/` directory and verify mode `0600`.

## File map

- `app/platform/key_manager.py` — resolve the default encrypted vault beneath canonical `LEADGEN_RUNTIME_DATA_DIR`; provide env-first, vault-second in-process secret resolution.
- `app/platform/telegram_coordinator.py` — use the shared resolver for Notify/fallback egress slots while keeping Jarvis polling env-only.
- `app/utils/telegram_egress.py` — use the same resolver for all egress send helpers.
- `tests/test_key_manager_security.py` — prove runtime-root persistence and fail-closed production behavior.
- `tests/test_telegram_dual_bot.py` — prove vault fallback and env precedence without network calls.
- `tests/test_telegram_egress.py` — prove the send utility sees the same vault fallback without exposing values.
- `docs/context/SESSION_HANDOFF.md` — record deploy/migration gate and local verification.

## Tasks

1. Add failing tests for runtime-root default, env precedence, vault fallback, and missing-secret behavior. Run targeted tests and confirm failures are due to missing behavior.
2. Implement the minimal runtime-path and resolver changes; keep raw values in-process only and never log them.
3. Run targeted tests, Ruff, secret scan, `prod_check.py`, diff check, and the 1000-engineer preflight.
4. Record exact evidence and the required pre-deploy encrypted-envelope copy. Do not commit, push, deploy, or mutate production.

## Wiring and operational gates

- Existing compose services already mount `${LEADGEN_RUNTIME_DATA_HOST_DIR}` at `LEADGEN_RUNTIME_DATA_DIR`; no new volume or route is required.
- Environment variables remain first priority, so rollback and emergency recovery keep working.
- Telegram polling token remains env-only to avoid changing the single-poller authority path.
- Runtime vault read failures degrade to “token absent”; they never bypass owner authorization or compliance gates.
