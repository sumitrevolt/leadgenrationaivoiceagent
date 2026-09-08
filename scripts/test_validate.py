import sys
import pathlib

# Add workspace scripts to path
workspace = pathlib.Path(r'C:\Users\Ratanshila\.openclaw\workspace')
scripts = workspace / 'scripts'
sys.path.insert(0, str(scripts))

from pathlib import Path
from app.platform import runtime_data_allowlist as _allow
from app.platform import runtime_data_scan as _scan

repo = Path(r'C:\Users\Ratanshila\.openclaw\workspace')
entries = _allow.load()
findings = _scan.scan_repo(repo, allowlist=entries)
problems = _allow.validate(findings=findings)

print(f"Total findings: {len(findings)}")
bad = [f for f in findings if f['classification'] in (_scan.UNDECLARED_MUTABLE_PATH, _scan.AMBIGUOUS_REQUIRES_REVIEW)]
print(f"Bad findings (unddeclared/ambiguous): {len(bad)}")

if problems:
    print("\nProblems:")
    for p in problems:
        print(f"  {p}")
else:
    print("\nNo problems - allowlist is coherent!")

if bad:
    print("\nUndecledared/ambiguous findings (first 30):")
    for f in bad[:30]:
        print(f"  {f['file']}:{f['line']}  {f['operation']} - {f['path_expression'][:80]} - {f['classification']}")