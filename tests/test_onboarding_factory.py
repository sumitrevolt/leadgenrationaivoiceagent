"""Tests for the onboarding factory pipeline.

Covers:
  - Pipeline state tracking (PipelineState)
  - Stage executors (validate, kb_seed, content_pack, content_queue, niche_snapshot, complete)
  - Pipeline orchestrator (resume, skip completed, fail-at-stage)
  - Backpressure
  - Capacity metrics
  - Flag gating (ONBOARDING_PIPELINE)
  - Celery task wrapping (run_onboard_pipeline, run_single_stage)
  - Batch onboard with time budget
  - Tenant isolation (per-client pipeline state)
  - Idempotency (skip completed pipelines)
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_redis():
    """In-memory Redis mock for pipeline state."""
    store = {}

    class MockRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value

        def incr(self, key):
            v = int(store.get(key, 0)) + 1
            store[key] = str(v)
            return v

        def decr(self, key):
            v = int(store.get(key, 0)) - 1
            store[key] = str(v)
            return v

        def expire(self, key, ex):
            pass

        def llen(self, key):
            return 0

        def keys(self, pattern):
            prefix = pattern.replace("*", "")
            return [k for k in store if k.startswith(prefix)]

        def hincrby(self, key, field, amount=1):
            if key not in store:
                store[key] = {}
            if isinstance(store[key], dict):
                store[key][field] = int(store[key].get(field, 0)) + amount
            else:
                # Parse JSON
                data = json.loads(store[key]) if store[key] else {}
                data[field] = int(data.get(field, 0)) + amount
                store[key] = json.dumps(data)

        def hgetall(self, key):
            val = store.get(key)
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return {}
            return {}

        def zadd(self, key, mapping):
            pass

        def zremrangebyrank(self, key, start, end):
            pass

        def zrange(self, key, start, end, withscores=False):
            return []

    return MockRedis(), store


# ---------------------------------------------------------------------------
# PipelineState tests
# ---------------------------------------------------------------------------


class TestPipelineState:
    def test_load_new(self):
        from app.marketing.onboarding_factory import PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_123", r)
        d = state.load()
        assert d["cid"] == "client_123"
        assert d["stages"] == {}
        assert d["status"] == "new"

    def test_mark_stage_done(self):
        from app.marketing.onboarding_factory import PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_456", r)
        state.mark_stage("validate", "done", result={"ok": True})
        d = state.load()
        assert d["stages"]["validate"]["status"] == "done"
        assert d["status"] == "in_progress"

    def test_all_stages_completed(self):
        from app.marketing.onboarding_factory import STAGE_ORDER, PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_789", r)
        for s in STAGE_ORDER:
            state.mark_stage(s, "done")
        d = state.load()
        assert d["status"] == "completed"

    def test_stage_failed(self):
        from app.marketing.onboarding_factory import PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_fail", r)
        state.mark_stage("kb_seed", "failed", error="scrape timeout")
        d = state.load()
        assert d["stages"]["kb_seed"]["status"] == "failed"
        assert d["stages"]["kb_seed"]["error"] == "scrape timeout"

    def test_next_pending_stage(self):
        from app.marketing.onboarding_factory import PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_next", r)
        state.mark_stage("validate", "done")
        assert state.next_pending_stage() == "kb_seed"

    def test_stage_done_check(self):
        from app.marketing.onboarding_factory import PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_done", r)
        assert not state.stage_done("validate")
        state.mark_stage("validate", "done")
        assert state.stage_done("validate")

    def test_to_dict_progress(self):
        from app.marketing.onboarding_factory import STAGE_ORDER, PipelineState

        r, store = _mock_redis()
        state = PipelineState("client_pct", r)
        state.mark_stage("validate", "done")
        state.mark_stage("kb_seed", "done")
        d = state.to_dict()
        assert d["progress"] == f"2/{len(STAGE_ORDER)}"
        assert d["pct"] == round(2 / len(STAGE_ORDER) * 100)


# ---------------------------------------------------------------------------
# Backpressure tests
# ---------------------------------------------------------------------------


class TestBackpressure:
    def test_backpressure_ok_when_empty(self):
        from app.marketing.onboarding_factory import check_backpressure

        r, store = _mock_redis()
        ok, reason = check_backpressure(r)
        assert ok is True

    def test_backpressure_triggers_on_active_count(self):
        from app.marketing.onboarding_factory import (
            _MAX_CONCURRENT,
            check_backpressure,
            increment_active,
        )

        r, store = _mock_redis()
        for _ in range(_MAX_CONCURRENT):
            increment_active(r)
        ok, reason = check_backpressure(r)
        assert ok is False
        assert "active_pipelines" in reason

    def test_increment_decrement_active(self):
        from app.marketing.onboarding_factory import (
            REDIS_BACKPRESSURE_KEY,
            decrement_active,
            increment_active,
        )

        r, store = _mock_redis()
        increment_active(r)
        increment_active(r)
        assert int(store.get(REDIS_BACKPRESSURE_KEY, 0)) == 2
        decrement_active(r)
        assert int(store.get(REDIS_BACKPRESSURE_KEY, 0)) == 1

    def test_decrement_floor_at_zero(self):
        from app.marketing.onboarding_factory import REDIS_BACKPRESSURE_KEY, decrement_active

        r, store = _mock_redis()
        store[REDIS_BACKPRESSURE_KEY] = "0"
        decrement_active(r)
        assert int(store.get(REDIS_BACKPRESSURE_KEY, 0)) == 0


# ---------------------------------------------------------------------------
# Capacity metrics tests
# ---------------------------------------------------------------------------


class TestCapacityMetrics:
    def test_record_and_retrieve(self):
        from app.marketing.onboarding_factory import get_capacity_metrics, record_stage_metrics

        r, store = _mock_redis()
        record_stage_metrics("validate", 0.5, True, r)
        record_stage_metrics("validate", 0.8, True, r)
        record_stage_metrics("validate", 2.0, False, r)
        metrics = get_capacity_metrics(hours=1, r=r)
        assert "validate" in metrics["stages"]
        v = metrics["stages"]["validate"]
        assert v["ok"] == 2
        assert v["fail"] == 1
        assert v["total"] == 3
        assert v["failure_rate"] == pytest.approx(33.3, abs=0.1)

    def test_empty_metrics(self):
        from app.marketing.onboarding_factory import get_capacity_metrics

        r, store = _mock_redis()
        metrics = get_capacity_metrics(hours=1, r=r)
        assert metrics["summary"]["total_pipelines"] == 0
        assert metrics["summary"]["failure_rate"] == 0


# ---------------------------------------------------------------------------
# Stage executor tests (mocked dependencies)
# ---------------------------------------------------------------------------


class TestStageExecutors:
    @pytest.mark.asyncio
    async def test_validate_missing_client(self):
        from app.marketing.onboarding_factory import stage_validate

        with patch("app.marketing.clients_store") as mock_cs:
            mock_cs.get_client.return_value = None
            result = await stage_validate("nonexistent")
            assert result["ok"] is False
            assert "client_not_found" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_already_setup(self):
        from app.marketing.onboarding_factory import stage_validate

        with patch("app.marketing.clients_store") as mock_cs:
            mock_cs.get_client.return_value = {"id": "c1", "setup_done": True}
            result = await stage_validate("c1")
            assert result["ok"] is False
            assert "already_setup_done" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_force_skip(self):
        from app.marketing.onboarding_factory import stage_validate

        with patch("app.marketing.clients_store") as mock_cs:
            mock_cs.get_client.return_value = {
                "id": "c1",
                "setup_done": True,
                "business_name": "Test",
            }
            result = await stage_validate("c1", force=True)
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_validate_eligible_client(self):
        from app.marketing.onboarding_factory import stage_validate

        with patch("app.marketing.clients_store") as mock_cs:
            mock_cs.get_client.return_value = {
                "id": "c1",
                "setup_done": False,
                "business_name": "Test",
            }
            result = await stage_validate("c1")
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_content_queue(self):
        from app.marketing.onboarding_factory import stage_content_queue

        with (
            patch("app.marketing.clients_store") as mock_cs,
            patch("app.marketing.auto_content") as mock_ac,
        ):
            mock_cs.get_client.return_value = {"id": "c1"}
            mock_ac.seed_client_content = AsyncMock(return_value=5)
            result = await stage_content_queue("c1")
            assert result["ok"] is True
            assert result["items_created"] == 5


# ---------------------------------------------------------------------------
# Pipeline orchestrator tests
# ---------------------------------------------------------------------------


class TestPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_full_pipeline_mock(self):
        """Full pipeline with stage executors mocked."""
        import app.marketing.onboarding_factory as mod
        from app.marketing.onboarding_factory import run_pipeline

        mock_executors = {
            "validate": AsyncMock(return_value={"ok": True, "client_id": "c_full"}),
            "kb_seed": AsyncMock(return_value={"ok": True, "kb_chunks": 5}),
            "content_pack": AsyncMock(return_value={"ok": True, "html": "<h1>pack</h1>"}),
            "content_queue": AsyncMock(return_value={"ok": True, "items_created": 7}),
            "niche_snapshot": AsyncMock(return_value={"ok": True}),
            "complete": AsyncMock(return_value={"ok": True, "client_id": "c_full"}),
        }

        r, store = _mock_redis()
        with (
            patch.object(mod, "_redis", return_value=r),
            patch.object(mod, "record_stage_metrics"),
            patch.object(mod, "STAGE_EXECUTORS", mock_executors),
        ):
            result = await run_pipeline("c_full", force=True, send_welcome=True)

        assert result["overall_ok"] is True
        assert all(s["status"] == "done" for s in result["stages"].values())

    @pytest.mark.asyncio
    async def test_resume_from_completed_stages(self):
        """Pipeline resumes from last completed stage on re-run."""
        import app.marketing.onboarding_factory as mod
        from app.marketing.onboarding_factory import PipelineState, run_pipeline

        r, store = _mock_redis()
        state = PipelineState("c_resume", r)
        state.mark_stage("validate", "done")
        state.mark_stage("kb_seed", "done")

        mock_executors = {
            "validate": AsyncMock(return_value={"ok": True}),
            "kb_seed": AsyncMock(return_value={"ok": True}),
            "content_pack": AsyncMock(return_value={"ok": True}),
            "content_queue": AsyncMock(return_value={"ok": True}),
            "niche_snapshot": AsyncMock(return_value={"ok": True}),
            "complete": AsyncMock(return_value={"ok": True}),
        }

        with (
            patch.object(mod, "_redis", return_value=r),
            patch.object(mod, "record_stage_metrics"),
            patch.object(mod, "STAGE_EXECUTORS", mock_executors),
        ):
            result = await run_pipeline("c_resume", force=True)

        # Validate + kb_seed should be skipped
        assert result["stages"]["validate"]["status"] == "skipped"
        assert result["stages"]["kb_seed"]["status"] == "skipped"
        assert result["overall_ok"] is True

    @pytest.mark.asyncio
    async def test_pipeline_stops_on_stage_failure(self):
        """Pipeline stops at failed stage and doesn't continue."""
        import app.marketing.onboarding_factory as mod
        from app.marketing.onboarding_factory import run_pipeline

        mock_executors = {
            "validate": AsyncMock(return_value={"ok": False, "error": "client_not_found"}),
            "kb_seed": AsyncMock(return_value={"ok": True}),
            "content_pack": AsyncMock(return_value={"ok": True}),
            "content_queue": AsyncMock(return_value={"ok": True}),
            "niche_snapshot": AsyncMock(return_value={"ok": True}),
            "complete": AsyncMock(return_value={"ok": True}),
        }

        r, store = _mock_redis()
        with (
            patch.object(mod, "_redis", return_value=r),
            patch.object(mod, "record_stage_metrics"),
            patch.object(mod, "STAGE_EXECUTORS", mock_executors),
        ):
            result = await run_pipeline("c_nope", force=True)

        assert result["overall_ok"] is False
        assert result.get("failed_at") == "validate"
        # Content stages should not have run
        assert (
            "content_pack" not in result["stages"]
            or result["stages"].get("content_pack", {}).get("status") != "done"
        )


