from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)
r = client.post(
    "/api/customer/auth/signup",
    json={
        "business_name": "Test Biz",
        "email": "test@test.com",
        "password": "secret123",  # pragma: allowlist secret
        "plan": "growth",
    },
)
print("status:", r.status_code)
print("keys:", list(r.json().keys()))
print("json:", r.json())
