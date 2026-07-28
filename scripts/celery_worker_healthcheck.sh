#!/bin/sh
# Fail-closed Celery worker liveness for Docker HEALTHCHECK.
#
# MUST ping THIS container's worker only (`-d celery@$HOSTNAME`). A broadcast
# `inspect ping` can collect a healthy sibling's pong while this process is
# dead — false green under OOM (2026-07-28).
#
# Timeout: `-t 8` must stay under compose healthcheck `timeout` (15s).
# Broken pipe / Error / empty / no pong → exit 1.
set -eu

DEST="celery@${HOSTNAME:?HOSTNAME unset}"
OUT="$(celery -A app.worker inspect ping -d "$DEST" -t 8 2>&1)" || {
  echo "$OUT" | grep -qiE 'broken pipe|error|connection|not connected|timed out' && exit 1
  exit 1
}

echo "$OUT" | grep -qiE 'broken pipe' && exit 1
# Require this destination to appear with a pong (not another worker).
echo "$OUT" | grep -F "$DEST" | grep -q pong || exit 1
exit 0
