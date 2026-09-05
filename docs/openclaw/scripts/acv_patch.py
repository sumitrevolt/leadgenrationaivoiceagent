import re

with open('/app/app/marketing/packages.py', 'r') as f:
    content = f.read()

# Add ACV_ANNUAL_BUNDLE definition after the Advanced package, before get_packages
acv_def = '''

# ACV Annual Bundle Package - Option 1: \u20b914,999/year
# Added 2026-09-02 per owner decision
ACV_ANNUAL_BUNDLE = {
    "key": "acv_annual",
    "name": "AI Marketing Annual Bundle",
    "tagline": "Full AI Marketing Automation + Voice Callback \u2014 annual prepaid, 2 months FREE",
    "price_inr_month": 1250,
    "price_inr_year": 14999,
    "annual_note": "Saal bhar ka ek saath: \u20b914,999 (2 mahine FREE vs monthly)",
    "price_note": "Starter marketing (\u20b91,999/mo) + Voice callback (500 min/mo) = \u20b914,999/yr",
    "marketing_only": False,
    "features": [
        "AI Marketing Automation (Starter plan) \u2014 content, leads, reviews, CRM, mini-site, GBP, sab",
        "AI Inquiry Callback FEATURE \u2014 website/GBP inquiry ko ~2-min me AI call (Hindi awaaz)",
        "500 calling minutes/month included \u2014 top-up packs available",
        "Lead qualification \u2014 budget, timeline, interest score AI capture karta hai",
        "Appointment booking \u2014 AI calendar slots offer + confirm karta hai",
        "Weekly 50 follow-up calls \u2014 purani leads garam rakho",
        "Sab call transcripts + AI summary dashboard me",
        "TRAI-compliant AI disclosure greeting har call pe",
        "Annual billing \u2014 2 mahine FREE vs monthly (\u20b914,999 vs \u20b923,988)",
        "Priority support + strategy calls included",
    ],
    "highlight": True,
    "badge": "BEST VALUE",
    "public": True,
}
'''

# Insert ACV_ANNUAL_BUNDLE before the get_packages function definition
content = content.replace(
    'def get_packages(include_trial: bool = False) -> list:',
    acv_def + 'def get_packages(include_trial: bool = False) -> list:'
)

# Also add ACV_ANNUAL_BUNDLE to the PACKAGES list after the advanced package
acv_to_packages = ''',
    ACV_ANNUAL_BUNDLE,
]

# ACV Annual Bundle Package'''

# Find the closing of PACKAGES list and the get_packages function
# The pattern is: after the Advanced package's closing "},]," then blank line then def get_packages
old_pattern = '''        "badge": "ADVANCED",
    },
]


def get_packages'''

new_pattern = '''        "badge": "ADVANCED",
    },
    ACV_ANNUAL_BUNDLE,
]


def get_packages'''

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print("Added ACV_ANNUAL_BUNDLE to PACKAGES list")
else:
    print("ERROR: Could not find pattern for PACKAGES")
    # Debug: print last 50 chars before def get_packages
    idx = content.find('def get_packages')
    print(f"Found def get_packages at index {idx}")
    print(f"Context: {repr(content[idx-200:idx])}")

with open('/app/app/marketing/packages.py', 'w') as f:
    f.write(content)

print("Done writing!")