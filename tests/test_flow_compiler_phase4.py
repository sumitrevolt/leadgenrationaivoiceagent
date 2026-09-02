from app.automation.flow_compiler import compile_flow


def _flow(nodes, edges, name="t"):
    return {"id": "f", "name": name, "nodes": nodes, "edges": edges}


def test_inputs_map_forces_dag_even_on_linear_chain():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {
                    "id": "b",
                    "action": "crm_queue",
                    "inputs_map": {"leads": {"from": "a", "key": "detail"}},
                },
            ],
            [{"f": "a", "t": "b"}],
        )
    )
    assert kind == "dag" and errs == []
    assert proc["nodes"]["b"]["inputs_map"] == {"leads": {"from": "a", "key": "detail"}}


def test_literal_value_is_valid():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "crm_queue", "inputs_map": {"client_id": {"value": "acme"}}},
            ],
            [{"f": "a", "t": "b"}],
        )
    )
    assert kind == "dag" and errs == []
    assert proc["nodes"]["b"]["inputs_map"]["client_id"] == {"value": "acme"}


def test_non_ancestor_source_rejected():
    # b reads from c, but c is NOT an ancestor of b (parallel branch) -> error
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {
                    "id": "b",
                    "action": "crm_queue",
                    "inputs_map": {"leads": {"from": "c", "key": "detail"}},
                },
                {"id": "c", "action": "harvest"},
            ],
            [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        )
    )
    assert proc is None and any("ancestor" in e.lower() for e in errs)


def test_forward_reference_rejected():
    # a reads from b, but b runs AFTER a -> not an ancestor -> error
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape", "inputs_map": {"x": {"from": "b", "key": "count"}}},
                {"id": "b", "action": "rescore"},
            ],
            [{"f": "a", "t": "b"}],
        )
    )
    assert proc is None and any("ancestor" in e.lower() for e in errs)


def test_unknown_key_rejected():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {
                    "id": "b",
                    "action": "crm_queue",
                    "inputs_map": {"leads": {"from": "a", "key": "bogus"}},
                },
            ],
            [{"f": "a", "t": "b"}],
        )
    )
    assert proc is None and any("key" in e.lower() for e in errs)


def test_missing_from_node_rejected():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {
                    "id": "b",
                    "action": "crm_queue",
                    "inputs_map": {"leads": {"from": "ghost", "key": "detail"}},
                },
            ],
            [{"f": "a", "t": "b"}],
        )
    )
    assert proc is None and errs


def test_flow_without_inputs_map_stays_linear():
    proc, errs, kind = compile_flow(
        _flow(
            [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
            [{"f": "a", "t": "b"}],
        )
    )
    assert kind == "linear" and errs == []
