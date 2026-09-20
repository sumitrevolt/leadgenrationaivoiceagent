#!/bin/bash
# Check TypeSafe key in container safely (sha256 fingerprint only, never key or prefix)
docker exec leadgen_app python -c '
import hashlib, os
k = os.getenv("TYPESAFE_API_KEY", "")
fp = hashlib.sha256(k.encode()).hexdigest()[:12] if k else "none"
state = "PRESENT" if k else "ABSENT"
print(f"state={state} fingerprint={fp} enabled={bool(k)}")
'
echo "---"
docker exec leadgen_app python -c '
import hashlib
from app.platform.typesafe_integration import get_typesafe_client, credential_state
client = get_typesafe_client()
cred = credential_state()
print(f"enabled={client.enabled}")
print(f"state={cred.get(\"state\")} fingerprint={cred.get(\"fingerprint\")}")
resp = client.initialize()
print(f"initialized={resp.success}")
' 2>&1
