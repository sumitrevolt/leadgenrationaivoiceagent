"""Duplicate checker — main.py routes + frontend files + key modules"""

import os
import re
from collections import Counter, defaultdict

BASE = r"C:\Users\Ratanshila\Documents\leadgenrationaiagent"


def read(path):
    for enc in ("utf-8", "latin-1"):
        try:
            return open(path, encoding=enc).read()
        except:
            pass
    return ""


# 1. Duplicate route paths in main.py
content = read(rf"{BASE}\app\main.py")

routes = re.findall(r'@app\.(get|post|put|delete)\("([^"]+)"', content)
route_paths = [r[1] for r in routes]
dup_routes = [k for k, v in Counter(route_paths).items() if v > 1]
print("=== DUP ROUTES in main.py ===")
print(dup_routes if dup_routes else "NONE")

# 2. Duplicate function names in main.py
fn_names = re.findall(r"^(?:async )?def (\w+)", content, re.MULTILINE)
dup_fns = [k for k, v in Counter(fn_names).items() if v > 1]
print("\n=== DUP FUNCTION NAMES in main.py ===")
print(dup_fns if dup_fns else "NONE")

# 3. command_center references
cc = re.findall(r".*(command.center|command_center).*", content)
print(f"\n=== command_center lines in main.py ({len(cc)}) ===")
for l in cc:
    print(" ", l.strip())

# 4. Frontend HTML — command* files
fe_dir = rf"{BASE}\frontend"
html_files = os.listdir(fe_dir)
cc_files = [f for f in html_files if "command" in f.lower()]
print(f"\n=== frontend/ command* files ({len(cc_files)}) ===")
for f in sorted(cc_files):
    print(" ", f)

# 5. Duplicate @router paths across app/api/
router_dir = rf"{BASE}\app\api"
all_router_routes = []
for fname in os.listdir(router_dir):
    if not fname.endswith(".py"):
        continue
    txt = read(os.path.join(router_dir, fname))
    for method, path in re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"', txt):
        all_router_routes.append((fname, method, path))

path_map = defaultdict(list)
for fname, method, path in all_router_routes:
    path_map[(method, path)].append(fname)
dup_api = {k: v for k, v in path_map.items() if len(v) > 1}
print("\n=== DUP API ROUTES across app/api/ ===")
if dup_api:
    for (m, p), files in dup_api.items():
        print(f"  {m.upper()} {p}  ->  {files}")
else:
    print("NONE")

print(
    f"\nTotal: main.py={len(routes)}, routers={len(all_router_routes)}, sum={len(routes) + len(all_router_routes)}"
)
print("DONE")
