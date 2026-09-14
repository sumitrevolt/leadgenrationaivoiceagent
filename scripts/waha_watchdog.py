#!/usr/bin/env python3
"""WAHA session watchdog — polls the WAHA session, auto-restarts FAILED/STOPPED.

WHY THIS FILE IS NOW TRACKED (2026-09-14)
-----------------------------------------
It ran on the VPS as a bare ``python3 waha_watchdog.py`` process and existed ONLY
there, so nothing in CI could see it. The production copy polled
``http://localhost:3111`` while the WAHA container publishes host port **3002**, and
therefore wrote ``{"waha_status": "UNKNOWN", "raw": {"error": "Connection refused"}}``
to ``data/wa_health_check.json`` for weeks — a pure false negative that looked
identical to "the session status is unreadable". Both halves are fixed here:

* every host/path/port is configurable (env var first, then the VPS default);
* ``SCAN_QR_CODE`` / ``UNPAIRED`` (reachable, but nobody is logged in) is reported as
  its own ``logged_out`` state — never as "unreachable" (see ``classify()``).

Launch + supervision: ``scripts/WAHA_WATCHDOG.md``.

Config (env var -> default):
    WAHA_WATCHDOG_URL          WAHA base URL                  http://127.0.0.1:3002
    WAHA_WATCHDOG_SESSION      WAHA session name              default
    WAHA_WATCHDOG_ENV_FILE     .env holding the API key       /opt/leadgen/.env
    WAHA_WATCHDOG_HEALTH_FILE  health JSON written each poll  /opt/leadgen/data/wa_health_check.json
    WAHA_WATCHDOG_LOG_FILE     append-only log                /opt/leadgen/data/waha_watchdog.log
    WAHA_WATCHDOG_INTERVAL     seconds between polls          60
    WAHA_WATCHDOG_TIMEOUT      per-request timeout seconds    10

The WAHA API key is READ, never carried: ``WAHA_API_KEY`` from the environment, else
from the ``.env`` file above. No hardcoded fallback — the VPS copy had one and it was
removed there; it must not come back.
"""

import asyncio
import datetime
import json
import os
import urllib.error
import urllib.request

DEFAULT_WAHA_URL = "http://127.0.0.1:3002"
DEFAULT_SESSION = "default"
DEFAULT_ENV_FILE = "/opt/leadgen/.env"
DEFAULT_HEALTH_FILE = "/opt/leadgen/data/wa_health_check.json"
DEFAULT_LOG_FILE = "/opt/leadgen/data/waha_watchdog.log"

# WAHA session statuses that mean "the account needs a QR scan", NOT "the service is
# down". SCAN_QR_CODE = linked session logged out; UNPAIRED = never paired.
LOGGED_OUT_STATUSES = ("SCAN_QR_CODE", "UNPAIRED", "NOT_CREATED")
# Statuses the watchdog acts on by itself.
RESTART_STATUSES = ("FAILED", "STOPPED")


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or "").strip() or default


def waha_url() -> str:
    return _env("WAHA_WATCHDOG_URL", DEFAULT_WAHA_URL).rstrip("/")


def session_name() -> str:
    return _env("WAHA_WATCHDOG_SESSION", DEFAULT_SESSION)


def env_file() -> str:
    return _env("WAHA_WATCHDOG_ENV_FILE", DEFAULT_ENV_FILE)


def health_file() -> str:
    return _env("WAHA_WATCHDOG_HEALTH_FILE", DEFAULT_HEALTH_FILE)


def log_file() -> str:
    return _env("WAHA_WATCHDOG_LOG_FILE", DEFAULT_LOG_FILE)


def interval_s() -> int:
    try:
        return max(5, int(_env("WAHA_WATCHDOG_INTERVAL", "60")))
    except Exception:
        return 60


def timeout_s() -> float:
    try:
        return max(1.0, float(_env("WAHA_WATCHDOG_TIMEOUT", "10")))
    except Exception:
        return 10.0


def _env_from_file(name: str, path: str = "") -> str:
    """Read a key from the project .env (this watchdog runs on the HOST, so the
    container-only env vars are absent and ``os.getenv`` alone returns nothing)."""
    try:
        with open(path or env_file(), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export ") :].lstrip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def api_key() -> str:
    """Env first, then the .env file. NEVER a hardcoded fallback."""
    return os.getenv("WAHA_API_KEY") or _env_from_file("WAHA_API_KEY")


def ist_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)


