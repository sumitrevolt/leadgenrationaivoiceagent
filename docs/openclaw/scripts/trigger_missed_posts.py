"""
Trigger missed social + video posts immediately.
This bypasses the Celery beat schedule and runs jobs directly.
"""
import sys
import traceback

results = {}

# --- 1. Daily social post (missed 9:30 AM run) ---
try:
    from app.tasks.daily_social_post import run_daily_social_post
    r = run_daily_social_post()
    results['daily_social_post'] = r
    print("[OK] Daily social post completed:", r)
except Exception as e:
    results['daily_social_post_error'] = str(e)
    print("[FAIL] Daily social post error:", e)
    traceback.print_exc()

# --- 2. Social drain (missed hourly drain - was 502 earlier) ---
try:
    from app.tasks.staff_jobs import run_staff_job
    r2 = run_staff_job('social_drain')
    results['social_drain'] = r2
    print("[OK] Social drain completed:", r2)
except Exception as e:
    results['social_drain_error'] = str(e)
    print("[FAIL] Social drain error:", e)
    traceback.print_exc()

# --- 3. Summary for ntfy (optional) ---
try:
    import json
    summary = json.dumps(results, indent=2, default=str)
    print("\n=== FINAL SUMMARY ===")
    print(summary)

    # Optional: send to ntfy
    try:
        import urllib.request
        data = summary.encode()
        req = urllib.request.Request(
            "http://ntfy:8080/leadgen",
            data=data,
            method="POST"
        )
        req.add_header("Title", "MISSED SOCIAL POST - Catchup")
        req.add_header("Priority", "high")
        req.add_header("Tags", "warning,rocket")
        resp = urllib.request.urlopen(req, timeout=10)
        print("[ntfy] Sent catchup summary")
    except Exception as e:
        print(f"[ntfy] Could not send to ntfy: {e}")
except Exception as e:
    print("[summary] Could not format results:", e)