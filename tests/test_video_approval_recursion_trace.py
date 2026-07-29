"""Stage 3A trace: prove the approval path re-enters the video writer.

`cell.approve_version` calls `content_approval.approve(token)`, and
`content_approval._decide` calls `video_ad_cycle.on_approved` as a CALLBACK,
which now calls `record_approval`. `approve_version` then calls
`record_approval` a second time itself.

One customer click therefore performs TWO approval writes. This test pins the
current (wrong) behaviour so the Stage 3A coordinator can be shown to fix it.
"""

from __future__ import annotations

import hashlib

import pytest

# ruff: noqa: F811
from tests.test_video_preview_identity import preview_client  # noqa: F401


def test_single_approval_currently_writes_twice(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    calls = []
    real = V.record_approval
    monkeypatch.setattr(
        V, "record_approval", lambda *a, **k: (calls.append((a, k)), real(*a, **k))[1]
    )

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    r = c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={
            "action": "approve",
            "expected_revision": 0,
            "expected_content_sha256": digest,
        },
    )
    assert r.status_code == 200

    # DOCUMENTS THE DEFECT: expected 1, actual 2 (callback + direct call).
    assert len(calls) == 2, f"expected the known double-write, saw {len(calls)}"
    actors = [k.get("actor") for _, k in calls]
    assert len(set(actors)) > 0
