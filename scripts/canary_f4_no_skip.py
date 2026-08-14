#!/usr/bin/env python3
"""Lead gate: TM2 canary contract must fail-not-skip (F4).

Exit 0 = no skip/skipif/xfail patterns tied to missing canary doc.
Exit 2 = refused (dead assert risk).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "tests" / "test_agent_teams_canary_contract.py"

# Patterns that kill the coupling signal when doc is missing.
_BAD = re.compile(r"""(?ix)
    pytest\.(skip|xfail)\s*\(
    | @pytest\.mark\.(skip|skipif|xfail)\b
    | pytest\.importorskip\s*\(
    """)
_DOC_HINT = re.compile(r"AGENT_TEAMS_CANARY|canary.?doc|missing.?doc", re.I)


def main() -> int:
    if not TARGET.is_file():
        print(f"REFUSED: missing {TARGET.relative_to(REPO)} — TM2 not merged yet?", file=sys.stderr)
        return 2
    text = TARGET.read_text(encoding="utf-8")
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if _BAD.search(line):
            # Always refuse skip/xfail in this file — canary contract must not soft-pass.
            hits.append(f"{i}:{line.strip()}")
    if "pytest.fail" not in text and "raise AssertionError" not in text and "assert " not in text:
        print("REFUSED: no hard fail/assert found in TM2 contract", file=sys.stderr)
        return 2
    # Prefer explicit fail on missing doc
    if "pytest.fail" not in text and not re.search(
        r"assert\s+.+\.is_file\(|assert\s+.+\.exists\(", text
    ):
        print(
            "WARN: no pytest.fail / path.exists assert detected — review manually", file=sys.stderr
        )
    if hits:
        print("REFUSED: skip/xfail found in TM2 canary contract (F4):", file=sys.stderr)
        for h in hits:
            print(f"  {h}", file=sys.stderr)
        return 2
    print(f"OK f4_fail_not_skip path={TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
