"""model_signing — HMAC-SHA256 sidecar for pickled ML models (ADR-002 close).

Contract under test (asymmetric by design):
- no MODEL_SIGNING_KEY            → verify True  (fail-OPEN, feature inert)
- key set, no sidecar             → verify True  (fail-OPEN, legacy models)
- key set, sidecar matches        → verify True
- key set, sidecar MISMATCH       → verify False (fail-CLOSED — tampered pickle = RCE)

Hermetic: tmp_path files only; env via monkeypatch. Never touches data/models.

Run: .venv\\Scripts\\python.exe -m pytest tests/test_model_signing.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ml import model_signing as ms


@pytest.fixture()
def model_file(tmp_path: Path) -> Path:
    p = tmp_path / "intent_classifier_latest.pkl"
    p.write_bytes(b"\x80\x04fake-pickle-bytes-for-hmac-test")
    return p


def test_no_key_is_inert_fail_open(monkeypatch: pytest.MonkeyPatch, model_file: Path) -> None:
    monkeypatch.delenv("MODEL_SIGNING_KEY", raising=False)
    assert ms.signing_enabled() is False
    assert ms.sign_file(model_file) is False  # nothing written
    assert not Path(str(model_file) + ".sig").exists()
    assert ms.verify_file(model_file) is True  # fail-open


def test_sign_then_verify_roundtrip(monkeypatch: pytest.MonkeyPatch, model_file: Path) -> None:
    monkeypatch.setenv("MODEL_SIGNING_KEY", "test-secret-key")
    assert ms.signing_enabled() is True
    assert ms.sign_file(model_file) is True
    sig = Path(str(model_file) + ".sig")
    assert sig.is_file() and len(sig.read_text().strip()) == 64  # sha256 hex
    assert ms.verify_file(model_file) is True


def test_missing_sidecar_fail_open_with_key(
    monkeypatch: pytest.MonkeyPatch, model_file: Path
) -> None:
    monkeypatch.setenv("MODEL_SIGNING_KEY", "test-secret-key")
    assert ms.verify_file(model_file) is True  # legacy unsigned model keeps working


def test_tampered_model_fail_closed(monkeypatch: pytest.MonkeyPatch, model_file: Path) -> None:
    monkeypatch.setenv("MODEL_SIGNING_KEY", "test-secret-key")
    assert ms.sign_file(model_file) is True
    model_file.write_bytes(b"\x80\x04EVIL-tampered-bytes")  # attacker rewrites pickle
    assert ms.verify_file(model_file) is False  # REFUSE the load


def test_tampered_sidecar_fail_closed(monkeypatch: pytest.MonkeyPatch, model_file: Path) -> None:
    monkeypatch.setenv("MODEL_SIGNING_KEY", "test-secret-key")
    assert ms.sign_file(model_file) is True
    Path(str(model_file) + ".sig").write_text("0" * 64, encoding="utf-8")
    assert ms.verify_file(model_file) is False


def test_wrong_key_fail_closed(monkeypatch: pytest.MonkeyPatch, model_file: Path) -> None:
    monkeypatch.setenv("MODEL_SIGNING_KEY", "key-one")
    assert ms.sign_file(model_file) is True
    monkeypatch.setenv("MODEL_SIGNING_KEY", "key-two")  # rotated w/o re-sign
    assert ms.verify_file(model_file) is False
