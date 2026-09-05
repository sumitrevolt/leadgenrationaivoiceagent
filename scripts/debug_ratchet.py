"""Debug runtime-data path scan to find 12 new entries needing allowlist."""
import sys
sys.path.insert(0, r'.')
from pathlib import Path
from app.platform import runtime_data_allowlist as _allow
from app.platform import runtime_data_scan as _scan
from app.platform import runtime_data_ratchet as _ratchet

repo = Path(r'C:\Users\Ratanshila\.openclaw\workspace')
entries = _allow.load()
findings = _scan.scan_repo(repo, allowlist=entries)
problems = _allow.validate(findings=findings)

print(f'Total findings: {len(findings)}')
bad = [f for f in findings if f['classification'] in (_scan.UNDECLARED_MUTABLE_PATH, _scan.AMBIGUOUS_REQUIRES_REVIEW)]
print(f'Bad findings (unddeclared/ambiguous): {len(bad)}')

# Run ratchet to see new unresolved
verdict = _ratchet.evaluate(findings)
print(f'\nRatchet verdict:')
print(f'  unresolved now: {verdict["unresolved_now"]}')
print(f'  newly unresolved: {len(verdict["new_unresolved"])}')
print(f'  resolved since baseline: {len(verdict["resolved"])}')
print(f'  removed since baseline: {len(verdict["removed"])}')

if verdict["new_unresolved"]:
    print(f'\nNewly unresolved findings:')
    for f in verdict["new_unresolved"]:
        print(f'  {f["file"]}:{f["line"]}  {f["operation"]} - {f["path_expression"][:80]} - {f["classification"]}')

# Also check what the validate produces
if problems:
    print(f'\nValidation problems ({len(problems)}):')
    for p in problems:
        print(f'  {p}')