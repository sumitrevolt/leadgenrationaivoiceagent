from app.automation.edge_condition import edge_taken, validate


def test_none_and_empty_are_unconditional():
    assert edge_taken(None, {"count": 0}) is True
    assert edge_taken({}, {"count": 0}) is True


def test_numeric_leaf_ops():
    assert edge_taken({"field": "count", "op": ">=", "value": 1}, {"count": 5}) is True
    assert edge_taken({"field": "count", "op": "<", "value": 1}, {"count": 0}) is True
    assert edge_taken({"field": "count", "op": ">=", "value": 1}, {"count": 0}) is False


def test_string_vs_numeric_coercion():
    # both castable to float -> numeric compare
    assert edge_taken({"field": "count", "op": "==", "value": 3}, {"count": "3"}) is True
    # not castable -> string compare
    assert (
        edge_taken({"field": "detail", "op": "==", "value": "merged"}, {"detail": "merged"}) is True
    )
    assert edge_taken({"field": "detail", "op": "!=", "value": "x"}, {"detail": "merged"}) is True


def test_truthy_falsy_exists():
    assert edge_taken({"field": "ok", "op": "truthy", "value": None}, {"ok": True}) is True
    assert edge_taken({"field": "ok", "op": "falsy", "value": None}, {"ok": False}) is True
    assert edge_taken({"field": "count", "op": "exists", "value": None}, {"count": 0}) is True
    assert edge_taken({"field": "nope", "op": "exists", "value": None}, {"count": 0}) is False


def test_in_not_in():
    assert edge_taken({"field": "count", "op": "in", "value": [1, 2, 3]}, {"count": 2}) is True
    assert edge_taken({"field": "count", "op": "not_in", "value": [1, 2, 3]}, {"count": 9}) is True


def test_all_any_combinators():
    cond = {
        "all": [
            {"field": "ok", "op": "truthy", "value": None},
            {"field": "count", "op": ">=", "value": 1},
        ]
    }
    assert edge_taken(cond, {"ok": True, "count": 2}) is True
    assert edge_taken(cond, {"ok": True, "count": 0}) is False
    any_cond = {
        "any": [
            {"field": "count", "op": ">=", "value": 100},
            {"field": "ok", "op": "truthy", "value": None},
        ]
    }
    assert edge_taken(any_cond, {"ok": True, "count": 0}) is True


def test_missing_field_relational_fail_closed():
    # relational op on a missing field -> None -> False (fail-closed)
    assert edge_taken({"field": "ghost", "op": ">=", "value": 1}, {"count": 5}) is False


def test_malformed_when_fail_closed():
    assert edge_taken({"field": "count", "op": "bogus", "value": 1}, {"count": 5}) is False
    assert edge_taken("not-a-dict", {"count": 5}) is False


def test_validate_accepts_good():
    assert validate({"field": "count", "op": ">=", "value": 1}) == []
    assert validate({"all": [{"field": "ok", "op": "truthy", "value": None}]}) == []
    assert validate(None) == []


def test_validate_rejects_bad():
    assert validate({"field": "count", "op": "bogus", "value": 1})  # unknown op
    assert validate({"field": "", "op": "==", "value": 1})  # empty field
    deep = {"all": [{"all": [{"all": [{"all": [{"field": "a", "op": "==", "value": 1}]}]}]}]}
    assert validate(deep)  # depth > 3
