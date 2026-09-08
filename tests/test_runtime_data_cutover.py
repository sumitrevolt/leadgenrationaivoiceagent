"""The cutover tool must refuse more often than it succeeds.

This tool is the only thing that will ever be pointed at the live consent
ledger, the paying customer's delivery ledger and 182 MB of DPDP recordings, on
a production host, by an operator under time pressure. So the tests that matter
are the refusals: a tool that copies bytes correctly but activates on unverified
evidence is worse than no tool, because it produces a marker that tells the
deploy guard everything is fine.

Every test runs against a tmp_path root and a monkeypatched REPO. Nothing here
touches the repository's own data/ directory.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.platform import runtime_data_manifest as manifest
from app.platform import runtime_data_marker as mk

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "_cutover_testmod", REPO / "scripts" / "runtime_data_cutover.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tool(tmp_path, monkeypatch):
    """The tool, with its REPO pointed at a fake checkout."""
    mod = _load()
    fake_repo = tmp_path / "checkout"
    (fake_repo / "data").mkdir(parents=True)
    monkeypatch.setattr(mod, "REPO", fake_repo)
    return mod


@pytest.fixture
def dual_read_store(monkeypatch, tool):
    """A manifest row in DUAL_READ_PRE_CUTOVER whose source file exists.

    The row is monkeypatched rather than invented so the test exercises the real
    manifest shape — a fabricated row would let a field rename pass silently.
    """
    row = next(s for s in manifest.STORES if s["store_id"] == "compliance.voice_suppression")
    monkeypatch.setitem(row, "migration_state", manifest.DUAL_READ_PRE_CUTOVER)
    src = tool.REPO / "data" / "voice_suppression.jsonl"
    src.write_text('{"phone":"911111111111"}\n{"phone":"922222222222"}\n', encoding="utf-8")
    return row["store_id"], src


# ------------------------------------------------------------------- refusals
def test_refuses_a_store_whose_code_cannot_follow_a_cutover(tool, tmp_path, monkeypatch):
    """LEGACY_IN_CHECKOUT means the app still reads the old path."""
    row = next(s for s in manifest.STORES if s["store_id"] == "billing.invoices")
    monkeypatch.setitem(row, "migration_state", manifest.LEGACY_IN_CHECKOUT)
    with pytest.raises(SystemExit) as e:
        tool.main(["plan", "--root", str(tmp_path / "rt"), "--stores", "billing.invoices"])
    assert "LEGACY_IN_CHECKOUT" in str(e.value)


def test_refuses_unknown_store_id(tool, tmp_path):
    with pytest.raises(SystemExit) as e:
        tool.main(["plan", "--root", str(tmp_path / "rt"), "--stores", "not.a.store"])
    assert "unknown store ids" in str(e.value)


def test_refuses_when_the_declared_source_is_absent(tool, tmp_path, monkeypatch):
    """ "Migrating" a store whose bytes cannot be found would fake a cutover."""
    row = next(s for s in manifest.STORES if s["store_id"] == "compliance.consent_ledger")
    monkeypatch.setitem(row, "migration_state", manifest.DUAL_READ_PRE_CUTOVER)
    with pytest.raises(SystemExit) as e:
        tool.main(["plan", "--root", str(tmp_path / "rt"), "--stores", "compliance.consent_ledger"])
    assert "absent" in str(e.value)


def test_copy_refuses_without_yes(tool, tmp_path, dual_read_store):
    store_id, _ = dual_read_store
    with pytest.raises(SystemExit) as e:
        tool.main(["copy", "--root", str(tmp_path / "rt"), "--stores", store_id])
    assert "--yes" in str(e.value)


def test_activate_refuses_when_verify_never_ran(tool, tmp_path, dual_read_store):
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    with pytest.raises(SystemExit) as e:
        tool.main(["activate", "--yes", "--root", str(root), "--rollback-reference", "dd193a69"])
    assert "not marked verified" in str(e.value)


def test_activate_refuses_without_a_rollback_reference(tool, tmp_path, dual_read_store):
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    tool.main(["verify", "--root", str(root)])
    with pytest.raises(SystemExit) as e:
        tool.main(["activate", "--yes", "--root", str(root), "--rollback-reference", "   "])
    assert "rollback" in str(e.value).lower()


def test_copy_refuses_to_overwrite_an_existing_destination(tool, tmp_path, dual_read_store):
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    with pytest.raises(SystemExit) as e:
        tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    assert "already exists" in str(e.value)


# ------------------------------------------------------------ detection power
def test_verify_catches_a_writer_that_appended_during_the_cutover(tool, tmp_path, dual_read_store):
    """The realistic failure: a live process appends between copy and verify.

    Byte-comparing source to destination alone would MISS this — they differ, but
    so would a legitimately-stale copy. The source hash recorded at copy time is
    what makes the difference detectable and attributable.
    """
    store_id, src = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    with src.open("a", encoding="utf-8") as fh:
        fh.write('{"phone":"933333333333"}\n')
    assert tool.main(["verify", "--root", str(root)]) == 1


def test_verify_catches_a_truncated_destination(tool, tmp_path, dual_read_store):
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    payload = json.loads(
        (root / tool.EVIDENCE_DIRNAME / tool.COPY_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    Path(payload["entries"][0]["destination"]).write_text("", encoding="utf-8")
    assert tool.main(["verify", "--root", str(root)]) == 1


def test_verify_catches_a_deleted_destination(tool, tmp_path, dual_read_store):
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    payload = json.loads(
        (root / tool.EVIDENCE_DIRNAME / tool.COPY_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    Path(payload["entries"][0]["destination"]).unlink()
    assert tool.main(["verify", "--root", str(root)]) == 1


# ------------------------------------------------------------- happy path
def test_source_survives_a_full_cutover(tool, tmp_path, dual_read_store):
    """The checkout copy is the fallback. Nothing here may delete it."""
    store_id, src = dual_read_store
    before = src.read_bytes()
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    assert tool.main(["verify", "--root", str(root)]) == 0
    tool.main(
        [
            "activate",
            "--yes",
            "--root",
            str(root),
            "--rollback-reference",
            "dd193a69",
            "--release-sha",
            "2b64686",
        ]
    )
    assert src.exists() and src.read_bytes() == before


def test_the_written_marker_passes_the_real_validator(tool, tmp_path, dual_read_store):
    """Not 'looks right' — the same validator the authority gates on."""
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    tool.main(["verify", "--root", str(root)])
    tool.main(
        [
            "activate",
            "--yes",
            "--root",
            str(root),
            "--rollback-reference",
            "dd193a69",
            "--release-sha",
            "2b6468678a69c66c61d1467bf4b64453249f90ee",  # pragma: allowlist secret,
            "--operator",
            "test",
        ]
    )
    marker_path = root.joinpath(*mk.MARKER_RELATIVE_PATH)
    assert mk.validate_marker_file(marker_path, runtime_root_identifier=str(root)) == []
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["migrated_store_ids"] == [store_id]
    # The marker must cite the evidence it was based on, not just assert PASSED.
    assert tool.COPY_MANIFEST_NAME in marker["verification_reference"]


def test_lock_files_are_skipped_not_copied(tool, tmp_path, monkeypatch):
    """A copied lock hands the new root a lock nobody holds."""
    row = next(s for s in manifest.STORES if s["store_id"] == "compliance.email_suppression")
    monkeypatch.setitem(row, "migration_state", manifest.DUAL_READ_PRE_CUTOVER)
    assert any(str(p).endswith(".lock") for p in row["legacy_paths"]), "fixture assumption"
    (tool.REPO / "data" / "email_suppression.jsonl").write_text("{}\n", encoding="utf-8")
    (tool.REPO / "data" / "email_suppression.jsonl.lock").write_text("", encoding="utf-8")
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", row["store_id"]])
    payload = json.loads(
        (root / tool.EVIDENCE_DIRNAME / tool.COPY_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert [s["path"] for s in payload["skipped_locks"]] == ["data/email_suppression.jsonl.lock"]
    assert not any(str(e["destination"]).endswith(".lock") for e in payload["entries"])


def test_activate_refuses_when_no_release_sha_can_be_determined(tool, tmp_path, dual_read_store):
    """A marker without a release sha cannot be diffed against anything later.

    The fake checkout in these tests is not a git repo, which is exactly the
    tarball-deploy case an operator can hit for real — so the refusal must name
    the flag that fixes it rather than emitting 'malformed'.
    """
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    tool.main(["verify", "--root", str(root)])
    with pytest.raises(SystemExit) as e:
        tool.main(["activate", "--yes", "--root", str(root), "--rollback-reference", "dd193a69"])
    assert "--release-sha" in str(e.value)
    assert not root.joinpath(*mk.MARKER_RELATIVE_PATH).exists()


def test_activate_does_not_flip_manifest_state_or_the_gate(tool, tmp_path, dual_read_store):
    """Those are reviewed code changes, not side effects of a host script."""
    store_id, _ = dual_read_store
    root = tmp_path / "rt"
    before = len(manifest.blocking_stores())
    tool.main(["copy", "--yes", "--root", str(root), "--stores", store_id])
    tool.main(["verify", "--root", str(root)])
    tool.main(
        [
            "activate",
            "--yes",
            "--root",
            str(root),
            "--rollback-reference",
            "dd193a69",
            "--release-sha",
            "2b64686",
        ]
    )
    assert len(manifest.blocking_stores()) == before
