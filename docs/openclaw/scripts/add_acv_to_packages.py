import sys
sys.path.insert(0, '/app')
from app.marketing.packages import PACKAGES, ACV_ANNUAL_BUNDLE

# Add ACV bundle to PACKAGES list
PACKAGES.append(ACV_ANNUAL_BUNDLE)

# Verify
print('All packages after adding ACV:')
for p in PACKAGES:
    print(f'  {p["key"]}: {p["name"]} - {p["price_inr_year"]}/yr')

# Also add to public packages (get_public_packages filters by p.get("public", True))
# Need to set public=True on ACV_ANNUAL_BUNDLE
ACV_ANNUAL_BUNDLE['public'] = True
print('\nPublic packages after:')
from app.marketing.packages import get_public_packages
for p in get_public_packages():
    print(f'  {p["key"]}: {p["name"]} - {p["price_inr_year"]}/yr')