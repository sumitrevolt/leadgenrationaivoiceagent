"""Submit one signed governor review to a loopback LeadGen dev-control API.

The selected governor process receives only its own scoped env secret. This
client never prints the secret or HMAC headers and refuses non-loopback URLs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

# Direct ``python scripts/governor_review_submit.py`` puts only scripts/ on
# sys.path. Bootstrap the repo root before importing the trusted auth helper.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.dev_control.governor_auth import build_configured_governor_headers

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_request(
    *,
    base_url: str,
    task_id: str,
    governor: str,
    decision: str,
    artifact_hash: str,
    summary: str,
) -> Request:
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in _LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("loopback_url_required")
    body = {
        "governor": governor,
        "decision": decision,
        "artifact_hash": artifact_hash,
        "summary": summary,
    }
    headers = build_configured_governor_headers(
        task_id=task_id,
        governor=governor,
        decision=decision,
        artifact_hash=artifact_hash,
        summary=summary,
    )
    headers["Content-Type"] = "application/json"
    url = f"{base_url.rstrip('/')}/dev-tasks/{quote(task_id, safe='')}/governor-review"
    return Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )


def submit_review(**kwargs: Any) -> dict[str, Any]:
    request = build_request(**kwargs)
    with urlopen(request, timeout=10) as response:  # noqa: S310 - loopback enforced above
        payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {"ok": False, "reason": "invalid_response"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit a scoped governor review to local LeadGen")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--governor", choices=("claude", "chatgpt"), required=True)
    parser.add_argument(
        "--decision", choices=("approve", "changes_requested", "reject"), required=True
    )
    parser.add_argument("--artifact-hash", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    try:
        result = submit_review(
            base_url=args.base_url,
            task_id=args.task_id,
            governor=args.governor,
            decision=args.decision,
            artifact_hash=args.artifact_hash,
            summary=args.summary,
        )
    except Exception as exc:  # never expose request headers or secret material
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
