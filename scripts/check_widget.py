"""Verify embeddable lead-capture widget: pure funcs + live routes (TestClient)."""

import os
import sys

for _p in ("/opt/leadgen/.env", ".env"):
    if os.path.exists(_p):
        for _ln in open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if _ln and not _ln.startswith("#") and "=" in _ln:
                _k, _v = _ln.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        break
sys.path.insert(0, os.getcwd())

from app.marketing import embed_widget  # noqa: E402

fake = {"business_name": "Sharma Dental", "slug": "sharma-dental", "brand_color": "#0a7a55"}
pg = embed_widget.embed_page_html(fake)
print(
    "embed_page_html len:",
    len(pg),
    "| posts_inquiry:",
    "/api/public/inquiry" in pg,
    "| has_phone:",
    'name="phone"' in pg,
    "| source_slug:",
    "sharma-dental" in pg,
)
js = embed_widget.widget_js("sharma-dental")
print(
    "widget_js len:",
    len(js),
    "| has_embed_url:",
    "/b/sharma-dental/embed" in js,
    "| has_btn:",
    "lgai-btn" in js,
)
print("snippet:", embed_widget.snippet("sharma-dental"))

try:
    import app.marketing.clients_store as CS

    slug = None
    for fn in ("list_clients", "all_clients", "get_all", "list_all", "load_all", "all"):
        f = getattr(CS, fn, None)
        if callable(f):
            try:
                rows = f() or []
                if rows:
                    slug = str((rows[0] or {}).get("slug") or "") or None
                if slug:
                    break
            except Exception:
                pass
    print("sample real client slug:", slug)

    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    ts = slug or "sharma-dental"
    r = c.get("/b/%s/widget.js" % ts)
    print(
        "GET widget.js ->",
        r.status_code,
        "|",
        (r.headers.get("content-type", "")[:30]),
        "| len",
        len(r.text),
    )
    r2 = c.get("/b/%s/embed" % ts, follow_redirects=False)
    print("GET embed ->", r2.status_code, "| has_form:", "/api/public/inquiry" in (r2.text or ""))
except Exception as e:
    print("route test skipped:", e)
