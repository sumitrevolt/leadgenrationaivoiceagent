#!/usr/bin/env python3
"""Add ACV Annual Bundle to packages.py"""
import sys

with open('/opt/leadgen/app/marketing/packages.py', 'r') as f:
    content = f.read()

# Find the line after the closing brace of PACKAGES list
# The line is: "]" followed by blank line then "def get_packages"
# We need to insert the ACV bundle definition before the blank line before def get_packages

acv_bundle = '''
# ACV Annual Bundle Package - Option 1: ₹14,999/year
# Added 2026-09-02 per owner decision
ACV_ANNUAL_BUNDLE = {
    "key": "acv_annual",
    "name": "AI Marketing Annual Bundle",
    "tagline": "Full AI Marketing Automation + Voice Callback \u2014 annual prepaid, 2 months FREE",
    "price_inr_month": 1250,  # Effective monthly (₹14,999/12)
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
}
'''

# Find the insertion point: right before "def get_packages"
insert_marker = '\n\ndef get_packages'
if insert_marker in content:
    content = content.replace(insert_marker, acv_bundle + insert_marker)
    print("ACV bundle added before get_packages")
else:
    print("ERROR: Could not find insertion marker")
    sys.exit(1)

with open('/opt/leadgen/app/marketing/packages.py', 'w') as f:
    f.write(content)

print("Done!")