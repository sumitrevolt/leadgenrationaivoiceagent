"""Flow Runner starter templates — shape + compile validity (Phase: starter content).

Guards the "dormant-but-wireable" fix: FLOW_RUNNER shipped with an empty builder;
these 3 templates must stay compile-valid under the STRICTEST (customer) gate so a
1-click apply always yields a runnable flow.
"""

from app.automation import flow_compiler, flow_templates


def test_three_starter_templates():
    tpls = flow_templates.list_templates()
    assert len(tpls) == 3
    assert {t["tid"] for t in tpls} == {"daily_content", "weekly_reputation", "festival_campaign"}
    for t in tpls:
        assert t["name"] and t["description"]
        assert t["steps"] >= 1
        assert t["trigger"] in ("manual", "cron", "event")


def test_unknown_template_is_none():
    assert flow_templates.get_template("nope") is None
    assert flow_templates.to_flow("nope") is None


def test_templates_compile_customer_safe():
    # every starter must compile cleanly under the strictest (customer) gate
    for t in flow_templates.list_templates():
        flow = flow_templates.to_flow(t["tid"])
        assert flow is not None
        proc, errs, _kind = flow_compiler.compile_flow(flow, customer_safe=True)
        assert errs == [], f"{t['tid']} compile errors: {errs}"
        assert proc is not None


def test_to_flow_has_no_id_and_is_immutable():
    f1 = flow_templates.to_flow("daily_content")
    assert "id" not in f1  # save_flow assigns a fresh id
    f1["nodes"][0]["action"] = "HACKED"
    f2 = flow_templates.to_flow("daily_content")
    assert f2["nodes"][0]["action"] == "content_pack"  # source constants untouched


def test_name_override():
    f = flow_templates.to_flow("festival_campaign", name_override="Diwali Dhamaka")
    assert f["name"] == "Diwali Dhamaka"
