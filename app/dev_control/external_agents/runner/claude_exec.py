"""Claude Code CLI reviewer — real non-interactive invocation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.dev_control.external_agents.policy import redact
from app.dev_control.external_agents.runner.process_safe import (
    ProcessResult,
    ProcessSafetyError,
    run_allowlisted,
)
from app.dev_control.external_agents.schema import Mission


def resolve_claude_executable() -> str:
    exe = shutil.which("claude") or shutil.which("claude.exe")
    if not exe:
        raise ProcessSafetyError("claude_cli_unavailable")
    return exe


def auth_ok() -> dict[str, Any]:
    """Preflight Claude auth without exposing tokens."""
    exe = resolve_claude_executable()
    try:
        st = subprocess.run(
            [exe, "auth", "status"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )
        probe = subprocess.run(
            [exe, "-p", "Return only: AUTH_OK"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"auth_probe_failed:{type(exc).__name__}"}
    logged_in = "loggedIn" in (st.stdout or "") and "true" in (st.stdout or "").lower()
    auth_line = (probe.stdout or "").strip().splitlines()[-1:] or [""]
    ok = probe.returncode == 0 and auth_line[-1].strip() == "AUTH_OK"
    return {
        "ok": ok and (logged_in or ok),
        "version_probe_exit": probe.returncode,
        "auth_status_exit": st.returncode,
        # Never return raw stdout (may include email); only booleans.
        "auth_ok": ok,
    }


def build_claude_argv(prompt: str, *, add_dir: str) -> list[str]:
    """Fixed template: prompt MUST follow ``-p`` before variadic ``--add-dir``."""
    exe = resolve_claude_executable()
    return [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        "plan",
        "--disallowedTools",
        "Write,Edit,NotebookEdit",
        "--add-dir",
        add_dir,
    ]


def build_review_prompt(
    mission: Mission,
    *,
    result_manifest: dict[str, Any],
    diff_text: str,
) -> str:
    return (
        "You are an INDEPENDENT Claude reviewer for LeadGen External Agent missions.\n"
        "Read-only. Do not edit files. Do not deploy. Do not call or bill.\n"
        "Return EXACTLY one JSON object:\n"
        "{\n"
        f'  "mission_id": "{mission.mission_id}",\n'
        '  "reviewer": "claude",\n'
        '  "verdict": "PASS|CHANGES_REQUIRED|BLOCKED",\n'
        '  "findings": ["cite file:line or test"],\n'
        '  "citations": ["file:line or test name"]\n'
        "}\n\n"
        f"MISSION_ID={mission.mission_id}\n"
        f"TITLE={mission.title}\n"
        f"EXECUTOR={mission.executor}\n"
        f"ALLOWED={json.dumps(mission.allowed_paths)}\n"
        f"RESULT_MANIFEST={json.dumps(redact(result_manifest), ensure_ascii=False)[:6000]}\n"
        f"<DIFF>\n{diff_text[:12000]}\n</DIFF>\n"
    )


def extract_review_manifest(stdout: str, mission_id: str) -> dict[str, Any]:
    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProcessSafetyError("claude_output_not_json") from exc
    text = outer.get("result") if isinstance(outer, dict) else stdout
    if isinstance(text, dict):
        data = text
    else:
        s = str(text)
        start = s.find("{")
        if start < 0:
            raise ProcessSafetyError("claude_review_not_json")
        depth = 0
        end = -1
        for i, ch in enumerate(s[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            raise ProcessSafetyError("claude_review_not_json")
        data = json.loads(s[start:end])
    if str(data.get("mission_id") or "") != mission_id:
        raise ProcessSafetyError("claude_mission_id_mismatch")
    if str(data.get("reviewer") or "").lower() != "claude":
        raise ProcessSafetyError("claude_reviewer_mismatch")
    verdict = str(data.get("verdict") or "").upper()
    if verdict not in {"PASS", "CHANGES_REQUIRED", "BLOCKED"}:
        raise ProcessSafetyError("claude_verdict_invalid")
    data["verdict"] = verdict
    return data


def invoke_claude_review(
    mission: Mission,
    *,
    result_manifest: dict[str, Any],
    diff_text: str,
    allowed_root: str,
    timeout_s: int = 600,
    heartbeat=None,
) -> tuple[ProcessResult, dict[str, Any] | None]:
    auth = auth_ok()
    if not auth.get("ok"):
        raise ProcessSafetyError("claude_auth_unavailable")
    workspace_path = Path(mission.worktree).resolve()
    workspace = str(workspace_path)
    prompt_path = workspace_path / ".external_agent_runner_review_prompt.txt"
    prompt_path.write_text(
        build_review_prompt(mission, result_manifest=result_manifest, diff_text=diff_text),
        encoding="utf-8",
    )
    short = (
        f"Read .external_agent_runner_review_prompt.txt in this workspace and perform "
        f"that independent review. Respond with ONLY the required JSON review manifest "
        f"(mission_id={mission.mission_id}). Do not edit files."
    )
    argv = build_claude_argv(short, add_dir=workspace)
    try:
        result = run_allowlisted(
            argv,
            cwd=workspace,
            allowed_root=allowed_root,
            timeout_s=timeout_s,
            heartbeat=heartbeat,
        )
    finally:
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
            manifest = extract_review_manifest(result.stdout, mission.mission_id)
        except ProcessSafetyError:
            manifest = None
    return result, manifest
