"""Tests — skill_pack (skills→VPS agents) + code_upgrader (hybrid autonomy).
Sync + asyncio.run pattern, tmp stores via monkeypatch. No network/DB needed.
"""

from __future__ import annotations

import asyncio
import os


def _mk_skill(root, name: str, desc: str, body: str) -> None:
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n")


def _fresh(monkeypatch, tmp_path):
    from app.platform import skill_pack as sp

    skills_dir = str(tmp_path / "skills")
    extra_dir = str(tmp_path / "extra")
    os.makedirs(skills_dir, exist_ok=True)
    monkeypatch.setattr(sp, "_SKILLS_DIR", skills_dir)
    monkeypatch.setattr(sp, "_EXTRA_DIR", extra_dir)
    sp._cache["at"] = 0.0
    sp._cache["skills"] = []
    return sp, skills_dir


def test_skill_pack_list_find_snippet(tmp_path, monkeypatch):
    sp, skills_dir = _fresh(monkeypatch, tmp_path)
    _mk_skill(
        skills_dir,
        "cold-email-craft",
        "Rohan ke cold email frameworks",
        "Subject lines chhote rakho. Personalize first line.",
    )
    _mk_skill(
        skills_dir, "seo-growth", "programmatic SEO pages", "Niche x city landing pages banao."
    )

    skills = sp.list_skills()
    assert len(skills) == 2 and {s["name"] for s in skills} == {"cold-email-craft", "seo-growth"}

    hits = sp.find("cold email outreach", k=2)
    assert hits and hits[0]["name"] == "cold-email-craft"

    sn = sp.snippet_for("cold email")
    assert "cold-email-craft" in sn and "Subject lines" in sn
    # no-match → empty, kabhi raise nahi
    assert sp.snippet_for("zzz qqq xyzabc") == ""


def test_skill_pack_author_tier1_guards(tmp_path, monkeypatch):
    sp, _ = _fresh(monkeypatch, tmp_path)
    # path-escape sanitized: "../evil" → slug "evil", file extra-dir ke ANDAR hi bane
    r = sp.author("../evil", "safe text")
    assert r["ok"] and r["name"] == "evil"
    assert os.path.dirname(os.path.abspath(r["path"])) == os.path.abspath(sp._EXTRA_DIR)
    # empty/invalid → block
    assert sp.author("!!!", "x")["ok"] is False
    assert sp.author("name", "")["ok"] is False
    # script block + size cap
    assert sp.author("ok-name", "<script>alert(1)</script>")["ok"] is False
    assert sp.author("big", "x" * (17 * 1024))["ok"] is False
    # happy path → runtime-live (list me dikhe)
    r = sp.author("My New_Playbook", "# Naya playbook\nLeads follow-up 5 min me.")
    assert r["ok"] and r["name"] == "mynew_playbook"
    names = {s["name"] for s in sp.list_skills()}
    assert "mynew_playbook" in names and "evil" in names


def test_skill_pack_flag_gate(monkeypatch):
    from app.platform import skill_pack as sp

    monkeypatch.delenv("SKILL_PACK", raising=False)
    assert sp.enabled() is False
    monkeypatch.setenv("SKILL_PACK", "1")
    assert sp.enabled() is True


