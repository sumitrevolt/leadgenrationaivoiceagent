#!/usr/bin/env python3
"""One-shot celery queue trim (VPS safe). Run inside leadgen_app container.

Covers every queue app/worker.py's task_routes can send work to — not just
the default "celery" queue. 2026-07-02: leadgen_worker was fixed to actually
consume the calling/scraping/reporting/sync/training queues (previously it
only drained "celery", so those queues silently accumulated undelivered
tasks with no consumer at all). Before that worker restart picks up a large
pre-existing backlog in one burst, run this once with
CELERY_TRIM_QUEUES=calling,scraping,reporting,sync,training,heavy (or just
run it as-is — the default list already includes them) to trim any stale
backlog first. Ongoing protection is also wired into the Saturday hygiene
job (app/platform/scheduled_ops.py::run_saturday_hygiene).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN = int(os.environ.get("CELERY_TRIM_MIN_DEPTH", "800") or 800)
DEFAULT_QUEUES = "celery,calling,scraping,reporting,sync,training,heavy"
QUEUES = [
    q.strip() for q in os.environ.get("CELERY_TRIM_QUEUES", DEFAULT_QUEUES).split(",") if q.strip()
]


def main() -> int:
    import redis

    from app.config import settings

    r = redis.Redis.from_url(str(settings.redis_url), socket_timeout=5)
    dlq = int(r.llen("dlq:failed_tasks") or 0)
    print(f"dlq={dlq}")
    for q in QUEUES:
        depth = int(r.llen(q) or 0)
        if depth < MIN:
            print(f"{q}: depth={depth} < min={MIN}, skip")
            continue
        r.delete(q)
        after = int(r.llen(q) or 0)
        print(f"{q}: cleared={depth} after={after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
