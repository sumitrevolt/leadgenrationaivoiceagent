"""Import-health / circular-ref check: build the full app and confirm telephony routes."""

from app.main import app

print("IMPORT_OK routes=%d" % len(app.routes))
paths = {getattr(r, "path", "") for r in app.routes}
for p in (
    "/api/webhooks/vobiz/answer",
    "/api/webhooks/vobiz/status",
    "/api/webhooks/health",
):
    print(("MOUNTED " if p in paths else "MISSING ") + p)
