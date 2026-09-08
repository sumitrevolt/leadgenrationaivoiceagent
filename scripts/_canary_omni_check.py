import os
import urllib.request

print("OMNIROUTE_ENABLED", os.getenv("OMNIROUTE_ENABLED"))
print("OMNIROUTE_VOICE", os.getenv("OMNIROUTE_VOICE"))
print("BASE_URL_set", bool(os.getenv("OMNIROUTE_BASE_URL")))
try:
    from app.voice_agent.omniroute_client import omniroute_available

    print("omniroute_available", omniroute_available())
except Exception as e:
    print("omniroute_available ERROR", e)

try:
    r = urllib.request.urlopen("http://172.16.1.1:20128/health", timeout=5)  # nosec B310 — fixed http health URL
    print("gateway_status", getattr(r, "status", 200))
    print("gateway_body", r.read().decode()[:300])
except Exception as e:
    print("gateway_error", type(e).__name__, str(e)[:200])

from app.telephony.dial_gate import allowlist, test_mode

print("test_mode", test_mode())
print("9359984977_in_allowlist", "9359984977" in allowlist())
