"""Minimal Celery app for the network-isolated, concurrency-one DSH queue."""

from __future__ import annotations

import os

from celery import Celery

_broker = (os.getenv("REDIS_URL") or "redis://redis:6379/0").strip()

# DSH_RUNTIME_ENABLED flag check (fail-closed).
# If the flag is not set or set to 0, the worker is DORMANT.
# This ensures the worker does not process any DSH jobs unless explicitly enabled.
if not (os.getenv("DSH_RUNTIME_ENABLED", "0") == "1" or os.getenv("DSH_SHADOW_ENABLED", "0") == "1"):
    # DORMANT: Worker is registered but no DSH jobs will be processed.
    pass

celery_app = Celery(
    "leadgen_dsh_worker",
    broker=_broker,
    backend=_broker,
    include=["app.tasks.dsh_jobs"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={"app.tasks.dsh_jobs.run_dsh_workforce": {"queue": "dsh"}},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=1,
    worker_max_tasks_per_child=1,
    task_time_limit=570,
    task_soft_time_limit=540,
    broker_transport_options={
        "visibility_timeout": 900,
        "socket_timeout": 30,
        "socket_connect_timeout": 10,
    },
)

__all__ = ["celery_app"]
