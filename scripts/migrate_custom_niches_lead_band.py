"""Migrate data/custom_niches.json: pricing_inr -> lead_band (ADR-009).

Purane custom-niche records me per-lead `pricing_inr` tha; ADR-009 ke baad sirf
`lead_band` (A/B/C). Band = qualified_lead range ke midpoint se (builtin transform
jaisa hi): mid < 800 => A, 800-2500 => B, > 2500 => C. pricing_inr DROP.

Idempotent + safe: backup `.bak_leadband` banata hai, missing file = no-op.
Run: python scripts/migrate_custom_niches_lead_band.py  (host ya `docker exec leadgen_app`)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DATA = Path("data/custom_niches.json")


def band_from_mid(mid: float) -> str:
    if mid < 800:
        return "A"
    if mid <= 2500:
        return "B"
    return "C"


def main() -> int:
    if not DATA.exists():
        print("NO_FILE (ok) — koi custom niches nahi")
        return 0
    try:
        data = json.loads(DATA.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"PARSE_FAIL: {e}")
        return 1
    changed = 0
    for key, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        if "lead_band" not in cfg:
            mid = 1000.0  # default => B-adjacent; pricing_inr ho to usse derive
            pr = cfg.get("pricing_inr") or {}
            ql = pr.get("qualified_lead") or []
            try:
                if isinstance(ql, (list, tuple)) and len(ql) == 2:
                    mid = (float(ql[0]) + float(ql[1])) / 2
            except Exception:
                pass
            cfg["lead_band"] = band_from_mid(mid)
            changed += 1
        if "pricing_inr" in cfg:
            cfg.pop("pricing_inr", None)
            changed += 1
    if not changed:
        print("ALREADY_MIGRATED (0 changes)")
        return 0
    shutil.copy2(DATA, DATA.with_suffix(".json.bak_leadband"))
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"MIGRATED: {changed} field-changes across {len(data)} custom niches (backup .bak_leadband)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
