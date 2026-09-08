"""QA helper: enumerate every syntactically invalid .py file in a tree.
Read-only (compiles in memory, writes nothing).
Usage: python3 scan_syntax.py <root> [subdir ...]
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
subs = sys.argv[2:] or ["app", "tests"]

bad = []
count = 0
for sub in subs:
    base = root / sub
    if not base.exists():
        continue
    for p in sorted(base.rglob("*.py")):
        count += 1
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        try:
            compile(src, str(p), "exec")
        except SyntaxError as e:
            bad.append((str(p.relative_to(root)), e.lineno, (e.msg or "").strip()))

print("scanned %d .py files under %s" % (count, ", ".join(subs)))
print("BROKEN: %d" % len(bad))
for path, lineno, msg in bad:
    print("  %s:%s  %s" % (path, lineno, msg))
