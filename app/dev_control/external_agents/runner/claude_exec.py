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
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=30,
            check=False,
        )
        probe = subprocess.run(
            [exe, "-p", "Return only: AUTH_OK"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"auth_probe_failed:{type(exc).__name__}"}
    logged_in = "loggedIn" in (st.stdout or "") and "true" in (st.stdout or "").lower()
    auth_line = (probe.stdout or "").strip().splitlines()[-1:] or [""]
    # Envelope JSON may wrap AUTH_OK — accept substring match on last lines.
    probe_text = (probe.stdout or "").strip()
    ok = probe.returncode == 0 and (
        auth_line[-1].strip() == "AUTH_OK" or "AUTH_OK" in probe_text.splitlines()[-3:]
    )
    return {
        "ok": bool(ok or logged_in),
        "version_probe_exit": probe.returncode,
        "auth_status_exit": st.returncode,
        # Never return raw stdout (may include email); only booleans.
        "auth_ok": ok,
        "logged_in": logged_in,
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
        "Write,Edit,NotebookEdit,Bash",
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


def extract_usage_from_cli_json(stdout: str) -> dict[str, float | int]:
    """Parse token/cost fields from Cursor/Claude ``--output-format json`` envelopes.

    Budget tokens = input + output (+ cache *writes*). Cache *reads* are excluded —
    Cursor/Claude envelopes often report hundreds of thousands of cache-read tokens
    that would false-trip ``token_budget`` on tiny GREEN missions.
    """
    tokens = 0
    cost = 0.0
    try:
        outer = json.loads(stdout)
    except Exception:
        return {"tokens_used": 0, "cost_usd": 0.0}
    if not isinstance(outer, dict):
        return {"tokens_used": 0, "cost_usd": 0.0}
    usage = outer.get("usage") or {}
    if isinstance(usage, dict):
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "inputTokens",
            "outputTokens",
            "cacheWriteTokens",
        ):
            try:
                tokens += int(usage.get(k) or 0)
            except Exception:
                pass
    try:
        cost = float(outer.get("total_cost_usd") or outer.get("cost_usd") or 0.0)
    except Exception:
        cost = 0.0
    mu = outer.get("modelUsage") or {}
    if isinstance(mu, dict):
        for meta in mu.values():
            if isinstance(meta, dict):
                try:
                    cost += float(meta.get("costUSD") or 0.0)
                except Exception:
                    pass
                for k in (
                    "inputTokens",
                    "outputTokens",
                    "cacheCreationInputTokens",
                ):
                    try:
                        tokens += int(meta.get(k) or 0)
                    except Exception:
                        pass
    return {"tokens_used": tokens, "cost_usd": cost}


def extract_review_manifest(stdout: str, mission_id: str) -> dict[str, Any]:
    """Legacy helper — prefer ``recover_independent_review`` on the live path.

    Kept for unit tests that exercise envelope parsing in isolation. Live
    ``invoke_claude_review`` MUST NOT call this directly.
    """
    from app.dev_control.external_agents.runner.review_parse import parse_claude_cli_envelope

    data = parse_claude_cli_envelope(stdout)
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
    expected_head: str | None = None,
) -> tuple[ProcessResult, dict[str, Any] | None, dict[str, Any]]:
    """Run Claude review via the canonical ``review_parse`` ingestion path.

    Returns ``(process, review_manifest|None, parse_evidence)``.
    """
    from app.dev_control.external_agents.runner.review_parse import recover_independent_review

    auth = auth_ok()
    if not auth.get("ok"):
        raise ProcessSafetyError("claude_auth_unavailable")
    workspace_path = Path(mission.worktree).resolve()
    workspace = str(workspace_path)
    head = (expected_head or mission.base_sha or "").strip()
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
            env_profile="claude",
        )
    finally:
        try:
            prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            if prompt_path.exists():
                prompt_path.unlink()
        except Exception:
            pass
    recovered = recover_independent_review(
        result.stdout or "",
        mission_id=mission.mission_id,
        expected_head=head,
        exit_code=int(result.exit_code if result.exit_code is not None else -1),
        timed_out=bool(result.timed_out),
        cancelled=bool(result.cancelled),
        truncated=bool(getattr(result, "truncated", False)),
    )
    evidence = {
        "transport": recovered.get("transport"),
        "parser": recovered.get("parser"),
        "recovery_source": recovered.get("recovery_source"),
        "reason": recovered.get("reason"),
        "recovered_verdict": recovered.get("recovered_verdict"),
    }
    manifest = recovered.get("rich") if recovered.get("ok") else None
    return result, manifest, evidence
