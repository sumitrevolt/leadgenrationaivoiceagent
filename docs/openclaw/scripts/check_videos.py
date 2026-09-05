import os

search_terms = ['video', 'post', 'social', 'wahta', 'instagram', 'meta', 'canvas']
workspace = r"C:\Users\Ratanshila\.openclaw\workspace"

count = 0
for root, dirs, files in os.walk(workspace):
    skip = {'.venv', '.git', 'node_modules', '.claude', '.memory', '.cursor', '.freebuff', 'analytics', 'evals', 'tests', 'skills', 'scripts', 'config', 'deploy', 'knowledge', 'infrastructure', 'agent-os', 'unity', '.pytest-override'}
    dirs[:] = [d for d in dirs if d not in skip]
    for f in files:
        if any(term in f.lower() for term in search_terms):
            path = os.path.join(root, f)
            print(path)
            count += 1

print(f"\nTotal files found: {count}")