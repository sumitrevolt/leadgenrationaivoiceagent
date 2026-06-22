#!/usr/bin/env python3
"""One-shot celery queue trim (VPS safe). Run inside leadgen_app container."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN = int(os.environ.get("CELERY_TRIM_MIN_DEPTH", "800") or 800)


def main() -> int:
    import redis
    from app.config import settings

    r = redis.Redis.from_url(str(settings.redis_url), socket_timeout=5)
    depth = int(r.llen("celery") or 0)
    dlq = int(r.llen("dlq:failed_tasks") or 0)
    print(f"before celery={depth} dlq={dlq}")
    if depth < MIN:
        print(f"skip: depth {depth} < min {MIN}")
        return 0
    r.delete("celery")
    after = int(r.llen("celery") or 0)
    print(f"cleared={depth} after={after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
