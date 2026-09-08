import sys
sys.path.insert(0, '/app')
from app.tasks.daily_social_post import run_daily_social_post
from app.tasks.staff_jobs import run_staff_job
import traceback

print("=== Triggering missed daily social post ===")
try:
    r = run_daily_social_post()
    print("DAILY_POST_OK:", r)
except Exception as e:
    traceback.print_exc()
    print("DAILY_POST_FAIL:", e)

print("\n=== Triggering missed social drain ===")
try:
    r2 = run_staff_job("social_drain")
    print("SOCIAL_DRAIN_OK:", r2)
except Exception as e:
    traceback.print_exc()
    print("SOCIAL_DRAIN_FAIL:", e)

print("\n=== Done ===")