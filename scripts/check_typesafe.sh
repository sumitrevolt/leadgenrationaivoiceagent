#!/bin/bash
# Check TypeSafe key in container
docker exec leadgen_app python -c 'import os; k=os.getenv("TYPESAFE_API_KEY",""); print(f"len={len(k)} prefix={k[:12]}... enabled={bool(k)}")'
echo "---"
docker exec leadgen_app python -c '
from app.platform.typesafe_integration import get_typesafe_client
client = get_typesafe_client()
print(f"enabled={client.enabled}")
print(f"key_prefix={client.api_key[:12]}...")
resp = client.initialize()
print(f"initialized={resp.success}")
' 2>&1
