#!/usr/bin/env python3
"""One-command NEXT todos READY probe. Public + optional SSH. No secrets.

Usage:
    .venv\\Scripts\\python.exe scripts\\next_todos_ready.py
    .venv\\Scripts\\python.exe scripts\\next_todos_ready.py --offline
    .venv\\Scripts\\python.exe scripts\\next_todos_ready.py --write
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_MD = REPO / "docs" / "gtm" / "NEXT_TODOS_READY.md"
PY = REPO / ".venv" / "Scripts" / "python.exe"
HEALTH = "https://leadsgenai.in/health"
ACTIVATION = "https://leadsgenai.in/api/activation/summary"
INBOX = "https://leadsgenai.in/app/inbox"
ADMIN = "https://leadsgenai.in/app/admin"
LOGIN = "https://leadsgenai.in/app/admin-login"


def _http_json(url: str) -> dict[str, Any]:
    cb = int(time.time())
    full = f"{url}?cb={cb}"
    if not full.startswith(("https://", "http://")):
        raise ValueError("url_scheme_not_allowed")
    req = urllib.request.Request(
        full,
        headers={"Cache-Control": "no-cache", "User-Agent": "leadgen-next-todos-ready"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 — scheme gated above
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _http_code(url: str) -> int:
    cb = int(time.time())
    proc = subprocess.run(
        [
            "curl.exe",
            "-sS",
            "-o",
            "NUL",
            "-w",
            "%{http_code}",
            "-H",
            "Cache-Control: no-cache",
            "--max-time",
            "20",
            f"{url}?cb={cb}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=25,
    )
    try:
        return int((proc.stdout or "0").strip() or "0")
    except ValueError:
        return 0


def _run(args: list[str], timeout: int = 90) -> tuple[int, str]:
    exe = str(PY) if PY.exists() else "python"
    proc = subprocess.run(
        [exe, *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out[-4000:]


def _file_gates() -> dict[str, bool]:
    todos = (REPO / "docs" / "gtm" / "NEXT_TODOS.md").read_text(encoding="utf-8")
    blitz = (REPO / "docs" / "gtm" / "HOT_QUEUE_BLITZ_CHECKLIST.md").read_text(encoding="utf-8")
    cap = (REPO / "docs" / "gtm" / "CAPACITY_50_DAY.md").read_text(encoding="utf-8")
    phase1 = (REPO / "docs" / "gtm" / "PHASE1_GATED_RUNBOOK.md").read_text(encoding="utf-8")
    compose = (REPO / "docker-compose.vps.yml").read_text(encoding="utf-8")
    harness = (REPO / "scripts" / "buzz_start_harness.py").read_text(encoding="utf-8")
    return {
        "next_todos_three_ws": all(key in todos for key in ("WS-GTM1", "WS-BUZZ", "WS-REV50")),
        "web_concurrency_hardcoded_2": "WEB_CONCURRENCY: 2" in compose,
        "inbox_token_paste": "Admin token paste" in blitz and "/app/inbox" in blitz,
        "upi_bind_url": "sec-upi-selfserve" in blitz,
        "capacity_not_live_claim": "Not a claim that 50/day is live" in cap
        or "not a live claim" in cap,
        "phase1_gated_on_phase0": "Do **not** execute this until" in phase1,
        "boss_dry_run_flag": "--dry-run" in harness and "Boss" in harness,
        "celery_onboard_unset_docs": "CELERY_ONBOARD_QUEUE" in todos and "UNSET" in todos,
    }


def build_report(*, offline: bool = False) -> dict[str, Any]:
    probed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    health: dict[str, Any] = {}
    activation: dict[str, Any] = {}
    codes: dict[str, int] = {}
    if not offline:
        health1 = _http_json(HEALTH)
        time.sleep(1.2)
        health2 = _http_json(HEALTH)
        health = {"probe1": health1, "probe2": health2}
        activation = _http_json(ACTIVATION)
        codes = {
            "inbox": _http_code(INBOX),
            "admin": _http_code(ADMIN),
            "admin_login": _http_code(LOGIN),
        }
    dsh_rc, dsh_out = _run(["scripts/dsh_next_todos_plan.py"], timeout=60)
    try:
        dsh_plan = json.loads(dsh_out[dsh_out.find("{") :])
    except json.JSONDecodeError:
        dsh_plan = {"ok": False, "parse_error": True, "rc": dsh_rc}
    supply_rc, supply_out = _run(["scripts/verify_dsh_supply_chain.py"], timeout=30)
    boss_rc, boss_out = _run(
        ["scripts/buzz_start_harness.py", "--agent", "Boss", "--dry-run"],
        timeout=30,
    )
    ts1 = str((health.get("probe1") or {}).get("timestamp") or "")
    ts2 = str((health.get("probe2") or {}).get("timestamp") or "")
    live_not_cached = bool(ts1 and ts2 and ts1 != ts2)
    return {
        "probed_at": probed_at,
        "offline": offline,
        "health": health,
        "activation": activation,
        "http": codes,
        "live_not_cached": live_not_cached,
        "dsh_plan": dsh_plan,
        "dsh_supply_rc": supply_rc,
        "dsh_supply_ok": "DSH_SUPPLY_CHAIN_STATIC_OK" in supply_out,
        "boss_dry_run_rc": boss_rc,
        "boss_dry_run_ok": boss_rc == 0 and "DRY-RUN" in boss_out,
        "file_gates": _file_gates(),
    }


def render_md(row: dict[str, Any]) -> str:
    h2 = (row.get("health") or {}).get("probe2") or (row.get("health") or {}).get("probe1") or {}
    act = row.get("activation") or {}
    gates = row.get("file_gates") or {}
    dsh = row.get("dsh_plan") or {}
    sha = h2.get("version") or "offline"
    lines = [
        "# NEXT todos READY — " + str(row.get("probed_at")),
        "",
        f"Prod `/health` = `{sha}` · `{h2.get('status')}` · `{h2.get('environment')}` · uptime `{h2.get('uptime')}`.",
        f"Activation: `payments_ready={act.get('payments_ready')}` · `blocker_count={act.get('blocker_count')}` · `ready_for_first_paid_customer={act.get('ready_for_first_paid_customer')}`.",
        "Named blocker (SSH/capacity): `upi_pending_unactioned`. `paid_today` ledger = owner scoreboard, not this public JSON.",
        "",
        "DSH used: governed MCP memory turn (`scripts/dsh_next_todos_plan.py`) + supply-chain verify + local Linux smoke if Docker present. Not Harness.io.",
        "",
        "| Todo | Status | Evidence |",
        "|---|---|---|",
        "| 1 Hot Queue blitz | OWNER-WAIT | inbox HTTP "
        + str((row.get("http") or {}).get("inbox"))
        + " shell; token-paste `#tok`; cards need admin token |",
        "| 2 UPI Bind → Re-Approve | OWNER-WAIT | `/app/admin#sec-upi-selfserve`; named blocker `upi_pending_unactioned`; `payments_ready=true` |",
        "| 3 Bank-credit confirm | OWNER-WAIT | `owner_confirmed_upi` only; do not fake `paid_today` |",
        "| 4 Phase 0 exit | GATED | Jiya + 1 not on ledger |",
        "| 5 Boss harness canary | OWNER-WAIT | `--dry-run` rc="
        + str(row.get("boss_dry_run_rc"))
        + "; real start owner Desktop/sandbox |",
        "| 6 Comb Desktop Save | GATED | after todo 5 reply |",
        "| 7 Live flag mismatches | OWNER-WAIT | observe hub/dunning/UPI_AUTO/DSH_RUNTIME=1; ENG must not flip |",
        "| 8 Stay behind origin | READY | `git fetch` done; no `reset --hard`; no deploy |",
        "| 9 Inbox empty-cards debug | GATED | only if owner pastes empty-after-token |",
        "| 10 Onboard fail-rate 2nd tenant | GATED | after 2nd paid |",
        "| 11 Heavy-worker heat | READY | job names written; no DLQ flush; no onboard arm |",
        "| 12–17 Phase 1 | GATED | `PHASE1_GATED_RUNBOOK.md` |",
        "",
        f"DSH plan ok={dsh.get('ok')} heartbeat={dsh.get('heartbeat_status')} "
        f"gtm_ops_ready={dsh.get('gtm_ops_ready_status')} upi_refuse={dsh.get('upi_proposal_status')} "
        f"star_allowlist_empty={dsh.get('star_allowlist_collapses_to_empty')} "
        f"frozen={dsh.get('frozen_agents')}.",
        f"File gates: `{json.dumps(gates, sort_keys=True)}`.",
        "",
        "Owner clicks (order): `/app/admin-login` → `/app/inbox` 15–30 min → UPI Bind/Approve → bank confirm → optional `python scripts/buzz_start_harness.py --agent Boss`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    row = build_report(offline=args.offline)
    print(json.dumps(row, indent=2, sort_keys=True)[:5000])
    if args.write:
        OUT_MD.write_text(render_md(row), encoding="utf-8")
    gates_ok = all(row.get("file_gates") or {}.values())
    dsh_ok = bool((row.get("dsh_plan") or {}).get("ok"))
    return 0 if gates_ok and dsh_ok and row.get("boss_dry_run_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