# ---------------------------------------------------------------------------
# Flag gating tests
# ---------------------------------------------------------------------------


class TestFlagGating:
    def test_pipeline_flag_off(self):
        from app.tasks.onboard_pipeline import run_onboard_pipeline

        with patch("app.tasks.onboard_pipeline._flag", return_value=False):
            result = run_onboard_pipeline("c1")
            assert result["skipped"] == "flag_off"

    def test_single_stage_flag_off(self):
        from app.tasks.onboard_pipeline import run_single_stage

        with patch("app.tasks.onboard_pipeline._flag", return_value=False):
            result = run_single_stage("c1", "validate")
            assert result["skipped"] == "flag_off"

    def test_batch_flag_off(self):
        from app.tasks.onboard_pipeline import batch_onboard

        with patch("app.tasks.onboard_pipeline._flag", return_value=False):
            result = batch_onboard(["c1", "c2"])
            assert result["skipped"] == "flag_off"


# ---------------------------------------------------------------------------
# Feature flag manifest test
# ---------------------------------------------------------------------------


class TestFeatureFlagManifest:
    def test_onboarding_pipeline_flag_registered(self):
        from app.platform.automation_flag_manifest import describe_flag

        meta = describe_flag("ONBOARDING_PIPELINE")
        assert meta.default_hint == "0"
        assert meta.risk_lane == "ops"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestPipelineAPI:
    def test_api_router_importable(self):
        from app.api.onboard_pipeline_api import router

        assert router is not None
        # Check routes exist (with prefix)
        routes = [r.path for r in router.routes]
        assert any("/status" in p for p in routes)
        assert any("/run" in p for p in routes)
        assert any("/metrics" in p for p in routes)
        assert any("/backpressure" in p for p in routes)


