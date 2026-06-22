#!/bin/sh
exec python3 /app/scripts/fire_calls_loop.py --batch-size 3 --platform --learn --pause-batch 120 >> /app/data/call_loop.log 2>&1
