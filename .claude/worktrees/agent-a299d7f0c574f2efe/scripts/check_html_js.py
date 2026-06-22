"""Extract inline <script> (non-src) from an HTML file and `node --check` it.
Usage: python scripts/check_html_js.py frontend/analytics.html"""
import os
import re
import subprocess
import sys
import tempfile

path = sys.argv[1] if len(sys.argv) > 1 else "frontend/analytics.html"
html = open(path, encoding="utf-8").read()
scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)
js = "\n;\n".join(scripts)
if not js.strip():
    print(f"{path}: NO_INLINE_JS")
    sys.exit(0)
tf = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
tf.write(js)
tf.close()
try:
    r = subprocess.run(["node", "--check", tf.name], capture_output=True, text=True)
finally:
    os.unlink(tf.name)
if r.returncode == 0:
    print(f"{path}: JS_OK")
else:
    print(f"{path}: JS_ERROR\n" + (r.stderr or "")[-800:])
    sys.exit(1)
