"""Regression: Smartflo typed settings must bind to the env vars production actually sets.

Background (2026-09-10): `app/config.py` gained additive typed mirrors of the
Tata Smartflo trunk settings. Three of them were named `tata_smartflo_*`, but the
live readers do NOT use a TATA_ prefix:

    app/api/telephony_smartflo.py:121  SMARTFLO_VOICE_STREAM_ENABLED
    app/api/telephony_smartflo.py:133  SMARTFLO_WS_SECRET
    app/api/telephony_smartflo.py:134  SMARTFLO_WS_REQUIRE_SECRET

With pydantic-settings (`case_sensitive = False`, no env_prefix) a field named
`tata_smartflo_voice_stream_enabled` binds to `TATA_SMARTFLO_VOICE_STREAM_ENABLED`
— an env var nobody ever sets. Any future `settings.<field>` reader would then
silently read the default (False / "") and keep the provider INERT even with the
real switch armed. That is a "configured but dead" state, which is exactly the
class of bug that is hardest to see in production.

The fix is `validation_alias=AliasChoices(REAL_NAME, TATA_NAME)`. These tests lock
that in: real name wins, TATA_ spelling still works, and defaults are unchanged
when nothing is set.
"""

import os
import unittest

from app.config import Settings

REAL_TO_FIELD = {
    "SMARTFLO_VOICE_STREAM_ENABLED": ("tata_smartflo_voice_stream_enabled", True),
    "SMARTFLO_WS_SECRET": ("tata_smartflo_ws_secret", "s3cret"),
    "SMARTFLO_WS_REQUIRE_SECRET": ("tata_smartflo_ws_require_secret", True),
}


def _build(env: dict[str, str]) -> Settings:
    """Instantiate Settings with only `env` visible for the three switches."""
    saved = {k: os.environ.pop(k, None) for k in list(REAL_TO_FIELD) + [
        "TATA_SMARTFLO_VOICE_STREAM_ENABLED",
        "TATA_SMARTFLO_WS_SECRET",
        "TATA_SMARTFLO_WS_REQUIRE_SECRET",
    ]}
    try:
        for k, v in env.items():
            os.environ[k] = v
        return Settings()
    finally:
        for k, v in env.items():
            os.environ.pop(k, None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


class TestSmartfloAliasBinding(unittest.TestCase):
    def test_real_env_name_binds(self):
        s = _build({
            "SMARTFLO_VOICE_STREAM_ENABLED": "1",
            "SMARTFLO_WS_SECRET": "s3cret",
            "SMARTFLO_WS_REQUIRE_SECRET": "1",
        })
        self.assertIs(s.tata_smartflo_voice_stream_enabled, True)
        self.assertEqual(s.tata_smartflo_ws_secret, "s3cret")
        self.assertIs(s.tata_smartflo_ws_require_secret, True)

    def test_tata_prefixed_fallback_still_binds(self):
        s = _build({
            "TATA_SMARTFLO_VOICE_STREAM_ENABLED": "true",
            "TATA_SMARTFLO_WS_SECRET": "fallback",
            "TATA_SMARTFLO_WS_REQUIRE_SECRET": "yes",
        })
        self.assertIs(s.tata_smartflo_voice_stream_enabled, True)
        self.assertEqual(s.tata_smartflo_ws_secret, "fallback")
        self.assertIs(s.tata_smartflo_ws_require_secret, True)

    def test_defaults_unchanged_when_unset(self):
        s = _build({})
        self.assertIs(s.tata_smartflo_voice_stream_enabled, False)
        self.assertEqual(s.tata_smartflo_ws_secret, "")
        self.assertIs(s.tata_smartflo_ws_require_secret, False)
        # untouched neighbours must keep their defaults
        self.assertEqual(s.tata_smartflo_weight, 50)
        self.assertEqual(s.tata_smartflo_cps_limit, 2)
        self.assertEqual(s.tata_smartflo_max_concurrent, 5)

    def test_real_name_wins_over_tata_spelling(self):
        s = _build({
            "SMARTFLO_WS_SECRET": "real",
            "TATA_SMARTFLO_WS_SECRET": "stale",
        })
        self.assertEqual(s.tata_smartflo_ws_secret, "real")


if __name__ == "__main__":
    unittest.main()
