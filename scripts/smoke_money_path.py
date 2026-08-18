import json

import httpx

base_url = "https://leadsgenai.in"


def smoke_test():
    print("Smoking money path...")
    with httpx.Client(base_url=base_url) as client:
        # 1. /
        r1 = client.get("/")
        print("/", r1.status_code)

        # 2. /pricing
        r2 = client.get("/pricing")
        print("/pricing", r2.status_code)

        # 3. /start
        r3 = client.get("/start")
        print("/start", r3.status_code)

        # 4. Signup
        signup_data = {
            "business_name": "Smoke Test E2E22",
            "email": "smoketest123444@example.com",
            "password": "password123",  # pragma: allowlist secret,
            "phone": "+919999999901",
            "plan": "starter",
            "_turnstile_token": "",  # Fail-closed if actually validated, let's see
        }
        r4 = client.post("/api/public/signup", json=signup_data)
        print("Signup:", r4.status_code, r4.text)

        auth_token = None
        if r4.status_code == 200:
            resp = r4.json()
            auth_token = resp.get("access_token")
            client_id = resp.get("client_id")
            print("Token acquired.")

            # Submit UPI
            headers = {"Authorization": f"Bearer {auth_token}"}
            r5 = client.post(
                "/api/upi/submit",
                json={"upi_ref": "SMOKETEST002", "amount": 1999, "plan": "starter"},
                headers=headers,
            )
            print("UPI Submit:", r5.status_code, r5.text)


if __name__ == "__main__":
    smoke_test()
