from app.platform.prospector import _scraped_reject_reason

result = _scraped_reject_reason('Welworth Realty', '2025530544', '', 'osm', primary_type='', types=(), business_status='')
print(f'Reject reason: "{result}"')

# Also test with the OM Properties entry
result2 = _scraped_reject_reason('OM Properties', '919604048412', '', 'osm', primary_type='', types=(), business_status='')
print(f'Reject reason2: "{result2}"')
