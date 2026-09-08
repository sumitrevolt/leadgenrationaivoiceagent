import re

with open('/opt/leadgen/docker-compose.vps.yml', 'r') as f:
    content = f.read()

# Fix the DSH_ALLOWLIST_CSV lines - they should have ${DSH_ALLOWLIST_CSV:-}
content = content.replace(
    '      DSH_ALLOWLIST_CSV: \n',
    '      DSH_ALLOWLIST_CSV: ${DSH_ALLOWLIST_CSV:-}\n'
)
content = content.replace(
    '      DSH_ALLOWLIST_CSV: \n',
    '      DSH_ALLOWLIST_CSV: ${DSH_ALLOWLIST_CSV:-}\n'
)

with open('/opt/leadgen/docker-compose.vps.yml', 'w') as f:
    f.write(content)

print("Fixed docker-compose.vps.yml")