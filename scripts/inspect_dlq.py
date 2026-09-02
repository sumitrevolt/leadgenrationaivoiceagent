#!/usr/bin/env python3
"""
Inspect and audit Redis DLQ for stuck/QA-only entries.
Run on VPS: python scripts/inspect_dlq.py
"""

import json
import sys
from datetime import datetime


# Simulated inspection (would need actual Redis connection on VPS)
def inspect_dlq():
    """Inspect dlq:dead entries. Prod: requires REDIS_URL connection."""
    try:
        import redis

        from app.config import settings

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

        # Get DLQ entries
        dlq_len = r.llen("dlq:dead")
        print("\n=== DLQ INSPECTION ===")
        print(f"Total entries in dlq:dead: {dlq_len}")

        if dlq_len == 0:
            print("✓ DLQ is empty")
            return {"status": "clean", "count": 0}

        # Sample first 10 entries
        entries = r.lrange("dlq:dead", 0, min(9, dlq_len - 1))
        qa_count = 0
        prod_count = 0
        by_job = {}

        for entry_str in entries:
            try:
                entry = json.loads(entry_str)
                job_type = entry.get("task_name", "unknown")
                is_qa = "qa" in job_type.lower() or "test" in job_type.lower()

                by_job[job_type] = by_job.get(job_type, 0) + 1
                if is_qa:
                    qa_count += 1
                else:
                    prod_count += 1
                    print(f"  ⚠️  PROD ENTRY: {job_type} - {entry.get('exc_message', '')[:80]}")
            except Exception as e:
                print(f"  Parse error: {e}")

        print(f"\nQA entries found: {qa_count}")
        print(f"Prod entries found: {prod_count}")
        print(f"By job type: {json.dumps(by_job, indent=2)}")

        if prod_count == 0:
            print("\n✓ SAFE TO CLEAN: All entries are QA/test jobs")
            print("Run: redis-cli DEL dlq:dead")
            return {
                "status": "safe_to_clean",
                "qa_count": qa_count,
                "prod_count": prod_count,
                "by_job": by_job,
            }
        else:
            print(f"\n✗ DO NOT CLEAN: {prod_count} production entries found")
            return {"status": "has_prod_entries", "prod_count": prod_count, "by_job": by_job}

    except ImportError:
        print("Redis not available. Run on VPS where redis is configured.")
        return {"status": "redis_unavailable"}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    result = inspect_dlq()
    print(f"\nResult: {json.dumps(result, indent=2)}")
    sys.exit(0 if result.get("status") in ["clean", "safe_to_clean"] else 1)
