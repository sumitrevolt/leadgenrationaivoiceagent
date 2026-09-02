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

import ast
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

#: The canonical ledger filename.
LEDGER = "email_suppression.jsonl"

#: Only this module may name the ledger path.
CANONICAL_MODULE = "email_unsub.py"

#: Declarative governance metadata that DESCRIBES the ledger without accessing
#: it: the runtime-data allowlist and store manifest record owner, migration
#: tier, cutover target and review condition for every legacy store, and the
#: suppression ledger is one of them. Naming a path in a data table is not a
#: runtime bypass — it is the opposite, it is the path being placed under
#: review.
#:
#: EXACT FILENAMES, never a directory prefix. Excluding `app/platform/**` would
#: have exempted the whole folder the canonical service lives in, so a real
#: `open("data/email_suppression.jsonl", "a")` added next door would pass this
#: audit unnoticed. The exemption is verified below, not merely asserted:
#: test_governance_metadata_exemption_is_minimal_and_declarative proves each
#: entry still needs the exemption and cannot perform I/O at all.
GOVERNANCE_METADATA_MODULES = frozenset(
    {
        "runtime_data_allowlist_entries.py",
        "runtime_data_manifest.py",
    }
)

#: Imports a purely declarative module may use. Anything able to reach a
#: filesystem (os, pathlib, shutil, json, aiofiles, sqlite3, ...) disqualifies
#: it from the exemption.
_DECLARATIVE_IMPORT_ROOTS = frozenset({"__future__", "typing"})


def _py_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if p.is_file()]


def test_only_canonical_module_names_the_ledger_path() -> None:
    """No EXECUTABLE module outside email_unsub.py may reference the ledger.

    Declarative governance tables are exempt by exact filename only; every
    module that can actually run I/O stays in scope.
    """
    offenders: list[str] = []
    for path in _py_files():
        if path.name == CANONICAL_MODULE:
            continue
        if path.name in GOVERNANCE_METADATA_MODULES:
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


def test_governance_metadata_exemption_is_minimal_and_declarative() -> None:
    """The exemption list must earn itself, every run.

    An exception list that is never re-checked is how a structural guard dies:
    the entry survives long after the module it excused has grown a writer, and
    the audit above then reports success for a file nobody is auditing.

    So each entry must (1) be an exact filename resolving to exactly one module,
    (2) still actually name the ledger — a stale exemption gets deleted, not
    kept — and (3) be provably incapable of touching a filesystem: imports
    limited to `__future__`/`typing` and no `open()` anywhere. The check is on
    the AST, because both modules quote `os.replace` and `write_text` inside
    their evidence PROSE, and a token scan would take that prose for code.
    """
    assert GOVERNANCE_METADATA_MODULES == {
        "runtime_data_allowlist_entries.py",
        "runtime_data_manifest.py",
    }, "the exemption list changed — a new entry needs its own justification"
    assert CANONICAL_MODULE not in GOVERNANCE_METADATA_MODULES

    for name in sorted(GOVERNANCE_METADATA_MODULES):
        assert "/" not in name and "\\" not in name and "*" not in name, (
            f"{name}: exemptions are exact filenames — a path prefix or glob "
            "would exempt modules nobody reviewed"
        )
        matches = [p for p in _py_files() if p.name == name]
        assert len(matches) == 1, f"{name}: expected exactly one module, found {matches}"
        path = matches[0]
        text = path.read_text(encoding="utf-8", errors="ignore")

        assert LEDGER in text, (
            f"{name} no longer names the ledger — delete the exemption instead "
            "of leaving a blanket hole in the audit"
        )

        tree = ast.parse(text)
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                raise AssertionError(f"{name} calls open() — it is not declarative metadata")
        extra = roots - _DECLARATIVE_IMPORT_ROOTS
        assert not extra, (
            f"{name} imports {sorted(extra)} — a module that can reach a "
            "filesystem does not qualify for the declarative exemption"
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
    assert LEDGER not in text, (
        "the WhatsApp campaign runner must not write the unified email ledger"
    )


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
