"""Read-only inventory of deployment mutation surface. Prints facts, changes nothing.

Exists because three successive hand-written summaries disagreed with each other.
Counts must come from one scan, not from memory.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"

GIT_MUTATION = re.compile(r"git\s+(stash|reset\s+--hard|clean|pull|checkout\s+-B|switch|restore)\b")
CONTAINER_MUTATION = re.compile(
    r"docker\s+compose[^\n]*\b(up\s+-d|down|pull|build|recreate)\b"
    r"|docker\s+(rm|system\s+prune)\b"
)
FS_MUTATION = re.compile(r"\brsync[^\n]*--delete\b|\brm\s+-rf\b")
PROD_MARKER = re.compile(r"/opt/leadgen|docker-compose\.vps\.yml|leadsgenai\.in|72\.61\.245")
GUARD = re.compile(r"_runtime_data_guard\.sh|runtime_data_preflight\.py")


def strip_noise(text: str, py: bool) -> str:
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            continue
        out.append(ln)
    body = "\n".join(out)
    if py:
        # crude: drop triple-quoted blocks so docstrings cannot match
        body = re.sub(r'""".*?"""', "", body, flags=re.S)
        body = re.sub(r"'''.*?'''", "", body, flags=re.S)
    return body


def scan_file(p: Path) -> dict | None:
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    body = strip_noise(raw, p.suffix == ".py")
    git_hits = GIT_MUTATION.findall(body)
    cont_hits = CONTAINER_MUTATION.findall(body)
    fs_hits = FS_MUTATION.findall(body)
    total = len(git_hits) + len(cont_hits) + len(fs_hits)
    if total == 0:
        return None
    return {
        "file": str(p.relative_to(ROOT)).replace("\\", "/"),
        "git_mutations": len(git_hits),
        "container_mutations": len(cont_hits),
        "fs_mutations": len(fs_hits),
        "occurrences": total,
        "production_marker": bool(PROD_MARKER.search(body)),
        "guarded": bool(GUARD.search(body)),
    }


def main() -> int:
    rows = []
    for base in (SCRIPTS, WORKFLOWS):
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix not in {".sh", ".py", ".yml", ".yaml"}:
                continue
            if p.name.startswith("_deploy_surface_inventory"):
                continue
            r = scan_file(p)
            if r:
                rows.append(r)

    occ = sum(r["occurrences"] for r in rows)
    prod = [r for r in rows if r["production_marker"]]
    guarded = [r for r in prod if r["guarded"]]
    unguarded = [r for r in prod if not r["guarded"]]
    nonprod = [r for r in rows if not r["production_marker"]]

    summary = {
        "raw_command_occurrences": occ,
        "unique_files_with_mutations": len(rows),
        "production_capable_files": len(prod),
        "non_production_files": len(nonprod),
        "guarded_files": len(guarded),
        "unguarded_production_files": len(unguarded),
    }
    print(json.dumps({"summary": summary}, indent=2))
    print("\n--- PRODUCTION-CAPABLE, UNGUARDED ---")
    for r in sorted(unguarded, key=lambda x: -x["occurrences"]):
        print(
            f"  {r['file']:<52} occ={r['occurrences']:<3} git={r['git_mutations']} cont={r['container_mutations']}"
        )
    print("\n--- PRODUCTION-CAPABLE, GUARDED ---")
    for r in guarded:
        print(f"  {r['file']}")
    print("\n--- NON-PRODUCTION (no prod marker) ---")
    for r in nonprod:
        print(f"  {r['file']:<52} occ={r['occurrences']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
