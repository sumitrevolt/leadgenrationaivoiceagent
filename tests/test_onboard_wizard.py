"""Tests: onboarding wizard — business-type → niche template → auto-setup.

Covers: catalog sanity, niche resolution, template preview flags, auto-setup
apply (flag-gated), unknown business type fallback, marketing-only niches.
"""

from __future__ import annotations

from app.marketing import onboard_wizard as wz

# --------------------------------------------------------------------------- #
# Catalog + resolution
# --------------------------------------------------------------------------- #


def test_catalog_has_core_business_types():
    ids = [b["id"] for b in wz.get_business_types()]
    for must in ("salon", "restaurant", "clinic", "dental", "gym", "general"):
        assert must in ids, f"business type '{must}' catalog me hona chahiye"


def test_catalog_has_new_business_types():
    ids = [b["id"] for b in wz.get_business_types()]
    for must in ("tiffin", "salon-men", "tuition", "play-school", "laundry", "electronics-repair"):
        assert must in ids, f"business type '{must}' catalog me hona chahiye"


def test_catalog_entries_have_required_shape():
    for b in wz.get_business_types():
        assert b["id"] and b["label"] and b["niche"]
        assert isinstance(b["auto_setup_fields"], list) and b["auto_setup_fields"]
        assert isinstance(b["products"], list) and b["products"]


def test_resolve_niche_maps_known_types():
    assert wz.resolve_niche("salon") == "salon_spa"
    assert wz.resolve_niche("restaurant") == "restaurant_cafe"
    assert wz.resolve_niche("clinic") == "hospital_appointments"
    assert wz.resolve_niche("dental") == "dental_implants"
    assert wz.resolve_niche("gym") == "gym_fitness"


def test_resolve_niche_unknown_falls_back_general():
    assert wz.resolve_niche("") == "general"
    assert wz.resolve_niche("quantum_energy") == "general"
    assert wz.resolve_niche("SALON") == "salon_spa"  # case-insensitive


def test_resolve_niche_new_types():
    assert wz.resolve_niche("tiffin") == "tiffin_service"
    assert wz.resolve_niche("salon-men") == "gents_salon"
    assert wz.resolve_niche("tuition") == "tuition_classes"
    assert wz.resolve_niche("play-school") == "play_school"
    assert wz.resolve_niche("laundry") == "laundry_dryclean"
    assert wz.resolve_niche("electronics-repair") == "electronics_repair"


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #


def test_preview_salon():
    p = wz.get_template_preview("salon")
    assert p["niche"] == "salon_spa"
    assert p["label"] == "Salon / Beauty Parlour"
    assert p["has_knowledge_pack"] is True
    assert p["auto_setup_fields"]


def test_preview_clinic():
    p = wz.get_template_preview("clinic")
    assert p["niche"] == "hospital_appointments"
    assert p["has_voice_script"] is True  # hospital_appointments script exists
    assert p["has_knowledge_pack"] is True


def test_preview_unknown_type_ok():
    p = wz.get_template_preview("does_not_exist")
    assert p["niche"] == "general"
    assert p["label"] == "Other Business"
    assert isinstance(p["auto_setup_fields"], list)


# --------------------------------------------------------------------------- #
# Auto-setup apply (flag-gated)
# --------------------------------------------------------------------------- #


def test_apply_disabled_without_flag(monkeypatch):
    monkeypatch.delenv("ONBOARD_WIZARD_APPLY", raising=False)
    res = wz.apply_auto_setup("client_x", "salon")
    assert res["ok"] is False
    assert "disabled" in (res.get("error") or "")


def test_apply_requires_client_id(monkeypatch):
    monkeypatch.setenv("ONBOARD_WIZARD_APPLY", "1")
    res = wz.apply_auto_setup("", "salon")
    assert res["ok"] is False
    assert "client_id" in (res.get("error") or "")


def test_apply_missing_client_graceful(monkeypatch):
    """Client nahi mila to bhi crash nahi — snapshot warning + knowledge best-effort."""
    monkeypatch.setenv("ONBOARD_WIZARD_APPLY", "1")
    res = wz.apply_auto_setup("no_such_client_zzz", "restaurant")
    # ok may be True (knowledge seed) or False — but never raises, never crash
    assert "error" not in res or isinstance(res["error"], str)
    assert res["niche"] == "restaurant_cafe"


def test_apply_marketing_only_niche_resolves(monkeypatch):
    """Restaurant marketing-only niche — knowledge pack exists, script fallback general."""
    monkeypatch.setenv("ONBOARD_WIZARD_APPLY", "1")
    res = wz.apply_auto_setup("no_such_client_zzz", "restaurant")
    assert res["niche"] == "restaurant_cafe"
    assert res["business_type"] == "restaurant"


# --------------------------------------------------------------------------- #
# Marketing-only voice fallback classification
# --------------------------------------------------------------------------- #


