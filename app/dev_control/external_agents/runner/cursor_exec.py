"""Cursor Agent CLI executor — real non-interactive invocation.

``--trust`` decision: **KEEP --trust**. Cursor Agent non-interactive print mode
requires it for a pre-provisioned workspace. Containment is NOT provided by
``--trust`` itself; it comes from: dedicated feat/ext-* worktree, deny-by-default
env (no secret wildcards), redirected HOME/USERPROFILE/APPDATA/LOCALAPPDATA to
runner-owned profile trees (minimal Claude/Cursor auth material only), allowlisted
argv, post-run git-observed path scope checks, pushurl disabled://no-push on the
worktree, and dual-flag inert defaults.

**Windows argv safety:** never launch ``agent.cmd`` (cmd.exe re-parses ``&|<>^``).
Resolve to ``versions/*/node.exe`` + ``index.js`` (CreateProcess argv array), with
``powershell -File agent.ps1`` as fallback — never ``%*`` through ``.cmd``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from app.dev_control.external_agents.policy import redact
from app.dev_control.external_agents.runner.process_safe import (
    ProcessResult,
    ProcessSafetyError,
    run_allowlisted,
)
from app.dev_control.external_agents.runner.review_parse import _extract_json_object
from app.dev_control.external_agents.schema import Mission

_VERSION_DIR_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}(-\d{2}-\d{2}-\d{2})?-[a-f0-9]+$", re.I)

# Written by the executor inside the worktree — preferred over chat-envelope parse.
RESULT_MANIFEST_FILENAME = ".external_agent_result_manifest.json"
RUNNER_CONTROL_FILES = frozenset(
    {
        RESULT_MANIFEST_FILENAME,
        ".external_agent_runner_prompt.txt",
    }
)


def _cursor_agent_home() -> Path | None:
    forced_home = (os.getenv("EXTERNAL_AGENT_CURSOR_HOME") or "").strip()
    candidates: list[Path] = []
    if forced_home:
        candidates.append(Path(forced_home))
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        candidates.append(Path(local) / "cursor-agent")
    # Install lives under the real user LocalAppData even when child LOCALAPPDATA
    # is redirected for compile-cache isolation.
    candidates.append(Path.home() / "AppData" / "Local" / "cursor-agent")
    seen: set[str] = set()
    for home in candidates:
        key = str(home.resolve()) if home.exists() else str(home)
        if key in seen:
            continue
        seen.add(key)
        if home.is_dir() and (
            (home / "versions").is_dir()
            or (home / "agent.ps1").is_file()
            or (home / "cursor-agent.ps1").is_file()
        ):
            return home
    return None


def _latest_version_dir(home: Path) -> Path | None:
    versions = home / "versions"
    if not versions.is_dir():
        return None
    dirs = [p for p in versions.iterdir() if p.is_dir() and _VERSION_DIR_RE.match(p.name)]
    if not dirs:
        return None

    def _key(p: Path) -> tuple:
        # Sort by leading date stamp then name.
        return (p.name,)

    dirs.sort(key=_key, reverse=True)
    return dirs[0]


def resolve_cursor_invocation() -> list[str]:
    """Return argv prefix that does **not** go through ``agent.cmd``.

    Preferred: ``node.exe`` + ``index.js`` from the latest cursor-agent version.
    Fallback: ``powershell.exe -File agent.ps1`` (still argv-array safe).
    """
    forced = (os.getenv("EXTERNAL_AGENT_CURSOR_BIN") or "").strip()
    if forced:
        p = Path(forced).resolve()
        if not p.is_file():
            raise ProcessSafetyError("cursor_bin_missing")
        # Refuse .cmd/.bat forced bins — they re-parse metacharacters.
        if p.suffix.lower() in {".cmd", ".bat"}:
            raise ProcessSafetyError("cursor_cmd_wrapper_refused")
        if p.suffix.lower() == ".ps1":
            ps = shutil.which("powershell.exe") or shutil.which("powershell")
            if not ps:
                raise ProcessSafetyError("powershell_unavailable")
            return [
                str(Path(ps).resolve()),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(p),
            ]
        return [str(p)]

    home = _cursor_agent_home()
    if home is None:
        raise ProcessSafetyError("cursor_cli_unavailable")

    ver = _latest_version_dir(home)
    if ver is not None:
        node = ver / "node.exe"
        index = ver / "index.js"
        if node.is_file() and index.is_file():
            return [str(node.resolve()), str(index.resolve())]

    for ps1_name in ("cursor-agent.ps1", "agent.ps1"):
        ps1 = home / ps1_name
        if ps1.is_file():
            ps = shutil.which("powershell.exe") or shutil.which("powershell")
            if not ps:
                raise ProcessSafetyError("powershell_unavailable")
            return [
                str(Path(ps).resolve()),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1.resolve()),
            ]
    raise ProcessSafetyError("cursor_cli_unavailable")


def resolve_cursor_executable() -> str:
    """Compatibility: first path element of ``resolve_cursor_invocation()``."""
    return resolve_cursor_invocation()[0]


def build_cursor_argv(*, workspace: str, print_mode: bool = True) -> list[str]:
    argv = list(resolve_cursor_invocation())
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
    manifest_schema = (
        "{\n"
        f'  "mission_id": "{mission.mission_id}",\n'
        '  "executor": "cursor",\n'
        '  "changed_files": ["repo-relative paths you changed"],\n'
        '  "commands": ["commands you ran"],\n'
        '  "tests": [{"command":"...", "exit_code":0, "summary":"..."}],\n'
        '  "summary": "...",\n'
        '  "evidence": {},\n'
        '  "scope_breach": false\n'
        "}"
    )
    return (
        "You are the Cursor executor for LeadGen External Agent Orchestrator.\n"
        "Implement ONLY the mission below. Stay inside allowed_paths.\n"
        "Do NOT touch voice, telephony, billing, .env, deploy workflows, or customer data.\n"
        "Do NOT commit or push unless the mission explicitly requires it (this dogfood does not).\n"
        f"REQUIRED COMPLETION CONTRACT: write the file `{RESULT_MANIFEST_FILENAME}` at the "
        "worktree root containing EXACTLY one JSON object matching this schema "
        "(mission_id and executor must match exactly):\n"
        f"{manifest_schema}\n"
        "Do not invent alternate field names. Writing that file is mandatory and is how "
        "the runner accepts your result (chat text alone is insufficient).\n\n"
        f"MISSION_ID={mission.mission_id}\n"
        f"TITLE={mission.title}\n"
        f"DESCRIPTION={mission.description}\n"
        f"BRANCH={mission.branch}\n"
        f"BASE_SHA={mission.base_sha}\n"
        f"ALLOWED_PATHS:\n{allowed}\n"
        f"ACCEPTANCE={json.dumps(mission.acceptance_criteria)}\n"
        f"PACKET={json.dumps(redact(packet), ensure_ascii=False)[:4000]}\n"
    )


def _validate_result_manifest(data: Any, mission_id: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProcessSafetyError("cursor_manifest_invalid")
    if str(data.get("mission_id") or "") != mission_id:
        raise ProcessSafetyError("cursor_mission_id_mismatch")
    if str(data.get("executor") or "").lower() != "cursor":
        raise ProcessSafetyError("cursor_executor_mismatch")
    return data


def load_result_manifest_file(workspace: str | Path, mission_id: str) -> dict[str, Any]:
    """Load + validate the worktree result-manifest file (preferred contract)."""
    path = Path(workspace) / RESULT_MANIFEST_FILENAME
    if not path.is_file():
        raise ProcessSafetyError("cursor_result_file_missing")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProcessSafetyError("cursor_result_file_unreadable") from exc
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ProcessSafetyError("cursor_result_file_not_json") from exc
    return _validate_result_manifest(data, mission_id)


def extract_result_manifest(stdout: str, mission_id: str) -> dict[str, Any]:
    """Parse Cursor agent JSON envelope into a result manifest.

    Fail-closed on outer stdout: the entire stdout must be one JSON value
    (no surrounding prose). Cursor may wrap the mission manifest in
    ``{result: ...}``; the inner ``result`` string may contain leading prose,
    in which case the first JSON object is extracted (same as Claude review).
    """
    text = stdout.strip()
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProcessSafetyError("cursor_output_not_json") from exc

    # Cursor agent may wrap in {result: "..."} or {result: {...}}
    if isinstance(data, dict) and "result" in data and "mission_id" not in data:
        inner = data["result"]
        if isinstance(inner, str):
            try:
                data = json.loads(inner.strip())
            except json.JSONDecodeError:
                # Agent often prepends prose inside the result string.
                try:
                    data = _extract_json_object(inner)
                except ProcessSafetyError as exc:
                    raise ProcessSafetyError("cursor_result_not_json") from exc
        elif isinstance(inner, dict):
            data = inner
        else:
            raise ProcessSafetyError("cursor_result_not_json")
    return _validate_result_manifest(data, mission_id)


def invoke_cursor(
    mission: Mission,
    packet: dict[str, Any],
    *,
    allowed_root: str,
    timeout_s: int = 900,
    heartbeat=None,
) -> tuple[ProcessResult, dict[str, Any] | None, str | None]:
    """Run Cursor; return ``(process, manifest|None, parse_error|None)``."""
    workspace = Path(mission.worktree).resolve()
    prompt_path = workspace / ".external_agent_runner_prompt.txt"
    manifest_path = workspace / RESULT_MANIFEST_FILENAME
    try:
        if manifest_path.exists():
            manifest_path.unlink()
    except OSError:
        pass
    prompt_path.write_text(build_executor_prompt(mission, packet), encoding="utf-8")
    # Short argv — agent reads the prompt file (avoids Windows command-line limits).
    short = (
        f"Read the file .external_agent_runner_prompt.txt in this workspace and execute "
        f"that mission exactly. Stay inside allowed_paths. When finished you MUST write "
        f"{RESULT_MANIFEST_FILENAME} at the worktree root with the exact JSON schema from "
        f"the prompt (mission_id={mission.mission_id}, executor=cursor)."
    )
    argv = build_cursor_argv(workspace=str(workspace)) + [short]
    result = run_allowlisted(
        argv,
        cwd=str(workspace),
        allowed_root=allowed_root,
        timeout_s=timeout_s,
        heartbeat=heartbeat,
        env_profile="cursor",
    )
    try:
        prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
    except TypeError:
        if prompt_path.exists():
            prompt_path.unlink()
    except Exception:
        pass
    manifest = None
    parse_error: str | None = None
    if result.exit_code == 0 and not result.timed_out and not result.cancelled:
        # Prefer durable worktree file over chat-envelope parse.
        try:
            manifest = load_result_manifest_file(workspace, mission.mission_id)
        except ProcessSafetyError as file_exc:
            try:
                manifest = extract_result_manifest(result.stdout, mission.mission_id)
            except ProcessSafetyError as stdout_exc:
                parse_error = f"{file_exc};{stdout_exc}"
                manifest = None
    return result, manifest, parse_error
