import sys
sys.path.insert(0, '/app')
from app.marketing.packages import PACKAGES, get_public_packages

# Check current packages
print("Current packages:")
for p in PACKAGES:
    print(f"  {p['key']}: {p['name']} - {p['price_inr_month']}/mo")

print("\nPublic packages:")
for p in get_public_packages():
    print(f"  {p['key']}: {p['name']} - {p['price_inr_month']}/mo")