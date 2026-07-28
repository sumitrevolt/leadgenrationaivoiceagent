"""Proofs for 2026-07-28 worker-OOM containment (self-improve → heavy).

QueuePool / "No response returned" are NOT claimed as effects of OOM here —
those stay a separate unresolved blocker until connection-owner evidence exists.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def _compose():
    return yaml.safe_load((REPO / "docker-compose.vps.yml").read_text(encoding="utf-8"))


def test_app_scheduler_worker_all_send_heavy_queue_flag():
    """Routing is SEND-side: app + beat + default worker must set CELERY_HEAVY_QUEUE=1."""
    services = _compose()["services"]
    for name in ("app", "scheduler", "worker", "worker-heavy"):
        env = services[name].get("environment") or {}
        assert env.get("CELERY_HEAVY_QUEUE") == "1", f"{name} missing CELERY_HEAVY_QUEUE=1"


def test_default_worker_does_not_consume_heavy_queue():
    services = _compose()["services"]
    cmd = services["worker"]["command"]
    assert isinstance(cmd, str)
    assert "-Q" in cmd
    # heavy must stay exclusive to worker-heavy
    q = cmd.split("-Q", 1)[1].strip().split()[0]
    assert "heavy" not in q.split(",")
    heavy_cmd = services["worker-heavy"]["command"]
    assert "-Q heavy" in heavy_cmd or heavy_cmd.endswith("-Q heavy")


def test_self_improve_tasks_route_heavy_under_flag(monkeypatch):
    from app import worker

    monkeypatch.setenv("CELERY_HEAVY_QUEUE", "1")
    for name in (
        "app.tasks.staff_jobs.self_improve_tick",
        "app.tasks.staff_jobs.self_improve_revive",
    ):
        assert worker._route_self_improve_task(name, (), {}, {}) == {"queue": "heavy"}
    # Router is registered in task_routes so app/beat/worker share one evaluation path.
    routes = worker.celery_app.conf.task_routes
    assert worker._route_self_improve_task in routes


def test_worker_max_memory_per_child_is_kib_not_bytes():
    """Celery documents worker_max_memory_per_child as KiB.

    A mistaken '512000 bytes' reading would be ~0.5MB (useless). Our value must
    sit in the hundreds-of-MiB band and stay under the default worker's 2g cgroup.
    """
    from app import worker

    kib = int(worker.celery_app.conf.worker_max_memory_per_child)
    # 100 MiB .. 512 MiB inclusive band
    assert 100_000 <= kib <= 512_000, kib
    # Convert to bytes the way Celery does (kib * 1024) and stay < 2 GiB cgroup.
    assert kib * 1024 < 2 * 1024 * 1024 * 1024


def test_healthcheck_script_targets_this_hostname_only():
    script = (REPO / "scripts" / "celery_worker_healthcheck.sh").read_text(encoding="utf-8")
    assert "-d" in script
    assert "HOSTNAME" in script
    assert "celery@${HOSTNAME" in script
    assert "broken" in script.lower() and "pipe" in script.lower()
    assert "-t 8" in script
    # Capture-then-match: no pipeline hardening; fail closed via case on OUT.
    assert "set -o pipefail" not in script
    assert "| grep" not in script
    assert 'case "$OUT"' in script
    # Broadcast ping without -d must not be the sole probe.
    assert "inspect ping -t 8 2>&1)" not in script.replace(" ", "")


def test_vps_compose_healthcheck_timeout_exceeds_inspect_t():
    services = _compose()["services"]
    for name in ("worker", "worker-heavy", "worker-video"):
        hc = services[name]["healthcheck"]
        assert "celery_worker_healthcheck.sh" in str(hc["test"])
        assert int(str(hc["timeout"]).rstrip("s")) >= 15


def test_sentry_keeps_original_and_only_drops_exact_mask():
    from app.main import _sentry_before_send

    original = ImportError("lead_topup_price missing")
    payload = {"event_id": "keep-me"}

    # Exact secondary mask with cause → drop (original already in chain / prior event).
    mask = AttributeError("'_IncludedRouter' object has no attribute 'path'")
    mask.__cause__ = original
    assert _sentry_before_send(payload, {"exc_info": (AttributeError, mask, None)}) is None

    # Original exception alone → keep.
    assert _sentry_before_send(payload, {"exc_info": (ImportError, original, None)}) is payload

    # Similar but not exact message → keep (do not over-suppress).
    other = AttributeError("'_IncludedRouter' object has no attribute 'routes'")
    other.__cause__ = original
    assert _sentry_before_send(payload, {"exc_info": (AttributeError, other, None)}) is payload

    # Bare IncludedRouter with no chain → keep (might be the only signal).
    bare = AttributeError("'_IncludedRouter' object has no attribute 'path'")
    assert _sentry_before_send(payload, {"exc_info": (AttributeError, bare, None)}) is payload


def test_queuepool_not_claimed_fixed_in_this_change():
    """Guardrail: this wave must not pretend QueuePool is solved."""
    # Presence of this test documents the unresolved blocker in CI evidence.
    assert True
