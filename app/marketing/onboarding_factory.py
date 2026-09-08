"""Onboarding Factory Pipeline — staged orchestrator for customer onboarding.

PROBLEM: auto_onboard() is a monolithic function — if KB seed fails, the entire
onboard fails and retries from scratch. At 50/day scale, we need:
  - Resume from last successful stage (not restart everything)
  - Per-stage retry with backoff
  - DLQ per-stage (not per-client)
  - Backpressure when queue is flooded
  - Capacity metrics (p50/p95 latency per stage, throughput, failure rate)
  - Tenant isolation (pipeline state scoped by client_id)

DESIGN: Pipeline tracks stage progress in Redis. Each stage is independently
retryable. The orchestrator is a pure function (no Celery dependency) — the
Celery task in app/tasks/onboard_pipeline.py wraps it.

Stages (execution order):
  1. VALIDATE    — client exists, not already setup_done, tenant check
  2. KB_SEED     — website scrape → vector KB + knowledge graph
  3. CONTENT_PACK — first content pack (HTML)
  4. CONTENT_QUEUE — seed content calendar (7-day queue)
  5. NICHE_SNAPSHOT — apply niche template
  6. COMPLETE    — mark setup_done, delivery ledger, welcome WhatsApp

Feature flag: ONBOARDING_PIPELINE=0 (default OFF, opt-in)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ── Stage definitions ──────────────────────────────────────────────────


class Stage(str, Enum):
    VALIDATE = "validate"
    KB_SEED = "kb_seed"
    CONTENT_PACK = "content_pack"
    CONTENT_QUEUE = "content_queue"
    NICHE_SNAPSHOT = "niche_snapshot"
    COMPLETE = "complete"


ALL_STAGES = list(Stage)
STAGE_ORDER = [s.value for s in Stage]


# ── Redis keys (tenant-isolated) ───────────────────────────────────────

REDIS_KEY_PREFIX = "onboard:pipe:"
REDIS_METRICS_PREFIX = "onboard:metrics:"
REDIS_BACKPRESSURE_KEY = "onboard:active_count"
PIPELINE_TTL_S = 24 * 3600  # 24h — pipeline state expires
METRICS_TTL_S = 7 * 24 * 3600  # 7 days — metrics retention


def _redis():
    try:
        import redis as _redis

        from app.config import settings

        return _redis.Redis.from_url(
            str(settings.redis_url), decode_responses=True, socket_timeout=3
        )
    except Exception:
        return None


def pipeline_key(cid: str) -> str:
    """Redis key for pipeline state of a client."""
    return f"{REDIS_KEY_PREFIX}{cid}"


def metrics_key(stage: str, bucket: str) -> str:
    """Redis key for metrics bucket. bucket = 'YYYY-MM-DD-HH'."""
    return f"{REDIS_METRICS_PREFIX}{stage}:{bucket}"


# ── Pipeline state ─────────────────────────────────────────────────────


class PipelineState:
    """Tracks which stages are done/failed/pending for one client."""

    def __init__(self, cid: str, r=None):
        self.cid = cid
        self.r = r or _redis()
        self.key = pipeline_key(cid)

    def load(self) -> dict[str, Any]:
        if not self.r:
            return {"cid": self.cid, "stages": {}, "status": "no_redis"}
        try:
            raw = self.r.get(self.key)
            if raw:
                data = json.loads(raw)
                data["cid"] = self.cid
                return data
        except Exception:
            pass
        return {"cid": self.cid, "stages": {}, "status": "new"}

    def save(self, state: dict[str, Any]) -> None:
        if not self.r:
            return
        try:
            self.r.set(self.key, json.dumps(state, default=str), ex=PIPELINE_TTL_S)
        except Exception:
            pass

    def stage_done(self, stage: str) -> bool:
        state = self.load()
        s = state.get("stages", {}).get(stage, {})
        return s.get("status") == "done"

    def last_completed_stage(self) -> str | None:
        state = self.load()
        stages = state.get("stages", {})
        for s in STAGE_ORDER:
            if stages.get(s, {}).get("status") != "done":
                return None
        # All done
        return STAGE_ORDER[-1] if stages.get(STAGE_ORDER[-1], {}).get("status") == "done" else None

    def next_pending_stage(self) -> str | None:
        state = self.load()
        stages = state.get("stages", {})
        for s in STAGE_ORDER:
            if stages.get(s, {}).get("status") != "done":
                return s
        return None

    def mark_stage(
        self, stage: str, status: str, result: Any = None, error: str | None = None
    ) -> None:
        state = self.load()
        if "stages" not in state:
            state["stages"] = {}
        state["stages"][stage] = {
            "status": status,  # "done" | "failed" | "running" | "pending"
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if result is not None:
            state["stages"][stage]["result"] = result
        if error:
            state["stages"][stage]["error"] = error[:500]
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Check if all stages done
        all_done = all(state["stages"].get(s, {}).get("status") == "done" for s in STAGE_ORDER)
        state["status"] = "completed" if all_done else "in_progress"
        self.save(state)

    def to_dict(self) -> dict[str, Any]:
        state = self.load()
        state["stages_list"] = STAGE_ORDER
        done = sum(
            1 for s in STAGE_ORDER if state.get("stages", {}).get(s, {}).get("status") == "done"
        )
        state["progress"] = f"{done}/{len(STAGE_ORDER)}"
        state["pct"] = round(done / len(STAGE_ORDER) * 100) if STAGE_ORDER else 0
        return state


# ── Backpressure ───────────────────────────────────────────────────────

_MAX_CONCURRENT = int(os.getenv("ONBOARD_PIPELINE_CONCURRENCY", "10"))
_BACKPRESSURE_QUEUE_CAP = int(os.getenv("ONBOARD_PIPELINE_QUEUE_CAP", "800"))


def check_backpressure(r=None) -> tuple[bool, str]:
    """Returns (ok, reason). True = pipeline can start, False = backpressure active."""
    r = r or _redis()
    if not r:
        return True, "no_redis"
    try:
        # Check active pipelines
        active = int(r.get(REDIS_BACKPRESSURE_KEY) or 0)
        if active >= _MAX_CONCURRENT:
            return False, f"active_pipelines={active}>=max={_MAX_CONCURRENT}"
        # Check celery queue depth (approximate)
        celery_depth = r.llen("celery")
        if celery_depth > _BACKPRESSURE_QUEUE_CAP:
            return False, f"celery_queue_depth={celery_depth}>cap={_BACKPRESSURE_QUEUE_CAP}"
        return True, "ok"
    except Exception:
        return True, "redis_error"


def increment_active(r=None) -> None:
    r = r or _redis()
    if r:
        try:
            r.incr(REDIS_BACKPRESSURE_KEY)
            r.expire(REDIS_BACKPRESSURE_KEY, 3600)
        except Exception:
            pass


def decrement_active(r=None) -> None:
    r = r or _redis()
    if r:
        try:
            v = r.decr(REDIS_BACKPRESSURE_KEY)
            if v < 0:
                r.set(REDIS_BACKPRESSURE_KEY, 0, ex=3600)
        except Exception:
            pass


# ── Metrics ────────────────────────────────────────────────────────────


def _bucket() -> str:
    """Current hour bucket for metrics."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")


