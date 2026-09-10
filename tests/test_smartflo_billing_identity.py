"""Regression: stream path and status webhook must resolve the SAME call id.

Why this matters (2026-09-10)
-----------------------------
`meter_call_completion` dedupes on ``call_meter:{call_id}``. Two different code
paths meter a Smartflo call:

* the status webhook  -> ``smartflo_webhooks.py:183``
  ``_pick(data, "call_id", "callId", "callid", "uuid", "id")``
* the media stream    -> ``smartflo_stream._extract_call_id`` (new)

If they resolve DIFFERENT ids for the same call, they use two distinct dedupe
keys and **the call is billed twice**.

The stream used to read only ``start.callSid`` / ``start.call_sid`` — a much
narrower set than the webhook's. Any other spelling left ``self.call_sid`` empty,
``_cleanup()`` fell back to ``stream_sid``, and the stream silently billed under
a key the webhook would never match. Fixed by sharing one key list.

The strongest guarantee here is not a hardcoded list — it is the invariant
"**every key the webhook accepts, the stream must also accept**", asserted below
by parsing the webhook's actual source. If someone adds a spelling to the webhook
and forgets the stream, this test fails.
"""

from __future__ import annotations

import re
import unittest

from app.telephony.smartflo_stream import _CALL_ID_KEYS, _extract_call_id


def _webhook_call_id_keys() -> list[str]:
    """Extract the key list the status webhook uses to resolve ``call_id``."""
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app"
        / "telephony"
        / "smartflo_webhooks.py"
    ).read_text(encoding="utf-8")

    match = re.search(r"call_id\s*=\s*str\(\s*_pick\(\s*data\s*,([^)]*)\)", src, re.S)
    if not match:  # pragma: no cover - guards a future refactor of the webhook
        raise AssertionError(
            "Could not locate the webhook call_id _pick(...) call — the parser "
            "must be updated when smartflo_webhooks.py changes shape."
        )
    args = match.group(1).split("default=")[0]
    pairs = re.findall(r'"([^"]*)"|\'([^\']*)\'', args)
    return [a or b for a, b in pairs]


class TestCallIdExtraction(unittest.TestCase):
    def test_known_spellings_resolve(self):
        for key in ("callSid", "call_sid", "callId", "call_id", "callid", "uuid", "id"):
            with self.subTest(key=key):
                self.assertEqual(_extract_call_id({}, {key: "CA-x"}), "CA-x")
                # ...and from the top level of the frame too
                self.assertEqual(_extract_call_id({key: "CA-y"}, {}), "CA-y")

    def test_start_wins_over_frame(self):
        got = _extract_call_id({"call_id": "frame"}, {"call_id": "start"})
        self.assertEqual(got, "start")

    def test_stream_sid_is_never_mistaken_for_a_call_id(self):
        """streamSid is NOT a billing identity — falling back to it is the
        double-billing risk, so it must resolve to '' (empty), not to 'MZ-9'."""
        self.assertEqual(_extract_call_id({}, {"streamSid": "MZ-9"}), "")
        self.assertEqual(_extract_call_id({"streamSid": "MZ-9"}, {}), "")

    def test_empty_payload_resolves_empty(self):
        self.assertEqual(_extract_call_id({}, {}), "")

    def test_blank_values_are_skipped(self):
        self.assertEqual(_extract_call_id({}, {"callSid": "   ", "call_id": "CA-ok"}), "CA-ok")

    def test_non_dict_sources_do_not_crash(self):
        self.assertEqual(_extract_call_id(None, None), "")  # type: ignore[arg-type]


class TestWebhookStreamKeyParity(unittest.TestCase):
    def test_stream_accepts_every_key_the_webhook_accepts(self):
        webhook_keys = _webhook_call_id_keys()
        self.assertTrue(
            webhook_keys,
            "Parsed an empty key list from the webhook — regex is broken, not the code.",
        )
        missing = [k for k in webhook_keys if k not in _CALL_ID_KEYS]
        self.assertFalse(
            missing,
            "smartflo_stream._CALL_ID_KEYS is missing key(s) the status webhook "
            f"accepts: {missing}. Same call, two dedupe keys => billed twice.",
        )

    def test_every_webhook_key_actually_resolves(self):
        """Parity of the CONSTANT is not enough — prove it resolves end to end."""
        for key in _webhook_call_id_keys():
            with self.subTest(key=key):
                self.assertEqual(_extract_call_id({}, {key: "CA-z"}), "CA-z")


if __name__ == "__main__":
    unittest.main()
