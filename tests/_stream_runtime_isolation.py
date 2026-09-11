"""Structural (autouse) isolation for SmartFlo WS-stream tests.

Why this exists (2026-09-10 regression)
---------------------------------------
A P0 compliance fix made ``smartflo_stream._persist_opt_out`` actually call
``consent_ledger.record_opt_out`` (it previously imported names that do not
exist — ``ConsentAction`` / ``persist_opt_out`` — so the ``ImportError`` was
swallowed by ``except Exception: pass`` and press-9 opt-outs were never
recorded). Separately ``_cleanup`` now really calls
``post_call_hooks.finalize_stream_session``.

Both production fixes are correct and MUST stay. But they turned previously
inert tests into writers of REAL on-disk runtime data:

* ``data/consent_ledger.jsonl``  <- ``record_opt_out``
* ``data/interactions.jsonl``    <- ``finalize_stream_session`` ->
  ``persist_call_log`` -> ``interaction_log.record``
* ``data/call_transcripts/``     <- ``smartflo_stream._persist_transcript``

One polluted ledger row for ``+919876543210`` was enough to make the unrelated
``test_telephony_upgrades.py::test_compliance_fails_closed_on_unverified_dnd``
see ``opted_out`` instead of ``dnd_lookup_failed``.

The fix is therefore structural, not per-test: every stream test gets
in-memory stand-ins by default, so no test path can reach a real writer even if
somebody adds a new ``_cleanup()``-reaching test later.

Opting back in
--------------
Tests that exist specifically to assert on one of these calls already patch the
target themselves with ``unittest.mock.patch`` — an inner patch simply wins for
the duration of its ``with`` block, so there is no fight with the autouse
fixture. The one case that needs the REAL ``finalize_stream_session`` (it
asserts the metering kwargs produced by that whole chain) carries the
``real_finalize_stream_session`` marker; even then every downstream disk writer
is redirected to memory.

Nothing here weakens a compliance gate: the fakes record the call (so an
assertion on "was it called / with what" still works) instead of dropping it.
"""

from __future__ import annotations

from typing import Any

#: Marker for tests that deliberately exercise the real finalize chain.
BYPASS_MARKER = "real_finalize_stream_session"

_CONSENT_LEDGER = "app.telephony.consent_ledger"
_POST_CALL_HOOKS = "app.telephony.post_call_hooks"
_SMARTFLO_STREAM = "app.telephony.smartflo_stream"
_INTERACTION_LOG = "app.platform.interaction_log"
_OBJECTION_EXTRACTOR = "app.platform.objection_extractor"
_VOICE_FOLLOWUP = "app.telephony.voice_followup"
_OUTBOUND_WEBHOOKS = "app.platform.outbound_webhooks"


class RecordedWriters:
    """In-memory capture of every runtime write the stream path would have made.

    Exposed to tests via the ``_isolate_stream_runtime_writers`` fixture so a
    test can assert on the EFFECT (what would have been persisted) without any
    of it touching disk.
    """

    def __init__(self) -> None:
        self.opt_outs: list[dict[str, Any]] = []
        self.finalized: list[dict[str, Any]] = []
        self.interactions: list[dict[str, Any]] = []
        self.transcripts: list[dict[str, Any]] = []
        self.followups: list[dict[str, Any]] = []
        self.webhooks: list[dict[str, Any]] = []

    @property
    def opt_out_phones(self) -> list[str]:
        """Phones that would have been written to the consent ledger."""
        return [row["phone"] for row in self.opt_outs]

    def clear(self) -> None:
        """Drop everything recorded so far (self-documenting test helper)."""
        self.opt_outs.clear()
        self.finalized.clear()
        self.interactions.clear()
        self.transcripts.clear()
        self.followups.clear()
        self.webhooks.clear()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<RecordedWriters opt_outs={len(self.opt_outs)} "
            f"finalized={len(self.finalized)} interactions={len(self.interactions)} "
            f"transcripts={len(self.transcripts)}>"
        )


def _set(monkeypatch: Any, target: str, value: Any) -> bool:
    """Monkeypatch ``module.attr`` by dotted path. Returns True if applied.

    Returns False (never raises) when the module or the attribute is absent, so
    an optional dependency can never break collection of a whole test file.
    """
    try:
        monkeypatch.setattr(target, value, raising=False)
        return True
    except Exception:
        return False


