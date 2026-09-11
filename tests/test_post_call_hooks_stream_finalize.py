"""Regression: `finalize_stream_session` provider labelling + customer webhook.

Two defects fixed 2026-09-10, both on the SmartFlo (and any) WS-stream cleanup path:

1. **Analytics mislabel.** `persist_call_log` was called with a hardcoded
   `provider="phone"`, so a Smartflo call was indistinguishable from every other
   stream session in the `call_logs` table. Vobiz passes `provider="vobiz"`
   (`vobiz_stream.py:3374`); Smartflo had no way to say who it was. Fixed by
   adding a `provider` parameter (default `"phone"`, so existing callers are
   unchanged) and threading `"tata_smartflo"` through from `smartflo_stream`.

2. **Missing customer webhook.** Vobiz emits `outbound_webhooks.emit("call_completed", ...)`
   from its own cleanup (`vobiz_stream.py:3327`). This helper did not, so a
   Smartflo call never reached a customer's subscribed `call_completed` endpoint
   — silently, because the failure lived inside a swallowed `except`.

These tests patch every collaborator, so nothing touches a DB, Redis or disk.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.telephony import post_call_hooks as pch

_HISTORY = [
    {"role": "assistant", "content": "Namaste, main AI assistant bol rahi hoon."},
    {"role": "user", "content": "haan boliye"},
]


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class _FinalizeHarness:
    """Patch EVERY collaborator of finalize_stream_session.

    2026-09-10: the first version of this harness only patched four of them, so
    `interaction_log.record` (and friends) fired for real and appended 6 rows to
    the gitignored `data/interactions.jsonl` on every run. `finalize_stream_session`
    reaches a LOT of writers — patch all of them or you are writing to disk.
    Tests that need a specific behaviour (e.g. a throwing webhook emit) simply
    patch on top; the inner patch wins.
    """

    def __enter__(self):
        self.emitted: list[tuple] = []
        self.interactions: list[dict] = []

        async def _fake_emit(event, payload, client_id=""):
            self.emitted.append((event, payload, client_id))
            return None

        async def _fake_interaction(**kwargs):
            self.interactions.append(dict(kwargs))

        async def _noop(*a, **k):
            return None

        self.patches = {
            "persist_transcript": patch.object(pch, "persist_transcript", lambda *a, **k: None),
            "meter": patch.object(pch, "meter_call_completion", AsyncMock(return_value=True)),
            "qualify": patch.object(
                pch, "auto_qualify_and_downstream", AsyncMock(return_value={"qualified": True})
            ),
            "persist_call_log": patch.object(pch, "persist_call_log", AsyncMock(return_value=True)),
            # --- writers the first version missed ---------------------------- #
            "emit": patch("app.platform.outbound_webhooks.emit", new=_fake_emit),
            "interaction": patch("app.platform.interaction_log.record", new=_fake_interaction),
            "objection": patch(
                "app.platform.objection_extractor.extract_from_transcript", new=_noop
            ),
            "followups": patch(
                "app.telephony.voice_followup.run_post_call_workflows", new=_noop
            ),
        }
        self.mocks = {k: v.start() for k, v in self.patches.items()}
        return self

    def __exit__(self, *exc):
        for p in self.patches.values():
            p.stop()
        return False


class TestProviderLabelling(unittest.TestCase):
    def test_provider_is_passed_through_to_call_log(self):
        with _FinalizeHarness() as h:
            _run(
                pch.finalize_stream_session(
                    _HISTORY,
                    call_id="CA-1",
                    client_id="jiya-makeover",
                    phone="919876543210",
                    niche="salon_spa",
                    provider="tata_smartflo",
                )
            )
        kwargs = h.mocks["persist_call_log"].call_args.kwargs
        assert kwargs["provider"] == "tata_smartflo", kwargs

    def test_default_provider_stays_phone_for_back_compat(self):
        """Existing callers that pass nothing must not change behaviour."""
        with _FinalizeHarness() as h:
            _run(pch.finalize_stream_session(_HISTORY, call_id="CA-2"))
        kwargs = h.mocks["persist_call_log"].call_args.kwargs
        assert kwargs["provider"] == "phone", kwargs

    def test_empty_provider_falls_back_to_phone(self):
        with _FinalizeHarness() as h:
            _run(pch.finalize_stream_session(_HISTORY, call_id="CA-3", provider=""))
        kwargs = h.mocks["persist_call_log"].call_args.kwargs
        assert kwargs["provider"] == "phone", kwargs


class TestCallCompletedWebhook(unittest.TestCase):
    def test_emit_fires_with_provider_specific_source(self):
        emitted: list[tuple] = []

        async def _fake_emit(event, payload, client_id=""):
            emitted.append((event, payload, client_id))
            return None

        with _FinalizeHarness(), patch(
            "app.platform.outbound_webhooks.emit", new=_fake_emit
        ):
            _run(
                pch.finalize_stream_session(
                    _HISTORY,
                    call_id="CA-1",
                    client_id="jiya-makeover",
                    client_name="Jiya Makeover",
                    phone="919876543210",
                    niche="salon_spa",
                    started_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 9, 10, 12, 1, tzinfo=timezone.utc),
                    provider="tata_smartflo",
                )
            )

        assert len(emitted) == 1, f"expected exactly one webhook, got {emitted}"
        event, payload, client_id = emitted[0]
        assert event == "call_completed"
        assert payload["call_id"] == "CA-1"
        assert payload["source"] == "tata_smartflo_stream"
        assert payload["client_id"] == "jiya-makeover"
        assert payload["phone"] == "919876543210"
        assert payload["duration_seconds"] == 60
        assert client_id == "jiya-makeover"

    def test_emit_failure_is_logged_not_swallowed(self):
        """A customer webhook that never fires must be visible, not silent."""

        async def _boom(event, payload, client_id=""):
            raise RuntimeError("subscriber down")

        with _FinalizeHarness(), patch(
            "app.platform.outbound_webhooks.emit", new=_boom
        ), self.assertLogs("app.telephony.post_call_hooks", level="WARNING") as logs:
            _run(pch.finalize_stream_session(_HISTORY, call_id="CA-9"))

        assert any("call_completed webhook emit FAILED" in line for line in logs.output), logs.output

    def test_finalize_survives_a_broken_webhook_layer(self):
        """Emit throwing must not cost us the rest of the post-call work."""

        async def _boom(event, payload, client_id=""):
            raise RuntimeError("subscriber down")

        with _FinalizeHarness() as h, patch(
            "app.platform.outbound_webhooks.emit", new=_boom
        ):
            _run(pch.finalize_stream_session(_HISTORY, call_id="CA-10"))

        # metering + analytics still happened
        assert h.mocks["meter"].await_count == 1
        assert h.mocks["persist_call_log"].await_count == 1


if __name__ == "__main__":
    unittest.main()
