#!/bin/sh
# Fail-closed Celery worker liveness for Docker HEALTHCHECK.
#
# MUST ping THIS container's worker only (`-d celery@$HOSTNAME`). A broadcast
# `inspect ping` can collect a healthy sibling's pong while this process is
# dead — false green under OOM (2026-07-28).
#
# Timeout: `-t 8` must stay under compose healthcheck `timeout` (15s).
# Broken pipe / Error / empty / no pong → exit 1.
# No pipelines: slim /bin/sh cannot harden pipelines; capture then match.
set -eu

DEST="celery@${HOSTNAME:?HOSTNAME unset}"
OUT="$(celery -A app.worker inspect ping -d "$DEST" -t 8 2>&1)" || {
  case "$OUT" in
    *[Bb]roken\ [Pp]ipe*|*[Ee]rror*|*[Cc]onnection*|*not\ connected*|*timed\ out*) exit 1 ;;
  esac
  exit 1
}

case "$OUT" in
  *[Bb]roken\ [Pp]ipe*) exit 1 ;;
esac

# Require this destination AND a pong in the captured output.
case "$OUT" in
  *"$DEST"*[Pp]ong*|*[Pp]ong*"$DEST"*) exit 0 ;;
esac
# Celery prints nested dict: {'celery@host': {'ok': 'pong'}}
case "$OUT" in
  *"$DEST"*)
    case "$OUT" in
      *pong*|*Pong*|*PONG*) exit 0 ;;
    esac
    ;;
esac
exit 1
