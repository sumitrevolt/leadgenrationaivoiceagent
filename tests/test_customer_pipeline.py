"""Pure unit tests for the customer Pipeline Kanban grouping logic.

NO network / NO DB / NO app startup — we import only the pure helper
``group_by_status`` from app.api.customer_pipeline and assert grouping/counts.
"""

from __future__ import annotations

from app.api.customer_pipeline import PIPELINE_COLUMNS, group_by_status


class _LeadObj:
    """Minimal stand-in for a LeadRow (object access, not dict)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_columns_are_the_six_allowed_statuses():
    assert PIPELINE_COLUMNS == ["Hot", "Warm", "Cold", "Follow-up", "Won", "Lost"]


def test_empty_input_returns_all_empty_columns():
    board = group_by_status([])
    assert board["columns"] == PIPELINE_COLUMNS
    assert all(board["leads_by_status"][c] == [] for c in PIPELINE_COLUMNS)
    assert all(board["counts"][c] == 0 for c in PIPELINE_COLUMNS)


def test_groups_dict_leads_by_status_with_counts():
    leads = [
        {
            "id": "1",
            "business": "A Solar",
            "status": "Hot",
            "phone": "98",
            "city": "Pune",
            "niche": "solar",
        },
        {"id": "2", "business": "B Dental", "status": "Hot"},
        {"id": "3", "business": "C", "status": "Won"},
        {"id": "4", "business": "D", "status": "Follow-up"},
    ]
    board = group_by_status(leads)
    assert board["counts"]["Hot"] == 2
    assert board["counts"]["Won"] == 1
    assert board["counts"]["Follow-up"] == 1
    assert board["counts"]["Cold"] == 0
    ids_hot = {c["id"] for c in board["leads_by_status"]["Hot"]}
    assert ids_hot == {"1", "2"}


def test_card_carries_business_phone_city_niche():
    board = group_by_status(
        [
            {
                "id": "1",
                "business": "A Solar",
                "status": "Cold",
                "phone": "98765",
                "city": "Pune",
                "niche": "solar",
            }
        ]
    )
    card = board["leads_by_status"]["Cold"][0]
    assert card["business"] == "A Solar"
    assert card["phone"] == "98765"
    assert card["city"] == "Pune"
    assert card["niche"] == "solar"
    assert card["status"] == "Cold"


def test_object_leads_supported():
    leads = [
        _LeadObj(id="9", business="Obj Co", status="Warm", phone="1", city="Goa", niche="hotel")
    ]
    board = group_by_status(leads)
    assert board["counts"]["Warm"] == 1
    assert board["leads_by_status"]["Warm"][0]["business"] == "Obj Co"


def test_status_is_case_insensitive():
    board = group_by_status([{"id": "1", "business": "X", "status": "follow-UP"}])
    assert board["counts"]["Follow-up"] == 1


def test_blank_status_falls_back_to_score_tier():
    # When status is empty, the AI tier (`score`) keeps the lead visible.
    board = group_by_status([{"id": "1", "business": "X", "status": "", "score": "Hot"}])
    assert board["counts"]["Hot"] == 1


def test_unknown_status_is_dropped_not_raised():
    board = group_by_status([{"id": "1", "business": "X", "status": "Banana"}])
    # unmappable -> not counted anywhere, but no exception
    assert sum(board["counts"].values()) == 0


def test_never_raises_on_garbage_input():
    # Mixed junk: None, missing keys, wrong types — must not raise.
    board = group_by_status([None, {}, {"status": "Hot"}, 42, "nope"])
    assert isinstance(board, dict)
    assert board["counts"]["Hot"] == 1  # only the valid Hot dict maps


def test_business_name_alias_supported():
    # builder may emit `business` but be tolerant of `business_name` too.
    board = group_by_status([{"id": "1", "business_name": "Alias Co", "status": "Lost"}])
    assert board["leads_by_status"]["Lost"][0]["business"] == "Alias Co"
