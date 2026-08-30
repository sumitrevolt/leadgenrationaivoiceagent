import os, requests, json

env = {}
with open("/opt/leadgen/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")

auth_id = env.get("VOBIZ_AUTH_ID")
auth_token = env.get("VOBIZ_AUTH_TOKEN")
caller_id = env.get("VOBIZ_CALLER_ID")
print(f"Config: AuthID={auth_id}, CallerID={caller_id}")

auth = (auth_id, auth_token)
base = f"https://api.vobiz.ai/api/v1/Account/{auth_id}"

# 1. Account
r = requests.get(f"{base}/", auth=auth)
print("Account status:", r.status_code, r.text[:300])

# 2. Number
r = requests.get(f"{base}/Number/", auth=auth)
print("Numbers:", r.status_code, r.text[:500])

# 3. Calls
r = requests.get(f"{base}/Call/?limit=30", auth=auth)
if r.status_code == 200:
    data = r.json()
    print("Total calls in Vobiz:", data.get("meta", {}).get("total_count"))
    for c in data.get("objects", []):
        print(f"{c.get('created_at')} | From: {c.get('from_number')} | To: {c.get('to_number')} | Cause: {c.get('hangup_cause')} ({c.get('hangup_cause_code')}) | Dur: {c.get('bill_duration')}")
