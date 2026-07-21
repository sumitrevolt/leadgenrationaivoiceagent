"""Regression: in-process startup migrations must not disable application loggers.

Root cause (2026-07-21): `alembic/env.py` called `fileConfig(config_file_name)`
with the default `disable_existing_loggers=True`. Because `run_startup_migrations()`
imports env.py in-process during the FastAPI lifespan, every already-created app
logger (e.g. `app.integrations.email_sender`) had `logger.disabled` set to True and
stayed silenced for the rest of the process.

That silently killed application logging after any startup migration, and — because
pytest shares one process — made every later test that asserts on emitted log output
fail in an order-dependent way (empty capture, "record never emitted"). The minimal
reproducer was `test_customer_timeline_endpoint.py` (runs a lifespan) followed by
`test_email_log_redaction.py`.

Fix: `fileConfig(config_file_name, disable_existing_loggers=False)`.

This test fails before the fix (logger.disabled becomes True after the lifespan)
and passes after it.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient


def test_startup_lifespan_does_not_disable_app_loggers():
    from app.main import app

    # Ensure the target logger exists and is enabled BEFORE the lifespan runs, so
    # that if fileConfig disables existing loggers, this specific one is affected.
    sentinel = logging.getLogger("app.integrations.email_sender")
    sentinel.disabled = False

    # Entering the TestClient context runs the app lifespan, which runs startup
    # migrations in-process (alembic env.py -> fileConfig).
    with TestClient(app):
        pass

    assert sentinel.disabled is False, (
        "A startup-migration lifespan disabled an application logger. "
        "alembic/env.py must call fileConfig(..., disable_existing_loggers=False)."
    )
