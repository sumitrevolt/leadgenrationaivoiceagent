from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dsh_internal
from app.platform.workforce_runtime import free_ai_proxy, run_store, scheduled, tokens
from app.platform.workforce_runtime.types import WorkforceRequest, WorkforceResult
from app.tasks import dsh_jobs
from app.worker import celery_app

dispatch = importlib.import_module("app.platform.workforce_runtime.dispatch")


@pytest.fixture(autouse=True)
def _memory_backends(monkeypatch):
    monkeypatch.setenv("DSH_TOKEN_BACKEND", "memory")
    monkeypatch.setenv("DSH_RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME", "1")
    monkeypatch.delenv("DSH_RUNTIME_ENABLED", raising=False)
    monkeypatch.delenv("DSH_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("DSH_AGENT_ALLOWLIST", raising=False)
    tokens.reset_memory_for_tests()
    run_store.reset_memory_for_tests()


def _request(**overrides) -> WorkforceRequest:
    values = {
        "agent_id": "kavya",
        "action": "ops_health_check",
        "payload": {"opaque_ref": "lead_123"},
        "tenant_id": "tenant-a",
        "idempotency_key": "idem_12345678",
        "trigger": "owner_os",
    }
    values.update(overrides)
    return WorkforceRequest(**values)


def _queued_result(request: WorkforceRequest, **overrides) -> WorkforceResult:
    values = {
        "agent_id": request.agent_id,
        "action": request.action,
        "status": "queued",
        "provider": "dsh",
        "run_id": "dshrun_1234567890abcdef1234",
        "queue": "dsh",
        "runtime_version": "47f94385",
        "rollout_wave": "wave_1_read_only",
    }
    values.update(overrides)
    return WorkforceResult(**values)


def test_dsh_tasks_bind_configured_celery_app():
    assert dsh_jobs.run_dsh_workforce.app is celery_app
    assert dsh_jobs.execute_governed_capability.app is celery_app
    assert str(celery_app.conf.broker_url).startswith("redis://")


def test_run_token_is_hash_only_bound_and_revocable(monkeypatch):
    token, binding = tokens.issue(
        run_id="dshrun_1234567890abcdef1234",
        tenant_id="tenant-a",
        agent_id="kavya",
        allowed_tools=("dsh_heartbeat",),
        deadline=time.time() + 60,
        ttl_s=60,
    )
    binding = tokens.authenticate(token, required_tool="dsh_heartbeat")
    assert binding.tenant_id == "tenant-a"
    assert binding.agent_id == "kavya"
    assert token not in json.dumps(tokens._MEMORY)
    assert tokens._key(token) in tokens._MEMORY

    with pytest.raises(PermissionError, match="tool_not_allowed"):
        tokens.authenticate(token, required_tool="dsh_llm_chat")
    tokens.revoke(token)
    with pytest.raises(PermissionError, match="run_token_expired_or_unknown"):
        tokens.authenticate(token)


def test_run_token_expiry_is_fail_closed(monkeypatch):
    token, _binding = tokens.issue(
        run_id="dshrun_1234567890abcdef1234",
        tenant_id="",
        agent_id="kavya",
        allowed_tools=("dsh_heartbeat",),
        deadline=time.time() + 60,
        ttl_s=60,
    )
    payload, _expires = tokens._MEMORY[tokens._key(token)]
    tokens._MEMORY[tokens._key(token)] = (payload, time.time() - 1)
    with pytest.raises(PermissionError, match="run_token_expired_or_unknown"):
        tokens.authenticate(token)


def test_run_store_exactly_once_and_hash_chain():
    request = _request()
    row, created = run_store.create_run(
        run_id="dshrun_1234567890abcdef1234",
        agent_id=request.agent_id,
        tenant_id=request.tenant_id,
        action=request.action,
        idempotency_key=request.idempotency_key,
        approval_ref=request.approval_ref,
        trigger=request.trigger,
        timeout_s=request.timeout_s,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 60,
        input_payload=request.payload,
    )
    assert created is True
    duplicate, created = run_store.create_run(
        run_id=row["run_id"],
        agent_id=request.agent_id,
        tenant_id=request.tenant_id,
        action=request.action,
        idempotency_key=request.idempotency_key,
        approval_ref=request.approval_ref,
        trigger=request.trigger,
        timeout_s=request.timeout_s,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 60,
        input_payload=request.payload,
    )
    assert created is False
    assert duplicate["request_hash"] == row["request_hash"]

    with pytest.raises(ValueError, match="immutable_collision"):
        run_store.create_run(
            run_id=row["run_id"],
            agent_id=request.agent_id,
            tenant_id=request.tenant_id,
            action="different_action",
            idempotency_key=request.idempotency_key,
            approval_ref=request.approval_ref,
            trigger=request.trigger,
            timeout_s=request.timeout_s,
            provider="dsh",
            shadow=False,
            deadline=time.time() + 60,
            input_payload=request.payload,
        )

    first = run_store.append_event(row["run_id"], "one", {"status": "queued"})
    second = run_store.append_event(row["run_id"], "two", {"status": "running"})
    assert first["seq"] == 1
    assert second["seq"] == 2
    assert second["prev_hash"] == first["event_hash"]


def test_run_and_submission_claims_are_single_owner():
    request = _request()
    run_id = "dshrun_claim1234567890abcdef"
    run_store.create_run(
        run_id=run_id,
        agent_id=request.agent_id,
        tenant_id=request.tenant_id,
        action=request.action,
        idempotency_key=request.idempotency_key,
        approval_ref=request.approval_ref,
        trigger=request.trigger,
        timeout_s=request.timeout_s,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 60,
        input_payload=request.payload,
    )
    _run, claimed = run_store.claim_run(run_id)
    assert claimed is True
    _run, claimed = run_store.claim_run(run_id)
    assert claimed is False

    submission_id = run_store.submission_id_for(run_id, request.action)
    run_store.create_submission(
        submission_id=submission_id,
        run_id=run_id,
        capability=request.action,
        task_id=run_store.submission_task_id_for(run_id, request.action),
    )
    _submission, claimed = run_store.claim_submission(submission_id)
    assert claimed is True
    _submission, claimed = run_store.claim_submission(submission_id)
    assert claimed is False


@pytest.mark.asyncio
async def test_dispatch_defaults_to_direct(monkeypatch):
    async def fake_direct(request):
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="succeeded",
            provider="direct",
            output={"ok": True},
        )

    monkeypatch.setattr(dispatch, "_direct", fake_direct)
    result = await dispatch.dispatch(_request())
    assert result.provider == "direct"


