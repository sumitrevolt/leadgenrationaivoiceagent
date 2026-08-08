#!/usr/bin/env python3
"""Load Agent Teams canary SSOT (docs/coordination/canary_frozen_paths.yml).

TM2 contract tests and lead tooling must import this — never paste frozen paths.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
SSOT_PATH = REPO / "docs" / "coordination" / "canary_frozen_paths.yml"


@lru_cache(maxsize=1)
def load_canary_ssot() -> dict[str, Any]:
    if not SSOT_PATH.is_file():
        raise FileNotFoundError(f"missing canary SSOT: {SSOT_PATH}")
    data = yaml.safe_load(SSOT_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("canary SSOT must be a mapping")
    required = ("schema_version", "frozen_paths", "branch_prefix", "max_teammates", "pass_rule", "stop_rule")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"canary SSOT missing keys: {missing}")
    if not isinstance(data["frozen_paths"], list) or not data["frozen_paths"]:
        raise ValueError("frozen_paths must be a non-empty list")
    return data


def frozen_paths() -> list[str]:
    return [str(p) for p in load_canary_ssot()["frozen_paths"]]


def branch_prefix() -> str:
    return str(load_canary_ssot()["branch_prefix"])


def max_teammates() -> int:
    return int(load_canary_ssot()["max_teammates"])


def render_frozen_markdown() -> str:
    """Helper for TM1 docs — render bullets from SSOT (no hand-copied list)."""
    lines = ["<!-- rendered from docs/coordination/canary_frozen_paths.yml — do not hand-edit paths -->", ""]
    for p in frozen_paths():
        lines.append(f"- `{p}`")
    classes = load_canary_ssot().get("frozen_classes") or []
    if classes:
        lines.append("")
        lines.append("Classes:")
        for c in classes:
            lines.append(f"- `{c}`")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(f"ssot={SSOT_PATH}")
    print(f"branch_prefix={branch_prefix()}")
    print(f"max_teammates={max_teammates()}")
    print(render_frozen_markdown())
