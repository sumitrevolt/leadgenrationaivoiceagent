#!/usr/bin/env python3
"""Verify every OmniRoute combo can actually COMPLETE an inference.

2026-09-25: the gateway served /v1/models 200 while every chat completion
failed ("No active credentials for provider: anthropic"). A model list is not
proof of a working lane -- only a real completion is. This sends a trivial
one-token request per combo and reports pass/fail from the response BODY,
never from the HTTP status alone.
"""

from __future__ import annotations

import json
import subprocess
import sys

GW = "http://127.0.0.1:20128/v1/chat/completions"
PROBE = "reply with the single word OK"


def probe(model: str, timeout: int = 90) -> tuple[bool, str]:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": PROBE}],
            "max_tokens": 12,
            "stream": False,
        }
    )
    try:
        out = subprocess.run(
            [
                "curl", "-s", "--max-time", str(timeout),
                "-X", "POST", GW,
                "-H", "Content-Type: application/json",
                "-d", body,
            ],
            capture_output=True, text=True, timeout=timeout + 15,
        ).stdout
    except subprocess.TimeoutExpired:
        return False, "timeout"

    # Strip SSE framing if the gateway streamed despite stream:false.
    text = out.replace("data: ", "")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in d:
            return False, str(d["error"].get("message", "error"))[:70]
        for ch in d.get("choices", []):
            msg = ch.get("message", {}) or {}
            content = (msg.get("content") or "").strip()
            if content:
                return True, f"{d.get('model', '?')} -> {content[:24]!r}"
            if msg.get("reasoning_content"):
                return True, f"{d.get('model', '?')} -> (reasoning ok)"
    return False, "no completion in body"


def main() -> int:
    combos = [f"leadsgen combo {i}" for i in range(1, 15)]
    ok, bad = [], []
    for c in combos:
        passed, detail = probe(c)
        print(f"  {'PASS' if passed else 'FAIL'}  {c:<18} {detail}")
        (ok if passed else bad).append(c)

    print(f"\n{len(ok)}/{len(combos)} combos serving inference")
    if bad:
        print("failing: " + ", ".join(bad))
    return 0 if len(ok) == len(combos) else 1


if __name__ == "__main__":
    sys.exit(main())
