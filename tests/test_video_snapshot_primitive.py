"""Stage 2 — immutable snapshot primitive.

Filesystem only: no approval ledger, video record, queue, provider or UI is
touched. A hardlink would share the source inode, so the snapshot must be a NEW
inode; every failure path must leave nothing installed and no temp behind.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import pytest

from app.marketing import media_limits as ML
from app.marketing.video_production import snapshot as S

# ruff: noqa: F811  (pytest resolves the imported fixture by parameter name)
from tests.test_video_preview_identity import preview_client  # noqa: F401

TENANT = "jiya-makeover"
REC = "va-snap-1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.marketing import video_media_paths as vmp
    from app.marketing import video_pipeline

    # HERMETIC PRECONDITION (do not remove): every test here that does a REAL copy
    # writes to the host filesystem, and prepare_snapshot refuses when the destination
    # would fall below VIDEO_SNAPSHOT_MIN_FREE_PCT. Left unpinned, the whole file goes
    # red on any machine whose disk is under the default floor — a host-capacity fact,
    # not a snapshot defect. Pinned low here; the tests that are ABOUT the floor set
    # their own value (or stub _disk_free_total) and therefore still prove it.
    monkeypatch.setenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", "1")

    src_root = tmp_path / "reels"
    src_root.mkdir()
    approved = tmp_path / "video_ads" / "_approved"
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(src_root))
    monkeypatch.setattr(vmp, "approved_media_dir", lambda: approved)

    source = src_root / "render.mp4"
    source.write_bytes(b"SNAPSHOT-A" * 4096)
    return {
        "source": source,
        "approved": approved,
        "digest": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _prepare(env, **over):
    kw = {
        "tenant_id": TENANT,
        "record_id": REC,
        "revision": 0,
        "expected_sha256": env["digest"],
        "source_path": str(env["source"]),
    }
    kw.update(over)
    return S.prepare_snapshot(**kw)


def _temps(env):
    d = env["approved"] / TENANT
    return list(d.glob(".snap-*")) if d.exists() else []


# 1. correct digest/size and a NEW inode
def test_snapshot_is_new_inode_with_correct_identity(env):
    out = _prepare(env)
    assert out["ok"] is True and out["reused"] is False
    snap = os.stat(out["path"])
    src = os.stat(env["source"])
    assert snap.st_ino != src.st_ino  # copy, never a hardlink
    assert snap.st_nlink == 1
    assert out["sha256"] == env["digest"]
    assert out["bytes"] == src.st_size
    assert hashlib.sha256(open(out["path"], "rb").read()).hexdigest() == env["digest"]
    assert _temps(env) == []


# 2. hash mismatch installs nothing
def test_hash_mismatch_leaves_no_artifact(env):
    out = _prepare(env, expected_sha256="b" * 64)
    assert out["ok"] is False and out["error"] == "content_hash_mismatch"
    assert not (env["approved"] / TENANT).exists() or not list(
        (env["approved"] / TENANT).glob("*.mp4")
    )
    assert _temps(env) == []


# 3. concurrent source mutation refuses
def test_source_changed_during_copy_refuses(env, monkeypatch):
    real_fstat = os.fstat
    calls = {"n": 0}

    def _drifting_fstat(fd):
        st = real_fstat(fd)
        calls["n"] += 1
        if calls["n"] >= 2:  # the post-copy stat looks different
            return os.stat_result(tuple(st)[:7] + (st.st_atime, st.st_mtime + 5, st.st_ctime))
        return st

    monkeypatch.setattr(os, "fstat", _drifting_fstat)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "source_changed_during_copy"
    assert _temps(env) == []


# 4. interruption at each stage cleans the temp
@pytest.mark.parametrize("boom_at", ["fsync", "replace"])
def test_interruption_cleans_temp(env, monkeypatch, boom_at):
    if boom_at == "fsync":
        monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk gone")))
    else:
        monkeypatch.setattr(
            os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("rename failed"))
        )
    out = _prepare(env)
    assert out["ok"] is False
    assert _temps(env) == []
    assert not list((env["approved"] / TENANT).glob("*.mp4"))


# 5. size and disk-headroom budgets refuse
def test_snapshot_module_uses_no_private_cross_module_constants():
    body = open(S.__file__, encoding="utf-8").read()
    assert "_UPLOAD_MAX_BYTES" not in body
    assert "contentplus" not in body
    assert "staff" not in body
    assert "from app.marketing.media_limits import" in body


def test_upload_path_consumes_the_authority_not_a_duplicate(monkeypatch):
    """Single source of truth: contentplus must READ media_limits, not hold a
    second constant that merely happens to be equal."""
    from app.api import contentplus

    body = open(contentplus.__file__, encoding="utf-8").read()
    assert "from app.marketing.media_limits import max_upload_bytes" in body
    assert "= 200 * 1024 * 1024" not in body  # no independent definition

    # Change the authority; the upload path must follow.
    monkeypatch.setenv("MEDIA_UPLOAD_MAX_MB", "7")
    assert ML.max_upload_bytes() == 7 * 1024 * 1024
    assert contentplus._upload_max_bytes() == 7 * 1024 * 1024
    assert S.max_snapshot_bytes() == 7 * 1024 * 1024  # snapshot follows too


def test_invalid_config_fails_closed_for_both_upload_and_snapshot(monkeypatch):
    monkeypatch.setenv("MEDIA_UPLOAD_MAX_MB", "not-a-number")
    from app.api import contentplus

    with pytest.raises(ML.MediaLimitConfigError):
        contentplus._upload_max_bytes()
    with pytest.raises(ML.MediaLimitConfigError):
        S.max_snapshot_bytes()


def test_snapshot_ceiling_defaults_to_upload_ceiling():
    assert S.max_snapshot_bytes() == ML.max_upload_bytes()


def test_free_floor_default():
    assert S.min_free_percent() == 10.0


def test_override_may_tighten_but_never_raise_the_ceiling(monkeypatch):
    monkeypatch.setenv("VIDEO_SNAPSHOT_MAX_MB", "50")
    assert S.max_snapshot_bytes() == 50 * 1024 * 1024  # tighter: allowed
    monkeypatch.setenv("VIDEO_SNAPSHOT_MAX_MB", "201")  # above the 200 MB cap
    with pytest.raises(ML.MediaLimitConfigError):
        S.max_snapshot_bytes()


def test_artifact_over_canonical_upload_cap_cannot_be_accepted(env, monkeypatch):
    """201 MB artifact vs a 200 MB canonical cap — refused even if someone
    tries to widen VIDEO_SNAPSHOT_MAX_MB."""
    big = env["source"].parent / "big.mp4"
    with open(big, "wb") as fh:  # sparse: st_size is 201 MB, disk cost ~0
        fh.truncate(201 * 1024 * 1024)
    monkeypatch.setenv("VIDEO_SNAPSHOT_MAX_MB", "2048")
    out = _prepare(env, source_path=str(big), expected_sha256="c" * 64)
    assert out["ok"] is False and out["error"] == "snapshot_config_invalid"

    monkeypatch.delenv("VIDEO_SNAPSHOT_MAX_MB", raising=False)
    out = _prepare(env, source_path=str(big), expected_sha256="c" * 64)
    assert out["ok"] is False and out["error"] == "source_size_out_of_bounds"
    assert _temps(env) == []


@pytest.mark.parametrize("bad", ["0", "-5", "9999", "abc", "12.5", "201"])
def test_invalid_size_config_fails_closed(env, monkeypatch, bad):
    monkeypatch.setenv("VIDEO_SNAPSHOT_MAX_MB", bad)
    with pytest.raises(ML.MediaLimitConfigError):
        S.max_snapshot_bytes()
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "snapshot_config_invalid"
    assert _temps(env) == []


@pytest.mark.parametrize("bad", ["0", "95", "-1", "nope"])
def test_invalid_free_pct_config_fails_closed(env, monkeypatch, bad):
    monkeypatch.setenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", bad)
    with pytest.raises(ML.MediaLimitConfigError):
        S.min_free_percent()
    assert _prepare(env)["error"] == "snapshot_config_invalid"


def test_oversized_source_refused(env, monkeypatch):
    monkeypatch.setattr(S, "max_snapshot_bytes", lambda: 16)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "source_size_out_of_bounds"
    assert _temps(env) == []


def test_projected_free_crossing_threshold_refuses(env, monkeypatch):
    """Currently ABOVE the floor, but the copy would take it below."""
    # States its OWN floor rather than inheriting one: the arithmetic below is written
    # against 10%, so reading the ambient value would silently stop testing the
    # crossing once the floor changes anywhere else.
    monkeypatch.setenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", "10")
    size = env["source"].stat().st_size
    total = size * 100
    free = int(total * 0.105)  # 10.5% now; the copy costs 1% -> 9.5% after
    monkeypatch.setattr(S, "_disk_free_total", lambda p: (free, total))
    assert free / total * 100.0 > S.min_free_percent()  # admissible right now
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "insufficient_disk_headroom"
    assert _temps(env) == []


def test_projected_free_exactly_at_threshold_is_admitted(env, monkeypatch):
    """Documented boundary: >= floor passes; the floor itself is admissible."""
    monkeypatch.setenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", "10")
    size = env["source"].stat().st_size
    total = size * 100
    free = size + int(total * 0.10)  # exactly 10.0% remains after the copy
    monkeypatch.setattr(S, "_disk_free_total", lambda p: (free, total))
    assert _prepare(env)["ok"] is True


def test_disk_state_unavailable_fails_closed(env, monkeypatch):
    monkeypatch.setattr(S, "_disk_free_total", lambda p: (-1, -1))
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "disk_state_unavailable"
    assert _temps(env) == []


def test_disk_usage_is_queried_on_the_destination_filesystem(env, monkeypatch):
    seen = []

    def _spy(path):
        seen.append(str(path))
        return (10**12, 10**12)

    monkeypatch.setattr(S, "_disk_free_total", _spy)
    assert _prepare(env)["ok"] is True
    assert seen and str(env["approved"]) in seen[0]
    assert str(env["source"].parent) not in seen[0]


def test_empty_source_refused(env):
    env["source"].write_bytes(b"")
    out = _prepare(env, expected_sha256=hashlib.sha256(b"").hexdigest())
    assert out["ok"] is False and out["error"] == "source_size_out_of_bounds"


# 6. identical snapshot reused without rewrite
def test_identical_snapshot_is_reused(env):
    first = _prepare(env)
    before = os.stat(first["path"])
    second = _prepare(env)
    assert second["ok"] is True and second["reused"] is True
    after = os.stat(second["path"])
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)


# 7. corrupt existing destination refused, never overwritten
def test_existing_corrupt_snapshot_refused(env):
    first = _prepare(env)
    corrupted = b"TAMPERED"
    with open(first["path"], "wb") as fh:
        fh.write(corrupted)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "existing_snapshot_corrupt"
    assert open(first["path"], "rb").read() == corrupted  # untouched


# 8. concurrent same-revision calls do not corrupt
def test_concurrent_same_revision_is_safe(env):
    results = []

    def _run():
        results.append(_prepare(env))

    threads = [threading.Thread(target=_run) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert all(r["ok"] for r in results)
    paths = {r["path"] for r in results}
    assert len(paths) == 1
    only = paths.pop()
    assert hashlib.sha256(open(only, "rb").read()).hexdigest() == env["digest"]
    assert _temps(env) == []
    assert len(list((env["approved"] / TENANT).glob("*.mp4"))) == 1


# 9. distinct revisions cannot overwrite each other
def test_distinct_revisions_do_not_collide(env):
    r0 = _prepare(env, revision=0)
    env["source"].write_bytes(b"SNAPSHOT-B" * 4096)
    d1 = hashlib.sha256(env["source"].read_bytes()).hexdigest()
    r1 = _prepare(env, revision=1, expected_sha256=d1)
    assert r0["path"] != r1["path"]
    assert os.path.exists(r0["path"]) and os.path.exists(r1["path"])
    assert hashlib.sha256(open(r0["path"], "rb").read()).hexdigest() != d1


# 10. traversal identifiers are neutralised
@pytest.mark.parametrize(
    "tenant,record",
    [
        ("../../etc", "va-1"),
        ("t", "../../../evil"),
        ("a/b", "c-d"),
        ("a", "c\\d"),
        ("", "va-1"),
        ("t", ""),
        ("..", "va-1"),
        (".", "va-1"),
        ("t\x00x", "va-1"),
        ("t", "va\nnewline"),
        ("-leading", "va-1"),
        ("a" * 65, "va-1"),
    ],
)
def test_invalid_identifiers_are_REFUSED_not_sanitized(env, tenant, record):
    """Refusal, not silent rewriting. Sanitizing would collide distinct tenants
    onto one directory and turn traversal input into a valid in-root name."""
    out = _prepare(env, tenant_id=tenant, record_id=record)
    assert out["ok"] is False and out["error"] == "invalid_identifier"
    assert not env["approved"].exists() or list(env["approved"].rglob("*.mp4")) == []


def test_negative_revision_refused(env):
    out = _prepare(env, revision=-1)
    assert out["ok"] is False and out["error"] == "invalid_identifier"


def test_accepted_identifier_is_the_identity_mapping(env):
    """No transformation: what goes in is what lands on disk (collision-free)."""
    out = _prepare(env, tenant_id="Tenant_9-x", record_id="va_Rec-7")
    assert out["ok"] is True
    assert os.path.basename(os.path.dirname(out["path"])) == "Tenant_9-x"
    assert os.path.basename(out["path"]).startswith("va_Rec-7.r0.")


def test_invalid_expected_hash_refused(env):
    assert _prepare(env, expected_sha256="nothex")["error"] == "expected_sha256_invalid"
    assert _prepare(env, expected_sha256="")["error"] == "expected_sha256_invalid"


def test_source_outside_media_root_refused(env, tmp_path):
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x" * 100)
    out = _prepare(env, source_path=str(outside))
    assert out["ok"] is False and out["error"] == "source_unverifiable"


# 11-12. no hardlink, no ledger/record/queue/provider mutation
def test_never_uses_os_link(env, monkeypatch):
    calls = {"link": 0}
    monkeypatch.setattr(os, "link", lambda *a, **k: calls.__setitem__("link", calls["link"] + 1))
    assert _prepare(env)["ok"] is True
    assert calls["link"] == 0


def test_no_business_state_or_provider_mutation(env, monkeypatch):
    from app.marketing import content_approval
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as V

    counts = {"update": 0, "append": 0, "decide": 0, "postiz": 0}

    async def _spy_postiz(*a, **k):
        counts["postiz"] += 1
        return {"sent": True}

    monkeypatch.setattr(V, "_update", lambda *a, **k: counts.__setitem__("update", 1))
    monkeypatch.setattr(V, "_append", lambda *a, **k: counts.__setitem__("append", 1))
    monkeypatch.setattr(
        content_approval, "approve", lambda *a, **k: counts.__setitem__("decide", 1)
    )
    monkeypatch.setattr(pp, "publish_video", _spy_postiz, raising=False)

    assert _prepare(env)["ok"] is True
    assert counts == {"update": 0, "append": 0, "decide": 0, "postiz": 0}


def test_module_does_not_delete_finalized_snapshots():
    src = (S.__file__ or "").replace("\\", "/")
    body = open(src, encoding="utf-8").read()
    assert "read_bytes(" not in body
    assert "os.link(" not in body
    # the only unlink is the temp-artifact cleanup
    assert body.count("os.unlink(") == 1 and "os.unlink(tmp_path)" in body


# --- preflight: root authority + no path leakage -------------------------


def test_snapshot_root_comes_from_runtime_data_authority(monkeypatch):
    """approved_media_dir() must derive from the authority, not a CWD guess."""
    from app.marketing import video_media_paths as vmp

    seen = {}

    def _fake_authority(store_id, legacy, segments):
        seen["store_id"] = store_id
        seen["segments"] = segments
        return Path("/srv/runtime") / "artifacts" / "video_ads"

    monkeypatch.setattr(vmp, "_authority_path", _fake_authority)
    root = vmp.approved_media_dir()
    assert seen["store_id"] == "artifacts.video_ads"
    assert str(root).replace("\\", "/").endswith("artifacts/video_ads/_approved")
    # container/VPS safe: the authority's own root is used verbatim and the
    # process CWD never leaks into it.
    assert str(root).replace("\\", "/").startswith("/srv/runtime/")
    assert str(Path.cwd()) not in str(root)


def test_snapshot_path_and_layout_never_reach_customer_response(preview_client):
    """No filesystem path or tenant directory layout in customer JSON."""
    c, artifact = preview_client
    for url in (
        "/api/customer/videos",
        "/api/customer/videos/vid-preview-1/preview",
    ):
        body = c.get(url).text
        assert "_approved" not in body
        assert str(artifact) not in body
        assert "video_path" not in body
        assert "/reels/" not in body and "\\reels\\" not in body
