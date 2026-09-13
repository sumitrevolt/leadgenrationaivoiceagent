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

PRESERVED FROM `origin/master` (2026-09-07) — the honest parts only:
`run_single_agent()` (peer-healing executor) and the roster's `helper`/`task`
fields are kept so that
`tests/test_workforce_omniroute_auth.py::test_failed_primary_and_helper_never_claim_recovery`
(which asserts a failed primary+helper can never report recovery) keeps guarding
this file. `run_single_agent` is NOT wired to any writer: it touches only the
in-memory `agent_status_cache` / `recent_healing_events` and `log_event`.
Do not re-enable `run_continuous_batch()` without satisfying the three
conditions above — see `docs/context/SESSION_HANDOFF.md` P0 entry.
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

# 31 Agents Roster with primary combo and designated peer helper
AGENT_CONFIGS = [
    # Executive & Strategy
    {
        "key": "manager",
        "name": "Boss",
        "emoji": "🧑‍💼",
        "team": "Executive",
        "combo": "leadsgen combo 1",
        "helper": "pranav",
        "task": "Lead workforce standup and route pending operations in 12 words.",
    },
    {
        "key": "hermes",
        "name": "Hermes",
        "emoji": "🛰️",
        "team": "Platform",
        "combo": "leadsgen combo 1",
        "helper": "pranav",
        "task": "Check full stack infra readiness score in 10 words.",
    },
    # Sales & Voice Telephony
    {
        "key": "swara",
        "name": "Swara",
        "emoji": "📞",
        "team": "Voice",
        "combo": "leadsgen combo 6",
        "helper": "boss",
        "task": "Verify Hindi telecalling opening hook in 10 words.",
    },
    {
        "key": "ananya",
        "name": "Ananya",
        "emoji": "📅",
        "team": "Voice",
        "combo": "leadsgen combo 6",
        "helper": "swara",
        "task": "Propose Mumbai salon demo appointment slot in 10 words.",
    },
    {
        "key": "riya",
        "name": "Riya",
        "emoji": "🛎️",
        "team": "Voice",
        "combo": "leadsgen combo 6",
        "helper": "swara",
        "task": "Standard inbound reception greeting for clinic in 10 words.",
    },
    {
        "key": "raksha",
        "name": "Raksha",
        "emoji": "🆘",
        "team": "Voice",
        "combo": "leadsgen combo 6",
        "helper": "boss",
        "task": "Human escalation criteria check in 10 words.",
    },
    {
        "key": "tara",
        "name": "Tara",
        "emoji": "🎙️",
        "team": "Voice",
        "combo": "leadsgen combo 6",
        "helper": "pranav",
        "task": "Verify Vobiz India SIP trunk latency in 10 words.",
    },
    {
        "key": "arjun",
        "name": "Arjun",
        "emoji": "🧪",
        "team": "Voice",
        "combo": "leadsgen combo 7",
        "helper": "meera",
        "task": "Run voice conversation loop QA check in 10 words.",
    },
    {
        "key": "meera",
        "name": "Meera",
        "emoji": "🎓",
        "team": "Voice",
        "combo": "leadsgen combo 7",
        "helper": "arjun",
        "task": "Tuning suggestion for call silence threshold in 10 words.",
    },
    {
        "key": "lekha",
        "name": "Lekha",
        "emoji": "📊",
        "team": "Voice",
        "combo": "leadsgen combo 7",
        "helper": "boss",
        "task": "Compute call booking conversion target in 10 words.",
    },
    # Marketing & Growth
    {
        "key": "rohan",
        "name": "Rohan",
        "emoji": "🎯",
        "team": "Marketing",
        "combo": "leadsgen combo 8",
        "helper": "neha",
        "task": "Target high-ticket niche for Mumbai leadgen in 10 words.",
    },
    {
        "key": "neha",
        "name": "Neha",
        "emoji": "♻️",
        "team": "Marketing",
        "combo": "leadsgen combo 8",
        "helper": "rohan",
        "task": "Hot lead scoring threshold evaluation in 10 words.",
    },
    {
        "key": "ravi",
        "name": "Ravi",
        "emoji": "🌐",
        "team": "Marketing",
        "combo": "leadsgen combo 10",
        "helper": "isha",
        "task": "Primary programmatic SEO keyword for salon Mumbai in 10 words.",
    },
    {
        "key": "isha",
        "name": "Isha",
        "emoji": "📣",
        "team": "Marketing",
        "combo": "leadsgen combo 9",
        "helper": "ravi",
        "task": "Engaging Instagram headline for local business in 10 words.",
    },
    {
        "key": "zara",
        "name": "Zara",
        "emoji": "📱",
        "team": "Marketing",
        "combo": "leadsgen combo 9",
        "helper": "isha",
        "task": "Social broadcast queue dispatch status in 10 words.",
    },
    {
        "key": "anika",
        "name": "Anika",
        "emoji": "🔁",
        "team": "Marketing",
        "combo": "leadsgen combo 8",
        "helper": "ira",
        "task": "Cadence follow-up timing for inquiry in 10 words.",
    },
    {
        "key": "ira",
        "name": "Ira",
        "emoji": "🧩",
        "team": "Marketing",
        "combo": "leadsgen combo 8",
        "helper": "anika",
        "task": "Journey automation trigger on lead qualification in 10 words.",
    },
    {
        "key": "kiran",
        "name": "Kiran",
        "emoji": "📊",
        "team": "Marketing",
        "combo": "leadsgen combo 8",
        "helper": "rohan",
        "task": "Campaign A/B test variation hypothesis in 10 words.",
    },
    {
        "key": "priya",
        "name": "Priya",
        "emoji": "🔗",
        "team": "Marketing",
        "combo": "leadsgen combo 2",
        "helper": "dev",
        "task": "CRM sync status check for Zoho and HubSpot in 10 words.",
    },
    {
        "key": "dev",
        "name": "Dev",
        "emoji": "📚",
        "team": "Marketing",
        "combo": "leadsgen combo 2",
        "helper": "priya",
        "task": "RAG knowledge base grounding check in 10 words.",
    },
    # Technical & Engineering
    {
        "key": "pranav",
        "name": "Pranav",
        "emoji": "🔧",
        "team": "Engineering",
        "combo": "leadsgen combo 4",
        "helper": "vikram",
        "task": "SRE disaster recovery and backup pass check in 10 words.",
    },
    {
        "key": "vikram",
        "name": "Vikram",
        "emoji": "🛠️",
        "team": "Engineering",
        "combo": "leadsgen combo 11",
        "helper": "pranav",
        "task": "Audit code upgrade signals and safety gates in 10 words.",
    },
    {
        "key": "arya",
        "name": "Arya",
        "emoji": "🔌",
        "team": "Engineering",
        "combo": "leadsgen combo 3",
        "helper": "vikram",
        "task": "FastAPI MCP tool surface pulse verify in 10 words.",
    },
    {
        "key": "kabir",
        "name": "Kabir",
        "emoji": "🗄️",
        "team": "Engineering",
        "combo": "leadsgen combo 4",
        "helper": "pranav",
        "task": "Postgres connection pool and query health in 10 words.",
    },
    {
        "key": "diya",
        "name": "Diya",
        "emoji": "🧹",
        "team": "Engineering",
        "combo": "leadsgen combo 5",
        "helper": "kabir",
        "task": "Data integrity deduplication sweep check in 10 words.",
    },
    {
        "key": "aryan",
        "name": "Aryan",
        "emoji": "📦",
        "team": "Engineering",
        "combo": "leadsgen combo 5",
        "helper": "vikram",
        "task": "Dependency CVE and lockfile hygiene review in 10 words.",
    },
    {
        "key": "kavya",
        "name": "Kavya",
        "emoji": "🛡️",
        "team": "Engineering",
        "combo": "leadsgen combo 4",
        "helper": "pranav",
        "task": "Hostinger VPS memory and container pulse in 10 words.",
    },
    {
        "key": "arnav",
        "name": "Arnav",
        "emoji": "🛡️",
        "team": "Compliance",
        "combo": "leadsgen combo 12",
        "helper": "vikram",
        "task": "Confirm TRAI DND fail-closed posture in 10 words.",
    },
    {
        "key": "guru",
        "name": "Guru",
        "emoji": "📚",
        "team": "Platform",
        "combo": "leadsgen combo 12",
        "helper": "dev",
        "task": "Review active agent skills and context memory in 10 words.",
    },
    {
        "key": "nikhil",
        "name": "Nikhil",
        "emoji": "💰",
        "team": "Platform",
        "combo": "leadsgen combo 13",
        "helper": "vidya",
        "task": "Revenue operations dunning recovery status in 10 words.",
    },
    {
        "key": "vidya",
        "name": "Vidya",
        "emoji": "💹",
        "team": "Platform",
        "combo": "leadsgen combo 14",
        "helper": "nikhil",
        "task": "FinOps free-tier LLM token margin check in 10 words.",
    },
]

