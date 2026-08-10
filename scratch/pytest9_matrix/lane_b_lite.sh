#!/bin/bash
# Lane B-lite: synthetic loop×engine stress + small async suite (faster than full shard)
set -euo pipefail
OUT=scratch/pytest9_matrix
mkdir -p "$OUT"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq gcc g++ >/tmp/apt.log
python -m pip install -q --upgrade pip wheel
# Minimal deps to exercise greenlet + sqlalchemy async + pytest-asyncio
pip install -q "greenlet==3.5.4" "SQLAlchemy==2.0.36" "aiosqlite==0.22.1" \
  "pytest==9.0.3" "pytest-asyncio==1.4.0" "pytest-timeout==2.4.0"

python - <<'PY' | tee "$OUT/B_lite_stress_function.txt"
import asyncio, gc, os, tempfile
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

path = os.path.join(tempfile.gettempdir(), "gl_stress.db")
url = f"sqlite+aiosqlite:///{path}"
engine = create_async_engine(url, poolclass=NullPool)

async def one(i):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SELECT 1")

async def many(n=300):
    for i in range(n):
        # emulate pytest-asyncio function loop: new Runner each time
        asyncio.run(one(i))
        if i % 50 == 0:
            gc.collect()
    # pytest9-like hard collect
    for _ in range(5):
        gc.collect()
    await engine.dispose()

# dispose on fresh loop like conftest
asyncio.run(many())
print("function_loop_stress_exit=0")
PY

python - <<'PY' | tee "$OUT/B_lite_stress_session.txt"
import asyncio, gc, os, tempfile
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

path = os.path.join(tempfile.gettempdir(), "gl_stress2.db")
url = f"sqlite+aiosqlite:///{path}"
engine = create_async_engine(url, poolclass=NullPool)

async def one(i):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SELECT 1")

async def many(n=300):
    for i in range(n):
        await one(i)
        if i % 50 == 0:
            gc.collect()
    for _ in range(5):
        gc.collect()
    await engine.dispose()

asyncio.run(many())
print("session_loop_stress_exit=0")
PY

echo B_LITE_DONE | tee -a "$OUT/matrix.log"
