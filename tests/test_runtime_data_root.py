"""The runtime-data resolver must fail CLOSED in production.

Every assertion here maps to an observed failure:
  * deploy scripts running `git reset --hard` over live state,
  * committed `data/*.jsonl` deciding a CI test outcome,
  * lock files that could resolve away from the ledger they guard,
  * tenant ids reaching filenames.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.platform import runtime_data as rd


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(rd.ENV_KEY, raising=False)
    monkeypatch.delenv(rd.LEGACY_ENV_KEY, raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


def _prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")


# ------------------------------------------------------------ production gates
def test_production_requires_explicit_configuration(monkeypatch) -> None:
    _prod(monkeypatch)
    with pytest.raises(rd.RuntimeDataError, match="not set"):
        rd.runtime_root()


def test_production_rejects_relative_path(monkeypatch) -> None:
    _prod(monkeypatch)
    monkeypatch.setenv(rd.ENV_KEY, "relative/data")
    with pytest.raises(rd.RuntimeDataError, match="absolute"):
        rd.runtime_root()


def test_production_rejects_missing_directory(monkeypatch, tmp_path: Path) -> None:
    _prod(monkeypatch)
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path / "nope"))
    with pytest.raises(rd.RuntimeDataError, match="does not exist"):
        rd.runtime_root()


def test_production_rejects_file_instead_of_directory(monkeypatch, tmp_path: Path) -> None:
    _prod(monkeypatch)
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setenv(rd.ENV_KEY, str(f))
    with pytest.raises(rd.RuntimeDataError, match="not a directory"):
        rd.runtime_root()


def test_production_rejects_path_inside_the_checkout(monkeypatch) -> None:
    """THE core guard: mutable state inside Git is destroyed by reset --hard."""
    _prod(monkeypatch)
    inside = Path(rd.__file__).resolve().parents[2] / "data"
    inside.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(rd.ENV_KEY, str(inside))
    with pytest.raises(rd.RuntimeDataError, match="INSIDE the repository checkout"):
        rd.runtime_root()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_production_rejects_symlink_back_into_checkout(monkeypatch, tmp_path: Path) -> None:
    """The same hazard wearing a disguise."""
    _prod(monkeypatch)
    inside = Path(rd.__file__).resolve().parents[2] / "data"
    inside.mkdir(parents=True, exist_ok=True)
    link = tmp_path / "sneaky"
    link.symlink_to(inside, target_is_directory=True)
    monkeypatch.setenv(rd.ENV_KEY, str(link))
    with pytest.raises(rd.RuntimeDataError, match="INSIDE the repository checkout"):
        rd.runtime_root()


def test_production_accepts_valid_external_path(monkeypatch, tmp_path: Path) -> None:
    _prod(monkeypatch)
    monkeypatch.setenv(rd.ENV_KEY, str(tmp_path))
    assert rd.runtime_root() == tmp_path


# ------------------------------------------------------------------ dev + legacy
def test_development_default_is_not_the_committed_data_dir(monkeypatch) -> None:
    """A dev run must not dirty committed fixtures."""
    root = rd.runtime_root()
    assert root.name != "data"
    assert rd.DEV_DEFAULT.replace("/", os.sep) in str(root)


def test_legacy_data_dir_key_is_honoured(monkeypatch, tmp_path: Path) -> None:
    """Supersede the existing DATA_DIR convention, don't compete with it."""
    monkeypatch.setenv(rd.LEGACY_ENV_KEY, str(tmp_path))
    assert rd.runtime_root() == tmp_path


def test_canonical_key_wins_over_legacy(monkeypatch, tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    legacy = tmp_path / "legacy"
    canonical.mkdir()
    legacy.mkdir()
    monkeypatch.setenv(rd.ENV_KEY, str(canonical))
    monkeypatch.setenv(rd.LEGACY_ENV_KEY, str(legacy))
    assert rd.runtime_root() == canonical


# --------------------------------------------------------- resolution behaviour
def test_resolution_is_dynamic_not_import_time(monkeypatch, tmp_path: Path) -> None:
    """A module imported before a fixture must still see the test root.

    Import-time constants are precisely why the old stores could not be
    redirected from a fixture.
    """
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv(rd.ENV_KEY, str(a))
    assert rd.store_path("x.jsonl").parent == a
    monkeypatch.setenv(rd.ENV_KEY, str(b))
    assert rd.store_path("x.jsonl").parent == b


def test_use_test_root_redirects_everything(monkeypatch, tmp_path: Path) -> None:
    rd.use_test_root(tmp_path)
    assert rd.store_path("suppression.jsonl").parent == tmp_path


def test_lock_sits_beside_its_ledger(monkeypatch, tmp_path: Path) -> None:
    """A lock elsewhere coordinates nothing across five containers."""
    rd.use_test_root(tmp_path)
    ledger = rd.store_path("email_suppression.jsonl")
    lock = rd.lock_path("email_suppression.jsonl")
    assert lock.parent == ledger.parent
    assert str(lock).startswith(str(ledger))


# --------------------------------------------------------------- path traversal
@pytest.mark.parametrize("evil", ["..", "../etc", "a/b", "a\\b", ".", ""])
def test_unsafe_tenant_segments_rejected(monkeypatch, tmp_path: Path, evil: str) -> None:
    """Tenant ids reach filenames; `../../etc` must not escape the root."""
    rd.use_test_root(tmp_path)
    with pytest.raises(rd.RuntimeDataError):
        rd.store_path("content_queue", evil)


def test_normal_tenant_segment_allowed(monkeypatch, tmp_path: Path) -> None:
    rd.use_test_root(tmp_path)
    p = rd.store_path("content_queue", "jiya-makeover.jsonl")
    assert p == tmp_path / "content_queue" / "jiya-makeover.jsonl"


def test_store_dir_creates(monkeypatch, tmp_path: Path) -> None:
    rd.use_test_root(tmp_path)
    d = rd.store_dir("delivery_ledger")
    assert d.is_dir()


# --------------------------------------------------------------------- describe
def test_describe_exposes_no_secrets(monkeypatch, tmp_path: Path) -> None:
    rd.use_test_root(tmp_path)
    info = rd.describe()
    assert info["root"] == str(tmp_path)
    assert info["inside_checkout"] is False
    blob = " ".join(str(v) for v in info.values()).lower()
    for leak in ("password", "secret", "token", "api_key"):
        assert leak not in blob


def test_describe_reports_error_instead_of_raising(monkeypatch) -> None:
    _prod(monkeypatch)
    info = rd.describe()
    assert "error" in info