# In-memory peer-healing event log
recent_healing_events: collections.deque = collections.deque(maxlen=50)
agent_status_cache: dict[str, dict] = {}


_COMBO_KEY_CACHE: dict[str, str] = {}


def _resolve_combo_key(combo_name: str) -> str:
    """Resolve OmniRoute API key for a combo — env-only, never from gateway storage."""
    if combo_name in _COMBO_KEY_CACHE:
        return _COMBO_KEY_CACHE[combo_name]
    env_key = os.getenv(
        f"OMNIROUTE_KEY_{combo_name.replace(' ', '_').replace('-', '_').upper()}", ""
    )
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
                raw_content = msg.get("content") or msg.get("text") or ""
                content = raw_content.strip()
                if not content:
                    return False, "Empty completion returned"
                return True, content
        except Exception as e:
            msg = str(e)
            is_busy = (
                "503" in msg
                or "chat_admission_busy" in msg
                or "429" in msg
                or "busy" in msg.lower()
            )
            if attempt == 1 and is_busy:
                import time

                time.sleep(2)
                continue
            return False, msg
    return False, "unreachable"


def log_file_path() -> Path:
    """Log target for the (now manual-only) peer-healing executor."""
    from app.platform import runtime_data

    return runtime_data.store_path("workforce_orchestrator.log")


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    p = log_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_single_agent(agent_cfg: dict, cycle_num: int) -> dict:
    """Execute one agent workflow with Peer-Healing recovery if primary combo fails."""
    key = agent_cfg["key"]
    name = agent_cfg["name"]
    combo = agent_cfg["combo"]
    helper_key = agent_cfg["helper"]
    task_prompt = agent_cfg["task"]

    # Step 1: Attempt primary combo with 25s budget
    success, result = execute_omniroute_query(combo, task_prompt, timeout_s=25)

    healing_event = None

    # Step 2: Peer-Healing Intervention if primary fails
    if not success:
        helper_cfg = next((a for a in AGENT_CONFIGS if a["key"] == helper_key), AGENT_CONFIGS[0])
        rescue_combo = "leadsgen combo 13" if combo != "leadsgen combo 13" else "leadsgen combo 1"

        log(
            f"⚠️ [STALL DETECTED] {name} ({key}) failed on {combo} ({result[:40]}). Dispatching peer helper {helper_cfg['name']}!"
        )

        # Helper executes recovery via fallback combo
        helper_success, helper_result = execute_omniroute_query(
            rescue_combo, task_prompt, timeout_s=25
        )

        if helper_success:
            result = f"[RESCUED by {helper_cfg['name']} via {rescue_combo}] {helper_result}"
            status_label = "RESCUED_ACTIVE"
        else:
            result = "Primary and fallback inference failed; task execution unverified."
            status_label = "BLOCKED"

        healing_event = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "stalled_agent": name,
            "stalled_key": key,
            "failed_combo": combo,
            "helper_agent": helper_cfg["name"],
            "rescue_combo": rescue_combo,
            "reason": str(result)[:80],
            "status": "RECOVERED" if helper_success else "FAILED",
        }
        recent_healing_events.append(healing_event)
        log(
            f"[FALLBACK {'SUCCEEDED' if helper_success else 'FAILED'}] {name}: inference only; no task completion proof."
        )
    else:
        status_label = "ACTIVE"

    # Step 3: Record to platform DB agent_events
    try:
        from app.platform.team import log_event

        log_event(
            key,
            f"cycle_{cycle_num}",
            result[:140],
            "failed" if status_label == "BLOCKED" else "success",
            {
                "cycle": cycle_num,
                "combo": combo,
                "healed": healing_event is not None and healing_event["status"] == "RECOVERED",
                "evidence_kind": "inference_probe",
                "task_execution_verified": False,
            },
        )
    except Exception:
        pass

    agent_info = {
        "key": key,
        "name": name,
        "emoji": agent_cfg["emoji"],
        "team": agent_cfg["team"],
        "combo": combo,
        "status": status_label,
        "last_action": result[:90],
        "cycle": cycle_num,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    agent_status_cache[key] = agent_info
    return agent_info


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
    print("  Wrote: data/workforce_live_status.json (status=NOT_INSTRUMENTED)")
    print()


if __name__ == "__main__":
    main()
