"""Batch-2 Agent A: blog alias honesty + event/on-demand team_status idle."""

from __future__ import annotations

from unittest.mock import patch

from app.platform import agent_registry as ar
from app.platform import team as team_mod
from app.platform.agent_controls import ALIAS_TO_MEMBER, _canon
from app.platform.agent_registry import EVENT_OR_ONDEMAND_ONLY


def test_blog_alias_resolves_to_isha():
    assert ALIAS_TO_MEMBER.get("blog") == "isha"
    assert _canon("blog") == "isha"
    assert _canon("isha") == "isha"


def test_blog_alias_drift_removed_from_known_drifts():
    loci = {d["locus"] for d in ar.KNOWN_DRIFTS}
    assert not any("ALIAS_TO_MEMBER['blog']" in x for x in loci)


def test_team_status_event_ondemand_idle_is_healthy_idle_not_offline():
    """No recent events -> EVENT_OR_ONDEMAND_ONLY members stay healthy_idle."""
    assert EVENT_OR_ONDEMAND_ONLY, "registry set must be non-empty"

    with patch.object(team_mod, "_db", return_value=None):
        status = team_mod.team_status()

    by_key = {m["key"]: m for m in status["members"]}
    sample = next(iter(EVENT_OR_ONDEMAND_ONLY))
    assert sample in by_key
    assert by_key[sample]["state"] == "healthy_idle"
    assert by_key[sample]["state"] != "offline"

    for aid in EVENT_OR_ONDEMAND_ONLY:
        if aid in by_key:
            assert by_key[aid]["state"] != "offline", aid
            assert by_key[aid]["state"] in (
                "healthy_idle",
                "working",
                "active",
            ), (aid, by_key[aid]["state"])


def test_team_status_scheduled_agent_still_offline_without_events():
    """Non-event agents keep offline default when no last activity."""
    # Pick a STAFF key that is not event/on-demand (kavya is scheduled ops).
    assert "kavya" not in EVENT_OR_ONDEMAND_ONLY
    with patch.object(team_mod, "_db", return_value=None):
        status = team_mod.team_status()
    by_key = {m["key"]: m for m in status["members"]}
    assert by_key["kavya"]["state"] == "offline"


def test_runtime_event_only_still_healthy_idle():
    """Neighbour contract: agent_runtime keeps healthy_idle naming."""
    from app.platform import agent_runtime as rt

    status = rt.runtime_status()
    by_id = {a["agent_id"]: a for a in status["agents"]}
    assert by_id["riya"]["event_or_ondemand_only"] is True
    assert by_id["riya"]["health"] == "healthy_idle"
