#!/bin/bash
# Self-healing call loop wrapper
if ! docker exec leadgen_app test -f /app/app/tasks/call_loop_runner.py 2>/dev/null; then
    docker cp /opt/leadgen/app/tasks/call_loop_runner.py leadgen_app:/app/app/tasks/call_loop_runner.py 2>/dev/null
fi
docker exec leadgen_app /opt/venv/bin/python -m app.tasks.call_loop_runner
