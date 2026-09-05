from app.tasks.daily_social_post import run_daily_social_post
from app.tasks.staff_jobs import run_staff_job
import traceback

print("=== Triggering missed daily social post (missed 9:30 AM) ===")
try:
    result = run_daily_social_post()
    print("Daily social post completed:", result)
except Exception as e:
    print("Daily social post error:", e)
    traceback.print_exc()

print("\n=== Triggering missed social drain (missed hourly) ===")
try:
    result2 = run_staff_job("social_drain")
    print("Social drain completed:", result2)
except Exception as e:
    print("Social drain error:", e)
    traceback.print_exc()