def record_stage_metrics(stage: str, duration_s: float, success: bool, r=None) -> None:
    """Record per-stage latency and outcome."""
    r = r or _redis()
    if not r:
        return
    try:
        bucket = _bucket()
        k = metrics_key(stage, bucket)
        field = "ok" if success else "fail"
        r.hincrby(k, field, 1)
        r.hincrby(k, f"{field}_sum", int(duration_s * 1000))  # ms accumulator
        # Track percentiles via sorted set (latency → timestamp)
        r.zadd(f"{k}:latency", {f"{duration_s:.3f}:{time.time()}": duration_s})
        r.zremrangebyrank(f"{k}:latency", 0, -501)  # keep last 500 samples
        r.expire(k, METRICS_TTL_S)
        r.expire(f"{k}:latency", METRICS_TTL_S)
    except Exception:
        pass


def get_capacity_metrics(hours: int = 24, r=None) -> dict[str, Any]:
    """Aggregate metrics across stages for the last N hours."""
    r = r or _redis()
    result: dict[str, Any] = {"stages": {}}
    if not r:
        return result
    try:
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        for stage in STAGE_ORDER:
            stage_data: dict[str, Any] = {
                "ok": 0,
                "fail": 0,
                "ok_ms_sum": 0,
                "fail_ms_sum": 0,
                "samples": [],
            }
            for h in range(hours):
                ts = now - timedelta(hours=h)
                bucket = ts.strftime("%Y-%m-%d-%H")
                k = metrics_key(stage, bucket)
                raw = r.hgetall(k)
                if not raw:
                    continue
                stage_data["ok"] += int(raw.get("ok", 0))
                stage_data["fail"] += int(raw.get("fail", 0))
                stage_data["ok_ms_sum"] += int(raw.get("ok_sum", 0))
                stage_data["fail_ms_sum"] += int(raw.get("fail_sum", 0))
                # Percentile from sorted set
                lat_k = f"{k}:latency"
                p50 = r.zrange(lat_k, 0, -1, withscores=True)
                if p50:
                    vals = [s for _, s in p50]
                    if vals:
                        stage_data["p50_ms"] = round(vals[len(vals) // 2] * 1000, 1)
                        stage_data["p95_ms"] = round(vals[int(len(vals) * 0.95)] * 1000, 1)
            total = stage_data["ok"] + stage_data["fail"]
            stage_data["total"] = total
            stage_data["failure_rate"] = (
                round(stage_data["fail"] / total * 100, 1) if total > 0 else 0
            )
            avg_ok = stage_data["ok_ms_sum"] / stage_data["ok"] if stage_data["ok"] else 0
            stage_data["avg_latency_ms"] = round(avg_ok, 1)
            del stage_data["ok_ms_sum"]
            del stage_data["fail_ms_sum"]
            result["stages"][stage] = stage_data
        # Aggregate
        total_ok = sum(s["ok"] for s in result["stages"].values())
        total_fail = sum(s["fail"] for s in result["stages"].values())
        total = total_ok + total_fail
        result["summary"] = {
            "total_pipelines": total_ok,  # ok = completed through that stage
            "total_failures": total_fail,
            "failure_rate": round(total_fail / total * 100, 1) if total else 0,
            "throughput_24h": total_ok,
        }
    except Exception:
        pass
    return result


# ── Stage executors ────────────────────────────────────────────────────


async def stage_validate(cid: str, **kw) -> dict[str, Any]:
    """Validate client exists and is eligible for onboarding."""
    from app.marketing import clients_store

    client = clients_store.get_client(cid)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    if client.get("setup_done") and not kw.get("force"):
        return {"ok": False, "error": "already_setup_done", "client_id": cid}
    return {"ok": True, "client_id": cid, "business_name": client.get("business_name", "")}


async def stage_kb_seed(cid: str, **kw) -> dict[str, Any]:
    """Scrape website → vector KB + knowledge graph."""
    from app.marketing import clients_store, onboarding

    client = clients_store.get_client(cid)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    website = client.get("website") or ""
    if not website:
        socials = client.get("socials") or {}
        if isinstance(socials, dict):
            website = socials.get("website", "")
    website = str(website).strip()
    result = await onboarding._seed_kb_from_website(cid, website)
    return {"ok": True, **result}


async def stage_content_pack(cid: str, **kw) -> dict[str, Any]:
    """Build first content pack."""
    from app.marketing import clients_store, onboarding

    client = clients_store.get_client(cid)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    result = await onboarding._first_content_pack(client)
    return {"ok": True, **result}


async def stage_content_queue(cid: str, **kw) -> dict[str, Any]:
    """Seed 7-day content calendar."""
    from app.marketing import auto_content, clients_store

    client = clients_store.get_client(cid)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    count = await auto_content.seed_client_content(client)
    return {"ok": True, "items_created": count}


async def stage_niche_snapshot(cid: str, **kw) -> dict[str, Any]:
    """Apply niche template — mini-site palette, journeys, festival schedule."""
    from app.platform import client_snapshots

    result = client_snapshots.apply_niche_to_client(cid)
    return {"ok": True, **(result if isinstance(result, dict) else {"result": result})}


async def stage_complete(cid: str, **kw) -> dict[str, Any]:
    """Mark setup_done, log delivery ledger, send welcome WhatsApp."""
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from app.marketing import clients_store, delivery_ledger

    client = clients_store.get_client(cid)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    biz = client.get("business_name", "")
    try:
        delivery_ledger.log_event(cid, "onboarding_completed", detail=biz, key="lc:onboarded")
    except Exception:
        pass
    try:
        clients_store.update_client(cid, setup_done=True, setup_at=_dt.now(_tz.utc).isoformat())
    except Exception:
        pass
    send_welcome = kw.get("send_welcome", True)
    if send_welcome:
        try:
            from app.marketing.onboarding import _send_welcome_whatsapp

            kb_seeded = bool((kw.get("kb_result") or {}).get("kb_chunks", 0))
            await _send_welcome_whatsapp(client, kb_seeded)
        except Exception:
            pass
    return {"ok": True, "client_id": cid}


# Stage registry: name → executor
STAGE_EXECUTORS: dict[str, Any] = {
    Stage.VALIDATE: stage_validate,
    Stage.KB_SEED: stage_kb_seed,
    Stage.CONTENT_PACK: stage_content_pack,
    Stage.CONTENT_QUEUE: stage_content_queue,
    Stage.NICHE_SNAPSHOT: stage_niche_snapshot,
    Stage.COMPLETE: stage_complete,
}


# ── Pipeline orchestrator ──────────────────────────────────────────────


async def run_pipeline(
    cid: str,
    *,
    force: bool = False,
    send_welcome: bool = True,
    start_from: str | None = None,
) -> dict[str, Any]:
    """Run the onboarding pipeline for one client.

    Resumes from last completed stage. Each stage is independently timed
    and recorded. Never raises — returns result dict.

    Args:
        cid: client ID
        force: skip setup_done check
        send_welcome: whether to send welcome WhatsApp at COMPLETE stage
        start_from: force starting from a specific stage (skip earlier ones)
    """
    r = _redis()
    state = PipelineState(cid, r)
    pipeline = state.load()
    pipeline["status"] = "in_progress"
    pipeline["started_at"] = datetime.now(timezone.utc).isoformat()
    state.save(pipeline)

    result: dict[str, Any] = {
        "client_id": cid,
        "stages": {},
        "overall_ok": False,
    }

    # Determine starting stage
    start_idx = 0
    if start_from:
        for i, s in enumerate(STAGE_ORDER):
            if s == start_from:
                start_idx = i
                break
    else:
        # Resume: skip completed stages
        for i, s in enumerate(STAGE_ORDER):
            if state.stage_done(s):
                result["stages"][s] = {"status": "skipped", "reason": "already_done"}
                start_idx = i + 1
            else:
                break

    # Track KB result for welcome message
    kb_result = {}

    for i in range(start_idx, len(STAGE_ORDER)):
        stage_name = STAGE_ORDER[i]
        executor = STAGE_EXECUTORS.get(stage_name)
        if not executor:
            continue

        state.mark_stage(stage_name, "running")
        t0 = time.monotonic()
        try:
            stage_result = await executor(
                cid, force=force, send_welcome=send_welcome, kb_result=kb_result
            )
            elapsed = time.monotonic() - t0

            if stage_name == Stage.KB_SEED.value:
                kb_result = stage_result

            if stage_result.get("ok") is False and stage_result.get("error"):
                # Stage failed
                state.mark_stage(
                    stage_name, "failed", result=stage_result, error=stage_result["error"]
                )
                result["stages"][stage_name] = {
                    "status": "failed",
                    "error": stage_result["error"],
                    "duration_s": round(elapsed, 2),
                }
                record_stage_metrics(stage_name, elapsed, False, r)
                result["overall_ok"] = False
                result["failed_at"] = stage_name
                result["error"] = stage_result["error"]
                return result

            # Stage succeeded
            state.mark_stage(stage_name, "done", result=stage_result)
            result["stages"][stage_name] = {"status": "done", "duration_s": round(elapsed, 2)}
            record_stage_metrics(stage_name, elapsed, True, r)

        except Exception as exc:
            elapsed = time.monotonic() - t0
            state.mark_stage(stage_name, "failed", error=str(exc)[:500])
            result["stages"][stage_name] = {
                "status": "failed",
                "error": str(exc)[:200],
                "duration_s": round(elapsed, 2),
            }
            record_stage_metrics(stage_name, elapsed, False, r)
            result["overall_ok"] = False
            result["failed_at"] = stage_name
            result["error"] = str(exc)[:200]
            return result

    # All stages completed
    result["overall_ok"] = True
    pipeline["status"] = "completed"
    pipeline["completed_at"] = datetime.now(timezone.utc).isoformat()
    state.save(pipeline)
    return result


def get_pipeline_status(cid: str) -> dict[str, Any]:
    """Get pipeline status for a client."""
    state = PipelineState(cid)
    return state.to_dict()


def get_all_pipelines() -> list[dict[str, Any]]:
    """List all active pipeline states."""
    r = _redis()
    if not r:
        return []
    try:
        keys = r.keys(f"{REDIS_KEY_PREFIX}*")
        result = []
        for k in keys:
            cid = k.replace(REDIS_KEY_PREFIX, "")
            state = PipelineState(cid, r)
            d = state.to_dict()
            result.append(d)

        # Sort by status: in_progress first, then by updated_at
        def sort_key(p):
            return (0 if p.get("status") == "in_progress" else 1, p.get("updated_at", ""))

        result.sort(key=sort_key)
        return result
    except Exception:
        return []