def test_upgrader_propose_and_status(tmp_path, monkeypatch):
    from app.agents import code_upgrader as cu

    monkeypatch.setattr(cu, "_PATCHES", str(tmp_path / "patches.jsonl"))
    monkeypatch.delenv("CODE_UPGRADER", raising=False)
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    # signals stub — ek failing provider
    monkeypatch.setattr(
        cu,
        "_collect_signals",
        lambda: [
            {"key": "llm_groq", "issue": "groq ok-rate 0.2", "area": "app/voice_agent/free_ai.py"},
        ],
    )

    async def _no_llm(issue, area):
        return {"title": f"Fix: {issue}", "rationale": issue, "sketch": "cooldown badhao"}

    monkeypatch.setattr(cu, "_propose", _no_llm)

    res = asyncio.run(cu.scan_and_propose())
    assert res["ok"] and res["proposed"] == 1
    pid = res["ids"][0]

    rows = cu.list_patches()
    assert rows[0]["id"] == pid and rows[0]["status"] == "proposed"

    # same-day dedupe
    res2 = asyncio.run(cu.scan_and_propose())
    assert res2["proposed"] == 0

    # approve flow (apply NAHI hota — sirf marker; hybrid gate)
    assert cu.set_status(pid, "approved", "looks good")["ok"]
    assert cu.list_patches()[0]["status"] == "approved"
    assert cu.set_status(pid, "weird")["ok"] is False
    assert cu.set_status("nope", "approved")["ok"] is False

    # OPEN-signal dedupe (duplicate 8b05c720 regression): approved patch ka signal
    # agle din bhi re-propose NAHI hona chahiye (sirf rejected/applied = closed).
    res3 = asyncio.run(cu.scan_and_propose())
    assert res3["proposed"] == 0
    # reject (closed) ke baad — same-day guard ki wajah se aaj phir bhi nahi
    assert cu.set_status(pid, "rejected", "dup")["ok"]
    res4 = asyncio.run(cu.scan_and_propose())
    assert res4["proposed"] == 0


def test_llm_cooldown_escalates_and_resets(monkeypatch):
    from app.voice_agent import free_ai as fa

    monkeypatch.setattr(fa, "_LLM_COOLDOWN_UNTIL", {})
    monkeypatch.setattr(fa, "_LLM_TRIP_STREAK", {})
    base = fa._LLM_COOLDOWN_S
    now = 1_000_000.0
    monkeypatch.setattr(fa.time, "time", lambda: now)

    # 1st trip = base 60s
    fa._trip_cooldown("cerebras", "Error code: 429 too_many_requests")
    assert fa._LLM_COOLDOWN_UNTIL["cerebras"] == now + base
    # 2nd/3rd trip = escalate 2x, 4x
    fa._trip_cooldown("cerebras", "429 rate limit")
    assert fa._LLM_COOLDOWN_UNTIL["cerebras"] == now + base * 2
    fa._trip_cooldown("cerebras", "429 rate limit")
    assert fa._LLM_COOLDOWN_UNTIL["cerebras"] == now + base * 4
    # daily-quota wording = seedha max cooldown (Groq TPD lesson)
    fa._trip_cooldown("groq", "429 Rate limit reached for model x tokens per day")
    assert fa._LLM_COOLDOWN_UNTIL["groq"] == now + fa._LLM_COOLDOWN_MAX_S
    # non-rate error = no trip
    fa._trip_cooldown("xai", "boom connection reset")
    assert "xai" not in fa._LLM_COOLDOWN_UNTIL
    # success = streak reset → agla trip wapas base
    fa._reset_cooldown_streak("cerebras")
    fa._trip_cooldown("cerebras", "429")
    assert fa._LLM_COOLDOWN_UNTIL["cerebras"] == now + base


def test_upgrader_gated_off(monkeypatch, tmp_path):
    from app.agents import code_upgrader as cu

    monkeypatch.setattr(cu, "_PATCHES", str(tmp_path / "p.jsonl"))
    monkeypatch.delenv("CODE_UPGRADER", raising=False)
    res = asyncio.run(cu.run_if_enabled())
    assert res == {"ok": True, "enabled": False}


def test_self_improve_new_actions_registered():
    from app.agents import self_improve as si

    assert "study_skills" in si.ACTIONS and "code_scan" in si.ACTIONS
    # code_scan light (LLM-heavy=False) — degraded-LLM mode me bhi chale
    assert si.ACTIONS["code_scan"][0] is False


def test_study_skills_gated_off(monkeypatch):
    from app.agents import self_improve as si

    monkeypatch.delenv("SKILL_PACK", raising=False)
    res = asyncio.run(si._study_skills("cold email"))
    assert res["ok"] and "off" in res["detail"]


def test_team_has_new_staff():
    from app.platform import team

    assert "vikram" in team.STAFF and "guru" in team.STAFF
    # >= (== nahi) — naya staff add hone pe yeh test stale na ho (Hermes 13th lesson)
    assert len(team.STAFF) >= 13 and "hermes" in team.STAFF
