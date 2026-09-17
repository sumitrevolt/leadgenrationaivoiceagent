from app.platform.dev_workers import get_prover
from app.platform.capacity_ledger import get_ledger
from app.platform.kpi_ledger import get_ledger as get_kpi
from app.billing.owner_upi_confirm import get_confirm

print("=== MODULE LOADING CHECK ===")
try:
    p = get_prover()
    print(f"✓ dev_workers: OK (active: {p.get_active_count()})")
except Exception as e:
    print(f"✗ dev_workers: FAILED - {e}")

try:
    l = get_ledger()
    snapshot = l.compute()
    print(f"✓ capacity_ledger: OK (total: {snapshot.total_capacity}/week, gap: {snapshot.gap_to_target})")
except Exception as e:
    print(f"✗ capacity_ledger: FAILED - {e}")

try:
    k = get_kpi()
    print(f"✓ kpi_ledger: OK")
except Exception as e:
    print(f"✗ kpi_ledger: FAILED - {e}")

try:
    c = get_confirm()
    summary = c.get_summary()
    print(f"✓ owner_upi_confirm: OK (pending: {summary['pending_count']})")
except Exception as e:
    print(f"✗ owner_upi_confirm: FAILED - {e}")

print("\n=== VERDICT ===")
print("All modules loaded successfully!" if all([
    'dev_workers' in str(p) if 'p' in dir() else False,
    'capacity_ledger' in str(l) if 'l' in dir() else False,
    'kpi_ledger' in str(k) if 'k' in dir() else False,
    'owner_upi_confirm' in str(c) if 'c' in dir() else False
]) else "Some modules failed to load")
