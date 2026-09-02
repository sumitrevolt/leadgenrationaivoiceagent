"""Resolve Docker APP_VERSION pin for VPS recreate (ADR-097).

Never return ``latest`` — that tags UNKNOWN provenance and caused a live skew
when Automation-Max flags were flipped (2026-07-25).
"""

from __future__ import annotations

import os
import subprocess


def resolve_app_version_pin(
    *,
    env: dict[str, str] | None = None,
    inspect_image: str | None = None,
) -> str:
    """Return a non-latest image tag to pass as APP_VERSION.

    Order:
    1. ``LEADGEN_APP_VERSION`` env override
    2. Explicit ``inspect_image`` (``repo:tag`` or bare tag) — for tests
    3. ``docker inspect leadgen_app`` Config.Image tag
    """
    e = env if env is not None else os.environ
    pin = (e.get("LEADGEN_APP_VERSION") or "").strip()
    if pin and pin != "latest":
        return pin

    image = inspect_image
    if image is None:
        try:
            image = subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.Config.Image}}",
                    "leadgen_app",
                ],
                text=True,
            ).strip()
        except Exception:
            image = ""

    if image and ":" in image:
        pin = image.rsplit(":", 1)[-1].strip()
    elif image:
        pin = image.strip()

    if not pin or pin == "latest":
        raise SystemExit(
            "REFUSED recreate: APP_VERSION pin missing or :latest. "
            "Set LEADGEN_APP_VERSION=<sha> then re-run "
            "(after .env write already done — flags are saved)."
        )
    return pin
