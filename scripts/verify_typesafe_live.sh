#!/bin/bash
# Post-refresh verification: health + DSH worker + TypeSafe consumers
echo "=== app health ==="
curl -s http://127.0.0.1:8000/health 2>&1 | head -c 500
echo ""
echo "=== container states ==="
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'leadgen_(app|worker|dsh)' 
echo "=== TYPESAFE env in workers (len only) ==="
for c in leadgen_worker leadgen_app; do
  docker exec $c python -c "import os; k=os.getenv('TYPESAFE_API_KEY',''); print(f'$c len={len(k)} enabled={bool(k)}')" 2>&1
done
echo "=== TypeSafe consumers in code (grep) ==="
grep -rl "typesafe\|TypeSafe" /opt/leadgen/app 2>/dev/null | head -20
echo "DONE"
