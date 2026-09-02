"""CP5-3 regression: application startup + critical Product 1/Product 2 imports
survive the dependency upgrades (starlette 1.3.1, cryptography 50.0.0).

Runs against the FULL runtime environment (CI venv / built image) — not a delta
venv — because these modules import the app's real dependency graph.
"""

from __future__ import annotations

import importlib


def _import(module: str) -> None:
    importlib.import_module(module)


def test_app_main_starts() -> None:
    # Builds the FastAPI app (route wiring, mounts) — any import-time break from
    # the Starlette bump (route/mount/response APIs) surfaces here.
    import app.main  # noqa: F401


def test_product1_critical_imports() -> None:
    # Marketing product money-path + content engines (Product 1).
    import app.api.marketing  # noqa: F401
    import app.api.public_site  # noqa: F401
    import app.marketing.offers  # noqa: F401
    import app.marketing.packages  # noqa: F401
    import app.platform.upi_payments  # noqa: F401


def test_product2_critical_imports() -> None:
    # Voice product: telephony + free-stack AI chain (Product 2).
    import app.telephony.vobiz_stream  # noqa: F401
    import app.voice_agent.free_ai  # noqa: F401
    import app.voice_agent.telecaller_brain  # noqa: F401


def test_billing_and_auth_imports() -> None:
    import app.api.admin  # noqa: F401  # admin /auth/login
    import app.api.billing  # noqa: F401
    import app.api.customer_auth  # noqa: F401  # customer login/TOTP/magic-link
    import app.config  # noqa: F401  # app/config.py module (pydantic-settings)
