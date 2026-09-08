"""Boss unclear → LLM Council decide (safe side-effects only).

Boss samajh aaye → khud Approve/Done.
Samajh na aaye → multi-model council (opinions → peer rank → Chairman) ACTION nikaale.

Side-effects FAIL-SAFE:
  - Hot Queue: done | park_admin | keep (CALL = keep + hint; WA auto-send KABHI nahi)
  - Content approval: approve | park_admin | keep
Gated by LLM_COUNCIL (reuse existing flag). Never raises from public helpers.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_VALID_HQ = frozenset({"DONE", "PARK_ADMIN", "KEEP", "CALL"})
_VALID_APPROVAL = frozenset({"APPROVE", "PARK_ADMIN", "KEEP"})


def parse_council_action(text: str, *, allowed: frozenset[str]) -> dict[str, str]:
    """Chairman text se ACTION / CONFIDENCE / WHY / NEXT nikaalo. Pure logic."""
    raw = str(text or "")
    action = "KEEP"
    m = re.search(r"(?im)^\s*ACTION\s*:\s*([A-Z_]+)\s*$", raw)
    if m:
        cand = m.group(1).strip().upper()
        if cand in allowed:
            action = cand
    conf = "medium"
    cm = re.search(r"(?im)^\s*CONFIDENCE\s*:\s*(high|medium|low)\s*$", raw)
    if cm:
        conf = cm.group(1).lower()
    why = ""
    wm = re.search(r"(?im)^\s*WHY\s*:\s*(.+)$", raw)
    if wm:
        why = wm.group(1).strip()[:280]
    nxt = ""
    nm = re.search(r"(?im)^\s*NEXT\s*:\s*(.+)$", raw)
    if nm:
        nxt = nm.group(1).strip()[:280]
    return {"action": action, "confidence": conf, "why": why, "next": nxt}


def _hq_question(row: dict[str, Any]) -> str:
    return (
        "LeadGen Hot Queue — boss ko samajh nahi aaya. Tum Chairman ho.\n"
        "Decide karo kya karna chahiye. WhatsApp/email AUTO-SEND mat suggest karo as auto-exec.\n\n"
        f"From: {row.get('from') or '?'}\n"
        f"Business: {row.get('business_name') or '?'}\n"
        f"Intent: {row.get('intent') or '?'}\n"
        f"Niche/City: {row.get('niche') or ''} / {row.get('city') or ''}\n"
        f"Subject: {str(row.get('subject') or '')[:120]}\n"
        f"Draft reply:\n{str(row.get('draft') or '')[:700]}\n"
        f"Age days: {row.get('age_days')}\n"
        f"Injection flag: {bool(row.get('injection_flag'))}\n\n"
        "Allowed ACTION values ONLY:\n"
        "- DONE = boss already handled / spam / not a real sales lead — queue se hatao\n"
        "- PARK_ADMIN = unclear/risky — admin human review ke liye park\n"
        "- CALL = phone pe human call better (queue me rehne do)\n"
        "- KEEP = boss queue me rakho, draft theek hai — 1-click send boss karega\n\n"
        "Last lines MUST be exactly:\n"
        "ACTION: <one>\n"
        "CONFIDENCE: high|medium|low\n"
        "WHY: <one Hinglish line>\n"
        "NEXT: <one concrete step>\n"
    )


def _approval_question(rec: dict[str, Any]) -> str:
    content = rec.get("content") if isinstance(rec.get("content"), dict) else {}
    title = content.get("title") or content.get("occasion") or "post"
    caption = str(content.get("caption") or content.get("text") or "")[:700]
    return (
        "LeadGen customer content approval — boss/owner ko post samajh nahi aaya.\n"
        "Decide: approve publish queue me daale, admin park kare, ya pending chhodo.\n"
        "Auto-publish / WhatsApp bulk send mat suggest karo.\n\n"
        f"Client: {rec.get('client_id') or '?'}\n"
        f"Title: {title}\n"
        f"Caption:\n{caption}\n\n"
        "Allowed ACTION values ONLY:\n"
        "- APPROVE = content theek hai, publish/approval queue me daalo\n"
        "- PARK_ADMIN = unclear/brand-risk — admin review ke liye flag\n"
        "- KEEP = pending chhodo, boss baad me decide kare\n\n"
        "Last lines MUST be exactly:\n"
        "ACTION: <one>\n"
        "CONFIDENCE: high|medium|low\n"
        "WHY: <one Hinglish line>\n"
        "NEXT: <one concrete step>\n"
    )


async def _run_council(question: str) -> dict[str, Any]:
    from app.agents import llm_council

    return await llm_council.run_full_council(question)


async def decide_hot_queue(hq_id: str, *, apply: bool = True) -> dict[str, Any]:
    """Council decide for one Hot Queue row. Optional apply (done/park)."""
    try:
        from app.platform import reply_agent

        hq_id = str(hq_id or "").strip()
        if not hq_id:
            return {"ok": False, "error": "hq_id zaroori hai"}
        row = next(
            (r for r in reply_agent.hot_queue(limit=200, scope="all") if r.get("hq_id") == hq_id),
            None,
        )
        if row is None:
            return {"ok": False, "error": "hq_id nahi mila (ya already done)"}

        result = await _run_council(_hq_question(row))
        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error") or "council fail",
                "hq_id": hq_id,
                "applied": False,
            }

        summary = str((result.get("stage3") or {}).get("response") or "")
        parsed = parse_council_action(summary, allowed=_VALID_HQ)
        applied = False
        apply_error = ""
        if apply:
            action = parsed["action"]
            try:
                if action == "DONE":
                    applied = bool(reply_agent.mark_handled(hq_id))
                elif action == "PARK_ADMIN":
                    applied = bool(
                        reply_agent.park_for_admin(hq_id, note=parsed.get("why") or "council park")
                    )
                elif action in ("KEEP", "CALL"):
                    applied = True  # no mutation — intentional
            except Exception as exc:
                apply_error = str(exc)[:160]
                logger.warning("decide_hot_queue apply failed: %s", exc)

        return {
            "ok": True,
            "hq_id": hq_id,
            "decision": parsed,
            "summary": summary[:1200],
            "applied": applied,
            "apply_error": apply_error,
            "members_used": (result.get("metadata") or {}).get("members_used"),
        }
    except Exception as exc:
        logger.warning("decide_hot_queue failed: %s", exc)
        return {"ok": False, "error": str(exc)[:200], "applied": False}


async def decide_approval(
    client_id: str, approval_id: str, *, apply: bool = True
) -> dict[str, Any]:
    """Council decide for one pending content approval. Optional apply."""
    try:
        from app.marketing import content_approval

        client_id = str(client_id or "").strip()
        approval_id = str(approval_id or "").strip()
        if not client_id or not approval_id:
            return {"ok": False, "error": "client_id + approval_id zaroori"}

        rec = content_approval._by_id_for_client(client_id, approval_id)
        if rec is None or str(rec.get("status") or "") != "pending":
            return {"ok": False, "error": "pending approval nahi mila"}

        result = await _run_council(_approval_question(rec))
        if not result.get("ok"):
            return {
                "ok": False,
                "error": result.get("error") or "council fail",
                "approval_id": approval_id,
                "applied": False,
            }

        summary = str((result.get("stage3") or {}).get("response") or "")
        parsed = parse_council_action(summary, allowed=_VALID_APPROVAL)
        applied = False
        apply_error = ""
        apply_result: dict[str, Any] = {}
        if apply:
            action = parsed["action"]
            try:
                if action == "APPROVE":
                    apply_result = content_approval.decide_for_client(
                        client_id, approval_id, "approve", note="council:approve"
                    )
                    applied = bool(apply_result.get("ok"))
                elif action == "PARK_ADMIN":
                    apply_result = content_approval.escalate_for_client(
                        client_id,
                        approval_id,
                        note=parsed.get("why") or "council park_admin",
                    )
                    applied = bool(apply_result.get("ok"))
                elif action == "KEEP":
                    applied = True
            except Exception as exc:
                apply_error = str(exc)[:160]
                logger.warning("decide_approval apply failed: %s", exc)

        return {
            "ok": True,
            "approval_id": approval_id,
            "decision": parsed,
            "summary": summary[:1200],
            "applied": applied,
            "apply_error": apply_error,
            "apply_result": apply_result,
            "members_used": (result.get("metadata") or {}).get("members_used"),
        }
    except Exception as exc:
        logger.warning("decide_approval failed: %s", exc)
        return {"ok": False, "error": str(exc)[:200], "applied": False}


def _gbp_question(client: dict[str, Any], heuristic: dict[str, Any]) -> str:
    from app.marketing import gbp_audit
    from app.platform.safe_ai_payload import mask_customer_data, validate_no_secrets

    c_raw = client if isinstance(client, dict) else {}
    try:
        c = mask_customer_data(c_raw)
        if not isinstance(c, dict):
            c = c_raw
        validate_no_secrets(c)
    except Exception:
        c = c_raw

    socials = c.get("socials") if isinstance(c.get("socials"), dict) else {}
    lines = []
    for q in gbp_audit.AUDIT_QUESTIONS:
        opts = "; ".join(f"{i}={o.get('label')}" for i, o in enumerate(q.get("options") or []))
        lines.append(f"- {q['id']}: {q['q']} | options: {opts}")
    heur = heuristic.get("answers") or {}
    try:
        heur_display = mask_customer_data(heur)
    except Exception:
        heur_display = heur
    return (
        "LeadGen GBP self-audit — boss ko form bhari nahi. Tum Chairman ho.\n"
        "Har sawal ke liye OPTION INDEX suggest karo. Unknown pe CONSERVATIVE "
        "(worst / pata-nahi) index chuno — kabhi best score invent mat karo.\n"
        "Score SAVE mat karo — sirf suggestions. Boss confirm karega.\n\n"
        f"Business: {c.get('business_name') or '?'}\n"
        f"Niche/City: {c.get('niche') or ''} / {c.get('city') or ''}\n"
        f"Phone: {c.get('phone') or c.get('whatsapp_phone') or ''}\n"
        f"Website: {c.get('website') or ''}\n"
        f"GBP link: {c.get('gbp') or socials.get('gbp') or ''}\n"
        f"Services: {str(c.get('services') or '')[:200]}\n"
        f"Heuristic seeds: {heur_display}\n\n"
        "Questions:\n" + "\n".join(lines) + "\n\n"
        "Last lines MUST include one line per question:\n"
        "Q_<id>: <option_index>\n"
        "then:\n"
        "CONFIDENCE: high|medium|low\n"
        "WHY: <one Hinglish line>\n"
        "NEXT: <boss ko GBP pe kya check karna hai>\n"
    )


async def decide_gbp_suggest(client: dict[str, Any]) -> dict[str, Any]:
    """Council + heuristic GBP answer suggestions. NEVER persists score."""
    try:
        from app.marketing import gbp_audit

        heur = gbp_audit.heuristic_suggest(client)
        base = dict(heur.get("answers") or {})
        result = await _run_council(_gbp_question(client, heur))
        if not result.get("ok"):
            return {
                "ok": True,
                "answers": base,
                "sources": heur.get("sources") or {},
                "mode": "heuristic_fallback",
                "council_error": result.get("error") or "council fail",
                "note_hi": heur.get("note_hi") or "",
                "persisted": False,
            }

        summary = str((result.get("stage3") or {}).get("response") or "")
        parsed = gbp_audit.parse_council_gbp_answers(summary)
        merged = {**base, **parsed}
        # clamp all
        for q in gbp_audit.AUDIT_QUESTIONS:
            qid = q["id"]
            merged[qid] = gbp_audit._clamp_idx(qid, merged.get(qid, gbp_audit._worst_idx(qid)))

        meta = parse_council_action(
            summary, allowed=frozenset({"KEEP", "DONE", "PARK_ADMIN", "CALL", "APPROVE"})
        )
        return {
            "ok": True,
            "answers": merged,
            "sources": heur.get("sources") or {},
            "mode": "council",
            "council_filled": len(parsed),
            "why": meta.get("why") or "",
            "next": meta.get("next") or "",
            "confidence": meta.get("confidence") or "medium",
            "summary": summary[:1200],
            "note_hi": (
                "Council suggestions pre-select ho sakte hain. Boss GBP pe check "
                "karke Score nikaalo — bina confirm save nahi hota."
            ),
            "persisted": False,
            "members_used": (result.get("metadata") or {}).get("members_used"),
        }
    except Exception as exc:
        logger.warning("decide_gbp_suggest failed: %s", exc)
        try:
            from app.marketing import gbp_audit

            heur = gbp_audit.heuristic_suggest(client)
            return {**heur, "council_error": str(exc)[:160], "persisted": False}
        except Exception:
            return {"ok": False, "error": str(exc)[:200], "persisted": False}


__all__ = [
    "parse_council_action",
    "decide_hot_queue",
    "decide_approval",
    "decide_gbp_suggest",
]