def log(msg: str) -> None:
    ts = ist_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[WAHA_WATCHDOG {ts}] {msg}"
    print(line)
    try:
        with open(log_file(), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def poll_session() -> dict:
    """One WAHA session probe. Never raises — an unreachable service is DATA.

    Returns ``{"reachable", "session_status", "http_status", "error", "data"}``.
    ``reachable`` is about the SERVICE; the session status is a separate field so the
    two can never be conflated again.
    """
    url = f"{waha_url()}/api/sessions/{session_name()}"
    req = urllib.request.Request(url, headers={"X-Api-Key": api_key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s()) as r:
            data = json.loads(r.read() or b"{}")
            status = str((data or {}).get("status") or "").upper() or None
            return {
                "reachable": True,
                "session_status": status,
                "http_status": int(getattr(r, "status", 200) or 200),
                "error": None,
                "data": data if isinstance(data, dict) else {},
            }
    except urllib.error.HTTPError as e:
        # The service ANSWERED — only this request failed (usually a wrong API key).
        return {
            "reachable": False,
            "session_status": None,
            "http_status": int(getattr(e, "code", 0) or -1),
            "error": f"HTTP {getattr(e, 'code', '?')}",
            "data": {"error": str(e)},
        }
    except Exception as e:
        return {
            "reachable": False,
            "session_status": None,
            "http_status": None,
            "error": str(e),
            "data": {"error": str(e)},
        }


def classify(probe: dict) -> tuple:
    """(state, actionable) for one probe. The whole point of this file.

    * ``unreachable`` — the WAHA service did not answer (wrong port, dead container).
    * ``logged_out``  — WAHA answered, the SESSION is not linked (owner scans the QR).
    * ``failed``/``stopped`` — WAHA answered, the session needs a restart (we do it).

    Before this, the first two both surfaced as ``waha_status: "UNKNOWN"``.
    """
    if not probe.get("reachable"):
        # An HTTP status means the service ANSWERED and only this request failed.
        if probe.get("http_status"):
            return "auth_error", "check_waha_api_key"
        return "unreachable", "check_waha_service"
    status = str(probe.get("session_status") or "")
    if status in RESTART_STATUSES:
        return ("failed" if status == "FAILED" else "stopped"), "watchdog_restart"
    if status in LOGGED_OUT_STATUSES:
        return "logged_out", "owner_scan_qr"
    if status == "WORKING":
        return "working", None
    return "unknown", "inspect_session"


def restart_session() -> bool:
    url = f"{waha_url()}/api/sessions/{session_name()}/restart"
    req = urllib.request.Request(url, method="POST", headers={"X-Api-Key": api_key()})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s()) as r:
            return int(getattr(r, "status", 200) or 200) == 200
    except Exception as e:
        log(f"restart FAILED: {e}")
        return False


def build_record(probe: dict, state: str, actionable) -> dict:
    ts = ist_now().strftime("%Y-%m-%dT%H:%M:%S+05:30")
    status = probe.get("session_status")
    return {
        "timestamp_ist": ts,
        "waha_url": waha_url(),
        "state": state,
        "actionable": actionable,
        "reachable": bool(probe.get("reachable")),
        "session_status": status,
        # Legacy key: the WAHA status when there is one, else the state in caps — so a
        # reader can never mistake "unreachable" for "the session said UNKNOWN".
        "waha_status": status or state.upper(),
        "raw": probe.get("data") if probe.get("reachable") else {"error": probe.get("error")},
    }


def write_health(record: dict) -> None:
    try:
        with open(health_file(), "w") as f:
            json.dump(record, f, indent=2)
    except Exception:
        pass


def check_once(probe_fn=None, restart_fn=None, write: bool = True) -> dict:
    """One poll cycle: probe -> classify -> act -> record. Returns the health record."""
    probe = (probe_fn or poll_session)()
    state, actionable = classify(probe)
    record = build_record(probe, state, actionable)

    if state in ("failed", "stopped"):
        log(f"session={probe.get('session_status')} — RESTARTING")
        ok = (restart_fn or restart_session)()
        record["restart_ok"] = ok
        if not ok:
            record["actionable"] = "restart_failed"
        log(f"restart {'OK' if ok else 'FAIL'}")
    elif state == "logged_out":
        log(
            f"session={probe.get('session_status')} — LOGGED OUT (reachable): owner QR scan required"
        )
    elif state == "unreachable":
        log(f"WAHA UNREACHABLE at {waha_url()} — {probe.get('error')}")
    elif state == "auth_error":
        log(f"WAHA answered {probe.get('error')} — check WAHA_API_KEY")
    elif state == "working":
        log("session=WORKING — healthy")
    else:
        log(f"session={probe.get('session_status')} state={state}")

    if write:
        write_health(record)
    return record


async def main():
    log(f"START watchdog polling every {interval_s()}s url={waha_url()} session={session_name()}")
    while True:
        check_once()
        await asyncio.sleep(interval_s())


if __name__ == "__main__":
    asyncio.run(main())
