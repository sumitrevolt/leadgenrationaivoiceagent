"""Cursor Agent CLI executor — real non-interactive invocation."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from app.dev_control.external_agents.policy import redact
from app.dev_control.external_agents.runner.process_safe import (
    ProcessResult,
    ProcessSafetyError,
    run_allowlisted,
)
from app.dev_control.external_agents.schema import Mission

DEFAULT_CURSOR_CANDIDATES = (
    r"C:\Users\Ratanshila\AppData\Local\cursor-agent\agent.cmd",
    r"C:\Users\Ratanshila\AppData\Local\cursor-agent\agent.ps1",
)


def resolve_cursor_executable() -> str:
    forced = (os.getenv("EXTERNAL_AGENT_CURSOR_BIN") or "").strip()
    if forced:
        p = Path(forced)
        if not p.is_file():
            raise ProcessSafetyError("cursor_bin_missing")
        return str(p.resolve())
    which = shutil.which("agent") or shutil.which("agent.cmd")
    if which:
        return which
    for cand in DEFAULT_CURSOR_CANDIDATES:
        if Path(cand).is_file():
            return cand
    raise ProcessSafetyError("cursor_cli_unavailable")


def build_cursor_argv(*, workspace: str, print_mode: bool = True) -> list[str]:
    exe = resolve_cursor_executable()
    argv = [exe]
    if print_mode:
        argv += ["-p", "--print"]
    argv += [
        "--output-format",
        "json",
        "--workspace",
        workspace,
        "--trust",
    ]
    return argv


def build_executor_prompt(mission: Mission, packet: dict[str, Any]) -> str:
    allowed = "\n".join(f"- {p}" for p in mission.allowed_paths)
    return (
        "You are the Cursor executor for LeadGen External Agent Orchestrator.\n"
        "Implement ONLY the mission below. Stay inside allowed_paths.\n"
        "Do NOT touch voice, telephony, billing, .env, deploy workflows, or customer data.\n"
        "Do NOT commit or push unless the mission explicitly requires it (this dogfood does not).\n"
        "When finished, your FINAL message must be EXACTLY one JSON object matching:\n"
        "{\n"
        f'  "mission_id": "{mission.mission_id}",\n'
        '  "executor": "cursor",\n'
        '  "changed_files": ["repo-relative paths you changed"],\n'
        '  "commands": ["commands you ran"],\n'
        '  "tests": [{"command":"...", "exit_code":0, "summary":"..."}],\n'
        '  "summary": "...",\n'
        '  "evidence": {},\n'
        '  "scope_breach": false\n'
        "}\n\n"
        f"MISSION_ID={mission.mission_id}\n"
        f"TITLE={mission.title}\n"
        f"DESCRIPTION={mission.description}\n"
        f"BRANCH={mission.branch}\n"
        f"BASE_SHA={mission.base_sha}\n"
        f"ALLOWED_PATHS:\n{allowed}\n"
        f"ACCEPTANCE={json.dumps(mission.acceptance_criteria)}\n"
        f"PACKET={json.dumps(redact(packet), ensure_ascii=False)[:4000]}\n"
    )


def extract_result_manifest(stdout: str, mission_id: str) -> dict[str, Any]:
    """Parse Cursor agent JSON envelope into a result manifest."""
    text = stdout.strip()
    data: Any
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Find last JSON object in text
        start = text.rfind("{")
        if start < 0:
            raise ProcessSafetyError("cursor_output_not_json")
        depth = 0
        end = -1
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            raise ProcessSafetyError("cursor_output_not_json")
        data = json.loads(text[start:end])

    # Cursor agent may wrap in {result: "..."} or {result: {...}}
    if isinstance(data, dict) and "result" in data and "mission_id" not in data:
        inner = data["result"]
        if isinstance(inner, str):
            try:
                data = json.loads(inner)
            except json.JSONDecodeError:
                # search inside string
                s = inner.find("{")
                e = inner.rfind("}")
                if s >= 0 and e > s:
                    data = json.loads(inner[s : e + 1])
                else:
                    raise ProcessSafetyError("cursor_result_not_json")
        elif isinstance(inner, dict):
            data = inner
    if not isinstance(data, dict):
        raise ProcessSafetyError("cursor_manifest_invalid")
    if str(data.get("mission_id") or "") != mission_id:
        raise ProcessSafetyError("cursor_mission_id_mismatch")
    if str(data.get("executor") or "").lower() != "cursor":
        raise ProcessSafetyError("cursor_executor_mismatch")
    return data


def invoke_cursor(
    mission: Mission,
    packet: dict[str, Any],
    *,
    allowed_root: str,
    timeout_s: int = 900,
    heartbeat=None,
) -> tuple[ProcessResult, dict[str, Any] | None]:
    workspace = Path(mission.worktree).resolve()
    prompt_path = workspace / ".external_agent_runner_prompt.txt"
    prompt_path.write_text(build_executor_prompt(mission, packet), encoding="utf-8")
    # Short argv — agent reads the prompt file (avoids Windows command-line limits).
    short = (
        f"Read the file .external_agent_runner_prompt.txt in this workspace and execute "
        f"that mission exactly. Stay inside allowed_paths. When done, respond with ONLY "
        f"the required JSON result manifest (mission_id={mission.mission_id})."
    )
    argv = build_cursor_argv(workspace=str(workspace)) + [short]
    result = run_allowlisted(
        argv,
        cwd=str(workspace),
        allowed_root=allowed_root,
        timeout_s=timeout_s,
        heartbeat=heartbeat,
    )
    try:
        prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
    except TypeError:
        if prompt_path.exists():
            prompt_path.unlink()
    except Exception:
        pass
    manifest = None
    if result.exit_code == 0 and not result.timed_out and not result.cancelled:
        try:
            manifest = extract_result_manifest(result.stdout, mission.mission_id)
        except ProcessSafetyError:
            manifest = None
    return result, manifest
