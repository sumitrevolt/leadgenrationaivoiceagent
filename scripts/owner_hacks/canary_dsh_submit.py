import asyncio
import os
import time
import uuid

# Force the flags ON for this short lived script process
os.environ["DSH_RUNTIME_ENABLED"] = "1"
os.environ["DSH_SHADOW_ENABLED"] = "0"
os.environ["CELERY_ALWAYS_EAGER"] = "1"  # just to see if we submit via celery directly or not

from app.platform.workforce_runtime import run_store
from app.tasks.dsh_jobs import run_dsh_workforce


def run_canary():
    run_id = f"dshrun_{uuid.uuid4().hex[:20]}"
    print(f"Starting canary run: {run_id}")
    run_store.create_run(
        run_id=run_id,
        agent_id="ops_health_agent",
        tenant_id="ops",
        action="ops_health_check",
        idempotency_key=run_id,
        timeout_s=30,
        provider="dsh",
        shadow=False,
        deadline=time.time() + 30,
        input_payload={"test": "canary"},
    )

    # Run the worker function directly (foreground)
    try:
        res = asyncio.run(run_dsh_workforce(run_id=run_id))
        print("RESULT:")
        print(res)
    except Exception as e:
        print(f"Run failed: {e}")


if __name__ == "__main__":
    run_canary()
