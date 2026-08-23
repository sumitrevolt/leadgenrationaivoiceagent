from app.automation.flow_compiler import SIDE_EFFECT_ACTIONS, compile_flow


def _flow(nodes, edges, name="t"):
    return {"id": "f", "name": name, "nodes": nodes, "edges": edges}


def test_side_effect_actions_set():
    assert "crm_queue" in SIDE_EFFECT_ACTIONS


def test_new_phase5_action_compiles():
    proc, errs, kind = compile_flow(_flow([{"id": "a", "action": "brand_pulse"}], []))
    assert errs == [] and kind == "linear" and proc["steps"][0]["action"] == "brand_pulse"


def test_linear_side_effect_without_breakpoint_warns():
    proc, errs, kind = compile_flow(
        _flow(
            [{"id": "a", "action": "scrape"}, {"id": "b", "action": "crm_queue"}],
            [{"f": "a", "t": "b"}],
        )
    )
    assert errs == [] and kind == "linear"  # non-fatal
    assert proc.get("warnings") and any("crm_queue" in w for w in proc["warnings"])


def test_linear_side_effect_with_breakpoint_no_warn():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "g", "kind": "breakpoint", "question": "ok?"},
                {"id": "b", "action": "crm_queue"},
            ],
            [{"f": "a", "t": "g"}, {"f": "g", "t": "b"}],
        )
    )
    assert errs == [] and not proc.get("warnings")


def test_dag_side_effect_without_breakpoint_warns():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "crm_queue"},
                {"id": "c", "action": "rescore"},
            ],
            [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        )
    )
    assert kind == "dag" and errs == []
    assert proc.get("warnings") and any("crm_queue" in w for w in proc["warnings"])


def test_dag_side_effect_with_breakpoint_ancestor_no_warn():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "scrape"},
                {"id": "g", "kind": "breakpoint", "question": "ok?"},
                {"id": "b", "action": "crm_queue"},
                {"id": "c", "action": "rescore"},
            ],
            [{"f": "a", "t": "g"}, {"f": "g", "t": "b"}, {"f": "a", "t": "c"}],
        )
    )
    assert kind == "dag" and errs == [] and not proc.get("warnings")
