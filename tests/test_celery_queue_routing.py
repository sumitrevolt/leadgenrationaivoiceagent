"""Celery worker `-Q` must actually consume every queue app/worker.py routes
tasks to (2026-07-02).

Found while wiring the durable Celery campaign-launch task (P2-1,
app.tasks.calling.run_campaign_task): a bare `celery -A app.worker worker`
with no -Q only drains the DEFAULT queue ("celery"). task_routes sends
scraping/calling/reporting/sync/brain_training tasks to their own named
queues — without listing those queues on a worker's -Q, tasks enqueue
successfully (send_task/beat succeed, status looks "queued"/"running") but
NO worker ever picks them up; they sit in Redis forever. This silently
affected the pre-existing beat-scheduled process-call-queue task too, not
just the new one. Fixed in docker-compose.vps.yml / .prod.yml / .yml.
"""

from __future__ import annotations

import re
import sys
import time
import types
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _statically_routed_queues() -> set[str]:
    """Queue names from app/worker.py's static task_routes dict (the
    router-fns' dynamic "heavy"/"video" routes are checked separately below).
    task_routes is (router_fn, router_fn, ..., static_dict) — N router
    callables followed by exactly one trailing static dict, so unpack with a
    star instead of a fixed arity (a new router fn is additive, not a reason
    to touch this helper again)."""
    from app.worker import celery_app

    *router_fns, static_routes = celery_app.conf.task_routes
    assert router_fns and all(callable(fn) for fn in router_fns)
    return {v["queue"] for v in static_routes.values()}


def _worker_command(compose_path: Path, service: str) -> str:
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    svc = data["services"][service]
    cmd = svc["command"]
    return cmd if isinstance(cmd, str) else " ".join(cmd)


def _dash_q_queues(command: str) -> set[str]:
    m = re.search(r"-Q\s+([A-Za-z0-9_,]+)", command)
    assert m, f"no -Q flag found in worker command: {command!r}"
    return set(m.group(1).split(","))


def test_statically_routed_queues_are_known():
    # Sanity: this project routes exactly these — if someone adds a new
    # app.tasks.X module with its own queue, this test's failure is the
    # reminder to also add it to every worker -Q below.
    assert _statically_routed_queues() == {
        "scraping",
        "calling",
        "reporting",
        "sync",
        "training",
    }


def test_vps_worker_consumes_every_routed_queue():
    """docker-compose.vps.yml = the LIVE deploy file. "heavy" is deliberately
    excluded from `worker` here — a dedicated worker-heavy service consumes
    it instead (starve-prevention), verified separately below."""
    cmd = _worker_command(REPO_ROOT / "docker-compose.vps.yml", "worker")
    consumed = _dash_q_queues(cmd)
    missing = _statically_routed_queues() - consumed
    assert not missing, f"docker-compose.vps.yml worker never drains: {missing}"
    assert "celery" in consumed, "default queue must stay consumed too"


def test_vps_worker_heavy_consumes_heavy_queue():
    cmd = _worker_command(REPO_ROOT / "docker-compose.vps.yml", "worker-heavy")
    assert "heavy" in _dash_q_queues(cmd)


def test_vps_worker_video_consumes_video_queue():
    cmd = _worker_command(REPO_ROOT / "docker-compose.vps.yml", "worker-video")
    assert "video" in _dash_q_queues(cmd)


def test_vps_worker_does_not_drain_video():
    # worker-video isolates it — same starve-prevention shape as worker-heavy.
    cmd = _worker_command(REPO_ROOT / "docker-compose.vps.yml", "worker")
    assert "video" not in _dash_q_queues(cmd)


def test_prod_worker_consumes_every_routed_queue_plus_heavy_and_video():
    """docker-compose.prod.yml has no separate heavy or video worker, so its
    single `worker` service must drain both."""
    cmd = _worker_command(REPO_ROOT / "deploy" / "legacy" / "docker-compose.prod.yml", "worker")
    consumed = _dash_q_queues(cmd)
    missing = (_statically_routed_queues() | {"heavy", "video"}) - consumed
    assert not missing, f"docker-compose.prod.yml worker never drains: {missing}"


def test_base_compose_worker_consumes_every_routed_queue_plus_heavy_and_video():
    """docker-compose.yml has no separate heavy or video worker, so its
    single `worker` service must drain both."""
    cmd = _worker_command(REPO_ROOT / "deploy" / "legacy" / "docker-compose.legacy.yml", "worker")
    consumed = _dash_q_queues(cmd)
    missing = (_statically_routed_queues() | {"heavy", "video"}) - consumed
    assert not missing, f"docker-compose.yml worker never drains: {missing}"


