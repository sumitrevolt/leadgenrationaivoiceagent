"""Regression tests for the Celery per-process async loop lifecycle."""

from __future__ import annotations

import asyncio

from app.tasks import staff_jobs


def test_staff_wrapper_reuses_one_loop_for_process_local_async_resources():
    staff_jobs._reset_worker_loop_for_tests()

    async def current_loop_id() -> int:
        return id(asyncio.get_running_loop())

    first = staff_jobs._run_async(current_loop_id())
    second = staff_jobs._run_async(current_loop_id())

    assert first == second

    staff_jobs._reset_worker_loop_for_tests()


def test_staff_wrapper_reset_closes_loop_and_next_run_recreates_it():
    staff_jobs._reset_worker_loop_for_tests()

    async def current_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    first = staff_jobs._run_async(current_loop())
    staff_jobs._reset_worker_loop_for_tests()
    second = staff_jobs._run_async(current_loop())

    assert first is not second
    assert first.is_closed()

    staff_jobs._reset_worker_loop_for_tests()
