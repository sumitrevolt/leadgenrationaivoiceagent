"""A9 ratchet — call recordings/transcripts must stay migrated.

A1–A8 moved telephony kill switches, compliance ledgers, delivery, billing,
ops telemetry, prospects, and external missions. A9 clears the last LEGACY
deploy blockers:

  * artifacts.call_recordings — data/call_recordings/ + data/call_transcripts/
  * telephony.call_recordings — data/recordings/ (RECORDINGS_DIR override)

Shared resolvers live in ``app/platform/runtime_recording_paths.py``. Writer
modules call those (or thin wrappers) at operation time — never import-time
Path/str constants.

Two properties the repo-wide debt ratchet cannot give:

  * the A9 writer modules carry ZERO uncontrolled in-checkout runtime paths
    for the migrated stores (survivors must be named in OUT_OF_SCOPE);
  * resolvers are functions, not import-time Path/str constants.

Nothing here enables dial/WA/voice, writes a marker, or copies host bytes.
Blockers stay at 21 until a separate CUTOVER_COMPLETE host step.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.platform import runtime_data_allowlist as allowlist
from app.platform import runtime_data_baseline as baseline
from app.platform import runtime_data_manifest as manifest
from tests.runtime_data_waves import A9_STORE_IDS
from tests.test_runtime_data_a1_ratchet import (
    EXPECTED_ALLOWLIST_ENTRIES,
    EXPECTED_BASELINE_FINGERPRINTS,
    EXPECTED_BLOCKERS,
    _uncontrolled_path_findings,
)

REPO = Path(__file__).resolve().parents[1]

#: Production writer / reader modules for the two A9 stores.
A9_MODULES = (
    "app/platform/runtime_recording_paths.py",
    "app/telephony/voice_launch.py",
    "app/telephony/consent_ledger.py",
    "app/voice_agent/web_call_store.py",
    "app/api/call_recordings.py",
    "app/api/web_call.py",
    "app/api/web_call_admin.py",
    "app/telephony/post_call_hooks.py",
    "app/telephony/vobiz_stream.py",
    "app/platform/call_insights.py",
    "app/agents/live_eval.py",
    "app/voice_agent/stt_eval.py",
    "app/agents/staff.py",
    "app/platform/conversations.py",
    "app/api/admin_ops.py",
    "app/agents/campaign_optimizer.py",
    "app/platform/objection_extractor.py",
    "app/platform/team.py",
)

#: Resolver entry points each module must expose as functions.
A9_RESOLVERS = {
    "app/platform/runtime_recording_paths.py": (
        "call_recordings_dir",
        "call_transcripts_dir",
        "telephony_recordings_dir",
    ),
    "app/telephony/voice_launch.py": ("_recordings_dir",),
    "app/telephony/consent_ledger.py": ("recordings_dir",),
    "app/voice_agent/web_call_store.py": ("_TRANSCRIPTS_DIR",),
    "app/api/call_recordings.py": ("_REC_DIR",),
    "app/api/web_call.py": ("_CALL_RECORDINGS_DIR",),
    "app/api/web_call_admin.py": ("_CALL_RECORDINGS_DIR",),
    "app/telephony/post_call_hooks.py": ("_CALL_TRANSCRIPTS_DIR",),
    "app/telephony/vobiz_stream.py": ("_CALL_TRANSCRIPTS_DIR", "_CALL_RECORDINGS_DIR"),
    "app/platform/call_insights.py": ("_TRANSCRIPTS_DIR",),
    "app/agents/live_eval.py": ("_TRANSCRIPTS_DIR",),
    "app/voice_agent/stt_eval.py": ("_TRANSCRIPTS",),
    "app/agents/staff.py": ("_TRANSCRIPTS_DIR",),
    "app/platform/conversations.py": ("_CALL_TRANSCRIPTS_DIR",),
    "app/api/admin_ops.py": ("_call_transcripts_root",),
    "app/agents/campaign_optimizer.py": ("_call_transcripts",),
    "app/platform/objection_extractor.py": (),
    "app/platform/team.py": ("_call_transcripts_dir",),
}

#: Retired import-time constants. Reintroducing them as Assign is a defect.
RETIRED_CONSTANTS = (
    "RECORDINGS_DIR",
    "_REC_DIR",
    "_TRANSCRIPTS_DIR",
    "_TRANSCRIPTS",
    "_CALL_TRANSCRIPTS_DIR",
    "_CALL_RECORDINGS_DIR",
)

#: Paths that live in an A9 module but belong to a store A9 did NOT migrate.
#: Fat on purpose — several modules host unrelated ops paths beside recordings.
OUT_OF_SCOPE: dict[str, dict[str, str]] = {
    "app/platform/runtime_recording_paths.py": {},
    "app/telephony/voice_launch.py": {},
    "app/telephony/consent_ledger.py": {},
    "app/voice_agent/web_call_store.py": {
        "data/web_call_sessions.jsonl": "web-call session log (not A9 recordings)",
    },
    "app/api/call_recordings.py": {},
    "app/api/web_call.py": {
        "data": "parent mkdir / join root for non-recording paths",
    },
    "app/api/web_call_admin.py": {},
    "app/telephony/post_call_hooks.py": {
        "data": "parent mkdir for qualifications JSONL",
        "data/call_qualifications.jsonl": "post-call qualify log (not A9)",
    },
    "app/telephony/vobiz_stream.py": {
        "data": "parent mkdir / join root for non-recording paths",
        "data/call_qualifications.jsonl": "auto-qualify JSONL (not A9)",
        "data/voice_selfimprove_counter.json": "self-improve counter (not A9)",
    },
    "app/platform/call_insights.py": {
        "data/cadence_runs.jsonl": "A6 store — insights reads it, A9 does not own it",
        "data/call_qualifications.jsonl": "qualify log (not A9)",
        "data/dialer_logs.jsonl": "human dialer log (not A9)",
    },
    "app/agents/live_eval.py": {},
    "app/voice_agent/stt_eval.py": {},
    "app/agents/staff.py": {
        "data": "parent mkdir for trainer suggestions",
        "data/content_feedback.jsonl": "ops rotation list (not A9)",
        "data/daily_digest.txt": "ops digest artifact (not A9)",
        "data/daily_owner_brief.txt": "ops owner brief artifact (not A9)",
        "data/inquiries.jsonl": "digest inquiry count (not A9)",
        "data/reply_drafts.jsonl": "ops rotation list (not A9)",
        "data/self_improve_runs.jsonl": "ops rotation list (not A9)",
        "data/trainer_suggestions.jsonl": "trainer suggestions (not A9)",
    },
    "app/platform/conversations.py": {
        "data/cadence_runs.jsonl": "A6 store — inbox aggregate only",
        "data/conversation_replies.jsonl": "manual reply drafts (not A9)",
        "data/inquiries.jsonl": "public inquiries (not A9)",
        "data/interactions.jsonl": "A6 store — inbox aggregate only",
        "data/reply_drafts.jsonl": "reply drafts (not A9)",
        "data/widget_chats.jsonl": "widget chats (not A9)",
    },
    "app/api/admin_ops.py": {
        "data/voice_training_proposals.jsonl": "training proposals (not A9)",
    },
    "app/agents/campaign_optimizer.py": {
        "data/cadence_runs.jsonl": "A6 store — interaction counter input",
        "data/campaign_optimization": "optimizer own store (not A9)",
        "data/channel_outcomes.jsonl": "channel outcomes (not A9)",
        "data/content_feedback.jsonl": "content feedback (not A9)",
        "data/reply_drafts.jsonl": "reply drafts (not A9)",
    },
    "app/platform/objection_extractor.py": {
        "data": "parent mkdir for patterns JSONL",
        "data/objection_patterns.jsonl": "objection patterns store (not A9)",
    },
    "app/platform/team.py": {
        "data/content_queue": "A4 content.queue — pulse status only",
        "data/harvest_runs.jsonl": "harvest runs (not A9)",
        "data/job_heartbeats.json": "A6 job heartbeats — SRE pulse only",
        "data/prospects.jsonl": "A7 sales.prospects — pulse status only",
    },
}


# ------------------------------------------------------------------- code
@pytest.mark.parametrize("module_path", A9_MODULES)
def test_a9_writer_modules_have_zero_uncontrolled_runtime_paths(module_path):
    declared = OUT_OF_SCOPE.get(module_path, {})
    observed = {value for _, value in _uncontrolled_path_findings(module_path)}

    undeclared = sorted(observed - set(declared))
    assert not undeclared, f"{module_path} still opens an unclassified checkout path: {undeclared}"

    stale = sorted(set(declared) - observed)
    assert not stale, (
        f"{module_path}: {stale} no longer appears — delete the exclusion rather "
        "than leaving a hole the next literal can hide in"
    )


@pytest.mark.parametrize("module_path", A9_MODULES)
def test_a9_modules_resolve_at_call_time_not_import_time(module_path):
    """The resolver must be a function, and no module-level Assign may hold a
    retired constant name for a migrated store.
    """
    tree = ast.parse((REPO / module_path).read_text(encoding="utf-8"))

    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    for resolver in A9_RESOLVERS[module_path]:
        assert resolver in functions, f"{module_path} must expose {resolver}() as a function"

    def _module_level(body: list[ast.stmt]):
        for node in body:
            yield node
            if isinstance(node, ast.If | ast.Try):
                yield from _module_level(node.body)
                yield from _module_level(getattr(node, "orelse", []))
                yield from _module_level(getattr(node, "finalbody", []))
                for handler in getattr(node, "handlers", []):
                    yield from _module_level(handler.body)

    for node in _module_level(tree.body):
        targets: list[str] = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        for name in targets:
            assert name not in RETIRED_CONSTANTS, (
                f"{module_path} reintroduced module-level {name} — a path frozen "
                "at import cannot follow a cutover"
            )


def test_a9_shared_resolvers_use_override_env_for_telephony():
    """telephony.call_recordings must keep RECORDINGS_DIR override precedence."""
    src = (REPO / "app/platform/runtime_recording_paths.py").read_text(encoding="utf-8")
    assert 'override_env="RECORDINGS_DIR"' in src
    assert 'store_id="telephony.call_recordings"' in src
    assert 'store_id="artifacts.call_recordings"' in src


# --------------------------------------------------------------- manifest
def test_the_a9_rows_are_still_dual_read():
    """A9's own rows, asserted by A9's own file.

    Subset only — the exact global set is asserted once in
    ``test_runtime_data_waves.py`` as the union of every declared wave.
    """
    moved = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert set(A9_STORE_IDS) <= moved, set(A9_STORE_IDS) - moved


def test_manifest_still_validates():
    assert manifest.validate() == []


def test_migrating_the_code_does_not_reduce_the_blocker_count():
    """Migrated stores, and the count is still 21 — that is the honest answer.

    Writers can now follow a cutover; authoritative bytes are still inside the
    checkout (~182 MB recordings). A count that fell here would be a false green.
    """
    blocking = manifest.blocking_stores()
    assert len(blocking) == EXPECTED_BLOCKERS, sorted(s["store_id"] for s in blocking)
    assert not blocking
    assert manifest.DUAL_READ_PRE_CUTOVER in manifest.BLOCKING_STATES
    assert manifest.CUTOVER_COMPLETE not in manifest.BLOCKING_STATES


def test_no_allowlist_or_baseline_relaxation():
    """The migration must not buy its green by loosening a neighbouring control."""
    assert len(allowlist.load()) == EXPECTED_ALLOWLIST_ENTRIES
    assert len(baseline.ENTRIES) == EXPECTED_BASELINE_FINGERPRINTS
