# 2026-08-06 Free-Stack Upgrades — Wiring Gaps Plan

> Loop-run plan. Trigger: "sab karo one by one" for the free-stack improvements list.
> Audit pehle → 6 me se 2 invalid (evidence), 4 genuine wiring gaps. Ye doc final scope hai.

## Audit verdict (evidence-based)

| # | Original suggestion | Verdict | Evidence |
|---|---|---|---|
| 1 | DeepSeek as LLM primary | **ABORT** | `app/platform/safe_ai_payload.py:64` — `_UNSAFE_PROVIDERS` includes Chinese providers (PII security gate). Adding as primary = §5 security gate violation. FORBIDDEN. |
| 2 | Whisper.cpp local STT fallback | **SKIP** | Local STT ALREADY exists: `app/telephony/vobiz_stream.py` `_stt_chain()` last link = vosk/faster-whisper (always-on local). Duplicate. |
| 3 | Formal tool registry | **PARTIAL-GAP** | `CanonicalToolRegistry` exists; only `agent.delegate.dev` registered (GREEN/read-only, hashtags.research). `_tool_isha` → `post_generator.generate_post` = PURE read-only content-gen (no writes/sends) → honestly registerable as `agent.delegate.isha`. kavya/arjun/meera stay OUT: `_tool_kavya`→`staff.run_ops()` has data-retention PRUNING (DELETE side-effect), `_tool_arjun`→`run_qa` writes eval records, `_tool_meera`→`run_trainer` writes. Registry's conservative design is CORRECT for those. |
| 4 | Agent handoff protocol | **GAP** | `coordinator.coordinate()`/`fan_out()` pass raw result dicts via shared blackboard (`prior = json.dumps(results[-3:])[:1200]`) — no structured handoff metadata, no redaction of team context passed to next agent's LLM. |
| 5 | Guardrails pipeline | **GAP** | `app/voice_agent/guardrails.py` (Guardrails class, `check_input` L356 PII-redact/injection-block/profanity, `check_output` L435) used in voice (`natural_dialog.py`) but NOT wired into `coordinator._llm()` (L199) — agent/coordinator LLM path is unguarded. |
| 6 | OTel GenAI tracing | **GAP** | `app/agents/harness/audit.py:46` calls `obs.set_current_attributes`/`obs.annotate` — **NEITHER EXISTS** in `observability_llm.py` = dead call, `gen_ai.run.id` never stamped. `_otel_start` uses `start_span` not `start_as_current_span` → spans not parented under request context. Zero tests for `observability_llm`. |

## Genuine work — 4 items (all additive, flag-gated/INERT)

### Item A — Register `agent.delegate.isha` (GREEN, read-only)
- `app/agents/harness/registry.py`: 6th family in `_register_builtins()` — `agent.delegate.isha@1.0.0`, GREEN/READ_ONLY/INTERNAL_AUTONOMOUS, executor_ref `app.agents.coordinator._tool_isha (post_generator.generate_post, content-gen only)`, network_policy restricted. Comment documents why kavya/arjun/meera stay OUT.
- `app/agents/harness/adapters/coordinator_shadow.py`: `COORDINATOR_TOOL_MAP` += `"isha": ("agent.delegate.isha", "1.0.0")`.
- `tests/test_harness_manifest_determinism.py`: update `GOLDEN_MANIFEST` (recompute) + add `agent.delegate.isha` to `CANONICAL_TOOLS` + `test_isha_green_readonly`.
- `tests/test_harness_coordinator_registry.py`: add isha shadow-resolution assertion.

### Item B — Structured redacted handoff context (additive)
- `app/agents/coordinator.py` `coordinate()`/`fan_out()`: each blackboard result gets additive `handoff` key `{from_agent, seq, context_preview}` where `context_preview` = guardrails-redacted bounded text of prior results. Pure additive metadata; `execute=False` behavior unchanged. Uses `app.voice_agent.guardrails.redact_pii` (import-safe, lazy, fail-open).

### Item C — Coordinator `_llm()` guardrails (flag-gated)
- New flag `COORD_GUARDRAILS` (default OFF, INERT) → `app/api/automation_flags.py`.
- `coordinator._llm()`: when flag ON → `get_guardrails().check_input(user)` (use `.text`, block on injection) + `check_output(reply)` redact. Fail-open (any guardrail error = original text). When OFF = byte-identical.
- Test: flag ON → PII in user prompt redacted before `free_ai.chat`; flag OFF → unchanged.

### Item D — OTel fixes + tests
- `app/observability_llm.py`: add `set_current_attributes(**attrs)` + `annotate(**attrs)` — set attrs on the current OTel span (via `trace.get_current_span()`), no-op when OTel disabled. Fix `_otel_start` to `start_as_current_span` (parented under request trace). Add to `__all__`.
- `tests/test_observability_llm.py` (NEW): disabled → no-op; enabled (fake otel modules) → attrs stamped on current span; llm_span parenting.

## Verify gate
1. Targeted pytest: `test_harness_manifest_determinism.py`, `test_harness_coordinator_registry.py`, `test_coordinator_helpers.py`, new guardrail + observability tests.
2. `ruff check app tests/test_observability_llm.py`
3. `scripts/prod_check.py` import gate
4. Duplicate-route grep (no new routes added — registry only)
5. `check_secrets.py` clean

## Rollback
- Item A: revert registry block + `COORDINATOR_TOOL_MAP` + manifest test golden value.
- Item B/C/D: revert commits. All INERT/flag-gated — prod byte-identical when flags OFF.

## Out of scope
- Prod deploy (user ask pending). Local verify only.
- kavya/arjun/meera registration (side-effectful — stays UNREGISTERED by design).
- New LLM provider (free stack stays; audit found no missing free provider).
