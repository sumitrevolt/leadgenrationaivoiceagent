"""Component 4 — common objection-types merged into every niche script."""

from app.voice_agent.niche_scripts import NICHE_SCRIPTS, _COMMON_OBJECTIONS, get_script

NEW = ("fraud_suspicion", "decision_maker", "tried_before", "details_bhejo")


def test_common_objections_merged_into_all_niches():
    for niche in list(NICHE_SCRIPTS.keys()):
        obj = get_script(niche).get("objections") or {}
        for k in NEW:
            assert k in obj and obj[k].strip(), f"{niche} missing {k}"


def test_niche_specific_rebuttal_wins():
    # real_estate_luxury has its own "mehenga"; the merge must NOT override it
    base = NICHE_SCRIPTS["real_estate_luxury"]["objections"]["mehenga"]
    assert get_script("real_estate_luxury")["objections"]["mehenga"] == base


def test_source_not_mutated():
    before = set((NICHE_SCRIPTS["ai_marketing"].get("objections") or {}).keys())
    get_script("ai_marketing")  # must not mutate the source dict
    after = set((NICHE_SCRIPTS["ai_marketing"].get("objections") or {}).keys())
    assert before == after
    assert not (set(NEW) & before)  # source ai_marketing never had the new keys


def test_unknown_niche_gets_common():
    obj = get_script("some_unknown_niche_xyz").get("objections") or {}
    for k in NEW:
        assert k in obj
