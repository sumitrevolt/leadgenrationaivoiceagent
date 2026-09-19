#!/bin/bash
# Wrapper script for call loop — runs inside container via docker exec
while true; do
    docker exec leadgen_app /opt/venv/bin/python -m app.tasks.call_loop_runner
    sleep 5
done
