"""Wizard opening → auto-callback greeting chain — LIVE verification (dry-run).

Deploy ke baad poora chain prove karta hai BINA real call lagaye:

  POST /api/public/inquiry?dry_run=1  (business_type + niche + business_name + phone)
    → run_after_inquiry → _wizard_opening_for → _auto_callback(dry_run=True)
    → start_stream_call(dry_run=True) → Redis pending `vobiz:pending:<token>`
      (opening_line stored) + answer-stream URL (opening_line qs) — Vobiz dial SKIPPED.

Checks:
  A. Inquiry POST → ok:true (chain trigger live)
  B. Redis pending → token found (lead_phone match) + opening_line = wizard opening
     containing business_name (wizard path proven, generic fallback nahi)
  C. answer-stream XML → ws_url me opening_line qs (session override reach)

Usage:
    python scripts/verify_opening_chain.py
    python scripts/verify_opening_chain.py --url https://leadsgenai.in --phone +919999999903
    python scripts/verify_opening_chain.py --redis-cmd "docker exec leadgen_redis redis-cli"
    python scripts/verify_opening_chain.py --business-type "Restaurant / Cafe" --niche restaurant_cafe --business-name "Arm Smoke Cafe"

Exit code 0 = chain verified · 1 = problem (missing/blocked) · 2 = warning.
Disposable number pe chalana (lead row append-only ledger me banta hai — expected).
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Windows cp1252 console pe unicode crash karta hai — ASCII-only output.
_OK = "[ok]"
_WARN = "[warn]"
_ERR = "[!!]"


def _http_json(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    """Minimal HTTP helper — urllib (stdlib, koi dep nahi)."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 — fixed https URL
            body = resp.read().decode("utf-8", errors="ignore")
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}


def _redis_client(args):
    """--redis-python mode: venv ke redis package se direct (local dev, no docker)."""
    import os

    import redis

    return redis.from_url(
        os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True
    )


def _redis(args) -> list[str] | None:
    """Scan pending stream keys (redis-cli command ya in-process python)."""
    if args.redis_python:
        try:
            keys = _redis_client(args).keys("vobiz:pending:*")
            return [str(k) for k in keys]
        except Exception as e:
            print(f"{_ERR} redis python scan failed: {e}")
            return None
    cmd = shlex.split(args.redis_cmd) + ["--scan", "--pattern", "vobiz:pending:*"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f"{_ERR} redis-cli run failed: {e}")
        return None
    if out.returncode != 0:
        print(f"{_ERR} redis-cli scan failed (rc={out.returncode}): {out.stderr.strip()[:200]}")
        return None
    keys = [k.strip() for k in out.stdout.splitlines() if k.strip()]
    if not keys:
        return []
    return keys


def _redis_get(args, key: str) -> dict | None:
    if args.redis_python:
        try:
            raw = _redis_client(args).get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None
    cmd = shlex.split(args.redis_cmd) + ["GET", key]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return json.loads(out.stdout)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Wizard opening chain dry-run verification")
    ap.add_argument("--url", default="http://127.0.0.1:8000", help="app base URL (default local)")
    ap.add_argument("--phone", default="+919999999903", help="disposable test number")
    ap.add_argument(
        "--business-type", default="Salon / Beauty Parlour", help="wizard business type label"
    )
    ap.add_argument("--niche", default="salon_spa", help="wizard niche key")
    ap.add_argument(
        "--business-name", default="Arm Smoke Salon", help="business_name (personalization proof)"
    )
    ap.add_argument(
        "--redis-cmd",
        default="docker exec leadgen_redis redis-cli",
        help="redis-cli access (VPS default)",
    )
    ap.add_argument(
        "--redis-python",
        action="store_true",
        help="in-process redis package (local dev, no docker)",
    )
    ap.add_argument(
        "--timeout", type=int, default=12, help="seconds to poll pending (bg task race)"
    )
    args = ap.parse_args()

    url = args.url.rstrip("/")
    problems: list[str] = []
    print(f"verify_opening_chain -- dry-run ({args.phone} / {args.business_type})")
    redis_note = "python (local)" if args.redis_python else " ".join(args.redis_cmd.split()[:2])
    print(f"  base URL: {url} | redis: {redis_note}")

    # A) Inquiry POST (dry_run=1 → auto-callback chain trigger, dial skipped)
    qs = urllib.parse.urlencode({"dry_run": "1"})
    code, body = _http_json(
        f"{url}/api/public/inquiry?{qs}",
        method="POST",
        payload={
            "name": "Opening Chain Smoke",
            "phone": args.phone,
            "business_name": args.business_name,
            "business_type": args.business_type,
            "niche": args.niche,
            "source": "opening_chain_smoke",
        },
    )
    if code != 200 or not body.get("ok"):
        problems.append(
            f"inquiry POST failed: HTTP {code} — {json.dumps(body, ensure_ascii=False)[:300]}"
        )
        print(f"{_ERR} A) inquiry POST → HTTP {code} {json.dumps(body, ensure_ascii=False)[:200]}")
    else:
        print(f"{_OK} A) inquiry POST ok (dry_run=1) — chain trigger live")

    # B) Redis pending → token + wizard opening_line (bg task race — poll)
    token: str | None = None
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        keys = _redis(args)
        if keys:
            for k in keys:
                rec = _redis_get(args, k)
                if (
                    rec
                    and str(rec.get("lead_phone") or "") == args.phone
                    and rec.get("opening_line")
                ):
                    token = k.rsplit(":", 1)[-1]
                    pending = rec
                    break
            if token:
                break
        time.sleep(0.5)
    if not token:
        problems.append(
            "pending entry not found — chain didn't reach start_stream_call (AUTO_CALLBACK_INQUIRY=0?)"
        )
        print(
            f"{_ERR} B) redis pending `vobiz:pending:*` me phone match nahi mila ({args.timeout}s) — check AUTO_CALLBACK_INQUIRY"
        )
    else:
        opening = str(pending.get("opening_line") or "")
        print(f"{_OK} B) pending found (token {token[:10]}…) opening_line = {opening[:120]}")
        if args.business_name not in opening:
            problems.append(
                "opening_line wizard-personalized nahi hai (business_name missing) — generic path mila"
            )
            print(f"{_ERR}   expected '{args.business_name}' in opening_line")
        else:
            print(
                f"{_OK}   wizard opening PROVEN (business_name '{args.business_name}' personalized)"
            )

        # C) answer-stream XML → opening_line qs (session override reach)
        code2, body2 = _http_json(f"{url}/api/telephony/vobiz/answer-stream/{token}")
        xml = body2.get("raw", "") if isinstance(body2, dict) else ""
        if code2 != 200 or "opening_line=" not in xml:
            problems.append(f"answer-stream me opening_line qs nahi mila (HTTP {code2})")
            print(f"{_ERR} C) answer-stream/{token} → HTTP {code2}, opening_line qs missing")
        else:
            print(f"{_OK} C) answer-stream XML me opening_line qs present — session override reach")
            print(
                f"      ws snippet: {xml[xml.find('opening_line=') - 40 : xml.find('opening_line=') + 80]}"
            )

    print("-" * 60)
    if problems:
        print(f"{_ERR} FAILED — {len(problems)} problem(s):")
        for p in problems:
            print(f"      • {p}")
        return 1
    print(f"{_OK} chain verified end-to-end (dry-run, no real call placed) — exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
