import sys
sys.path.insert(0, '/app')
from app.marketing.packages import PACKAGES, get_public_packages, ACV_ANNUAL_BUNDLE
print('ACV Bundle:', ACV_ANNUAL_BUNDLE['key'], ACV_ANNUAL_BUNDLE['price_inr_year'])
print('All packages:')
for p in PACKAGES:
    print(f'  {p["key"]}: {p["name"]} - {p["price_inr_year"]}/yr')