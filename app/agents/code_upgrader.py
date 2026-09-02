"""Code upgrader (Vikram 🛠️) — system-agent jo zaroorat padne par code upgrade SUGGEST/karta hai.

Hybrid autonomy (user decision 2026-06-11, docs/AUTONOMOUS_INFRA_DESIGN.md):
  Tier-1 AUTO  : sirf `data/skills_extra/*.md` (skill_pack.author ke through) — runtime-live,
                 non-executable markdown. Agent khud naye playbooks/skills likh sakta hai.
  Tier-2 GATED : core code ke liye sirf PATCH PROPOSAL (file + rationale + suggested-diff sketch)
                 → `data/code_patches.jsonl` + NOTIFY_EMAIL alert → admin approve/reject API.
                 Apply HAMESHA normal deploy loop (git push → rebuild) se — container me live
                 code-patch lagta hi nahi (image-baked) aur prod-down lessons bhi yahi kehte.

Scan signals (sab existing, READ-only): llm_metrics provider errors · automation_health failing/
overdue jobs · skill_library worst actions. Dedupe per issue/day. Gated `CODE_UPGRADER=1`
(scheduler wiring); manual API flag-independent. Never-raise, import-safe.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATCHES = os.path.join("data", "code_patches.jsonl")
_MAX_PROPOSALS_PER_SCAN = 3


def enabled() -> bool:
    return (os.getenv("CODE_UPGRADER") or "").strip().lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now()


def _read() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if os.path.exists(_PATCHES):
            with open(_PATCHES, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return out


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_PATCHES, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def list_patches(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Latest-state view (jsonl me status-updates append hote hain)."""
    by_id: dict[str, dict[str, Any]] = {}
    for r in _read():
        pid = r.get("id")
        if not pid:
            continue
        if pid in by_id:
            by_id[pid].update({k: v for k, v in r.items() if v is not None})
        else:
            by_id[pid] = dict(r)
    rows = sorted(by_id.values(), key=lambda r: r.get("at", ""), reverse=True)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows[: max(1, limit)]


def set_status(patch_id: str, status: str, note: str = "") -> dict[str, Any]:
    """approve | reject | applied. Approve = sirf marker; apply deploy-loop me hota hai."""
    if status not in ("approved", "rejected", "applied"):
        return {"ok": False, "error": "status must be approved|rejected|applied"}
    cur = {r["id"]: r for r in list_patches(limit=500)}.get(patch_id)
    if not cur:
        return {"ok": False, "error": "patch not found"}
    _append({"id": patch_id, "status": status, "note": note[:300], "at": _now().isoformat()})
    try:
        from app.platform import team

        team.log_event(
            "vikram",
            "patch_" + status,
            f"🛠️ patch {patch_id[:8]} {status}: {cur.get('title', '')[:80]}",
        )
    except Exception:
        pass
    # D1: eval_gate on applied patches (INERT unless EVAL_GATE=1). Mirrors
    # self_improve._execute — slow quality drift after Vikram acceptances.
    if status == "applied":
        try:
            from app.agents import eval_gate

            if eval_gate.enabled():
                eval_gate.score_and_gate(
                    suite="code_upgrader",
                    metric="patch_outcome",
                    current_score=1.0,
                    agent="vikram",
                    artifact=str(patch_id),
                )
        except Exception as _eg_exc:
            logger.debug(f"[code_upgrader] eval_gate hook skip: {_eg_exc}")
    return {"ok": True, "id": patch_id, "status": status}


# ---------------------------------------------------------------- signals


def _collect_signals() -> list[dict[str, str]]:
    """Issue candidates from existing observability (READ-only, never-raise)."""
    sigs: list[dict[str, str]] = []
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(window=300) or {}
        for prov, d in (st.get("providers") or {}).items():
            if isinstance(d, dict) and d.get("calls", 0) >= 5 and (d.get("ok_rate") or 1.0) < 0.5:
                sigs.append(
                    {
                        "key": f"llm_{prov}",
                        "issue": f"LLM provider '{prov}' ok-rate {d.get('ok_rate')} (last error: {str(d.get('last_error', ''))[:120]})",
                        "area": "app/voice_agent/free_ai.py",
                    }
                )
    except Exception:
        pass
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        for d in h.get("jobs") or []:
            if isinstance(d, dict) and d.get("status") in ("overdue", "last_failed"):
                job = d.get("job", "?")
                sigs.append(
                    {
                        "key": f"job_{job}",
                        "issue": f"Scheduled job '{job}' {d.get('status')} (last run: {str(d.get('last_run', ''))[:40]})",
                        "area": "app/platform/team_scheduler.py",
                    }
                )
    except Exception:
        pass
    try:
        from app.platform import skill_library

        for w in skill_library.worst(3):
            if (w.get("uses") or 0) >= 5 and (w.get("rate") or w.get("success_rate") or 1.0) < 0.35:
                sigs.append(
                    {
                        "key": f"action_{w.get('skill')}",
                        "issue": f"self_improve action '{w.get('skill')}' success-rate low ({w.get('rate') or w.get('success_rate')}) over {w.get('uses')} uses",
                        "area": "app/agents/self_improve.py",
                    }
                )
    except Exception:
        pass
    return sigs


