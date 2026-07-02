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
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _statically_routed_queues() -> set[str]:
    """Queue names from app/worker.py's static task_routes dict (the
    router-fn's dynamic "heavy" route is checked separately below)."""
    from app.worker import celery_app

    router_fn, static_routes = celery_app.conf.task_routes
    assert callable(router_fn)
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


def test_prod_worker_consumes_every_routed_queue_plus_heavy():
    """docker-compose.prod.yml has no separate heavy worker, so its single
    `worker` service must also drain "heavy"."""
    cmd = _worker_command(REPO_ROOT / "docker-compose.prod.yml", "worker")
    consumed = _dash_q_queues(cmd)
    missing = (_statically_routed_queues() | {"heavy"}) - consumed
    assert not missing, f"docker-compose.prod.yml worker never drains: {missing}"


def test_base_compose_worker_consumes_every_routed_queue_plus_heavy():
    cmd = _worker_command(REPO_ROOT / "docker-compose.yml", "worker")
    consumed = _dash_q_queues(cmd)
    missing = (_statically_routed_queues() | {"heavy"}) - consumed
    assert not missing, f"docker-compose.yml worker never drains: {missing}"
