"""Import-health / circular-ref check: build the full app and confirm telephony routes."""
from app.main import app

print("IMPORT_OK routes=%d" % len(app.routes))
paths = {getattr(r, "path", "") for r in app.routes}
for p in (
    "/api/webhooks/twilio/voice/{call_id}",
    "/api/webhooks/twilio/status/{call_id}",
    "/api/webhooks/exotel/status",
    "/api/webhooks/exotel/voice",
    "/api/webhooks/health",
):
    print(("MOUNTED " if p in paths else "MISSING ") + p)
