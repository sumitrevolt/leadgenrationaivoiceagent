"""frontend/customer_dashboard.html — Setup Wizard card (business profile/
social/WhatsApp/brand-tone). Static-HTML guard, mirrors the established pattern
(tests/test_admin_clients_delivery_panel.py) — confirms the card/functions
exist and call the real endpoints, without needing a live authenticated
browser session. Originally piloted on customer_marketing.html/customer_voice.html
(deleted 2026-07-07 — both were unreachable duplicates of this consolidated file,
see tests/test_customer_dashboard_product_routing.py)."""


def _html():
    with open("frontend/customer_dashboard.html", encoding="utf-8") as f:
        return f.read()


def test_setup_wizard_card_exists():
    html = _html()
    assert 'id="setupWizardCard"' in html
    assert 'id="setupWizardBody"' in html


def test_setup_wizard_loaded_on_page_init():
    """P0-2026-07-12: the bottom-of-script boot sequence now calls each loader
    through _safeBoot() so one throwing loader can never block a sibling card
    (this is the exact mechanism that could leave Setup Wizard/Social Setup
    permanently stuck on "Load ho raha hai..."). Confirms loadGuidedSetup is
    still wired into that sequence, just via the safe wrapper."""
    html = _html()
    idx = html.index('_safeBoot("loadBilling", loadBilling);')
    snippet = html[idx : idx + 500]
    assert '_safeBoot("loadGuidedSetup", loadGuidedSetup);' in snippet
    # the wrapper itself must actually invoke fn() inside a try/catch
    helper_idx = html.index("function _safeBoot(name, fn)")
    helper = html[helper_idx : helper_idx + 200]
    assert "try{" in helper and "catch(e)" in helper and "fn()" in helper


def test_load_setup_wizard_calls_real_profile_get_endpoint():
    html = _html()
    idx = html.index("async function loadSetupWizard")
    snippet = html[idx : idx + 500]
    assert '"/api/customer/profile"' in snippet
    helper = html[html.index("async function fetchSetupJson") : idx]
    assert "billAuthHdr()" in helper
    assert "AbortController" in helper


def test_save_setup_wizard_calls_real_profile_post_endpoint():
    html = _html()
    idx = html.index("async function saveSetupWizard")
    snippet = html[idx : idx + 1500]
    assert '"/api/customer/profile"' in snippet
    assert 'method:"POST"' in snippet
    assert "billAuthHdr()" in snippet
    # all 4 wizard dimensions present in the payload
    for field in ("business_name", "instagram", "tagline", "tone"):
        assert field in snippet


def test_send_kb_info_reuses_existing_dormant_endpoint():
    """The mission's real find: /api/customer/kb-info already existed and
    worked, it just had no UI button — this wires it, doesn't reinvent it."""
    html = _html()
    idx = html.index("async function sendKbInfo")
    snippet = html[idx : idx + 700]
    assert '"/api/customer/kb-info"' in snippet
    assert 'method:"POST"' in snippet


def test_social_and_brand_sections_are_marketing_only():
    """Voice-only customers shouldn't see social/brand-tone fields (a voice
    telecaller product has no posts to brand) — business profile + the
    kb-info textarea stay universal (the AI voice agent uses the same KB)."""
    html = _html()
    idx = html.index("function renderSetupWizard")
    snippet = html[idx : idx + 5200]
    marketing_only_idx = snippet.index('class="marketing-only"')
    assert "Social Links" in snippet[marketing_only_idx : marketing_only_idx + 400]
    assert "swTone" in snippet[marketing_only_idx : marketing_only_idx + 900]
    # kb-info section must be OUTSIDE the marketing-only wrapper (universal)
    kb_idx = snippet.index("AI ko business ke baare me")
    assert kb_idx > snippet.rindex("</div>", marketing_only_idx, kb_idx)


def test_setup_wizard_reuses_real_helpers_not_invented_ones():
    """Loop 2's exact self-review lesson: confirm no invented CSS classes or
    helper names — only real ones (escH/toast/billAuthHdr/billToken/.btn/.card-h/.card-b)."""
    html = _html()
    idx = html.index('id="setupWizardCard"')
    card_snippet = html[idx : idx + 400]
    assert 'class="card-h"' in card_snippet
    assert 'class="card-b"' in card_snippet

    # window renderSetupWizard + saveSetupWizard dono cover kare (2026-07-07:
    # first-week-plan button add hone se 5500 chhota pad gaya tha)
    idx2 = html.index("function _swField")
    fn_snippet = html[idx2 : idx2 + 7000]
    assert "escH(" in fn_snippet
    assert "toast(" in fn_snippet