def test_video_router_routes_when_flag_on(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_VIDEO_QUEUE", "1")
    route = worker._route_video_task("app.tasks.video_jobs.build_creative_video_task", (), {}, {})
    assert route == {"queue": "video"}


def test_video_router_none_when_flag_off(monkeypatch):
    from app import worker

    monkeypatch.delenv("CELERY_VIDEO_QUEUE", raising=False)
    route = worker._route_video_task("app.tasks.video_jobs.build_creative_video_task", (), {}, {})
    assert route is None


def test_video_router_none_for_other_tasks(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_VIDEO_QUEUE", "1")
    route = worker._route_video_task("app.tasks.scraping.scrape_leads", (), {}, {})
    assert route is None


def test_static_routes_unchanged_by_video_addition():
    # video is router-fn based (like "heavy"), NOT added to the static dict —
    # this assertion must stay exactly as it is today.
    assert _statically_routed_queues() == {"scraping", "calling", "reporting", "sync", "training"}


def test_kb_refresh_router_routes_when_flag_on(monkeypatch):
    """2026-07-15 — ADR-104 kb_niche_refresh moved off the default queue after
    a live-prod OOM finding (see app/worker.py._route_kb_refresh_task
    docstring): it collided with the default queue's staff-job battery inside
    leadgen_worker's 2GB memcg limit, got SIGKILL'd 3x via WorkerLostError
    (which bypasses the task's own max_retries — broker-level redelivery of
    the same task id, unbounded). worker-heavy already exists + is already
    consumed by every compose worker's -Q (see tests above) — no compose
    change needed, only this routing rule."""
    from app import worker

    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    route = worker._route_kb_refresh_task(
        "app.tasks.kb_niche_refresh.refresh_niche_task", (), {}, {}
    )
    assert route == {"queue": "heavy"}


def test_kb_refresh_router_none_when_flag_off(monkeypatch):
    from app import worker

    monkeypatch.delenv("CELERY_HEAVY_QUEUE", raising=False)
    route = worker._route_kb_refresh_task(
        "app.tasks.kb_niche_refresh.refresh_niche_task", (), {}, {}
    )
    assert route is None


def test_kb_refresh_router_none_for_other_tasks(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    route = worker._route_kb_refresh_task("app.tasks.scraping.scrape_leads", (), {}, {})
    assert route is None


def test_static_routes_unchanged_by_kb_refresh_addition():
    # kb_refresh is router-fn based (like "heavy"/"video"), NOT added to the
    # static dict — this assertion must stay exactly as it is today.
    assert _statically_routed_queues() == {"scraping", "calling", "reporting", "sync", "training"}


def test_worker_process_init_warmup_skipped_on_default_worker(monkeypatch):
    """2026-07-15 ADR-104 A10 — worker_heavy Qdrant/fastembed warm-up (see
    on_worker_process_init docstring for the measured ~90s-hang finding this
    fixes). Routing stays enabled here, but the heavy process-role marker is
    absent, so the default worker must remain a true no-op."""
    from app import worker

    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    monkeypatch.delenv("CELERY_HEAVY_WORKER", raising=False)
    calls: list[str] = []
    fake_mod = types.ModuleType("app.voice_agent.knowledge_base")
    fake_mod.get_knowledge_base = lambda: calls.append("called") or None
    monkeypatch.setitem(sys.modules, "app.voice_agent.knowledge_base", fake_mod)

    worker.on_worker_process_init()
    time.sleep(0.2)  # generous wait for any (unexpected) background thread
    assert calls == []


def test_worker_process_init_warmup_runs_when_flag_on(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    monkeypatch.setenv("CELERY_HEAVY_WORKER", "1")
    calls: list[str] = []

    class _FakeKB:
        def backend(self, namespace):
            calls.append(namespace)
            return "qdrant"

    fake_mod = types.ModuleType("app.voice_agent.knowledge_base")
    fake_mod.get_knowledge_base = lambda: _FakeKB()
    monkeypatch.setitem(sys.modules, "app.voice_agent.knowledge_base", fake_mod)

    worker.on_worker_process_init()
    for _ in range(40):  # up to 2s for the background thread to run
        if calls:
            break
        time.sleep(0.05)
    assert calls == ["solar_residential"]


def test_worker_process_init_warmup_never_raises_on_failure(monkeypatch):
    """Warm-up is best-effort — a broken Qdrant endpoint must never crash
    worker boot. Task-time fallback logic (knowledge_base.py's own
    Qdrant->Chroma->keyword cascade) remains the real safety net; this
    warm-up is purely an optimization, never a dependency."""
    from app import worker

    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    monkeypatch.setenv("CELERY_HEAVY_WORKER", "1")

    class _BoomKB:
        def backend(self, namespace):
            raise RuntimeError("qdrant unreachable")

    fake_mod = types.ModuleType("app.voice_agent.knowledge_base")
    fake_mod.get_knowledge_base = lambda: _BoomKB()
    monkeypatch.setitem(sys.modules, "app.voice_agent.knowledge_base", fake_mod)

    worker.on_worker_process_init()  # must not raise
    time.sleep(0.2)


def _all_compose_files() -> list[Path]:
    """Every tracked compose file that defines services (vps + legacy + deploy/compose)."""
    paths = [REPO_ROOT / "docker-compose.vps.yml"]
    paths += sorted((REPO_ROOT / "deploy" / "legacy").glob("docker-compose*.yml"))
    paths += sorted((REPO_ROOT / "deploy" / "compose").glob("docker-compose*.yml"))
    return paths


def _env_map(service: dict) -> dict:
    """Compose `environment` accepts a dict OR a list of KEY=VALUE strings."""
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    out: dict[str, str] = {}
    for item in env:
        key, _, value = str(item).partition("=")
        out[key] = value
    return out


def test_heavy_worker_marker_is_exclusive_across_all_compose_files():
    """Only worker-heavy may run the memory-heavy Qdrant/ONNX warm-up.

    incidents.md rule (2026-07-16): CELERY_HEAVY_QUEUE is a SEND-side routing flag
    shared by app/scheduler/worker/heavy — using it as process-role identity made
    every default-worker fork pay the ~1.2-1.4 GiB warm-up. The fix introduced the
    exclusive CELERY_HEAVY_WORKER=1 marker on worker-heavy; this test proves the
    marker appears in EXACTLY ONE service across EVERY compose file, so a future
    file cannot silently re-introduce a duplicate warm-up path."""
    marked: list[tuple[str, str]] = []
    for path in _all_compose_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, service in (data.get("services") or {}).items():
            if _env_map(service).get("CELERY_HEAVY_WORKER") == "1":
                marked.append((path.name, name))
    assert marked == [("docker-compose.vps.yml", "worker-heavy")], marked
