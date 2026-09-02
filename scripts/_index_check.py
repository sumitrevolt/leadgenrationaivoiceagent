import json
import re

h = open("frontend/website/index.html", encoding="utf-8").read()
m = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
print("JSONLD_FOUND", bool(m))
if m:
    try:
        d = json.loads(m.group(1))
        faqs = [x for x in d.get("@graph", []) if x.get("@type") == "FAQPage"]
        nq = len(faqs[0]["mainEntity"]) if faqs else 0
        print("JSON_VALID True | graph_nodes", len(d.get("@graph", [])), "| faq_questions", nq)
    except Exception as e:
        print("JSON_INVALID", e)
print("ENDS_HTML", h.rstrip().endswith("</html>"))
print("last40:", repr(h.rstrip()[-40:]))
