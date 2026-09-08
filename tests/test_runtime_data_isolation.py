"""Canonical test isolation + the exact CI-pollution regression from PR #144.

WHAT HAPPENED: a PR #144 test passed locally and FAILED in CI because the
repository's committed `data/wa_suppression.jsonl` answered a suppression
lookup. The test never touched that file — it just happened to run in a
checkout where the file said "suppressed".

That is the whole argument for this module. Repository state must not be able
to decide a test outcome, and a test must not be able to write production state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.platform import runtime_data as rd
from app.platform import runtime_data_manifest as manifest


# ============================================================ bootstrap
@pytest.fixture
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The canonical bootstrap: one disposable runtime root per test."""
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv(rd.ENV_KEY, str(root))
    monkeypatch.delenv(rd.LEGACY_ENV_KEY, raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    return root


def test_each_test_gets_a_unique_root(isolated_runtime: Path) -> None:
    assert rd.runtime_root() == isolated_runtime
    assert "pytest" in str(isolated_runtime).lower() or str(isolated_runtime)


def test_root_is_outside_the_repository(isolated_runtime: Path) -> None:
    repo = Path(rd.__file__).resolve().parents[2]
    assert not str(isolated_runtime.resolve()).startswith(str(repo.resolve()))


def test_tests_cannot_resolve_production_paths(isolated_runtime: Path) -> None:
    resolved = str(rd.store_path("compliance", "x.jsonl"))
    assert "/opt/leadgen/data" not in resolved.replace("\\", "/")
    assert "/var/lib/leadgen/runtime" not in resolved.replace("\\", "/")


def test_import_before_fixture_still_resolves_dynamically(
    isolated_runtime: Path, monkeypatch, tmp_path
) -> None:
    """`runtime_data` was imported at module load, long before this fixture.

    It must still see the test root, because resolution happens at operation
    time. An import-time constant is what made the old stores un-redirectable.
    """
    first = rd.runtime_root()
    later = tmp_path / "later"
    later.mkdir()
    monkeypatch.setenv(rd.ENV_KEY, str(later))
    assert rd.runtime_root() == later != first


# ================================================== THE PR #144 REGRESSION
def _seed_repo_style_legacy_suppression(tmp_path: Path, email: str) -> Path:
    """A repository-style legacy file, exactly like the committed one."""
    legacy = tmp_path / "repo_data"
    legacy.mkdir()
    f = legacy / "email_suppression.jsonl"
    f.write_text(
        json.dumps({"email": email, "reason": "one_click", "ts": 1}) + "\n",
        encoding="utf-8",
    )
    return f


def test_case_A_repository_data_cannot_suppress(isolated_runtime: Path, tmp_path) -> None:
    """Repo file says SUPPRESSED, isolated root says nothing → NOT suppressed.

    This is the exact shape of the CI failure: a committed data file deciding a
    test outcome.
    """
    from app.platform import email_unsub

    _seed_repo_style_legacy_suppression(tmp_path, "victim@example.com")
    # The canonical store lives under the isolated runtime root, and is empty.
    email_unsub._store_path = lambda: isolated_runtime / "compliance" / "email_suppression.jsonl"

    assert email_unsub.is_suppressed("victim@example.com") is False, (
        "repository data leaked into the test — this is the PR #144 CI incident"
    )


def test_case_B_isolated_root_suppression_is_respected(isolated_runtime: Path, tmp_path) -> None:
    """Isolated root says SUPPRESSED, repo says nothing → blocked.

    The inverse guard: isolation must not silently disable real suppression.
    """
    from app.platform import email_unsub

    store = isolated_runtime / "compliance" / "email_suppression.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    email_unsub._store_path = lambda: store
    email_unsub.suppress("blocked@example.com", scope=email_unsub.SCOPE_ALL_OUTREACH)

    assert email_unsub.is_suppressed("blocked@example.com") is True
    assert email_unsub.is_contact_suppressed(email="blocked@example.com", channel="email") is True


def test_ledger_and_lock_share_the_isolated_root(isolated_runtime: Path) -> None:
    """A lock resolving elsewhere coordinates nothing across five containers."""
    ledger = rd.store_path("compliance", "email_suppression.jsonl")
    lock = rd.lock_path("compliance", "email_suppression.jsonl")
    assert lock.parent == ledger.parent
    assert str(ledger).startswith(str(isolated_runtime))
    assert str(lock).startswith(str(isolated_runtime))


def test_cleanup_cannot_target_a_non_test_path(isolated_runtime: Path) -> None:
    """Guard the guard: the root must be provably disposable before deletion."""
    repo = Path(rd.__file__).resolve().parents[2]
    root = rd.runtime_root()
    assert root != repo
    assert not str(root.resolve()).startswith(str((repo / "data").resolve()))


# ==================================================== legacy conflict policy
def test_canonical_wins_over_legacy_outside_production(monkeypatch, tmp_path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(rd.ENV_KEY, str(a))
    monkeypatch.setenv(rd.LEGACY_ENV_KEY, str(b))
    assert rd.runtime_root() == a


def test_production_rejects_conflicting_legacy_and_canonical(monkeypatch, tmp_path) -> None:
    """Two settings that disagree in production is exactly the ambiguity that
    puts live state somewhere nobody expects."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(rd.ENV_KEY, str(a))
    monkeypatch.setenv(rd.LEGACY_ENV_KEY, str(b))
    with pytest.raises(rd.RuntimeDataError, match="disagree"):
        rd.runtime_root()


def test_production_accepts_agreeing_legacy_and_canonical(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    monkeypatch.setenv(rd.LEGACY_ENV_KEY, str(tmp_path))
    assert rd.runtime_root() == tmp_path


def test_host_key_is_never_the_application_path() -> None:
    """Host and container paths are different concepts and must not collide."""
    assert rd.HOST_ENV_KEY != rd.ENV_KEY
    assert "HOST" in rd.HOST_ENV_KEY


# ============================================================== manifest
def test_manifest_store_ids_are_unique() -> None:
    ids = [s["store_id"] for s in manifest.STORES]
    assert len(ids) == len(set(ids)), "duplicate store_id — manifest is not deduplicated"


def test_manifest_states_are_valid() -> None:
    for s in manifest.STORES:
        assert s["migration_state"] in manifest.VALID_STATES, s["store_id"]


def test_manifest_required_fields_present() -> None:
    required = {
        "store_id",
        "display_name",
        "current_authority",
        "migration_tier",
        "migration_state",
        "deployment_blocker",
    }
    for s in manifest.STORES:
        missing = required - set(s)
        assert not missing, f"{s.get('store_id')} missing {missing}"


def test_declared_waves_are_cutover_complete() -> None:
    """After host cutover, declared wave stores are CUTOVER_COMPLETE."""
    from tests.runtime_data_waves import all_declared_store_ids

    complete = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert set(all_declared_store_ids()) <= complete
    assert not manifest.by_state(manifest.EXTERNAL_VERIFIED)


def test_unknown_authoritative_store_is_a_deployment_blocker() -> None:
    """ "We did not check" is not evidence of safety."""
    for s in manifest.by_state(manifest.UNKNOWN):
        assert s["deployment_blocker"] is True, s["store_id"]


def test_database_authoritative_stores_are_not_blockers() -> None:
    """Owner OS files are absent in production — migrating them is wasted work."""
    for s in manifest.STORES:
        if s.get("migration_state") in (
            manifest.FALLBACK_ONLY,
            manifest.DATABASE_AUTHORITY,
        ):
            assert s["deployment_blocker"] is False, s["store_id"]


def test_rebuildable_cache_is_not_a_blocker() -> None:
    for s in manifest.by_state(manifest.REBUILDABLE_CACHE):
        assert s["deployment_blocker"] is False


def test_blocking_stores_cleared_after_cutover_complete() -> None:
    """CUTOVER_COMPLETE stores no longer block; critical ids are complete."""
    blockers = manifest.blocking_stores()
    assert not blockers, sorted(s["store_id"] for s in blockers)
    complete = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    for critical in (
        "billing.invoices",
        "compliance.email_suppression",
        "compliance.consent_ledger",
        "customers.identity",
    ):
        assert critical in complete, f"{critical} must be CUTOVER_COMPLETE"


def test_counts_are_derived_not_asserted() -> None:
    c = manifest.counts()
    assert c["unique_families"] == len(manifest.STORES)
    assert c["deployment_blockers"] == len(manifest.blocking_stores())
    assert c["file_authoritative"] >= 8
    assert c["database_authoritative"] >= 1


def test_interactions_is_not_silently_tiered_as_resolved() -> None:
    """Dual-authority must be visible, not laundered into a normal tier."""
    row = next(s for s in manifest.STORES if s["store_id"] == "communications.interactions")
    assert row["current_authority"] == "DUAL_WRITE_DRIFTED"
    assert row["migration_state"] == manifest.CUTOVER_COMPLETE
    assert row["deployment_blocker"] is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX path semantics")
def test_manifest_paths_are_relative_not_absolute() -> None:
    for s in manifest.STORES:
        for p in s.get("legacy_paths", []):
            assert not p.startswith("/"), s["store_id"]
