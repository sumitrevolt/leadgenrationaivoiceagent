"""Log rotation helper — bounded log files (M6, crore-strategy T05).

WHY THIS EXISTS
---------------
ARCH §8 R8 (verified): `app/utils/logger.py` used plain `logging.FileHandler`
(lines ~468, 508) with **no** `RotatingFileHandler` and no logrotate config. That is
a real disk-blowup risk on prod (`/opt/leadgen/var/log/*` grows unbounded).

This module centralizes the rotating-handler construction so both the app logger and
the per-call logger use ONE policy. Belt (RotatingFileHandler) + suspenders
(deploy/logrotate/leadgen).

Design:
* Size-based rotation (`RotatingFileHandler`) — works without a cron/logrotate.
* `backupCount` bounded so total disk is capped.
* Never raises — falls back to a plain FileHandler if rotation cannot be built.

Evidence label: CODE-PRESENT (pinned by tests/test_deploy_log_rotation.py).
"""

from __future__ import annotations

import logging
import logging.handlers
import os

# Policy: 10 MB per file, keep 5 backups → ≤ ~60 MB per log file family.
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


def build_file_handler(
    log_file: str,
    *,
    level: int = logging.INFO,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    encoding: str = "utf-8",
) -> logging.Handler:
    """Return a bounded rotating file handler for ``log_file``. Never raises.

    Falls back to a plain ``FileHandler`` only if the rotating handler cannot be
    constructed, so logging never crashes the app.
    """
    log_dir = os.path.dirname(log_file)
    try:
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
    except OSError:
        pass
    try:
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max(0, int(max_bytes)),
            backupCount=max(0, int(backup_count)),
            encoding=encoding,
        )
    except Exception:
        handler = logging.FileHandler(log_file, encoding=encoding)
    handler.setLevel(level)
    return handler


__all__ = ["DEFAULT_MAX_BYTES", "DEFAULT_BACKUP_COUNT", "build_file_handler"]
