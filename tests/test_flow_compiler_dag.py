from app.automation.flow_compiler import compile_flow


def _flow(nodes, edges, name="t"):
    return {"id": "f1", "name": name, "nodes": nodes, "edges": edges}


def test_linear_flow_still_linear_kind():
    proc, errs, kind = compile_flow(
        _flow(
            [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
            [{"f": "a", "t": "b"}],
        )
    )
    assert kind == "linear" and errs == []
    assert proc["steps"] == [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}]


def test_conditional_edge_makes_dag():
    proc, errs, kind = compile_flow(
        _flow(
            [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
            [{"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}}],
        )
    )
    assert kind == "dag" and errs == []
    assert proc["roots"] == ["a"]
    assert proc["out"]["a"] == [{"t": "b", "when": {"field": "count", "op": ">=", "value": 1}}]
    assert proc["in"]["b"] == [{"f": "a", "when": {"field": "count", "op": ">=", "value": 1}}]


def test_parallel_fanout_and_merge():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
                {"id": "m", "kind": "merge", "join": "all"},
            ],
            [
                {"f": "a", "t": "b"},
                {"f": "a", "t": "c"},
                {"f": "b", "t": "m"},
                {"f": "c", "t": "m"},
            ],
        )
    )
    assert kind == "dag" and errs == []
    assert sorted(proc["in"]["m"], key=lambda e: e["f"]) == [
        {"f": "b", "when": None},
        {"f": "c", "when": None},
    ]
    assert proc["nodes"]["m"]["kind"] == "merge" and proc["nodes"]["m"]["join"] == "all"


def test_indegree2_without_merge_rejected():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            [{"f": "a", "t": "c"}, {"f": "b", "t": "c"}],
        )
    )
    assert proc is None and kind == "dag"
    assert any("merge" in e for e in errs)


def test_cycle_rejected_dag():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            [{"f": "a", "t": "b"}, {"f": "b", "t": "c"}, {"f": "c", "t": "b"}],
        )
    )
    assert proc is None and any("cycle" in e for e in errs)


def test_unreachable_node_rejected():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
                {"id": "d", "action": "optimizer"},
            ],
            [
                {"f": "a", "t": "b"},
                {"f": "a", "t": "c"},
                {"f": "c", "t": "d"},
                {"f": "d", "t": "c"},
            ],
        )
    )
    # cycle c<->d also triggers, but the point: invalid -> None
    assert proc is None and errs


def test_bad_condition_rejected_at_compile():
    proc, errs, kind = compile_flow(
        _flow(
            [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
            [{"f": "a", "t": "b", "when": {"field": "count", "op": "BOGUS", "value": 1}}],
        )
    )
    assert proc is None and any("unknown op" in e for e in errs)


def test_breakpoint_outedge_condition_rejected():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "g", "kind": "breakpoint", "question": "ok?"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            [
                {"f": "a", "t": "g"},
                {"f": "a", "t": "c"},
                {"f": "g", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
            ],
        )
    )
    assert proc is None and any("breakpoint" in e.lower() for e in errs)


def test_unknown_action_rejected_dag():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "nope"},
                {"id": "c", "action": "harvest"},
            ],
            [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        )
    )
    assert proc is None and any("whitelist" in e for e in errs)
