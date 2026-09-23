"""Regression test: canonical owner-directive archive checksum pin.

AGENTS.md (the single canonical governance file) pins the immutable owner
directive archive at `docs/OWNER_DIRECTIVE_2026-09-22.md` with a SHA-256
checksum. On Windows checkouts (`core.autocrlf=true`) git used to smudge the
file to CRLF, silently changing its bytes so the recorded pin never verified.
`.gitattributes` now pins that path to `text eol=lf`; these tests hash the
ACTUAL checked-out bytes so any accidental content or line-ending change
fails loudly instead of silently invalidating the tamper-evidence pin.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "OWNER_DIRECTIVE_2026-09-22.md"
AGENTS_MD = ROOT / "AGENTS.md"

ARCHIVE_NAME = "OWNER_DIRECTIVE_2026-09-22.md"
PIN_RE = re.compile(r"SHA-256\s+`([0-9A-Fa-f]{64})`")


def _pinned_sha256() -> str:
    """Extract the checksum pin bound to the directive path in AGENTS.md."""
    pins: list[str] = []
    for line in AGENTS_MD.read_text(encoding="utf-8").splitlines():
        if ARCHIVE_NAME in line:
            pins.extend(PIN_RE.findall(line))
    assert pins, (
        f"AGENTS.md no longer pins {ARCHIVE_NAME} with a SHA-256 checksum — "
        "governance tamper-evidence reference is broken"
    )
    return pins[0].lower()


def test_archive_exists_and_checksum_pin_is_declared() -> None:
    assert ARCHIVE.is_file(), f"missing canonical archive: {ARCHIVE}"
    _pinned_sha256()


def test_archive_bytes_match_pinned_checksum() -> None:
    data = ARCHIVE.read_bytes()
    assert b"\r" not in data, (
        "CRLF crept into the canonical archive — the .gitattributes "
        "`text eol=lf` pin is broken or the file was re-saved with "
        "Windows line endings; the AGENTS.md SHA-256 pin cannot verify"
    )
    assert hashlib.sha256(data).hexdigest() == _pinned_sha256(), (
        f"docs/{ARCHIVE_NAME} bytes no longer match the SHA-256 pinned in "
        "AGENTS.md — content changed without re-pinning the governance reference"
    )
