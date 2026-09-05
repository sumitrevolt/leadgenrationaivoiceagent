import sys

with open('/opt/leadgen/app/marketing/packages.py', 'r') as f:
    lines = f.readlines()

# Find the line "def get_packages(include_trial: bool = False) -> list:"
# and insert ACV_ANNUAL_BUNDLE definition before it

acv_bundle_lines = [
    '\n',
    '# ACV Annual Bundle Package - Option 1: \u20b914,999/year\n',
    '# Added 2026-09-02 per owner decision\n',
    'ACV_ANNUAL_BUNDLE = {\n',
    '    "key": "acv_annual",\n',
    '    "name": "AI Marketing Annual Bundle",\n',
    '    "tagline": "Full AI Marketing Automation + Voice Callback \u2014 annual prepaid, 2 months FREE",\n',
    '    "price_inr_month": 1250,\n',
    '    "price_inr_year": 14999,\n',
    '    "annual_note": "Saal bhar ka ek saath: \u20b914,999 (2 mahine FREE vs monthly)",\n',
    '    "price_note": "Starter marketing (\u20b91,999/mo) + Voice callback (500 min/mo) = \u20b914,999/yr",\n',
    '    "marketing_only": False,\n',
    '    "features": [\n',
    '        "AI Marketing Automation (Starter plan) \u2014 content, leads, reviews, CRM, mini-site, GBP, sab",\n',
    '        "AI Inquiry Callback FEATURE \u2014 website/GBP inquiry ko ~2-min me AI call (Hindi awaaz)",\n',
    '        "500 calling minutes/month included \u2014 top-up packs available",\n',
    '        "Lead qualification \u2014 budget, timeline, interest score AI capture karta hai",\n',
    '        "Appointment booking \u2014 AI calendar slots offer + confirm karta hai",\n',
    '        "Weekly 50 follow-up calls \u2014 purani leads garam rakho",\n',
    '        "Sab call transcripts + AI summary dashboard me",\n',
    '        "TRAI-compliant AI disclosure greeting har call pe",\n',
    '        "Annual billing \u2014 2 mahine FREE vs monthly (\u20b914,999 vs \u20b923,988)",\n',
    '        "Priority support + strategy calls included",\n',
    '    ],\n',
    '    "highlight": True,\n',
    '    "badge": "BEST VALUE",\n',
    '    "public": True,\n',
    '}\n',
    '\n',
]

# Find the line with "def get_packages"
insert_idx = None
for i, line in enumerate(lines):
    if 'def get_packages(include_trial: bool = False) -> list:' in line:
        insert_idx = i
        break

if insert_idx is None:
    print("ERROR: Could not find insertion point")
    sys.exit(1)

# Insert the ACV bundle definition
new_lines = lines[:insert_idx] + acv_bundle_lines + lines[insert_idx:]

# Now also add ACV_ANNUAL_BUNDLE to the PACKAGES list
# Find the closing of PACKAGES list
packages_end_idx = None
for i, line in enumerate(new_lines):
    if '        "badge": "ADVANCED",' in line:
        # The next non-empty, non-indented line should be the closing
        for j in range(i+1, len(new_lines)):
            if new_lines[j].strip() == '},':
                # Check if next line is ']' or contains 'ACV_ANNUAL_BUNDLE'
                if j+1 < len(new_lines) and ']' in new_lines[j+1]:
                    packages_end_idx = j
                    break
                break
        break

if packages_end_idx:
    # Insert ACV_ANNUAL_BUNDLE before the closing
    new_lines.insert(packages_end_idx + 1, '    ACV_ANNUAL_BUNDLE,\n')
    print(f"Added ACV_ANNUAL_BUNDLE to PACKAGES list at line {packages_end_idx + 2}")
else:
    print("ERROR: Could not find PACKAGES list end")
    sys.exit(1)

with open('/opt/leadgen/app/marketing/packages.py', 'w') as f:
    f.writelines(new_lines)

print("Done!")