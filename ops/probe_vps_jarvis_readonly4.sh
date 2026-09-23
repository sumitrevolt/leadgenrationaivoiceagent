#!/usr/bin/env bash
set -u
echo "=== container entrypoint/cmd ==="
docker inspect leadgen_telegram_jarvis -f 'ENTRYPOINT={{json .Config.Entrypoint}}'
docker inspect leadgen_telegram_jarvis -f 'CMD={{json .Config.Cmd}}'
echo
echo "=== compose service command field ==="
sed -n '/telegram-jarvis:/,/^[a-z_-]*:/p' /opt/leadgen/docker-compose.vps.yml | grep -E 'command:|entrypoint:' -A2
echo
echo "=== where does the container's data/ come from (mounts) ==="
docker inspect leadgen_telegram_jarvis -f '{{json .Mounts}}' | tr ',' '\n' | grep -E 'Source|Target' | head -8
