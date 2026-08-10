#!/bin/bash
# Fixed B-lite: function-loop topology via separate asyncio.Runner, not nested run()
set -euo pipefail
OUT=scratch/pytest9_matrix
mkdir -p "$OUT"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq gcc g++ >/tmp/apt.log
python -m pip install -q --upgrade pip wheel
pip install -q "greenlet==3.5.4" "SQLAlchemy==2.0.36" "aiosqlite==0.22.1"

python - <<'PY' | tee "$OUT/B_lite_stress_function.txt"
import asyncio, gc, os, tempfile, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

path = os.path.join(tempfile.gettempdir(), "gl_stress.db")
url = f"sqlite+aiosqlite:///{path}"
engine = create_async_engine(url, poolclass=NullPool)

async def one(i):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SELECT 1")

# Function-scoped loops: each call gets a fresh Runner/loop (pytest-asyncio 1.x default)
for i in range(400):
    with asyncio.Runner() as runner:
        runner.run(one(i))
    if i % 50 == 0:
        gc.collect()
for _ in range(8):
    gc.collect()
with asyncio.Runner() as runner:
    runner.run(engine.dispose())
print("function_loop_stress_exit=0")
sys.exit(0)
PY
echo FUNC_RC=$? | tee -a "$OUT/B_lite_stress_function.txt"

python - <<'PY' | tee "$OUT/B_lite_stress_session.txt"
import asyncio, gc, os, tempfile, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

path = os.path.join(tempfile.gettempdir(), "gl_stress2.db")
url = f"sqlite+aiosqlite:///{path}"
engine = create_async_engine(url, poolclass=NullPool)

async def one(i):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SELECT 1")

async def many(n=400):
    for i in range(n):
        await one(i)
        if i % 50 == 0:
            gc.collect()
    for _ in range(8):
        gc.collect()
    await engine.dispose()

asyncio.run(many())
print("session_loop_stress_exit=0")
sys.exit(0)
PY
echo SESS_RC=$? | tee -a "$OUT/B_lite_stress_session.txt"
echo B_LITE_DONE | tee -a "$OUT/matrix.log"
