#!/usr/bin/env python3
"""Production-friendly 15-minute scheduler for LeadGen.

The scheduler is dependency-free so it can run beside any LeadGen stack
(Next.js, FastAPI, Laravel, Docker, VPS, or systemd). Jobs are configured
through JSON in environment variables and can call HTTP endpoints or shell
commands.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INTERVAL_SECONDS = 15 * 60
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_LOCK_FILE = "/tmp/leadgen_scheduler.lock"


@dataclass(frozen=True)
class SchedulerConfig:
    interval_seconds: int
    lock_file: str
    log_file: str | None
    run_on_start: bool
    max_failures_before_exit: int
    jobs: list[dict[str, Any]]


class SchedulerStop(Exception):
    """Raised when the process receives a shutdown signal."""


def as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def load_config() -> SchedulerConfig:
    raw_jobs = os.getenv("LEADGEN_SCHEDULER_JOBS_JSON", "[]")
    try:
        jobs = expand_env(json.loads(raw_jobs))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid LEADGEN_SCHEDULER_JOBS_JSON: {exc}") from exc

    if not isinstance(jobs, list):
        raise ValueError("LEADGEN_SCHEDULER_JOBS_JSON must be a JSON array")

    return SchedulerConfig(
        interval_seconds=int(
            os.getenv("LEADGEN_SCHEDULER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
        ),
        lock_file=os.getenv("LEADGEN_SCHEDULER_LOCK_FILE", DEFAULT_LOCK_FILE),
        log_file=os.getenv("LEADGEN_SCHEDULER_LOG_FILE"),
        run_on_start=as_bool(os.getenv("LEADGEN_SCHEDULER_RUN_ON_START"), True),
        max_failures_before_exit=int(os.getenv("LEADGEN_SCHEDULER_MAX_FAILURES", "5")),
        jobs=jobs,
    )


def setup_logging(log_file: str | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=os.getenv("LEADGEN_SCHEDULER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def validate_job(job: dict[str, Any]) -> None:
    name = job.get("name")
    job_type = job.get("type")
    if not name or not isinstance(name, str):
        raise ValueError(f"Job must have a string name: {job}")
    if job_type not in {"http", "command"}:
        raise ValueError(f"Job {name} type must be 'http' or 'command'")
    if job_type == "http" and not job.get("url"):
        raise ValueError(f"HTTP job {name} must have url")
    if job_type == "command" and not job.get("command"):
        raise ValueError(f"Command job {name} must have command")


def run_http_job(job: dict[str, Any]) -> None:
    name = job["name"]
    method = str(job.get("method", "POST")).upper()
    timeout = int(job.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    headers = dict(job.get("headers", {}))
    body = job.get("body")
    data: bytes | None = None

    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        else:
            data = str(body).encode("utf-8")

    request = urllib.request.Request(
        url=str(job["url"]),
        data=data,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.getcode()
        response.read(512)

    if status >= 400:
        raise RuntimeError(f"HTTP job {name} failed with status {status}")


def run_command_job(job: dict[str, Any]) -> None:
    name = job["name"]
    command = job["command"]
    timeout = int(job.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))

    if isinstance(command, str):
        result = subprocess.run(
            command,
            shell=True,
            check=False,
            timeout=timeout,
            text=True,
            capture_output=True,
        )
    else:
        result = subprocess.run(
            command,
            shell=False,
            check=False,
            timeout=timeout,
            text=True,
            capture_output=True,
        )

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command job {name} failed ({result.returncode}): {details}")


def run_job(job: dict[str, Any]) -> bool:
    validate_job(job)
    name = job["name"]
    started = time.monotonic()
    logging.info("job_start name=%s type=%s", name, job["type"])

    try:
        if job["type"] == "http":
            run_http_job(job)
        else:
            run_command_job(job)
    except (urllib.error.URLError, subprocess.TimeoutExpired, Exception) as exc:
        logging.exception("job_failed name=%s error=%s", name, exc)
        return False

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logging.info("job_done name=%s elapsed_ms=%s", name, elapsed_ms)
    return True


def run_all_jobs(jobs: list[dict[str, Any]]) -> bool:
    if not jobs:
        logging.warning("no_jobs_configured")
        return True

    ok = True
    for job in jobs:
        ok = run_job(job) and ok
    return ok


def acquire_lock(lock_file: str):
    Path(lock_file).parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_file, "w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logging.warning("scheduler_already_running lock_file=%s", lock_file)
        handle.close()
        return None

    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def install_signal_handlers() -> None:
    def stop(_signum: int, _frame: object) -> None:
        raise SchedulerStop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def loop(config: SchedulerConfig, run_once: bool) -> int:
    lock = acquire_lock(config.lock_file)
    if lock is None:
        return 2

    failures = 0
    next_run = 0.0 if config.run_on_start else time.monotonic() + config.interval_seconds

    try:
        while True:
            sleep_for = max(0.0, next_run - time.monotonic())
            if sleep_for:
                logging.info("scheduler_sleep seconds=%s", int(sleep_for))
                time.sleep(sleep_for)

            logging.info("scheduler_tick interval_seconds=%s", config.interval_seconds)
            success = run_all_jobs(config.jobs)
            failures = 0 if success else failures + 1

            if run_once:
                return 0 if success else 1

            if failures >= config.max_failures_before_exit:
                logging.error("scheduler_exiting_after_failures count=%s", failures)
                return 1

            next_run = time.monotonic() + config.interval_seconds
    except SchedulerStop:
        logging.info("scheduler_stopped")
        return 0
    finally:
        lock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="LeadGen 15-minute scheduler")
    parser.add_argument("--check", action="store_true", help="validate config only")
    parser.add_argument("--run-once", action="store_true", help="run jobs once and exit")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config.log_file)

    for job in config.jobs:
        validate_job(job)

    if args.check:
        print(
            json.dumps(
                {
                    "ok": True,
                    "interval_seconds": config.interval_seconds,
                    "jobs": [job["name"] for job in config.jobs],
                },
                sort_keys=True,
            )
        )
        return 0

    install_signal_handlers()
    return loop(config, run_once=args.run_once)


if __name__ == "__main__":
    raise SystemExit(main())
