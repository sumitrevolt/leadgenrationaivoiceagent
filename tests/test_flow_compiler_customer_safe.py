from app.automation.flow_compiler import CUSTOMER_SAFE_ACTIONS, compile_flow


def _flow(nodes, edges, name="t"):
    return {"id": "f", "name": name, "nodes": nodes, "edges": edges}


def test_customer_safe_set_excludes_dangerous():
    for bad in ("http_request", "crm_queue", "whatsapp_draft", "scrape", "harvest"):
        assert bad not in CUSTOMER_SAFE_ACTIONS
    for good in (
        "content_pack",
        "social_drafts",
        "seo_blog_draft",
        "brand_pulse",
        "review_scan",
        "client_report_draft",
    ):
        assert good in CUSTOMER_SAFE_ACTIONS


def test_safe_action_compiles_under_customer_safe():
    proc, errs, kind = compile_flow(
        _flow([{"id": "a", "action": "seo_blog_draft"}], []), customer_safe=True
    )
    assert errs == [] and proc is not None


def test_http_request_rejected_under_customer_safe():
    proc, errs, kind = compile_flow(
        _flow([{"id": "a", "action": "http_request"}], []), customer_safe=True
    )
    assert proc is None and any("not allowed for customer" in e.lower() for e in errs)


def test_crm_and_scrape_rejected_under_customer_safe():
    for act in ("crm_queue", "scrape", "harvest"):
        proc, errs, kind = compile_flow(_flow([{"id": "a", "action": act}], []), customer_safe=True)
        assert proc is None and errs, act


def test_dangerous_action_allowed_for_admin():
    # customer_safe=False (admin default) -> http_request compiles fine
    proc, errs, kind = compile_flow(_flow([{"id": "a", "action": "http_request"}], []))
    assert errs == [] and proc is not None


def test_breakpoint_and_merge_allowed_under_customer_safe():
    proc, errs, kind = compile_flow(
        _flow(
            [
                {"id": "a", "action": "brand_pulse"},
                {"id": "g", "kind": "breakpoint", "question": "ok?"},
                {"id": "b", "action": "social_drafts"},
                {"id": "m", "kind": "merge", "join": "all"},
            ],
            [
                {"f": "a", "t": "g"},
                {"f": "a", "t": "b"},
                {"f": "g", "t": "m"},
                {"f": "b", "t": "m"},
            ],
        ),
        customer_safe=True,
    )
    assert errs == [] and kind == "dag"
