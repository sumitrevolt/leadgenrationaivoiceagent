#!/usr/bin/env python3
"""Agents + skills full debugger — STAFF, FDE, coordinator, skill_pack (NDJSON → debug-6e326c.log).

Loops:
  A STAFF roster + team_status + 7d event coverage
  B Coordinator allowlist vs STAFF gap
  C FDE agents + skill handlers (import/dry, no LLM deploy)
  D skill_pack load integrity (project + extra)
  E Skill wiring consumers (post_generator, self_improve, infra_handler)
  F Autonomous agents (self_improve, sales_team, process_engine, supervisor)
  G Engineer agents + flags (pranav/vidya/arnav, guru, vikram)

Run: python scripts/agents_skills_debug.py
VPS: docker exec leadgen_app python scripts/agents_skills_debug.py
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "debug-f2166f.log"
SESSION = "f2166f"
RUN = os.environ.get("AGENTS_DEBUG_RUN", "agents1")


def _log(hid: str, loc: str, msg: str, data: dict | None = None) -> None:
    row = {
        "sessionId": SESSION,
        "hypothesisId": hid,
        "location": loc,
        "message": msg,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": RUN,
    }
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    broken = data and data.get("broken") is True
    flag = "BROKEN" if broken else "OK"
    print(f"[{hid}][{flag}] {msg} | {data or {}}")


def probe_staff() -> None:
    from app.platform import team

    keys = list(team.STAFF.keys())
    ts = team.team_status() or {}
    members = {m.get("key"): m for m in (ts.get("members") or [])}
    evs = team.recent_events(limit=200) or []
    seen = {e.get("agent") or e.get("member") for e in evs}
    no_events = [k for k in keys if k not in seen]
    _log(
        "A",
        "agents:staff",
        "STAFF roster + activity",
        {
            "count": len(keys),
            "keys": keys,
            "working": (ts.get("totals") or {}).get("working_members"),
            "no_recent_events": no_events,
            "broken": len(keys) < 14,
        },
    )


def probe_coordinator_gap() -> None:
    from app.agents import coordinator
    from app.platform.team import STAFF

    allowed = set(coordinator._agent_keys())
    missing = [k for k in STAFF if k not in allowed]
    tools = set(getattr(coordinator, "_TOOLS", {}).keys())
    no_tool = [k for k in allowed if k not in tools and k not in ("manager", "rohan", "swara")]
    _log(
        "B",
        "agents:coordinator",
        "coordinator allowlist vs STAFF",
        {
            "allowed": len(allowed),
            "staff_total": len(STAFF),
            "not_in_coordinator": missing,
            "draft_only_agents": no_tool,
            "executable_agents": sorted(tools),
            "broken": bool(missing),
        },
    )


async def probe_fde() -> None:
    from app.agents import fde

    agents = fde.list_agents()
    broken_handlers: list[str] = []
    for sk_key, sk in fde.SKILLS.items():
        h = sk.get("handler")
        if not callable(h):
            broken_handlers.append(sk_key)
    ctx = {"business_name": "Debug Biz", "niche": "solar", "city": "Mumbai", "slug": "debug-slug"}
    dry_ok, dry_fail = [], []
    for sk_key in fde.SKILLS.keys():
        try:
            res = await fde.SKILLS[sk_key]["handler"](ctx)
            (dry_ok if res.get("ok") is not False else dry_fail).append(sk_key)
        except Exception as e:
            dry_fail.append(f"{sk_key}:{type(e).__name__}")
    _log(
        "C",
        "agents:fde",
        "FDE agents + skills",
        {
            "fde_agents": len(agents),
            "skills": len(fde.SKILLS),
            "broken_handlers": broken_handlers,
            "dry_all_ok": dry_ok,
            "dry_all_fail": dry_fail,
            "broken": bool(broken_handlers) or bool(dry_fail),
        },
    )


def probe_skill_pack() -> None:
    from app.platform import skill_pack

    skills = skill_pack.list_skills()
    empty = [s["name"] for s in skills if int(s.get("chars") or 0) < 50]
    load_fail = []
    for s in skills:
        if not skill_pack.load(s["name"]):
            load_fail.append(s["name"])
    dupes: dict[str, int] = {}
    for s in skills:
        dupes[s["name"]] = dupes.get(s["name"], 0) + 1
    dupe_names = [n for n, c in dupes.items() if c > 1]
    find_hit = skill_pack.find("deploy marketing automation", k=2)
    _log(
        "D",
        "skills:pack",
        "skill_pack integrity",
        {
            "total": len(skills),
            "project": sum(1 for s in skills if s.get("source") == "project"),
            "extra": sum(1 for s in skills if s.get("source") == "extra"),
            "enabled": skill_pack.enabled(),
            "empty_skills": empty[:10],
            "load_fail_sample": load_fail,
            "duplicate_names": dupe_names[:5],
            "find_matches": [h.get("name") for h in find_hit],
            "broken": bool(empty) or bool(load_fail),
        },
    )


def probe_skill_wiring() -> None:
    wiring = {}
    broken = False
    try:
        from app.platform import skill_pack

        wiring["post_generator"] = bool(
            skill_pack.snippet_for("marketing post caption", max_chars=200)
        )
        wiring["self_improve_flag"] = skill_pack.enabled()
        wiring["infra_handler_import"] = (
            importlib.util.find_spec("app.platform.infra_handler") is not None
        )
    except Exception as e:
        wiring["error"] = str(e)[:80]
        broken = True
    _log(
        "E",
        "skills:wiring",
        "skill consumer wiring",
        {**wiring, "broken": broken and not wiring.get("post_generator")},
    )


def probe_autonomous() -> None:
    out: dict = {}
    try:
        from app.agents import self_improve

        out["self_improve"] = self_improve.enabled()
    except Exception as e:
        out["self_improve_err"] = str(e)[:60]
    try:
        from app.agents import sales_team

        out["sales_team"] = sales_team._enabled()
    except Exception as e:
        out["sales_team_err"] = str(e)[:60]
    try:
        from app.agents import process_engine

        runs = process_engine.list_runs() or []
        out["process_engine_runs"] = len(runs)
    except Exception as e:
        out["process_engine_err"] = str(e)[:60]
    try:
        from app.agents import AGENTS_AVAILABLE

        out["langgraph_supervisor"] = AGENTS_AVAILABLE
    except Exception as e:
        out["supervisor_err"] = str(e)[:60]
    _log("F", "agents:autonomous", "autonomous agent modules", {**out, "broken": False})


def probe_automation_wiring() -> None:
    """H: dead flags / orphan STAFF_JOBS."""
    try:
        import subprocess

        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "automation_wiring_audit.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=str(ROOT),
        )
        out = (r.stdout or "") + (r.stderr or "")
        ok = r.returncode == 0 and ("[OK]" in out or "all automation flags wired" in out)
        _log(
            "H",
            "agents:wiring_audit",
            "automation wiring audit",
            {"exit": r.returncode, "ok_line": ok, "broken": not ok},
        )
    except Exception as e:
        _log(
            "H",
            "agents:wiring_audit",
            "automation wiring audit",
            {"error": str(e)[:80], "broken": True},
        )


async def probe_self_improve_fast() -> None:
    """I: self_improve ACTIONS import + gated skip (no network scrape)."""
    out: dict = {}
    broken = False
    try:
        from app.agents import self_improve as si

        out["actions"] = len(si.ACTIONS)
        out["enabled"] = si.enabled()
        for act in ("cadence_sweep", "code_scan", "voice_eval", "rescore_pipeline"):
            try:
                res = await asyncio.wait_for(si._execute(act, "debug-smoke"), timeout=15)
                out[f"exec_{act}"] = {
                    "ok": res.get("ok"),
                    "detail": str(res.get("detail", ""))[:60],
                }
            except Exception as e:
                out[f"exec_{act}"] = {"err": type(e).__name__}
                broken = True
    except Exception as e:
        out["import_err"] = str(e)[:80]
        broken = True
    _log("I", "agents:self_improve", "self_improve fast probe", {**out, "broken": broken})


def probe_security_kpi() -> None:
    """J: Arnav security agent KPI shape (post-Razorpay removal)."""
    import os

    prev = os.environ.get("SECURITY_AGENT")
    os.environ["SECURITY_AGENT"] = "1"
    try:
        from app.platform import engineer_agents as ea

        out = ea.run_security()
        armed = out.get("kpis", {}).get("webhook_secrets_armed") or {}
        has_razorpay = "razorpay" in armed
        _log(
            "J",
            "agents:security_kpi",
            "security webhook_secrets_armed shape",
            {
                "keys": list(armed.keys()),
                "has_razorpay_stale": has_razorpay,
                "score": out.get("score"),
                "broken": has_razorpay,
            },
        )
    except Exception as e:
        _log(
            "J",
            "agents:security_kpi",
            "security probe failed",
            {"error": str(e)[:80], "broken": True},
        )
    finally:
        if prev is None:
            os.environ.pop("SECURITY_AGENT", None)
        else:
            os.environ["SECURITY_AGENT"] = prev


def probe_engineers() -> None:
    def _on(k: str) -> bool:
        return os.getenv(k, "").strip().lower() in ("1", "true", "yes")

    flags = {
        "SKILL_PACK": _on("SKILL_PACK"),
        "CODE_UPGRADER": _on("CODE_UPGRADER"),
        "SRE_AGENT": _on("SRE_AGENT"),
        "FINOPS_AGENT": _on("FINOPS_AGENT"),
        "SECURITY_AGENT": _on("SECURITY_AGENT"),
        "INFRA_HANDLER": _on("INFRA_HANDLER"),
    }
    eng_status = {}
    try:
        from app.platform import engineer_agents

        for role, res in engineer_agents.run_all().items():
            eng_status[role] = res.get("status")
    except Exception as e:
        eng_status["error"] = str(e)[:80]
    _log(
        "G",
        "agents:engineers",
        "engineer agents + flags",
        {"flags": flags, "engineer_status": eng_status, "broken": False},
    )


async def main_async() -> int:
    print("=== AGENTS + SKILLS DEBUG ===")
    probe_staff()
    probe_coordinator_gap()
    await probe_fde()
    probe_skill_pack()
    probe_skill_wiring()
    probe_autonomous()
    probe_automation_wiring()
    await probe_self_improve_fast()
    probe_security_kpi()
    probe_engineers()
    # verdict from log file
    broken = []
    try:
        for line in LOG.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("sessionId") == SESSION and (row.get("data") or {}).get("broken"):
                broken.append(row.get("hypothesisId"))
    except Exception:
        pass
    print(f"\n=== VERDICT: {len(broken)} broken probe(s) {broken or '(none)'} ===")
    print(f"Logs -> {LOG}")
    return 1 if broken else 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
