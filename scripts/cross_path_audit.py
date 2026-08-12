#!/usr/bin/env python3
"""Cross-path wiring audit — telephony lifecycle parity + automation glue.

Detects wireable gaps that prod_check/wiring_audit miss:
  1. LIVE Vobiz stream cleanup must meter calls (minute billing + call.completed).
  2. Vobiz auto-qualify must fan out qualified-lead downstream hooks.
  3. Qualified-lead meter must be idempotent on ref (duplicate qualify guard).
  4. automation_wiring_audit (flags/jobs/beat) — reused, not duplicated.

Exit 0 = no gaps. Exit 1 = fix before ship.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PROBLEMS: list[str] = []


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        PROBLEMS.append(f"MISSING FILE: {rel}")
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def audit_call_insights_transcripts() -> None:
    text = _read("app/platform/call_insights.py")
    if text and "call_transcripts" not in text:
        PROBLEMS.append(
            "INSIGHTS: call_insights missing data/call_transcripts reader "
            "(LIVE Vobiz calls invisible to Ask AI)"
        )


def audit_vobiz_stream_lifecycle() -> None:
    text = _read("app/telephony/vobiz_stream.py")
    if not text:
        return
    cleanup_m = re.search(r"async def _cleanup\(.*?\n(.*?)(?=\n    (?:async )?def |\Z)", text, re.S)
    cleanup_body = cleanup_m.group(1) if cleanup_m else ""
    if "meter_call_completion" not in cleanup_body and "record_call_usage" not in cleanup_body:
        PROBLEMS.append(
            "TELEPHONY: vobiz_stream._cleanup missing meter_call_completion/record_call_usage "
            "(LIVE path skips minute billing + call.completed webhook)"
        )
    if "_teardown_done" not in cleanup_body and "_cleanup_done" not in cleanup_body:
        PROBLEMS.append(
            "TELEPHONY: vobiz_stream._cleanup missing idempotent teardown guard "
            "(double disconnect → duplicate qualify/meter risk)"
        )
    qual_m = re.search(
        r"async def _auto_qualify\(.*?\n(.*?)(?=\n    (?:async )?def |\Z)", text, re.S
    )
    qual_body = qual_m.group(1) if qual_m else ""
    if "apply_qualified_downstream" not in qual_body:
        PROBLEMS.append(
            "TELEPHONY: vobiz_stream._auto_qualify missing apply_qualified_downstream "
            "(CRM/sales/cadence only on legacy call_manager path)"
        )


def audit_qualified_lead_idempotency() -> None:
    text = _read("app/billing/lead_usage.py")
    if not text:
        return
    rec_fn = re.search(r"def record_qualified_lead\(.*?\n(.*?)(?=\n\ndef |\nclass |\Z)", text, re.S)
    body = rec_fn.group(1) if rec_fn else ""
    if "_ref_already_recorded" not in body and "seen_before" not in body:
        PROBLEMS.append(
            "BILLING: record_qualified_lead missing ref idempotency "
            "(same call qualified 2x → double meter/webhook)"
        )


def _fn_body(text: str, name: str) -> str:
    m = re.search(rf"async def {name}\(.*?\n(.*?)(?=\n    (?:async )?def |\Z)", text, re.S)
    return m.group(1) if m else ""


def audit_brain_guard_parity() -> None:
    """2da6239 lesson (2026-07-03): EVERY guard in reply() must be mirrored in
    reply_stream_sentences() — close-signals silently never fired on live calls
    because the stream fn lacked reply()'s guards. Encode it so a regression
    fails CI instead of shipping."""
    text = _read("app/voice_agent/telecaller_brain.py")
    if not text:
        return
    reply_body = _fn_body(text, "reply")
    stream_body = _fn_body(text, "reply_stream_sentences")
    if not reply_body or not stream_body:
        PROBLEMS.append("VOICE: telecaller_brain reply()/reply_stream_sentences() not found")
        return
    for marker, why in (
        ("deflect", "pre/post-LLM injection guard"),
        ("close_signal", "close-signal detection"),
        ("caller_phone", "caller-phone capture (deal-writes)"),
    ):
        if marker in reply_body and marker not in stream_body:
            PROBLEMS.append(
                f"VOICE: guard '{marker}' ({why}) in reply() but MISSING in "
                "reply_stream_sentences() — stream-path parity regression (2da6239 lesson)"
            )


def audit_stream_opt_out() -> None:
    """TCCCPR (audit 2026-07-04): LIVE stream calls must persist press-9 +
    verbal opt-out to the consent ledger — the legacy answer_url handler alone
    doesn't cover <Stream> calls."""
    text = _read("app/telephony/vobiz_stream.py")
    if not text:
        return
    if "_persist_opt_out" not in text or "record_opt_out" not in text:
        PROBLEMS.append(
            "COMPLIANCE: vobiz_stream missing _persist_opt_out/record_opt_out "
            "(stream-path opt-out never reaches the consent ledger)"
        )
    if "_is_opt_out" not in text:
        PROBLEMS.append("COMPLIANCE: vobiz_stream missing verbal opt-out detection (_is_opt_out)")


def audit_disclosure_enforcement() -> None:
    """AI-disclosure-at-start must be enforced on every spoken-opener surface."""
    for rel, why in (
        ("app/telephony/vobiz_stream.py", "LIVE stream greeting"),
        ("app/api/web_call.py", "web test-call greeting"),
        ("app/api/telephony_vobiz.py", "admin test-call message"),
    ):
        text = _read(rel)
        if text and "ensure_ai_disclosure" not in text:
            PROBLEMS.append(f"COMPLIANCE: {rel} missing ensure_ai_disclosure ({why})")


def audit_automation_parity() -> None:
    try:
        from scripts import automation_wiring_audit as awa

        awa.PROBLEMS.clear()
        blob = awa._all_app_text()
        awa.audit_flags(blob)
        awa.audit_jobs(blob)
        awa.audit_beat()
        PROBLEMS.extend(awa.PROBLEMS)
    except Exception as e:
        PROBLEMS.append(f"AUTOMATION: wiring audit import failed: {e}")


def main() -> int:
    print("=== CROSS-PATH WIRING AUDIT ===")
    audit_vobiz_stream_lifecycle()
    audit_call_insights_transcripts()
    audit_qualified_lead_idempotency()
    audit_brain_guard_parity()
    audit_stream_opt_out()
    audit_disclosure_enforcement()
    audit_automation_parity()
    print("-" * 48)
    if PROBLEMS:
        print(f"[FAIL] {len(PROBLEMS)} gap(s):")
        for p in PROBLEMS:
            print("  -", p)
        return 1
    print("[OK] cross-path telephony + automation parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
