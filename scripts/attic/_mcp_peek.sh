#!/bin/bash
echo "=== docker build activity (last 60s) ==="
docker events --since 60s --until 0s --filter type=image --filter type=container 2>/dev/null | head -20 || true
echo ""
echo "=== current containers ==="
docker ps --format "{{.Names}} {{.Status}}"
echo ""
echo "=== leadgen image age ==="
docker images | grep -i leadgen | head -5
echo ""
echo "=== buildkit progress (if active) ==="
ps aux | grep -E "docker.build|buildkit" | grep -v grep | head -5
