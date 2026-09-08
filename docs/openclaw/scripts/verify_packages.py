#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from app.marketing.packages import PACKAGES, get_public_packages
print("PACKAGES:")
for p in PACKAGES:
    print(f"  {p['key']}: {p['name']} - {p['price_inr_year']}/yr")
print("\nPublic:")
for p in get_public_packages():
    print(f"  {p['key']}: {p['name']} - {p['price_inr_year']}/yr")
print("\nACV_ANNUAL_BUNDLE in PACKAGES:", any(p.get('key') == 'acv_annual' for p in PACKAGES))