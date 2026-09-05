import sys
sys.path.insert(0, '/app')
from app.marketing.packages import PACKAGES, get_public_packages
for p in PACKAGES:
    print(p['key'], p['name'], p['price_inr_year'])
print('---')
for p in get_public_packages():
    print(p['key'], p['name'], p['price_inr_year'])