async def _propose(issue: str, area: str, grounding: str = "") -> dict[str, str]:
    """free-LLM se patch-proposal sketch. LLM fail = static template (kabhi empty nahi).

    `grounding` (optional) = codebase-search se retrieved REAL relevant code
    (Kilo-Code parity) — diya ho to LLM ko ek guessed `area` ke bajaye actual
    file/line context milta, sketch zyada concrete + sahi file pe banta.
    """
    title, rationale, sketch = (
        f"Fix: {issue[:80]}",
        issue,
        "Investigate karo aur targeted fix + test add karo.",
    )
    try:
        from app.voice_agent import free_ai

        user_content = (
            f"Issue: {issue}\nLikely area: {area}\n"
            "Repo: FastAPI leadgen platform, free-stack, never-raise/gated patterns."
        )
        if grounding:
            user_content += "\n\n" + grounding

        text, _ = await asyncio.wait_for(
            free_ai.chat(
                "Tu ek senior Python engineer hai. Ek production issue diya hai. JSON-only output: "
                '{"title": "...", "rationale": "kya/kyun (2 lines)", "sketch": "suggested code change ka concrete sketch — file, function, kya badle (5-8 lines)"}',
                [{"role": "user", "content": user_content}],
                max_tokens=400,
                temperature=0.3,
            ),
            timeout=40,
        )
        if text:
            s = text.strip()
            if "{" in s:
                s = s[s.index("{") : s.rindex("}") + 1]
            d = json.loads(s)
            title = str(d.get("title") or title)[:120]
            rationale = str(d.get("rationale") or rationale)[:500]
            sketch = str(d.get("sketch") or sketch)[:1500]
    except Exception:
        pass
    return {"title": title, "rationale": rationale, "sketch": sketch}


async def scan_and_propose() -> dict[str, Any]:
    """Hourly scan (watchdog-wired, gated) — naye issues pe Tier-2 proposals banao."""
    sigs = _collect_signals()
    if not sigs:
        return {"ok": True, "signals": 0, "proposed": 0}

    day = _now().strftime("%Y-%m-%d")
    recent = list_patches(limit=300)
    # Dedupe fix (duplicate 8b05c720 lesson): jis signal ka patch already OPEN hai
    # (proposed = decision pending, approved = fix in-flight via deploy-loop), usi
    # signal pe naya proposal mat banao — warna approve hote hi agle din wahi issue
    # dobara propose hota tha (merge me 'at' approval-time ban jata, day-check miss).
    # Sirf CLOSED (rejected/applied) signals re-propose ho sakte, woh bhi same-day nahi.
    open_keys = {r.get("signal_key") for r in recent if r.get("status") in ("proposed", "approved")}
    seen_today = {r.get("signal_key") for r in recent if str(r.get("at", "")).startswith(day)}
    new = [s for s in sigs if s["key"] not in open_keys and s["key"] not in seen_today][
        :_MAX_PROPOSALS_PER_SCAN
    ]

    proposed = []
    for s in new:
        # Kilo-Code parity: ground the proposal in ACTUAL relevant code (semantic
        # codebase search) instead of a single guessed `area` + blind LLM. Gated
        # CODE_SEARCH (default OFF), never-raise; empty index → behaves as before.
        grounding, grounded_files = "", []
        try:
            from app.agents import code_search

            if code_search.enabled():
                hits = await code_search.search(s["issue"], k=5)
                grounding = code_search.grounding_block(hits)
                grounded_files = [
                    f"{h.get('file')}:{h.get('start_line')}-{h.get('end_line')}" for h in hits
                ]
        except Exception:
            pass

        p = await _propose(s["issue"], s["area"], grounding)
        rec = {
            "id": uuid.uuid4().hex[:10],
            "signal_key": s["key"],
            "title": p["title"],
            "issue": s["issue"],
            "area": s["area"],
            "grounded_files": grounded_files,
            "rationale": p["rationale"],
            "sketch": p["sketch"],
            "status": "proposed",
            "at": _now().isoformat(),
        }

        # OpenCode parity: self-check the proposal's referenced paths actually exist
        # (hallucinated file-path = top LLM failure-mode) so admin can trust it before
        # approving. Gated CODE_DIAGNOSTICS (default OFF), never-raise. Code-syntax/lint
        # validation lives in the admin diagnostics endpoint (admin pastes real code).
        try:
            from app.agents import code_diagnostics

            if code_diagnostics.enabled():
                refs = [s["area"]] + grounded_files
                rdiags = code_diagnostics.check_references(refs)
                rec["diagnostics"] = rdiags
                rec["diagnostics_ok"] = not rdiags
        except Exception:
            pass

        _append(rec)
        proposed.append(rec)
        try:
            from app.platform import team

            team.log_event("vikram", "patch_proposed", f"🛠️ {p['title'][:90]}")
        except Exception:
            pass

    if proposed:
        notify = os.environ.get("NOTIFY_EMAIL", "").strip()
        if notify and enabled():
            try:
                from app.integrations.email_sender import email_sender

                body = "\n\n".join(
                    f"[{r['id']}] {r['title']}\nIssue: {r['issue']}\nSketch: {r['sketch'][:400]}"
                    for r in proposed
                )
                await email_sender.send_email(
                    [notify],
                    f"🛠️ Vikram: {len(proposed)} code-upgrade proposal(s)",
                    body + "\n\nApprove/reject: POST /api/growth/upgrader/patches/{id}/status",
                )
            except Exception:
                pass
    return {
        "ok": True,
        "signals": len(sigs),
        "proposed": len(proposed),
        "ids": [r["id"] for r in proposed],
    }


async def run_if_enabled() -> dict[str, Any]:
    if not enabled():
        return {"ok": True, "enabled": False}
    try:
        return await scan_and_propose()
    except Exception as e:  # pragma: no cover
        logger.warning(f"code_upgrader scan failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["enabled", "scan_and_propose", "run_if_enabled", "list_patches", "set_status"]
