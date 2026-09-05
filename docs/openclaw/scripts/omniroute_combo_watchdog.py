#!/usr/bin/env python3
"""omniroute_combo_watchdog.py — local watchdog over the 14 leadsgen combos.

WHY
---
The gateway (leadgen_omniroute Docker, :20128) carries the canonical
`leadsgen combo 1..14` ids that app/platform worker routing now depends on
(_TASK_ROUTES → generate()). If a combo's lanes go dead the scheduler/staff
jobs mapped to it silently degrade. This watchdog pings every canonical combo
through the SAME `/v1/responses` path the app uses and alerts (ntfy) when a
lane stops returning 200 for N consecutive checks — plus a recovery ping.

WHY RESPONSES (not /v1/models or /health)
------------------------------------------
`/v1/models` lists combos but the gateway consults a DIFFERENT per-connection
live catalog, and there is no /health endpoint — the only truthful signal is a
real HTTP 200 + non-empty output_text on `/v1/responses` with the combo name
(verified 12/12 task routes → combos on 2026-09-05). Combo name = the
app-routable unit; each combo carries 3 internal model lanes with gateway-side
priority failover, so a combo that answers 200 means its live lane set works.

STATE & ALERTING
----------------
Persists consecutive-failure counters to `data/omniroute_combo_state.json`
so a single blip never alerts. Alerts once per combo when failures reach
`--strikes` (default 3), then again on recovery. Alerts go through
`app.integrations.ntfy` (gated NTFY_URL+NTFY_TOPIC — unset = no-op, prints).

USAGE
-----
    .venv\\Scripts\\python.exe scripts/omniroute_combo_watchdog.py              # one pass
    .venv\\Scripts\\python.exe scripts/omniroute_combo_watchdog.py --loop 300   # every 5 min
    .venv\\Scripts\\python.exe scripts/omniroute_combo_watchdog.py --json       # wrapper-friendly
    # Optional Task Scheduler registration (pattern = setup_autoboot.ps1):
    powershell -ExecutionPolicy Bypass -File scripts\\register_omniroute_watchdog.ps1

Exit codes (one-shot): 0 = all combos OK · 1 = >=1 combo down past strikes ·
2 = gateway unreachable / config error. Pair with Task Scheduler or cron for a
periodic check; `--loop` keeps a single local process running forever.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_BASE = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1")
STATE_FILE = os.path.join("data", "omniroute_combo_state.json")
PROBE_PROMPT = "Reply with exactly: OK"
PROBE_MAX_TOKENS = 16

# Matches the app's own probe budget (omniroute_client._timeout_seconds clamps
# to 90; lanes measured up to ~22 s, so 40 s is safe headroom without a hang).
DEFAULT_TIMEOUT_S = 40.0
DEFAULT_STRIKES = 3
DEFAULT_WORKERS = 4


def _key() -> str:
    return os.getenv("OMNIROUTE_API_KEY") or os.getenv("OMNIROUTE_MANAGEMENT_API_KEY", "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — state is advisory, never crash
        print(f"[WARN] state write failed: {e}")


def discover_combos(base: str, key: str) -> list[str] | None:
    """Return the 14 canonical combo ids from /v1/models, or None if unreachable."""
    try:
        req = urllib.request.Request(
            base.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ids = [m.get("id", "") for m in json.loads(resp.read()).get("data", [])]
        canon = sorted(i for i in ids if i.startswith("leadsgen combo"))
        # Gateway must expose the canonical 14; tolerate exact-14 + sorted.
        return canon if len(canon) >= 14 else None
    except Exception as e:  # noqa: BLE001 — probe reports, never crashes
        print(f"[ERR] gateway /v1/models unreachable: {type(e).__name__}: {e}")
        return None


def probe_combo(base: str, key: str, combo: str, timeout: float) -> dict:
    """One real /v1/responses call with the combo name — same path the app uses.

    Returns {ok: bool, code: int|None, ms: int, error: str|None, model: str|None}.
    """
    payload = {
        "model": combo,
        "input": [{"role": "user", "content": PROBE_PROMPT}],
        "max_output_tokens": PROBE_MAX_TOKENS,
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/responses",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            text = str(body.get("output_text") or "").strip()
            ok = bool(text)
            return {
                "ok": ok,
                "code": resp.status,
                "ms": round((time.perf_counter() - t0) * 1000),
                "error": None if ok else "empty_output",
                "model": str(body.get("model") or "") or None,
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "code": e.code,
            "ms": round((time.perf_counter() - t0) * 1000),
            "error": f"HTTP {e.code}",
            "model": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "code": None,
            "ms": round((time.perf_counter() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
            "model": None,
        }


def _run_pass(base: str, key: str, combos: list[str], timeout: float, workers: int) -> dict:
    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(probe_combo, base, key, c, timeout): c for c in combos}
        for fut in concurrent.futures.as_completed(futs):
            combo = futs[fut]
            results[combo] = fut.result()
    return results


def _alert(title: str, body: str, priority: str = "high") -> None:
    """ntfy push when configured (repo-standard), else print. Never raises."""
    try:
        import asyncio

        from app.integrations import ntfy

        async def _go():
            try:
                await ntfy.push(title, body, priority=priority, tags=["computer"])
            except Exception:
                pass

        asyncio.run(_go())
    except Exception:  # noqa: BLE001 — watchdog must survive missing deps
        pass
    print(f"[ALERT] {title}\n{body}")


def run_once(
    base: str, key: str, timeout: float, strikes: int, workers: int, quiet: bool = False
) -> int:
    """One check pass over all combos. Returns process exit code."""
    combos = discover_combos(base, key)
    if combos is None:
        body = (
            f"Gateway {base} unreachable or canonical 14-combo set missing.\n"
            "Check: docker ps | grep leadgen_omniroute · docker logs leadgen_omniroute"
        )
        _alert("🚨 OmniRoute gateway DOWN", body, priority="urgent")
        return 2
    if not key:
        print("[WARN] OMNIROUTE_API_KEY unset — probing without auth header")
    state = _load_state()
    results = _run_pass(base, key, combos, timeout, workers)
    now = _now_iso()
    down_now: list[str] = []
    changed_alerts: list[tuple[str, str]] = []

    for combo in combos:
        r = results.get(combo, {})
        ok = bool(r.get("ok"))
        rec = dict(state.get(combo) or {})
        fails = int(rec.get("fails") or 0)
        was_alerted = bool(rec.get("alerted"))
        ms = r.get("ms") or 0
        error = r.get("error") or "unknown"
        model = r.get("model") or "-"

        if ok:
            if fails >= strikes and was_alerted:
                changed_alerts.append(
                    (
                        "✅ OmniRoute combo recovered",
                        f"{combo} answering again (was down {fails} checks). "
                        f"model={model} · {ms} ms",
                    )
                )
            rec = {"fails": 0, "alerted": False, "last_ok": now, "last_error": ""}
        else:
            fails += 1
            rec["fails"] = fails
            rec["alerted"] = False
            rec["last_error"] = f"{error} ({ms} ms)"
            if fails >= strikes:
                # Down past threshold — drives a non-zero exit every pass until
                # recovery, but the ALERT fires only once (transition to down).
                down_now.append(combo)
                if not was_alerted:
                    rec["alerted"] = True
                    changed_alerts.append(
                        (
                            "🚨 OmniRoute combo DOWN",
                            f"{combo} failed {fails} consecutive checks · last: {error} "
                            f"({ms} ms). Worker mapped to this combo is not getting 200s.",
                        )
                    )
        state[combo] = rec
        if not quiet:
            mark = "OK " if ok else f"FAIL({fails})"
            print(f"[{mark}] {combo:<18} {ms:>6} ms  {model if ok else (error or '')}")

    _save_state(state)

    for title, body in changed_alerts:
        _alert(title, body)

    if not quiet:
        ok_n = sum(1 for c in combos if results.get(c, {}).get("ok"))
        print(f"\npass complete: {ok_n}/{len(combos)} combos OK · strikes={strikes}")
    return 1 if down_now else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ping the 14 leadsgen combos; alert on dead lanes")
    ap.add_argument("--base", default=DEFAULT_BASE, help="gateway base URL")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="per-combo probe timeout s")
    ap.add_argument("--strikes", type=int, default=DEFAULT_STRIKES, help="consecutive failures before alert")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="parallel probes")
    ap.add_argument("--loop", type=float, default=0.0, help="run periodically every N seconds (0 = one pass)")
    ap.add_argument("--quiet", action="store_true", help="only print alerts/summary")
    ap.add_argument("--json", action="store_true", help="print final state as JSON (one-shot)")
    args = ap.parse_args()

    key = _key()
    while True:
        try:
            code = run_once(
                args.base, key, args.timeout, max(1, args.strikes), max(1, args.workers), args.quiet
            )
        except KeyboardInterrupt:
            return 130
        except Exception as e:  # noqa: BLE001 — outer guard
            print(f"[ERR] pass crashed: {type(e).__name__}: {e}")
            code = 2

        if args.json:
            print(json.dumps(_load_state(), indent=2))
        if args.loop <= 0:
            return code
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
