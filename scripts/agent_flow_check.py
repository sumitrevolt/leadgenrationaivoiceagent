"""Live agent + automation FLOW diagnostic — ek jagah: kaun-sa agent kaam kar raha,
kaun-se loop/job chal rahe/atke, LLM/infra health, flags, funnel. Never-raise.

Run (container me, live state):
  docker cp /opt/leadgen/scripts/agent_flow_check.py leadgen_app:/tmp/ && \
  docker exec leadgen_app python /tmp/agent_flow_check.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sec(t):
    print("\n" + "=" * 64 + f"\n{t}\n" + "=" * 64)


def _safe(label, fn):
    try:
        return fn()
    except Exception as e:
        print(f"  [ERR] {label}: {e}")
        return None


print(f"AGENT FLOW CHECK @ {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

# 1. AI STAFF — kaun active/working/offline
_sec("1. AI STAFF TEAM (kaun kaam kar raha)")


def _team():
    from app.platform import team

    ts = team.team_status() or {}
    members = ts.get("members", [])
    tot = ts.get("totals", {})
    print(f"  staff total={len(members)} working={tot.get('working_members', '?')}")
    for m in members:
        st = m.get("status") or ("working" if (m.get("last_active_mins") or 1e9) < 20 else "idle")
        print(
            f"   - {m.get('key'):10} {st:9} last_active={m.get('last_active_mins')}m  product={m.get('product', '')}"
        )
    return ts


_safe("team_status", _team)

# 2. AUTOMATION HEALTH — dead-man: kaun-se job overdue (= ATKA)
_sec("2. AUTOMATION HEALTH (jobs chal rahe ya atke)")


def _health():
    from app.platform import automation_health

    h = automation_health.health() or {}
    print(f"  overall ok={h.get('ok')} queue={h.get('queue')}")
    overdue = h.get("overdue") or []
    if overdue:
        print(f"  ⚠️ OVERDUE (atke) jobs: {overdue}")
    else:
        print("  ✅ koi job overdue nahi — sab schedule pe")
    # per-job last-run
    try:
        beats = automation_health.beats() if hasattr(automation_health, "beats") else None
    except Exception:
        beats = None
    return h


_safe("automation_health", _health)

# 3. HERMES INFRA SNAPSHOT — infra score + actions + skill suggestions
_sec("3. HERMES INFRA (score + kya theek karna)")


def _hermes():
    import asyncio

    from app.platform import infra_handler

    snap = asyncio.get_event_loop().run_until_complete(infra_handler.snapshot()) if False else None
    try:
        snap = asyncio.run(infra_handler.snapshot())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        snap = loop.run_until_complete(infra_handler.snapshot())
        loop.close()
    print(f"  score={snap.get('score')}/100 status={snap.get('status')}")
    for a in (snap.get("actions") or [])[:6]:
        print(f"   • {a}")
    return snap


_safe("infra_handler.snapshot", _hermes)

# 4. LLM PROVIDERS — AI chain ok-rate (yahin AI 'atak'ta hai agar quota out)
_sec("4. LLM PROVIDERS (AI brain health)")


def _llm():
    from app.platform import llm_metrics

    st = llm_metrics.stats(window=200) or {}
    print(
        f"  total_calls={st.get('total_calls')} fallback/fail_rate={st.get('fallback_or_fail_rate')}"
    )
    provs = st.get("providers") or {}
    for p, v in list(provs.items())[:12]:
        if isinstance(v, dict):
            print(
                f"   - {p:14} ok={v.get('ok_rate', v.get('ok', '?'))} calls={v.get('calls', '?')} last_err={str(v.get('last_error', ''))[:40]}"
            )
    return st


_safe("llm_metrics", _llm)

# 5. AUTOMATION FLAGS — kaun-se loop ON/OFF
_sec("5. AUTOMATION FLAGS (loops ON/OFF)")


def _flags():
    try:
        from app.api.growth import AUTOMATION_FLAGS

        flags = AUTOMATION_FLAGS
    except Exception:
        flags = []
    on, off = [], []
    for f in flags:
        v = (os.environ.get(f) or "").strip().lower()
        (
            on
            if v in ("1", "true", "yes") or (f in ("SEARXNG_URL", "NTFY_URL", "NTFY_TOPIC") and v)
            else off
        ).append(f)
    print(f"  ON ({len(on)}): {', '.join(sorted(on))}")
    print(f"  OFF ({len(off)}): {', '.join(sorted(off))}")
    return {"on": on, "off": off}


_safe("flags", _flags)

# 6. FUNNEL PULSE — lead pipeline kaha tak
_sec("6. GROWTH FUNNEL (lead pipeline state)")


def _pulse():
    from app.platform import growth_engine

    p = growth_engine.latest_pulse() or {}
    pr = p.get("prospects") or {}
    print(
        f"  prospects total={pr.get('total')} ready={pr.get('ready')} client={pr.get('client')} with_email={pr.get('with_email')}"
    )
    print(
        f"  inquiries={p.get('inquiries')} blog={p.get('blog_articles')} content={p.get('content_items')} clients_active={p.get('marketing_clients_active')}"
    )
    if p.get("best_niche"):
        print(f"  best_niche={p.get('best_niche')} ratio={p.get('best_niche_ratio')}")
    return p


_safe("growth_pulse", _pulse)

# 7. PROCESS ENGINE + SELF-IMPROVE — autonomous loops running?
_sec("7. AUTONOMOUS LOOPS (process-engine + self-improve)")


def _loops():
    try:
        from app.agents import process_engine

        runs = process_engine.list_runs() or []
        running = [r for r in runs if r.get("status") == "running"]
        waiting = [r for r in runs if r.get("status") in ("waiting", "paused")]
        print(
            f"  process_engine: total={len(runs)} running={len(running)} waiting-breakpoint={len(waiting)}"
        )
    except Exception as e:
        print(f"  process_engine: {e}")
    try:
        from app.agents import self_improve

        print(f"  self_improve: enabled={self_improve.enabled()}")
    except Exception as e:
        print(f"  self_improve: {e}")


_safe("loops", _loops)

# 8. RECENT AGENT EVENTS — actual activity (kya hua)
_sec("8. RECENT AGENT EVENTS (last 15 — actual kaam)")


def _events():
    from app.platform import team

    evs = team.recent_events(limit=15) or []
    for e in evs:
        print(
            f"   {str(e.get('at', ''))[:19]}  {e.get('agent', '?'):10} {e.get('action', '?'):22} {str(e.get('detail', ''))[:50]}"
        )
    if not evs:
        print("  (koi recent event nahi)")


_safe("recent_events", _events)

print("\n=== FLOW CHECK DONE ===")
