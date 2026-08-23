"""Live self-test of all new features (real env). Run on VPS:
   cd /opt/leadgen && .venv/bin/python scripts/test_features.py
Tests the actual module functions (LLM calls real), HTTP endpoint reachability,
the Pollinations image, and prints a problems summary.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

for _p in ("/opt/leadgen/.env", ".env"):
    if os.path.exists(_p):
        for _ln in open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if _ln and not _ln.startswith("#") and "=" in _ln:
                _k, _v = _ln.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        break
sys.path.insert(0, os.getcwd())

results = []


def rec(name, ok, info=""):
    results.append((name, ok, info))
    print(("PASS " if ok else "FAIL ") + name + " | " + str(info)[:140])


async def main():
    try:
        from app.marketing import post_generator

        p = await post_generator.generate_post("Test Cafe", "restaurant_cafe", offer="20% off")
        rec(
            "generate_post",
            bool(p.get("caption")),
            f"provider={p.get('provider')} cap={len(p.get('caption', ''))}ch tags={len(p.get('hashtags', []))} img={'image_url' in p}",
        )
    except Exception as e:
        rec("generate_post", False, repr(e))

    try:
        from app.marketing import ai_image

        img = await ai_image.marketing_image(
            "Test Cafe", "restaurant_cafe", occasion="Diwali", offer="20% off"
        )
        rec(
            "ai_image",
            img.get("url", "").startswith("http"),
            f"prompt='{img.get('prompt', '')[:60]}'",
        )
        rec(
            "logo",
            ai_image.logo_url("Test Cafe", "restaurant_cafe").startswith("http"),
            "url built",
        )
    except Exception as e:
        rec("ai_image", False, repr(e))

    try:
        from app.marketing import post_generator

        vs = await asyncio.gather(
            *[post_generator.generate_post("Test Cafe", "restaurant_cafe") for _ in range(2)]
        )
        rec(
            "variations",
            all(v.get("caption") for v in vs),
            f"{len(vs)} variants, providers={[v.get('provider') for v in vs]}",
        )
    except Exception as e:
        rec("variations", False, repr(e))

    try:
        from app.marketing import chatbot

        r = await chatbot.reply("aapke yahan home delivery hai?", "", "restaurant_cafe")
        rec(
            "chatbot",
            bool(r.get("answer")),
            f"ask_contact={r.get('ask_contact')} sources={r.get('sources')} ans='{r.get('answer', '')[:60]}'",
        )
    except Exception as e:
        rec("chatbot", False, repr(e))

    try:
        from app.marketing import sentiment

        s = await sentiment.analyze(
            ["bahut accha service tha", "delivery slow thi", "staff helpful hai"]
        )
        rec(
            "sentiment",
            s.get("count") == 3,
            f"breakdown={s.get('breakdown')} score={s.get('score')} summary={bool(s.get('summary'))}",
        )
    except Exception as e:
        rec("sentiment", False, repr(e))

    try:
        from app.marketing import hashtags

        h = await hashtags.research("salon_spa", "Pune", 12)
        rec(
            "hashtags",
            len(h.get("hashtags", [])) > 0,
            f"{len(h.get('hashtags', []))} tags, {len(h.get('best_times', []))} times",
        )
    except Exception as e:
        rec("hashtags", False, repr(e))

    try:
        from app.platform import ops_watchdog

        w = await ops_watchdog.run_watchdog()
        rec(
            "ops_watchdog",
            ("ok" in w) or ("skipped" in w),
            f"ok={w.get('ok')} issues={[i.get('key') for i in w.get('issues', [])]}",
        )
    except Exception as e:
        rec("ops_watchdog", False, repr(e))

    try:
        from app.marketing import onboarding

        o = await onboarding.run_onboarding_sweep(limit=1)
        rec("onboarding", isinstance(o, dict), json.dumps(o)[:120])
    except Exception as e:
        rec("onboarding", False, repr(e))

    try:
        from app.platform import setup_status

        a = setup_status.audit()
        rec("setup_status", "summary" in a, json.dumps(a["summary"]))
    except Exception as e:
        rec("setup_status", False, repr(e))


asyncio.run(main())

# HTTP endpoint reachability (no auth -> 401/403 = registered+gated; 404 = missing; 500 = bug)
print("\n=== HTTP endpoints (no auth; expect 401/403) ===")


def http_post(path, body):
    req = urllib.request.Request(
        "http://127.0.0.1:8000" + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "selftest"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return repr(e)


for ep in [
    "/api/marketing/ai-image",
    "/api/marketing/complete-post",
    "/api/marketing/post-variations",
    "/api/marketing/chatbot",
    "/api/marketing/sentiment",
    "/api/marketing/hashtags",
    "/api/marketing/brand-logo",
]:
    print(f"  {ep} -> {http_post(ep, {})}")

# Pollinations actually returns an image?
print("\n=== Pollinations image ===")
try:
    from app.marketing import ai_image

    u = ai_image.image_url("test marketing poster, vibrant", 256, 256)
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        ctype = r.headers.get("Content-Type", "")
        body = r.read(2048)
        print(f"  HTTP {r.status} | {ctype} | bytes>={len(body)} | is_image={'image' in ctype}")
except Exception as e:
    print("  Pollinations FAIL:", repr(e))

print("\n=== SUMMARY ===")
print(f"{sum(1 for _, ok, _ in results if ok)}/{len(results)} module tests passed")
probs = [(n, i) for n, ok, i in results if not ok]
if probs:
    print("PROBLEMS:")
    for n, i in probs:
        print(f"  - {n}: {i}")
else:
    print("No module-level failures.")
