"""capacity_baseline.py parser — wrong container names used to empty stats."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "capacity_baseline", REPO / "scripts" / "capacity_baseline.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["capacity_baseline"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load()

SAMPLE = """
---STATS---
leadgen_app 12.34% 1.2GiB / 3GiB 40.00%
leadgen_pgbouncer 0.10% 8MiB / 256MiB 3.12%
leadgen_worker 4.00% 900MiB / 2GiB 45.00%
---QUEUES---
0
1
0
0
1
23
---REDISMEM---
used_memory_human:4.50M
maxmemory_human:256.00M
evicted_keys:0
---FLAGS---
DSH_RUNTIME_ENABLED=1
GSC_ENABLED=0
WEB_CONCURRENCY=2
SALES_AUTOPILOT_WHATSAPP_ENABLED=0
---PG---
12
---DBHOST---
via_pgbouncer True
direct_db_5432 False
---CODE---
notify_owner_once True
list_actionable True
---HOST---
mem_used_mb=9000 mem_total_mb=16000
 05:00:00 up 3 days
---HEALTH---
{"status":"healthy","environment":"production","version":"91958c23"}
---ACTIVATION---
{"blocker_count":1,"payments_ready":true}
---BLOCKERS---
upi_pending_unactioned
"""


def test_parse_keeps_stats_and_named_flags():
    row = mod.parse(SAMPLE)
    assert any(s.startswith("leadgen_app") for s in row["stats"])
    assert any("pgbouncer" in s for s in row["stats"])
    assert row["queues"]["celery"] == 0
    assert row["queues"]["dlq:dead"] == 23
    assert row["flags"]["WEB_CONCURRENCY"] == "2"
    assert row["flags"]["GSC_ENABLED"] == "0"
    assert row["flags"]["DSH_RUNTIME_ENABLED"] == "1"
    assert "DATABASE_URL" not in row["flags"]
    assert row["blocker_keys"] == ["upi_pending_unactioned"]
    assert row["health"]["version"] == "91958c23"
    assert row["code_locks"] == ["notify_owner_once True", "list_actionable True"]
    assert row["dbhost"][0].startswith("via_pgbouncer")
    assert row["activation"]["payments_ready"] is True


def test_parse_does_not_drop_stats_when_one_name_is_missing():
    raw = "---STATS---\nleadgen_app 1% 100MiB / 3GiB 3.00%\n---QUEUES---\n0\n0\n0\n0\n0\n0\n"
    row = mod.parse(raw)
    assert row["stats"] == ["leadgen_app 1% 100MiB / 3GiB 3.00%"]
    assert row["queues"]["celery"] == 0
