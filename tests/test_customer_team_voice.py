"""ADR-009 product split — /api/customer/team is product-aware.

A voice-only customer must see the VOICE roster (Swara/Ananya/Meera + Boss) with
call-based activity, NEVER the marketing roster (Isha/Rohan/Dev). Marketing and
combo clients keep the existing marketing team (regression guard).
"""

from app.api import customer_dashboard as CD


def test_voice_team_response_roster_and_metrics():
    resp = CD._voice_team_response(
        client_id="c1",
        client_rec={"product": "voice", "business_name": "Test Salon"},
        total_leads=5,
        hot=2,
        has_profile=True,
        niche="salon",
    )
    keys = [a.key for a in resp.agents]
    # voice roster only — NO marketing agents leak in
    assert {"swara", "ananya", "meera", "manager"}.issubset(set(keys))
    assert not ({"isha", "rohan", "dev"} & set(keys))
    # Swara is actively calling when there are hot leads
    swara = next(a for a in resp.agents if a.key == "swara")
    assert swara.status == "working"
    assert "call" in swara.metric.lower()
    assert resp.total_today == 5


def test_voice_team_response_empty_state_is_never_blank():
    resp = CD._voice_team_response(
        client_id="demo",
        client_rec=None,
        total_leads=0,
        hot=0,
        has_profile=False,
        niche="",
    )
    keys = [a.key for a in resp.agents]
    assert keys == ["swara", "ananya", "meera", "manager"]
    assert resp.is_sample_data is True  # no client record + nothing today
    # every agent always shows a task line (no blank cards)
    assert all(a.task for a in resp.agents)


def test_get_customer_team_branches_on_product(monkeypatch):
    # isolate from real data files — counts are irrelevant; roster is what we assert
    monkeypatch.setattr(CD, "_inquiries_for_client", lambda cid, rec: [])

    # voice client -> voice roster
    monkeypatch.setattr(CD, "_client_record", lambda cid: {"product": "voice"})
    vkeys = [a.key for a in CD.get_customer_team(client_id="vclient").agents]
    assert "swara" in vkeys and "isha" not in vkeys

    # marketing client -> marketing roster (unchanged behaviour)
    monkeypatch.setattr(CD, "_client_record", lambda cid: {"product": "marketing"})
    mkeys = [a.key for a in CD.get_customer_team(client_id="mclient").agents]
    assert "isha" in mkeys and "swara" not in mkeys

    # combo client -> marketing roster (combo falls through, NOT voice)
    monkeypatch.setattr(CD, "_client_record", lambda cid: {"product": "combo"})
    ckeys = [a.key for a in CD.get_customer_team(client_id="cclient").agents]
    assert "isha" in ckeys and "swara" not in ckeys
