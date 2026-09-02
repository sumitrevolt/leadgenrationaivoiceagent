#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.platform.scheduled_ops import run_saturday_hygiene

print(asyncio.run(run_saturday_hygiene()))
