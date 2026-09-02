"""Smoke — process engine live (worker container me): client_content run start →
advance → breakpoint pe ruke → approve → complete. Run:
docker exec leadgen_worker python scripts/smoke_process.py
"""

from __future__ import annotations

import asyncio
import json


def main() -> None:
    from app.agents import process_engine as pe

    r = pe.start_run(
        "client_content",
        {"niche": "solar_dealers", "city": "Pune", "business_name": "Sharma Solar"},
    )
    print("START", json.dumps(r, ensure_ascii=False))
    rid = r["run_id"]

    out = asyncio.run(pe.advance(rid))
    print(
        "ADVANCE1",
        json.dumps(
            {k: out.get(k) for k in ("status", "breakpoint", "step", "error")}, ensure_ascii=False
        ),
    )
    assert out["status"] == pe.ST_WAITING, "breakpoint pe rukna chahiye tha"

    # enforced stop proof: approve ke bina aage nahi
    out2 = asyncio.run(pe.advance(rid))
    assert out2["status"] == pe.ST_WAITING
    print("ENFORCED_STOP ok")

    a = pe.approve(rid, "sumit-smoke", "pack reviewed")
    print("APPROVE", json.dumps(a, ensure_ascii=False))
    out3 = asyncio.run(pe.advance(rid))
    print("ADVANCE2", json.dumps({k: out3.get(k) for k in ("status", "error")}, ensure_ascii=False))

    st = pe.replay(rid)
    print("STEPS_DONE", [s["step"] for s in st["steps_done"]])
    print("JOURNAL_EVENTS", [e["type"] for e in pe.journal(rid)])
    print(
        "SMOKE_PROCESS_PASS"
        if st["status"] == pe.ST_COMPLETED
        else f"SMOKE_FAIL status={st['status']} err={st['last_error']}"
    )


if __name__ == "__main__":
    main()
