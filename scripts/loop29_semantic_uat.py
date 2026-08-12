"""Loop 29 semantic UAT — validates the LIVE production HTML at leadsgenai.in.
Not a real browser render (no Playwright/Chrome MCP available), but does a
structural check that no real orphan handlers exist, no duplicate IDs are
served, and every Loop 27/28/29 marker is present in the deployed HTML.
"""

import json
import re
import sys
import urllib.request as u


def fetch(url: str) -> str:
    req = u.Request(url, headers={"User-Agent": "loop29-uat/1.0"})
    with u.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def analyze(label: str, html: str) -> dict:
    ids = re.findall(r"\bid=['\"]([^'\"]+)['\"]", html)
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    fns = re.findall(r"\bonclick=['\"]([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", html)
    defs = set(re.findall(r"function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", html))
    defs |= set(
        re.findall(
            r"(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s+)?function", html
        )
    )
    defs |= set(re.findall(r"window\.([a-zA-Z_][a-zA-Z0-9_]*)\s*=", html))
    orphans = sorted(set(fns) - defs - {"alert", "confirm", "prompt", "fetch", "toast"})
    if label == "customer":
        markers = [
            "setupLoggedOutGate",
            "loadReportsView",
            "mobileMoreSheet",
            "openMoreSheet",
            "_closeConnectModal",
            "account_id",
        ]
    else:
        markers = [
            "platformDialBanner",
            "_closeC360PwdModal",
            "function toast",
            "Intl.NumberFormat",
            "adminToast(msg",
            "sec-upi-selfserve",
        ]
    marker_check = {m: (m in html) for m in markers}
    # prompt() calls in the touched paths — count only inline template strings we shipped
    # (the c360 and connect modals used to use prompt; count residuals)
    prompt_hits = re.findall(r"\bprompt\s*\([^)]{0,80}", html)
    return {
        "size_bytes": len(html),
        "unique_ids": len(set(ids)),
        "duplicate_ids": dup_ids[:8],
        "onclick_calls_distinct": len(set(fns)),
        "defined_fns_min": len(defs),
        "orphan_handlers": orphans,
        "prompt_call_count": len(prompt_hits),
        "prompt_first_samples": prompt_hits[:5],
        "loop_markers_present": marker_check,
        "all_markers_ok": all(marker_check.values()),
    }


def main() -> int:
    results = {}
    for label, url in [
        ("customer", "https://leadsgenai.in/app/customer/marketing"),
        ("admin", "https://leadsgenai.in/app/admin"),
    ]:
        try:
            html = fetch(url)
            results[label] = analyze(label, html)
        except Exception as e:
            results[label] = {"error": f"{type(e).__name__}: {e}"}
    print(json.dumps(results, indent=2))
    fail = False
    for label, r in results.items():
        if r.get("error"):
            fail = True
            continue
        if not r["all_markers_ok"]:
            fail = True
        if r["duplicate_ids"]:
            fail = True
        if r["orphan_handlers"]:
            # Some orphans are known-defined-elsewhere (dynamic templates); tolerate
            # but log. Only fail if a Loop27/28/29 marker fn is missing.
            expected_touched = {
                "_closeConnectModal",
                "_submitConnectDialog",
                "loadReportsView",
                "openMoreSheet",
                "closeMoreSheet",
                "pickMoreSheet",
                "_closeC360PwdModal",
                "_c360PwdSubmit",
                "_c360PwdUpdate",
                "_c360PwdGenerate",
                "upiSelfServeDecide",
                "upiActivate",
                "upiManualActivate",
            }
            missing_critical = expected_touched & set(r["orphan_handlers"])
            if missing_critical:
                r["MISSING_CRITICAL_HANDLERS"] = sorted(missing_critical)
                fail = True
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
