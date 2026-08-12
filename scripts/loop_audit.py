"""Full audit: incomplete loops, stubs, missing wiring across backend"""

import os
import re
from pathlib import Path

BASE = Path(r"C:\Users\Ratanshila\Documents\leadgenrationaiagent")
SEARCH_DIRS = [
    "app/api",
    "app/platform",
    "app/marketing",
    "app/billing",
    "app/voice_agent",
    "app/telephony",
    "app/agents",
]
PATTERNS = [
    ("TODO/FIXME", r"#\s*(TODO|FIXME|HACK|XXX|PLACEHOLDER|STUB)[^\n]*"),
    ("return {}", r"return \{\}"),
    ("pass stub", r"^\s+pass\s*$"),
    ("NotImplemented", r"raise NotImplementedError"),
    ("fake/mock data", r"#.*(fake|mock|dummy|hardcoded|sample data)"),
    ("print stub", r"^\s+print\("),
]

results = {}
for d in SEARCH_DIRS:
    p = BASE / d
    if not p.exists():
        continue
    for f in sorted(p.glob("*.py")):
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits = []
        for label, pat in PATTERNS:
            for m in re.finditer(pat, src, re.MULTILINE):
                line_no = src[: m.start()].count("\n") + 1
                hits.append((line_no, label, m.group()[:90].strip()))
        if hits:
            results[str(f.relative_to(BASE))] = hits

for fname, hits in sorted(results.items()):
    print(f"\n--- {fname} ---")
    for ln, label, text in hits[:10]:
        print(f"  L{ln} [{label}] {text}")

print("\n\n=== SUMMARY ===")
total = sum(len(v) for v in results.values())
print(f"Files with issues: {len(results)}, Total hits: {total}")
