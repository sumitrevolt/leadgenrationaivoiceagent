import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

files = ["frontend/pricing.html", "frontend/automation.html", "frontend/ops.html"]
node = shutil.which("node")
allok = True
for f in files:
    h = open(f, encoding="utf-8").read()
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", h, re.S | re.I)
    # skip external/src-only blocks (empty body)
    bodies = [(attrs, body) for attrs, body in scripts if body.strip()]
    fok = True
    for i, (attrs, b) in enumerate(bodies):
        # JSON-LD is data, not executable JavaScript. Validate it as JSON so a
        # valid schema block does not become a false Node syntax failure.
        if re.search(r"\btype\s*=\s*['\"]application/ld\+json['\"]", attrs, re.I):
            try:
                json.loads(b)
            except json.JSONDecodeError as exc:
                fok = False
                allok = False
                print(f"{f} script#{i} JSON_FAIL: {exc}")
            continue
        if node:
            tf = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
            tf.write(b)
            tf.close()
            r = subprocess.run([node, "--check", tf.name], capture_output=True, text=True)
            os.unlink(tf.name)
            if r.returncode != 0:
                fok = False
                allok = False
                print(
                    f"{f} script#{i} FAIL: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'err'}"
                )
        else:
            # fallback: brace/paren balance
            for op, cl in [("{", "}"), ("(", ")"), ("[", "]")]:
                if b.count(op) != b.count(cl):
                    fok = False
                    allok = False
                    print(f"{f} script#{i} UNBALANCED {op}{cl}: {b.count(op)} vs {b.count(cl)}")
    print(
        f"{f}: {'JS_OK' if fok else 'JS_FAIL'} ({len(bodies)} script blocks, node={'yes' if node else 'no'})"
    )
print("ALL_OK" if allok else "SOME_FAIL")