@pytest.mark.asyncio
async def test_dispatch_authority_is_idempotent(monkeypatch):
    monkeypatch.setenv("DSH_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("DSH_AGENT_ALLOWLIST", "kavya")
    calls: list[dict] = []

    class FakeTask:
        @staticmethod
        def apply_async(*, args, queue):
            calls.append({"args": args, "queue": queue})
            return SimpleNamespace(id="celery-dsh-1")

    monkeypatch.setattr(dsh_jobs, "run_dsh_workforce", FakeTask())
    monkeypatch.setattr(dispatch, "_dsh_preflight", lambda _request: None)
    request = _request()
    first = await dispatch.dispatch(request)
    second = await dispatch.dispatch(request)
    assert first.provider == "dsh" and first.status == "queued"
    assert second.run_id == first.run_id
    assert second.reason == "duplicate_submission"
    assert len(calls) == 1
    assert calls[0]["queue"] == "dsh"


@pytest.mark.asyncio
async def test_dsh_flags_without_explicit_allowlist_stay_direct(monkeypatch):
    monkeypatch.setenv("DSH_RUNTIME_ENABLED", "1")

    async def fake_direct(request):
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="succeeded",
            provider="direct",
        )

    monkeypatch.setattr(dispatch, "_direct", fake_direct)
    result = await dispatch.dispatch(_request())
    assert result.provider == "direct"


