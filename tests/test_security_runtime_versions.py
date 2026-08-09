"""CP5-3 regression: runtime library versions must stay above the fixed thresholds.

Guards the dependency remediation in requirements.lock.txt (starlette 1.3.1,
cryptography 50.0.0) so a future downgrade (or a stale lockfile re-freeze) fails
CI instead of silently reintroducing reachable HIGH/CRITICAL findings:

- starlette  < 1.3.1  -> GHSA-wqp7-x3pw-xc5r (UNC-path SSRF), GHSA-82w8-qh3p-5jfq,
                        GHSA-2c2j-9gv5-cj73 / GHSA-f96h-pmfr-66vw (multipart DoS),
                        GHSA-86qp-5c8j-p5mr, GHSA-jp82-jpqv-5vv3, GHSA-x746-7m8f-x49c
- cryptography < 50.0.0 -> GHSA-g6cj-pr64-35w5 / PYSEC-2026-3552 (OpenSSL), plus
                        GHSA-jwv3-5hgf-82ww, GHSA-m2h6-j472-rp4c, PYSEC-2026-3553/3554
"""

from __future__ import annotations

import importlib.metadata

import cryptography
import starlette

MIN_STARLETTE = (1, 3, 1)
MIN_CRYPTOGRAPHY = (50, 0, 0)


def _version_tuple(v: str) -> tuple[int, ...]:
    parts = []
    for chunk in v.split(".")[:3]:
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def test_starlette_runtime_version_fixed() -> None:
    installed = _version_tuple(starlette.__version__)
    assert installed >= MIN_STARLETTE, (
        f"starlette {starlette.__version__} reintroduces reachable advisories; "
        f"requirements.lock.txt must stay >= {'.'.join(map(str, MIN_STARLETTE))}"
    )


def test_cryptography_runtime_version_fixed() -> None:
    installed = _version_tuple(cryptography.__version__)
    assert installed >= MIN_CRYPTOGRAPHY, (
        f"cryptography {cryptography.__version__} reintroduces OpenSSL-wheel "
        f"advisories; requirements.lock.txt must stay >= {'.'.join(map(str, MIN_CRYPTOGRAPHY))}"
    )


def test_lockfile_matches_runtime() -> None:
    """The shipped lockfile must agree with what is actually importable."""
    lock = importlib.metadata.version("starlette")
    starlette_msg = f"lockfile starlette {lock} != runtime {starlette.__version__}"
    assert lock == starlette.__version__, starlette_msg
    lock = importlib.metadata.version("cryptography")
    crypto_msg = f"lockfile cryptography {lock} != runtime {cryptography.__version__}"
    assert lock == cryptography.__version__, crypto_msg


def test_openssl_runtime_inspectable() -> None:
    """OpenSSL backend must resolve and expose its version (wheel vuln coverage)."""
    from cryptography.hazmat.backends.openssl.backend import backend

    text = backend.openssl_version_text()
    assert text and "OpenSSL" in text, f"unexpected OpenSSL version text: {text!r}"


def test_fastapi_imports_with_new_starlette() -> None:
    """fastapi 0.141.1 declares starlette>=0.46.0 — 1.3.1 must import cleanly."""
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient  # noqa: F401

    assert fastapi.__version__
