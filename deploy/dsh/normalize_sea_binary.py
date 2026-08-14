#!/usr/bin/env python3
"""Normalize pkg SEA temp-path bytes so independent builds share one executable hash.

@yao-pkg/pkg --sea embeds ``/tmp/pkg-sea-XXXXXX/sea-main.js`` where XXXXXX comes
from ``mkdtemp``. LeadGen's Docker build rewrites that equal-length diagnostic
path to ``/tmp/pkg-sea-dsh000/sea-main.js`` and fails closed if the carrier
shape changes. This helper mirrors that rewrite for offline proof checks.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PATTERN = re.compile(rb"/tmp/pkg-sea-[0-9A-Za-z]{6}/sea-main\.js")
REPLACEMENT = b"/tmp/pkg-sea-dsh000/sea-main.js"


def normalize(path: Path) -> int:
    data = bytearray(path.read_bytes())
    if REPLACEMENT in data:
        raise SystemExit(
            f"normalize_sea_binary: expected exactly one unnormalized pkg-sea path in {path}, found 0"
        )
    matches = list(PATTERN.finditer(bytes(data)))
    if len(matches) != 1:
        raise SystemExit(
            f"normalize_sea_binary: expected exactly one pkg-sea path in {path}, found {len(matches)}"
        )
    match = matches[0]
    if len(match.group(0)) != len(REPLACEMENT):
        raise SystemExit("normalize_sea_binary: replacement length mismatch")
    data[match.start() : match.end()] = REPLACEMENT
    path.write_bytes(data)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    count = normalize(args.binary)
    print(f"normalize_sea_binary: rewrote {count} pkg-sea path(s) in {args.binary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