@pytest.mark.asyncio
async def test_dispatch_never_routes_frozen_voice(monkeypatch):
    monkeypatch.setenv("DSH_RUNTIME_ENABLED", "1")
    monkeypatch.setenv("DSH_AGENT_ALLOWLIST", "swara")

    async def fake_direct(request):
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="blocked",
            provider="direct",
            reason="red_lane_hard_off",
        )

    monkeypatch.setattr(dispatch, "_direct", fake_direct)
    result = await dispatch.dispatch(_request(agent_id="swara", action="frozen_transfer_status"))
    assert result.provider == "direct"


@pytest.mark.asyncio
async def test_shadow_runs_direct_and_queues_proposal_only(monkeypatch):
    monkeypatch.setenv("DSH_SHADOW_ENABLED", "1")
    monkeypatch.setenv("DSH_AGENT_ALLOWLIST", "kavya")
    queued: list[dict] = []

    async def fake_direct(request):
        return WorkforceResult(
            run_id=request.run_id,
            agent_id=request.agent_id,
            action=request.action,
            status="succeeded",
            provider="direct",
        )

    def fake_enqueue(request, *, shadow):
        queued.append({"request": request, "mode": "shadow" if shadow else "authority"})
        return _queued_result(request)

    monkeypatch.setattr(dispatch, "_direct", fake_direct)
    monkeypatch.setattr(dispatch, "_enqueue_dsh", fake_enqueue)
    result = await dispatch.dispatch(_request())
    assert result.provider == "direct"
    assert result.shadow_run_id
    assert queued[0]["mode"] == "shadow"


@pytest.mark.asyncio
async def test_scheduler_bridge_routes_only_allowlisted_safe_jobs(monkeypatch):
    monkeypatch.setattr(
        scheduled,
        "runtime_status",
        lambda: {
            "dsh_runtime_enabled": True,
            "dsh_shadow_enabled": False,
            "dsh_agent_allowlist": ["kavya"],
        },
    )
    monkeypatch.setattr(
        "app.platform.owner_agent_execution.agent_for_job",
        lambda job: "kavya" if job == "ops" else "rohan",
    )
    monkeypatch.setattr(scheduled, "_register", lambda agent_id, job, side: "scheduled__ops")
    seen: list[WorkforceRequest] = []

    async def fake_dispatch(request):
        seen.append(request)
        return _queued_result(request)

    monkeypatch.setattr(scheduled, "dispatch", fake_dispatch)
    routed = await scheduled.maybe_dispatch(
        "ops",
        idempotency_key="celery_task_123456",
    )
    assert routed is not None and routed.provider == "dsh"
    assert seen[0].trigger == "scheduler"
    assert await scheduled.maybe_dispatch("platform_dial") is None


def test_authority_run_exposes_generic_and_exact_submit_binding():
    allowed = dsh_jobs._allowed_tools({"action": "ops_health_check", "shadow": False})
    assert "dsh_capability_submit" in allowed
    assert "dsh_capability_submit:ops_health_check" in allowed


def test_shadow_run_never_exposes_capability_submit():
    allowed = dsh_jobs._allowed_tools({"action": "ops_health_check", "shadow": True})
    assert "dsh_capability_submit" not in allowed
    assert "dsh_capability_submit:ops_health_check" not in allowed


def test_child_environment_is_an_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "do-not-copy")
    monkeypatch.setenv("REDIS_URL", "do-not-copy")
    monkeypatch.setenv("UPI_VPA", "do-not-copy")
    env = dsh_jobs._child_env(
        "token-placeholder",
        mcp_url="http://app:8080/internal/dsh/mcp",
        llm_base_url="http://app:8080/internal/dsh/v1",
    )
    assert set(env) == dsh_jobs.CHILD_ENV_NAMES
    assert "DATABASE_URL" not in env
    assert "REDIS_URL" not in env
    assert "UPI_VPA" not in env


