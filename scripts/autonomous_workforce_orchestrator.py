#!/usr/bin/env python3
"""autonomous_workforce_orchestrator.py — DEPRECATED / INERT.

This script was generating FAKE telemetry — reporting 31 agents as
"LOCAL_ACTIVE" and inflating `actions_today` by +31 every 15 seconds
regardless of whether any real work happened. That data was piped into
`data/workforce_live_status.json` and rendered on the Owner Command
Center as if it were real worker activity. It was not.

STATUS (2026-09-11): INERT. The `main()` loop is disabled. Helper
functions are retained so existing security/contract tests continue to
pass, but they are NOT wired into any telemetry generation.

DO NOT RESTART THE MAIN LOOP without:
  1. Removing the `actions_today += cycle_num * 31` inflation.
  2. Reporting only REAL, OBSERVED agent activity (not synthetic probes).
  3. Separating "probe-only inference" from "verified execution" in the
     status schema (see `app/utils/owner_feed.py:FORCE_UNVERIFIED_SOURCES`).

Real 24×7 orchestration belongs in the Celery worker / scheduler plane
(`app/platform/team_scheduler.py`, `app/worker.py`), not in a standalone
Python script with a `while True` loop.
"""

from __future__ import annotations

import collections
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Make the project package importable when run as a standalone script so the
# canonical runtime-data resolver (and its provenance) is used instead of a
# hand-built REPO_ROOT/data literal.
sys.path.insert(0, str(REPO_ROOT))

OMNI_URL = "http://127.0.0.1:20128/v1/chat/completions"

# 31 Agents Roster — kept for reference only.
AGENT_CONFIGS = [
    {"key": "manager", "name": "Boss", "emoji": "🧑‍💼", "team": "Executive", "combo": "leadsgen combo 1"},
    {"key": "hermes", "name": "Hermes", "emoji": "🛰️", "team": "Platform", "combo": "leadsgen combo 1"},
    {"key": "swara", "name": "Swara", "emoji": "📞", "team": "Voice", "combo": "leadsgen combo 6"},
    {"key": "ananya", "name": "Ananya", "emoji": "📅", "team": "Voice", "combo": "leadsgen combo 6"},
    {"key": "riya", "name": "Riya", "emoji": "🛎️", "team": "Voice", "combo": "leadsgen combo 6"},
    {"key": "raksha", "name": "Raksha", "emoji": "🆘", "team": "Voice", "combo": "leadsgen combo 6"},
    {"key": "tara", "name": "Tara", "emoji": "🎙️", "team": "Voice", "combo": "leadsgen combo 6"},
    {"key": "arjun", "name": "Arjun", "emoji": "🧪", "team": "Voice", "combo": "leadsgen combo 7"},
    {"key": "meera", "name": "Meera", "emoji": "🎓", "team": "Voice", "combo": "leadsgen combo 7"},
    {"key": "lekha", "name": "Lekha", "emoji": "📊", "team": "Voice", "combo": "leadsgen combo 7"},
    {"key": "rohan", "name": "Rohan", "emoji": "🎯", "team": "Marketing", "combo": "leadsgen combo 8"},
    {"key": "neha", "name": "Neha", "emoji": "♻️", "team": "Marketing", "combo": "leadsgen combo 8"},
    {"key": "ravi", "name": "Ravi", "emoji": "🌐", "team": "Marketing", "combo": "leadsgen combo 10"},
    {"key": "isha", "name": "Isha", "emoji": "📣", "team": "Marketing", "combo": "leadsgen combo 9"},
    {"key": "zara", "name": "Zara", "emoji": "📱", "team": "Marketing", "combo": "leadsgen combo 9"},
    {"key": "anika", "name": "Anika", "emoji": "🔁", "team": "Marketing", "combo": "leadsgen combo 8"},
    {"key": "ira", "name": "Ira", "emoji": "🧩", "team": "Marketing", "combo": "leadsgen combo 8"},
    {"key": "kiran", "name": "Kiran", "emoji": "📊", "team": "Marketing", "combo": "leadsgen combo 8"},
    {"key": "priya", "name": "Priya", "emoji": "🔗", "team": "Marketing", "combo": "leadsgen combo 2"},
    {"key": "dev", "name": "Dev", "emoji": "📚", "team": "Marketing", "combo": "leadsgen combo 2"},
    {"key": "pranav", "name": "Pranav", "emoji": "🔧", "team": "Engineering", "combo": "leadsgen combo 4"},
    {"key": "vikram", "name": "Vikram", "emoji": "🛠️", "team": "Engineering", "combo": "leadsgen combo 11"},
    {"key": "arya", "name": "Arya", "emoji": "🔌", "team": "Engineering", "combo": "leadsgen combo 3"},
    {"key": "kabir", "name": "Kabir", "emoji": "🗄️", "team": "Engineering", "combo": "leadsgen combo 4"},
    {"key": "diya", "name": "Diya", "emoji": "🧹", "team": "Engineering", "combo": "leadsgen combo 5"},
    {"key": "aryan", "name": "Aryan", "emoji": "📦", "team": "Engineering", "combo": "leadsgen combo 5"},
    {"key": "kavya", "name": "Kavya", "emoji": "🛡️", "team": "Engineering", "combo": "leadsgen combo 4"},
    {"key": "arnav", "name": "Arnav", "emoji": "🛡️", "team": "Compliance", "combo": "leadsgen combo 12"},
    {"key": "guru", "name": "Guru", "emoji": "📚", "team": "Platform", "combo": "leadsgen combo 12"},
    {"key": "nikhil", "name": "Nikhil", "emoji": "💰", "team": "Platform", "combo": "leadsgen combo 13"},
    {"key": "vidya", "name": "Vidya", "emoji": "💹", "team": "Platform", "combo": "leadsgen combo 14"},
]

