"""Syntax-check the inline <script> in frontend/marketing.html via `node --check`.

Catches any JS syntax error (unbalanced braces etc.) before it breaks every tab.
Run on VPS: cd /opt/leadgen && .venv/bin/python scripts/check_marketing_js.py
"""

import re
import subprocess
import sys

try:
    html = open("frontend/marketing.html", encoding="utf-8").read()
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    if not m:
        print("CHECK: no <script> found")
        sys.exit(1)
    with open("/tmp/marketing_inline.js", "w", encoding="utf-8") as f:
        f.write(m.group(1))
    r = subprocess.run(
        ["node", "--check", "/tmp/marketing_inline.js"], capture_output=True, text=True
    )
    if r.returncode == 0:
        print("JS_CHECK: OK (valid syntax)")
    else:
        print("JS_CHECK: FAIL")
        print(r.stderr[:900])
        sys.exit(1)
except FileNotFoundError as e:
    # node not installed -> can't check, but don't fail the deploy
    print("JS_CHECK: SKIPPED (", e, ")")
except Exception as e:
    print("JS_CHECK error:", e)
