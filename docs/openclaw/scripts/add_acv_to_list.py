import sys
sys.path.insert(0, '/app')
# Read the file
with open('/app/app/marketing/packages.py', 'r') as f:
    content = f.read()

# Find the PACKAGES list closing and add acv_annual to it
# The list ends with "    },] " before the blank line and ACV_ANNUAL_BUNDLE definition
old = '''        "badge": "ADVANCED",
    },
]

# ACV Annual Bundle Package'''

new = '''        "badge": "ADVANCED",
    },
    ACV_ANNUAL_BUNDLE,
]

# ACV Annual Bundle Package'''

if old in content:
    content = content.replace(old, new)
    with open('/app/app/marketing/packages.py', 'w') as f:
        f.write(content)
    print("Added ACV_ANNUAL_BUNDLE to PACKAGES list")
else:
    print("ERROR: Could not find pattern")
    sys.exit(1)