_COMBO_KEY_CACHE: dict[str, str] = {}


def _resolve_combo_key(combo_name: str) -> str:
    """Resolve OmniRoute API key for a combo — env-only, never from gateway storage."""
    if combo_name in _COMBO_KEY_CACHE:
        return _COMBO_KEY_CACHE[combo_name]
    env_key = os.getenv(f"OMNIROUTE_KEY_{combo_name.replace(' ', '_').replace('-', '_').upper()}", "")
    if env_key and env_key.strip():
        _COMBO_KEY_CACHE[combo_name] = env_key.strip()
        return _COMBO_KEY_CACHE[combo_name]
    fallback = (os.getenv("OMNIROUTE_API_KEY", "") or "").strip()
    _COMBO_KEY_CACHE[combo_name] = fallback
    return fallback


def execute_omniroute_query(combo_name: str, prompt: str, timeout_s: int = 15) -> tuple[bool, str]:
    """Execute query against designated combo. Return (success_bool, content_or_error)."""
    api_key = _resolve_combo_key(combo_name)
    body = {
        "model": combo_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 40,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        OMNI_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if not choices:
                    return False, "Empty choices returned"
                msg = choices[0].get("message", {})
                raw_content = msg.get("content") or msg.get("reasoning") or msg.get("text") or ""
                content = raw_content.strip()
                if not content:
                    content = "Status verified: operational"
                return True, content
        except Exception as e:
            msg = str(e)
            is_busy = "503" in msg or "chat_admission_busy" in msg or "429" in msg or "busy" in msg.lower()
            if attempt == 1 and is_busy:
                import time
                time.sleep(2)
                continue
            return False, msg
    return False, "unreachable"


def run_continuous_batch(cycle_num: int, workers_count: int = 4):
    """DEPRECATED: This function used to run fake telemetry generation. Now inert."""
    pass


def write_inert_status():
    """Overwrite the status file with an honest 'not instrumented' payload."""
    status = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cycle": 0,
        "status": "NOT_INSTRUMENTED",
        "active_workers": 0,
        "actions_today": 0,
        "working_members": 0,
        "active_members": 0,
        "peer_rescues_count": 0,
        "evidence_kind": "inference_probe_only",
        "task_execution_verified": False,
        "note": (
            "This file was previously populated by autonomous_workforce_orchestrator.py "
            "which generated FAKE telemetry (inflated actions_today, synthetic agent status). "
            "It is now inert. Real worker activity is tracked via Celery/app.platform.team.log_event."
        ),
        "agents": [],
        "recent_rescues": [],
    }
    from app.platform import runtime_data

    out_path = runtime_data.store_path("workforce_live_status.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def main():
    """Entry point — INERT. Does NOT run the fake telemetry loop."""
    print("=" * 60)
    print("  autonomous_workforce_orchestrator.py — INERT")
    print("  This script no longer generates fake telemetry.")
    print("  Writing honest 'not instrumented' status and exiting.")
    print("=" * 60)
    write_inert_status()
    print(f"  Wrote: data/workforce_live_status.json (status=NOT_INSTRUMENTED)")
    print()


if __name__ == "__main__":
    main()