@pytest.mark.asyncio
async def test_free_ai_proxy_rejects_secrets_and_masks_pii(monkeypatch):
    with pytest.raises(free_ai_proxy.ProxyRefused, match="secret_material_refused"):
        await free_ai_proxy.complete(
            messages=[
                {"role": "user", "content": "api_key=" + "abcdefghijklmnopqrstuvwxyz" + "123456"}
            ],
            tools=None,
            allowed_tools=(),
        )

    from app.voice_agent import free_ai

    class FakeResponse:
        @staticmethod
        def model_dump(*_args, **_kwargs):
            return {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": "provider-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Contact owner@example.com or +919876543210",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeCompletions:
        @staticmethod
        async def create(**_kwargs):
            return FakeResponse()

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(free_ai, "_build_llm_chain", lambda _kind: [("fake", "fake-model")])
    monkeypatch.setattr(free_ai, "_provider_down", lambda _provider: False)
    monkeypatch.setattr(free_ai, "_client", lambda _provider: fake_client)
    monkeypatch.setattr(free_ai, "_reset_cooldown_streak", lambda _provider: None)
    result = await free_ai_proxy.complete(
        messages=[{"role": "user", "content": "Summarize opaque lead_ref_123"}],
        tools=None,
        allowed_tools=(),
    )
    content = result["choices"][0]["message"]["content"]
    assert "owner@example.com" not in content
    assert "+919876543210" not in content


def test_free_ai_proxy_refuses_provider_invented_tool_calls():
    value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "place_voice_call", "arguments": "{}"},
                        }
                    ],
                }
            }
        ]
    }
    with pytest.raises(free_ai_proxy.ProxyRefused, match="model_tool_not_allowed"):
        free_ai_proxy.validate_response_tools(
            value,
            allowed_tools=("dsh_heartbeat",),
        )


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(dsh_internal.router)
    return TestClient(app)


def _gateway_binding(*, allowed_tools: tuple[str, ...]) -> tuple[str, str]:
    request = _request()
    run_id = "dshrun_abcdef1234567890abcd"
    run_store.create_run(
        run_id=run_id,
        agent_id=request.agent_id,
        tenant_id=request.tenant_id,
        action=request.action,
        idempotency_key=request.idempotency_key,
        approval_ref=request.approval_ref,
        trigger=request.trigger,
        timeout_s=request.timeout_s,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 60,
        input_payload=request.payload,
    )
    token, _binding = tokens.issue(
        run_id=run_id,
        tenant_id=request.tenant_id,
        agent_id=request.agent_id,
        allowed_tools=allowed_tools,
        deadline=time.time() + 60,
        ttl_s=60,
    )
    return run_id, token


