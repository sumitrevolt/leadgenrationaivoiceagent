"""Structural guard: the suppression ledger has exactly ONE writer.

The whole point of a canonical suppression authority is that every write goes
through it — picking up the shared cross-process lock, namespace-safe
idempotency, scope validation, the partial-result model, and durable
cancellation. A future direct `open("data/email_suppression.jsonl", "a")`
somewhere else would silently bypass all five.

These tests are deliberately structural (they read the source tree) because that
is the only way to catch a bypass that has not been written yet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

#: The canonical ledger filename.
LEDGER = "email_suppression.jsonl"

#: Only this module may name the ledger path.
CANONICAL_MODULE = "email_unsub.py"


def _py_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if p.is_file()]


def test_only_canonical_module_names_the_ledger_path() -> None:
    """Nothing outside email_unsub.py may reference the ledger file directly."""
    offenders: list[str] = []
    for path in _py_files():
        if path.name == CANONICAL_MODULE:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # pragma: no cover
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if LEDGER in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path.relative_to(APP.parent)}:{i}: {line.strip()[:120]}")
    assert not offenders, (
        "Direct reference to the suppression ledger outside the canonical service — "
        "this bypasses the shared lock, idempotency, scope validation and "
        "cancellation:\n  " + "\n  ".join(offenders)
    )


def test_suppression_writes_go_through_the_canonical_service() -> None:
    """Every suppression write is an `email_unsub.suppress*` call."""
    call_re = re.compile(r"email_unsub\.(suppress\w*)\s*\(")
    # `suppressed_emails` is a READER (bulk send-filter preload in auto_outreach),
    # not a write path — it matches the `suppress*` prefix but takes no lock and
    # mutates nothing.
    allowed = {"suppress", "suppress_with_result", "suppressed_emails"}
    found: list[str] = []
    for path in _py_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # pragma: no cover
            continue
        for m in call_re.finditer(text):
            found.append(m.group(1))
    assert found, "expected at least one canonical suppression call in app/"
    bad = sorted(set(found) - allowed)
    assert not bad, f"unexpected suppression entry points: {bad}"


def test_whatsapp_campaign_list_is_a_documented_separate_store() -> None:
    """The WhatsApp campaign list may coexist, but must stay distinct and documented.

    It predates the unified authority and serves the campaign runner. Unified
    eligibility consults BOTH (the legacy check first, then the canonical one),
    so precedence is "either blocks". This test pins that it has not silently
    become a second general-purpose suppression ledger.
    """
    runner = APP / "marketing" / "wa_campaign_runner.py"
    text = runner.read_text(encoding="utf-8", errors="ignore")
    assert "wa_suppression.jsonl" in text
    assert (
        LEDGER not in text
    ), "the WhatsApp campaign runner must not write the unified email ledger"


def test_canonical_service_exposes_the_safety_primitives() -> None:
    """Guard against a refactor quietly dropping a safety primitive."""
    from app.platform import email_unsub

    for name in (
        "suppress",
        "suppress_with_result",
        "reconcile_suppressions",
        "build_event_id",
        "is_contact_suppressed",
        "_store_lock",
        "SCOPE_ALL_OUTREACH",
        "SCOPE_EMAIL_ADDRESS",
        "SCOPE_CHANNEL_CONTACT",
        "RESULT_NEEDS_RECONCILIATION",
    ):
        assert hasattr(email_unsub, name), f"canonical service lost {name}"


@pytest.mark.parametrize(
    "result",
    ["COMPLETE", "ALREADY_APPLIED", "SUPPRESSED_NEEDS_RECONCILIATION", "FAILED"],
)
def test_result_vocabulary_is_stable(result: str) -> None:
    """Callers branch on these strings; renaming one silently breaks them."""
    from app.platform import email_unsub

    assert result in {
        email_unsub.RESULT_COMPLETE,
        email_unsub.RESULT_ALREADY_APPLIED,
        email_unsub.RESULT_NEEDS_RECONCILIATION,
        email_unsub.RESULT_FAILED,
    }
