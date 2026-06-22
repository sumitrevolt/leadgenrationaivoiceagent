import subprocess, sys

cmds = [
    "cd /opt/leadgen",
    "git stash",
    "git clean -fd frontend/explorer.html",
    "git pull origin main",
    "docker compose -f docker-compose.vps.yml build app 2>&1 | tail -8",
    "docker compose -f docker-compose.vps.yml up -d --no-deps app",
    "sleep 18",
    "curl -s https://leadsgenai.in/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('HEALTH:', d.get('environment'), d.get('status'))\"",
]
full = " && ".join(cmds)
result = subprocess.run(full, shell=True, capture_output=True, text=True)
print(result.stdout[-3000:] if result.stdout else "")
print(result.stderr[-1000:] if result.stderr else "")