def install(
    monkeypatch: Any,
    *,
    allow_real_finalize: bool = False,
    tmp_path: Any = None,
) -> RecordedWriters:
    """Patch every on-disk runtime writer the stream path can reach.

    Args:
        monkeypatch: the pytest ``monkeypatch`` fixture of the current test.
        allow_real_finalize: keep the REAL ``finalize_stream_session`` (only for
            tests marked ``real_finalize_stream_session``); its own downstream
            writers are still neutralised.
        tmp_path: when given, per-call transcript JSON is redirected here.

    Returns:
        The :class:`RecordedWriters` that captured everything in memory.
    """
    rec = RecordedWriters()

    # -- 1. consent ledger (press-9 opt-out, TCCCPR) ------------------------ #
    def _fake_record_opt_out(
        phone: str,
        reason: str = "",
        channel: str = "",
        call_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        rec.opt_outs.append(
            {
                "phone": phone,
                "reason": reason,
                "channel": channel,
                "call_id": call_id,
                **kwargs,
            }
        )
        return {"ok": True, "suppressed": True}

    _set(monkeypatch, f"{_CONSENT_LEDGER}.record_opt_out", _fake_record_opt_out)

    # -- 2. analytics row: app/platform/interaction_log.py -> data/interactions.jsonl
    # ALWAYS patched, not just in the allow_real_finalize branch. vobiz_stream
    # calls `interaction_log.record` DIRECTLY (vobiz_stream.py:3345), bypassing
    # finalize_stream_session entirely — so faking finalize alone still leaked
    # one real row per run into data/interactions.jsonl.
    async def _fake_interaction_record(**kwargs: Any) -> None:
        rec.interactions.append(dict(kwargs))

    _set(monkeypatch, f"{_INTERACTION_LOG}.record", _fake_interaction_record)

    # -- 3. end-of-call finalize / billing ---------------------------------- #
    if allow_real_finalize:
        _neutralize_finalize_downstream(monkeypatch, rec)
    else:

        async def _fake_finalize_stream_session(
            history: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> bool:
            rec.finalized.append({"history": list(history or []), **kwargs})
            return True

        _set(
            monkeypatch,
            f"{_POST_CALL_HOOKS}.finalize_stream_session",
            _fake_finalize_stream_session,
        )

    # -- 4. per-call transcript JSON (smartflo_stream._persist_transcript) --- #
    if tmp_path is not None:
        _dir = str(tmp_path)

        def _fake_transcripts_dir() -> str:
            return _dir

        _set(monkeypatch, f"{_SMARTFLO_STREAM}._call_transcripts_dir", _fake_transcripts_dir)

    return rec


def _neutralize_finalize_downstream(monkeypatch: Any, rec: RecordedWriters) -> None:
    """Keep the REAL ``finalize_stream_session`` but stop it touching data/.

    Used by the marked metering contract test, which must observe the real
    ``finalize_stream_session`` -> ``meter_call_completion`` kwargs. Only the
    disk writers inside that chain are replaced.
    """

    def _fake_persist_transcript(
        history: list[dict[str, Any]], **kwargs: Any
    ) -> None:
        rec.transcripts.append({"history": list(history or []), **kwargs})

    async def _fake_extract(history: list[dict[str, Any]], **kwargs: Any) -> None:
        return None

    async def _fake_followups(**kwargs: Any) -> None:
        rec.followups.append(dict(kwargs))

    async def _fake_webhook_emit(event: str, payload: dict, client_id: str = "") -> None:
        rec.webhooks.append({"event": event, "payload": dict(payload), "client_id": client_id})

    # `interaction_log.record` is already neutralised by install() — see the
    # "ALWAYS patched" note there; do not re-patch it here.
    _set(monkeypatch, f"{_POST_CALL_HOOKS}.persist_transcript", _fake_persist_transcript)
    _set(
        monkeypatch,
        f"{_OBJECTION_EXTRACTOR}.extract_from_transcript",
        _fake_extract,
    )
    _set(
        monkeypatch,
        f"{_VOICE_FOLLOWUP}.run_post_call_workflows",
        _fake_followups,
    )
    # 2026-09-10: finalize_stream_session now emits the customer-facing
    # "call_completed" webhook. Without this the real emit fires on every run of
    # the marked metering test.
    _set(monkeypatch, f"{_OUTBOUND_WEBHOOKS}.emit", _fake_webhook_emit)


def install_fixture(request: Any, monkeypatch: Any, tmp_path: Any) -> RecordedWriters:
    """Fixture body shared by every stream test module.

    Honours the ``real_finalize_stream_session`` marker on the test item.
    """
    allow_real = False
    get_marker = getattr(getattr(request, "node", None), "get_closest_marker", None)
    if get_marker is not None:
        allow_real = get_marker(BYPASS_MARKER) is not None
    return install(monkeypatch, allow_real_finalize=allow_real, tmp_path=tmp_path)