# ---------------------------------------------------------------------------
# Integration: pipeline state + metrics together
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    @pytest.mark.asyncio
    async def test_pipeline_state_with_metrics(self):
        """Verify metrics are recorded during pipeline execution."""
        from app.marketing.onboarding_factory import (
            STAGE_ORDER,
            PipelineState,
            get_capacity_metrics,
            record_stage_metrics,
        )

        r, store = _mock_redis()

        # Simulate a pipeline run
        state = PipelineState("c_integ", r)
        for i, stage in enumerate(STAGE_ORDER):
            state.mark_stage(stage, "running")
            record_stage_metrics(stage, 0.1 * (i + 1), True, r)
            state.mark_stage(stage, "done")

        # Verify state
        d = state.to_dict()
        assert d["status"] == "completed"
        assert d["pct"] == 100

        # Verify metrics
        metrics = get_capacity_metrics(hours=1, r=r)
        for stage in STAGE_ORDER:
            assert stage in metrics["stages"]
            assert metrics["stages"][stage]["ok"] > 0


# ---------------------------------------------------------------------------
# Tenant isolation test
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_separate_clients_separate_state(self):
        from app.marketing.onboarding_factory import PipelineState

        r, store = _mock_redis()
        s1 = PipelineState("client_A", r)
        s2 = PipelineState("client_B", r)
        s1.mark_stage("validate", "done")
        assert s2.stage_done("validate") is False

    @pytest.mark.asyncio
    async def test_redis_keys_scoped(self):
        from app.marketing.onboarding_factory import pipeline_key

        k1 = pipeline_key("client_A")
        k2 = pipeline_key("client_B")
        assert k1 != k2
        assert "client_A" in k1
        assert "client_B" in k2