def test_dsh_authority_proxy_forces_capability_submit_tool(monkeypatch):
    captured = {}

    class _Response:
        def model_dump(self, mode="json"):
            return {
                "id": "chatcmpl-forced",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "dsh_capability_submit",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }

    class _Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Client:
        class chat:
            completions = _Completions()

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "_build_llm_chain", lambda _purpose: [("fake", "fake-model")])
    monkeypatch.setattr(free_ai, "_provider_down", lambda _provider: False)
    monkeypatch.setattr(free_ai, "_client", lambda _provider: _Client())
    monkeypatch.setattr(free_ai, "_reset_cooldown_streak", lambda _provider: None)

    result = asyncio.run(
        free_ai_proxy.complete(
            messages=[{"role": "user", "content": "Use the governed capability"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "dsh_capability_submit",
                        "description": "Submit governed capability",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            allowed_tools=("dsh_llm_chat", "dsh_capability_submit:ops_health_check"),
        )
    )

    assert captured["tool_choice"] == {
        "type": "function",
        "function": {"name": "dsh_capability_submit"},
    }
    assert (
        result["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
        == "dsh_capability_submit"
    )


def test_dsh_authority_proxy_synthesizes_submit_when_provider_ignores_tool_choice(monkeypatch):
    class _Response:
        def model_dump(self, mode="json"):
            return {
                "id": "chatcmpl-forced-fallback",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "I can help with that."},
                        "finish_reason": "stop",
                    }
                ],
            }

    class _Completions:
        async def create(self, **_kwargs):
            return _Response()

    class _Client:
        class chat:
            completions = _Completions()

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "_build_llm_chain", lambda _purpose: [("fake", "fake-model")])
    monkeypatch.setattr(free_ai, "_provider_down", lambda _provider: False)
    monkeypatch.setattr(free_ai, "_client", lambda _provider: _Client())
    monkeypatch.setattr(free_ai, "_reset_cooldown_streak", lambda _provider: None)

    result = asyncio.run(
        free_ai_proxy.complete(
            messages=[{"role": "user", "content": "Use the governed capability"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "dsh_capability_submit",
                        "description": "Submit governed capability",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            allowed_tools=("dsh_llm_chat", "dsh_capability_submit:ops_health_check"),
        )
    )

    choice = result["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] is None
    assert choice["message"]["tool_calls"][0]["function"] == {
        "name": "dsh_capability_submit",
        "arguments": "{}",
    }


def test_llm_gateway_records_protocol_shape_without_content_or_arguments(monkeypatch):
    run_id, token = _gateway_binding(
        allowed_tools=("dsh_llm_chat", "dsh_capability_submit:ops_health_check")
    )

    async def fake_complete(**_kwargs):
        return {
            "id": "chatcmpl-trace",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "private model explanation",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "dsh_capability_submit",
                                    "arguments": '{"private":"payload"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }

    monkeypatch.setattr(free_ai_proxy, "complete", fake_complete)
    response = _api_client().post(
        "/internal/dsh/v1/chat/completions",
        json={
            "model": "leadgen-free",
            "messages": [{"role": "user", "content": "Use the governed capability"}],
            "tools": [],
            "stream": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    row = run_store.get_run(run_id)
    event = row["audit_events"][-1]
    assert event["event"] == "dsh_llm_outcome"
    assert event["detail"] == {
        "finish_reason": "tool_calls",
        "tool_call_count": 1,
        "tool_names": ["dsh_capability_submit"],
        "content_present": True,
        "stream": True,
    }
    rendered = json.dumps(event)
    assert "private model explanation" not in rendered
    assert '"private":"payload"' not in rendered


def test_internal_gateway_requires_token_and_exact_tool(monkeypatch):
    client = _api_client()
    assert client.post("/internal/dsh/heartbeat", json={"phase": "running"}).status_code == 401
    _run_id, token = _gateway_binding(allowed_tools=("dsh_heartbeat",))
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/internal/dsh/heartbeat", json={"phase": "running"}, headers=headers)
    assert response.status_code == 200
    refused = client.post(
        "/internal/dsh/approval-proposals",
        json={
            "decision_type": "safe_review",
            "payload": {},
            "idempotency_key": "approval_123456",
        },
        headers=headers,
    )
    assert refused.status_code == 403


def test_capability_gateway_ignores_child_identity_and_enqueues_once(monkeypatch):
    _run_id, token = _gateway_binding(
        allowed_tools=(
            "dsh_capability_submit:ops_health_check",
            "dsh_capability_status",
        )
    )
    queued: list[dict] = []

    class FakeTask:
        @staticmethod
        def apply_async(*, kwargs, queue, task_id):
            queued.append({"kwargs": kwargs, "queue": queue, "task_id": task_id})
            return SimpleNamespace(id=task_id)

    monkeypatch.setattr(dsh_jobs, "execute_governed_capability", FakeTask())
    client = _api_client()
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/internal/dsh/capabilities/ops_health_check/submissions",
        headers=headers,
    )
    second = client.post(
        "/internal/dsh/capabilities/ops_health_check/submissions",
        headers=headers,
    )
    assert first.status_code == 200 and first.json()["created"] is True
    assert second.status_code == 200 and second.json()["created"] is False
    assert len(queued) == 1
    assert "tenant_id" not in queued[0]["kwargs"]
    submission_id = first.json()["submission_id"]
    status = client.get(f"/internal/dsh/submissions/{submission_id}", headers=headers)
    assert status.status_code == 200


def test_capability_enqueue_unknown_outcome_is_not_retried(monkeypatch):
    _run_id, token = _gateway_binding(allowed_tools=("dsh_capability_submit:ops_health_check",))

    class BrokenTask:
        @staticmethod
        def apply_async(**_kwargs):
            raise OSError("queue unavailable")

    monkeypatch.setattr(dsh_jobs, "execute_governed_capability", BrokenTask())
    client = _api_client()
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/internal/dsh/capabilities/ops_health_check/submissions",
        headers=headers,
    )
    second = client.post(
        "/internal/dsh/capabilities/ops_health_check/submissions",
        headers=headers,
    )
    assert first.status_code == 503
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["status"] == "enqueue_failed"


def test_submission_status_refuses_cross_run_token():
    run_a, token_a = _gateway_binding(allowed_tools=("dsh_capability_status",))
    request = _request(idempotency_key="other_12345678")
    run_b = "dshrun_other1234567890abcde"
    run_store.create_run(
        run_id=run_b,
        agent_id=request.agent_id,
        tenant_id="tenant-b",
        action=request.action,
        idempotency_key=request.idempotency_key,
        approval_ref="",
        trigger="owner_os",
        timeout_s=None,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 60,
        input_payload=request.payload,
    )
    submission_id = run_store.submission_id_for(run_b, request.action)
    run_store.create_submission(
        submission_id=submission_id,
        run_id=run_b,
        capability=request.action,
        task_id=run_store.submission_task_id_for(run_b, request.action),
    )
    assert run_a != run_b
    response = _api_client().get(
        f"/internal/dsh/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


def test_compose_is_internal_nonroot_and_has_no_application_env_file():
    compose = (Path(__file__).parents[1] / "docker-compose.vps.yml").read_text(encoding="utf-8")
    app_service = compose.split("\n  app:", 1)[1].split("\n  db:", 1)[0]
    assert "DSH_RUNTIME_ENABLED: ${DSH_RUNTIME_ENABLED:-0}" in app_service
    assert "DSH_SHADOW_ENABLED: ${DSH_SHADOW_ENABLED:-0}" in app_service
    service = compose.split("\n  dsh-worker:", 1)[1].split("\n  scheduler:", 1)[0]
    assert "networks: [dsh_net]" in service
    assert "read_only: true" in service
    assert 'user: "65532:65532"' in service
    assert "env_file:" not in service
    assert "APP_VERSION: ${APP_VERSION:?set APP_VERSION to the immutable git SHA}" in service
    assert "internal: true" in compose


def test_gateway_never_accepts_voice_or_billing_approval_proposals():
    _run_id, token = _gateway_binding(allowed_tools=("dsh_approval_proposal",))
    response = _api_client().post(
        "/internal/dsh/approval-proposals",
        json={
            "decision_type": "manual_upi_confirmation",
            "payload": {},
            "idempotency_key": "approval_123456",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "decision_type_never_delegated_to_dsh"


def test_exact_mcp_operation_inventory():
    assert set(dsh_internal.MCP_OPERATION_IDS) == {
        "dsh_capability_submit",
        "dsh_capability_status",
        "dsh_capability_wait",
        "dsh_approval_proposal",
        "dsh_heartbeat",
    }
    assert "dsh_llm_chat" not in dsh_internal.MCP_OPERATION_IDS


def test_manual_owner_and_scheduler_paths_share_workforce_dispatch():
    from app.api import owner_os, team
    from app.platform import agent_runtime, team_scheduler
    from app.tasks import staff_jobs

    assert "workforce_dispatch" in inspect.getsource(agent_runtime.submit)
    assert "agent_runtime.submit" in inspect.getsource(team.run_team_member)
    assert "agent_runtime.submit" in inspect.getsource(owner_os.owner_runtime_run)
    assert "maybe_dispatch" in inspect.getsource(team_scheduler._run_job)
    assert "idempotency_key=tid" in inspect.getsource(staff_jobs.run_staff_job)


def test_token_store_unavailable_fails_closed_503(monkeypatch):
    """Proof: Redis/token-store failure must fail closed (503), never open."""

    def _boom(raw_token, required_tool=""):
        raise tokens.TokenStoreUnavailable("store down")

    monkeypatch.setattr(dsh_internal.tokens, "authenticate", _boom)
    client = _api_client()
    response = client.post(
        "/internal/dsh/heartbeat",
        json={"phase": "running"},
        headers={"Authorization": "Bearer " + "x" * 40},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "run_token_store_unavailable"
