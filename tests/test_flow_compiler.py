from app.automation.flow_compiler import compile_flow


def _flow(nodes, edges, name="t"):
    return {"id": "f1", "name": name, "nodes": nodes, "edges": edges}


def test_valid_linear_compiles_in_order():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b"}],
    ))
    assert errs == []
    assert proc["steps"] == [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}]


def test_breakpoint_node_preserved():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"},
         {"id": "g", "kind": "breakpoint", "question": "send?"}],
        [{"f": "a", "t": "g"}],
    ))
    assert errs == []
    assert proc["steps"][1] == {"kind": "breakpoint", "id": "g", "question": "send?"}


def test_gate_and_retries_pass_through():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "content_pack", "gate": {"min_count": 1}, "max_retries": 2}], []))
    assert errs == []
    assert proc["steps"][0] == {"id": "a", "action": "content_pack", "gate": {"min_count": 1}, "max_retries": 2}


def test_empty_flow_errors():
    proc, errs = compile_flow(_flow([], []))
    assert proc is None and any("no nodes" in e for e in errs)


def test_dangling_edge_errors():
    proc, errs = compile_flow(_flow([{"id": "a", "action": "scrape"}], [{"f": "a", "t": "zzz"}]))
    assert proc is None and any("zzz" in e for e in errs)


def test_unknown_action_errors():
    proc, errs = compile_flow(_flow([{"id": "a", "action": "definitely_not_real"}], []))
    assert proc is None and any("whitelist" in e for e in errs)


def test_branch_rejected():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "optimizer"}],
        [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
    ))
    assert proc is None and any("linear" in e for e in errs)


def test_cycle_rejected():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b"}, {"f": "b", "t": "a"}],
    ))
    assert proc is None and errs