def test_salon_gym_boutique_now_have_scripts():
    """Salon/gym/boutique — own voice scripts + knowledge (general fallback nahi)."""
    for bt, niche in (
        ("salon", "salon_spa"),
        ("gym", "gym_fitness"),
        ("boutique", "boutique_fashion"),
    ):
        p = wz.get_template_preview(bt)
        assert p["niche"] == niche
        assert p["has_knowledge_pack"] is True
        assert p["has_voice_script"] is True, f"{bt}: voice script hona chahiye"


def test_new_types_have_own_scripts_and_knowledge():
    """Tiffin/salon-men/tuition/play-school/laundry/electronics — own scripts + KB."""
    for bt, niche in (
        ("tiffin", "tiffin_service"),
        ("salon-men", "gents_salon"),
        ("tuition", "tuition_classes"),
        ("play-school", "play_school"),
        ("laundry", "laundry_dryclean"),
        ("electronics-repair", "electronics_repair"),
    ):
        p = wz.get_template_preview(bt)
        assert p["niche"] == niche
        assert p["has_voice_script"] is True, f"{bt}: voice script hona chahiye"
        assert p["has_knowledge_pack"] is True, f"{bt}: knowledge pack hona chahiye"
        assert p["has_niche_catalog"] is True, f"{bt}: NICHES catalog entry honi chahiye"
        assert p["auto_setup_fields"]


def test_new_niches_in_catalog_with_lead_band():
    """Naye niches NICHES catalog me hain — lead_band + content_focus ke saath
    (full palette + festival schedule wizard auto-setup ke liye)."""
    from app.niches import NICHES

    for niche in (
        "tiffin_service",
        "gents_salon",
        "tuition_classes",
        "play_school",
        "laundry_dryclean",
        "electronics_repair",
    ):
        cfg = NICHES.get(niche)
        assert cfg, f"{niche} NICHES catalog me hona chahiye"
        assert cfg.get("lead_band") in ("A", "B", "C"), f"{niche}: valid lead_band"
        assert cfg.get("content_focus") and len(cfg["content_focus"]) >= 3
        assert cfg.get("pitch_hook") and cfg.get("keywords") and cfg.get("name")


def test_new_niche_scripts_are_complete():
    """Har naye script me opening/discovery/objections/closing hona chahiye."""
    from app.voice_agent.niche_scripts_data import NICHE_SCRIPTS

    for niche in (
        "tiffin_service",
        "gents_salon",
        "tuition_classes",
        "play_school",
        "laundry_dryclean",
        "electronics_repair",
    ):
        s = NICHE_SCRIPTS.get(niche)
        assert s, f"{niche} script missing"
        assert s.get("opening") and "[Company]" in s["opening"]
        assert s.get("discovery") and len(s["discovery"]) >= 3
        assert s.get("objections") and "mehenga" in s["objections"]
        assert s.get("closing")


def test_salon_gym_boutique_scripts_are_complete():
    """Salon/gym/boutique scripts me opening/discovery/objections/closing hona chahiye."""
    from app.voice_agent.niche_scripts_data import NICHE_SCRIPTS

    for niche in ("salon_spa", "gym_fitness", "boutique_fashion"):
        s = NICHE_SCRIPTS.get(niche)
        assert s, f"{niche} script missing"
        assert s.get("opening") and "[Company]" in s["opening"]
        assert s.get("discovery") and len(s["discovery"]) >= 3
        assert s.get("objections") and "mehenga" in s["objections"]
        assert s.get("value_lines") and len(s["value_lines"]) >= 2
        assert s.get("closing")


def test_new_knowledge_packs_are_complete():
    from app.niche_knowledge_data import NICHE_KNOWLEDGE

    for niche in (
        "tiffin_service",
        "gents_salon",
        "tuition_classes",
        "play_school",
        "laundry_dryclean",
        "electronics_repair",
    ):
        p = NICHE_KNOWLEDGE.get(niche)
        assert p, f"{niche} knowledge pack missing"
        assert p.get("facts") and len(p["facts"]) >= 4
        assert p.get("benefits") and len(p["benefits"]) >= 3
        assert p.get("objections") and "too_expensive" in p["objections"]


def test_wizard_catalog_completeness_guard():
    """GUARD: har wizard business type teeno layers me wired hona chahiye — voice
    script + knowledge pack + NICHES catalog entry. Naya business type half-wired
    ship nahi ho sakta (script hai par catalog nahi, ya catalog hai par script
    nahi). `general` = fallback niche, isliye exempt."""
    from app.niche_knowledge import NICHE_KNOWLEDGE as KB  # overlay-merged truth
    from app.niches import NICHES
    from app.voice_agent.niche_scripts_data import NICHE_SCRIPTS

    missing: list[str] = []
    for b in wz.get_business_types():
        niche = b["niche"]
        if niche == "general":
            continue  # fallback script, real niche nahi
        lacks = [
            layer
            for layer, ok in (
                ("voice script", niche in NICHE_SCRIPTS),
                ("knowledge pack", niche in KB),
                ("NICHES entry", niche in NICHES),
            )
            if not ok
        ]
        if lacks:
            missing.append(f"{b['id']} ({niche}): missing " + ", ".join(lacks))
    assert not missing, "half-wired wizard business types:\n" + "\n".join(missing)
