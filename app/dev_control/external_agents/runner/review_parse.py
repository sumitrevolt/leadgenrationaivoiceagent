"""Independent-review parse / recovery integrity (PR #147 cycle-4 lessons).

Transport failure and recovered verdict are SEPARATE facts. A recovered PASS
never overrides a failed/cancelled/timed-out process.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.dev_control.external_agents.runner.process_safe import ProcessSafetyError

_SECRET_SHAPED = re.compile(
    r"(?i)(sk-[a-z0-9]{10,}|api[_-]?key\s*[:=]|password\s*[:=]|begin private)"
)


def sanitize_review_dump(blob: str, *, limit: int = 8000) -> str:
    """Bounded dump for evidence — redacts secret-shaped substrings."""
    text = blob or ""
    if _SECRET_SHAPED.search(text):
        text = _SECRET_SHAPED.sub("[REDACTED]", text)
    if len(text) > limit:
        text = text[:limit] + "\n…[truncated]"
    return text


def _extract_json_object(text: str) -> dict[str, Any]:
    s = (text or "").strip()
    if not s:
        raise ProcessSafetyError("review_empty")
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start < 0:
        raise ProcessSafetyError("review_not_json")
    depth = 0
    end = -1
    in_str = False
    esc = False
    for i, ch in enumerate(s[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise ProcessSafetyError("review_not_json")
    data = json.loads(s[start:end])
    if not isinstance(data, dict):
        raise ProcessSafetyError("review_not_object")
    return data


def parse_claude_cli_envelope(stdout: str) -> dict[str, Any]:
    """Parse Claude ``--output-format json`` envelope into the inner review object."""
    outer = _extract_json_object(stdout)
    if "result" in outer and "verdict" not in outer and "mission_id" not in outer:
        inner = outer.get("result")
        if isinstance(inner, dict):
            return inner
        if isinstance(inner, str):
            # Prefer full-string JSON (handles braces inside strings safely).
            try:
                data = json.loads(inner.strip())
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
            return _extract_json_object(inner)
        raise ProcessSafetyError("claude_result_not_json")
    return outer


def validate_recovered_review(
    rich: dict[str, Any],
    *,
    mission_id: str,
    expected_head: str,
    expected_reviewer: str = "claude",
) -> dict[str, Any]:
    if not isinstance(rich, dict):
        raise ProcessSafetyError("review_not_object")
    if str(rich.get("mission_id") or "") != mission_id:
        raise ProcessSafetyError("review_mission_id_mismatch")
    reviewer = str(rich.get("reviewer") or "").lower()
    if reviewer != expected_reviewer.lower():
        raise ProcessSafetyError("review_reviewer_mismatch")
    head = str(rich.get("reviewed_head_sha") or "")
    if head and head != expected_head:
        raise ProcessSafetyError("review_head_mismatch")
    verdict = str(rich.get("verdict") or "").upper()
    if verdict not in {"PASS", "CHANGES_REQUIRED", "BLOCKED"}:
        raise ProcessSafetyError("review_verdict_invalid")
    out = dict(rich)
    out["verdict"] = verdict
    out["mission_id"] = mission_id
    out["reviewer"] = expected_reviewer.lower()
    out["reviewed_head_sha"] = expected_head
    return out


def recover_independent_review(
    stdout: str,
    *,
    mission_id: str,
    expected_head: str,
    exit_code: int,
    timed_out: bool = False,
    cancelled: bool = False,
    truncated: bool = False,
) -> dict[str, Any]:
    """Canonical review ingestion — transport integrity separate from verdict.

    Rules:
    - exit 0 + valid manifest → eligible (any verdict)
    - nonzero / cancelled / timed-out + recovered CHANGES_REQUIRED|BLOCKED →
      may be preserved as a conservative verdict after validation
    - nonzero exit never yields PASS
    - truncated output never yields PASS
    """
    transport = {
        "exit_code": int(exit_code),
        "timed_out": bool(timed_out),
        "cancelled": bool(cancelled),
        "truncated": bool(truncated),
        "process_ok": int(exit_code) == 0 and not timed_out and not cancelled,
        "stdout_len": len(stdout or ""),
        "stdout_tail_sanitized": sanitize_review_dump((stdout or "")[-2000:], limit=2000),
    }
    record: dict[str, Any] = {
        "ok": False,
        "transport": transport,
        "parser": {"status": "not_attempted", "error": None},
        "rich": None,
        "recovered_verdict": None,
        "recovery_source": None,
    }

    try:
        raw = parse_claude_cli_envelope(stdout)
        rich = validate_recovered_review(raw, mission_id=mission_id, expected_head=expected_head)
    except ProcessSafetyError as exc:
        record["parser"]["status"] = "parse_failed"
        record["parser"]["error"] = str(exc)
        record["reason"] = (
            "process_integrity_failed" if not transport["process_ok"] else f"parse_failed:{exc}"
        )
        return record
    except Exception as exc:  # noqa: BLE001 — evidence boundary
        record["parser"]["status"] = "parse_failed"
        record["parser"]["error"] = type(exc).__name__
        record["reason"] = f"parse_failed:{type(exc).__name__}"
        return record

    verdict = rich["verdict"]
    if truncated and verdict == "PASS":
        record["parser"]["status"] = "refused_truncated_pass"
        record["reason"] = "truncated_output_cannot_pass"
        record["recovered_verdict"] = verdict
        return record
    if not transport["process_ok"]:
        if verdict == "PASS":
            record["parser"]["status"] = "refused_failed_process_pass"
            record["reason"] = "failed_process_cannot_pass"
            record["recovered_verdict"] = verdict
            return record
        if verdict not in {"CHANGES_REQUIRED", "BLOCKED"}:
            record["parser"]["status"] = "skipped_process_integrity"
            record["reason"] = "process_integrity_failed"
            return record
        # Conservative recovery: keep CHANGES_REQUIRED / BLOCKED only.
        record["parser"]["status"] = "ok_conservative"
        record["rich"] = rich
        record["recovered_verdict"] = verdict
        record["recovery_source"] = "claude_cli_envelope_conservative"
        record["ok"] = True
        return record

    record["parser"]["status"] = "ok"
    record["rich"] = rich
    record["recovered_verdict"] = verdict
    record["recovery_source"] = "claude_cli_envelope"
    record["ok"] = True
    return record
