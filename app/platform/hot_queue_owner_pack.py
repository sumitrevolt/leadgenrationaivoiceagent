"""Owner Hot-Queue Day Action Pack — daily build of CSV+MD for the owner + ntfy push.

Goal: turn the 42 (or however many) `calling_flagged` / hot-reply cards in
`/api/ops/hotqueue` into a single click-ready file the owner can blast from
their phone in 10 minutes.

Outputs:
  data/hot_queue_for_owner_<YYYY-MM-DD>.csv — Excel-friendly, WA link column
  data/hot_queue_for_owner_<YYYY-MM-DD>.md  — top-15 with clickable wa.me links
  ntfy push → owner phone topic `leadgen-d6b984bd`
Idempotent: re-running on same day overwrites the file. Reads token from
`NTFY_TOKEN` env (matches what app/notifier.py uses). Never raises — wraps in
broad except so the scheduler mark stays ok even if ntfy down.

Customer suppression (2026-09-04): paying/active customer phone numbers are
stripped from the pack BEFORE any wa.me link or UPI kit is generated. See
`_existing_customer_phones` for the fail-visible contract.
"""
from __future__ import annotations

import csv
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.marketing.upi_kit import payment_kit
from app.platform import reply_agent

logger = logging.getLogger(__name__)


def _typesafe_score_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score hot-queue leads by TypeSafe judgment (intent urgency) and re-sort descending.

    TypeSafe `Score` question: how urgent is it to contact this lead RIGHT NOW
    (context: pricing_to_payment bottleneck — highest-intent leads must be
    contacted before they go cold).

    Contract:
    - One TypeSafe call per BUILD (not per row) — state carries all rows in batch.
      TypeSafe is a DECISION API, not a text generator; one call = O(1) quota.
    - FAIL-OPEN: TypeSafe absent/error → original freshness sort returned unchanged.
    - Only `ts_score` (float 0..1) and `ts_rank` (int 1..N) injected per row.
    - NEVER logs key, raw API body, or private lead content (only fingerprint).
    - Consumer: build_owner_pack() — runs once daily in scheduler.
    """
    if not rows:
        return rows

    try:
        from app.platform.typesafe_integration import (
            Noul,
            Score,
            TypeSafeClient,
            credential_state,
            fingerprint,
            _get_api_key,
        )

        cred = credential_state()
        if not cred.get("enabled"):
            logger.debug("[hq_pack_ts] TypeSafe ABSENT — original sort preserved")
            return rows

        key = _get_api_key()
        logger.info(
            "[hq_pack_ts] Scoring %d hot-queue rows via TypeSafe (fp=%s)",
            len(rows),
            fingerprint(key) if key else "NONE",
        )

        client = TypeSafeClient(api_key=key, model="jev-latest")

        # Build a compact state representing all rows (business/intent/channel only —
        # no phone numbers, emails, or PII go to the TypeSafe API).
        row_summaries = [
            {
                "idx": i,
                "intent": str(r.get("intent") or "unknown"),
                "channel": str(r.get("channel") or "email"),
                "niche": str(r.get("niche") or ""),
                "city": str(r.get("city") or ""),
                "age_hours": r.get("age_hours", 0),
                "has_phone": bool(r.get("phone")),
                "has_wa": bool(r.get("wa_link")),
            }
            for i, r in enumerate(rows)
        ]

        state = {
            "context": "LeadGen AI India hot-queue — leads who replied to outreach or called",
            "product": "AI Automated Marketing Rs1999/mo — target: small local Indian businesses",
            "bottleneck": "pricing_to_payment: visitors see pricing but hesitate on UPI manual payment",
            "goal": "Owner should contact highest-intent leads first to maximize conversion today",
            "row_count": len(rows),
            "leads": row_summaries[:20],  # send top-20 only (quota discipline)
        }

        # Score question: how urgent to contact? URGENT/SOON/LATER
        resp = client.system_one(
            state,
            {
                "top_lead_urgency": Score(
                    "Rank these hot-queue leads by contact urgency for the owner to maximize revenue conversion. "
                    "Interested/question intents with phone reachability = highest urgency.",
                    criteria=["urgent_contact_now", "contact_today", "can_wait"],
                ),
                "has_high_intent_lead": Noul(
                    "Does this hot-queue batch contain at least one lead likely to convert "
                    "to a paid subscription if the owner contacts them within 2 hours?"
                ),
            },
        )

        if not resp.success:
            logger.warning(
                "[hq_pack_ts] TypeSafe call failed: %s — original sort preserved",
                resp.error,
            )
            return rows

        # Map TypeSafe score back to rows:
        # - "urgent_contact_now" → 1.0, "contact_today" → 0.6, "can_wait" → 0.2
        # - Intent signals override: "interested" +0.3, "question" +0.15, "not_interested" -0.5
        # - has_phone + has_wa: +0.1 each
        _URGENCY_MAP = {
            "urgent_contact_now": 1.0,
            "contact_today": 0.6,
            "can_wait": 0.2,
        }
        _INTENT_BONUS = {
            "interested": 0.3,
            "question": 0.15,
            "objection": 0.05,
            "ooo": -0.1,
            "not_interested": -0.5,
            "unsubscribe": -0.8,
        }
        base_score_val = resp.value
        base = _URGENCY_MAP.get(str(base_score_val or "contact_today"), 0.6)
        has_high_intent = (resp.answers.get("has_high_intent_lead") or {}).get("noul", 0.5)

        scored = []
        for r in rows:
            intent_b = _INTENT_BONUS.get(str(r.get("intent") or ""), 0.0)
            phone_b = 0.1 if r.get("phone") else 0.0
            wa_b = 0.1 if r.get("wa_link") else 0.0
            # Freshness bonus: <2h old = +0.1, <24h = +0.05
            age = float(r.get("age_hours") or 0)
            fresh_b = 0.1 if age < 2 else (0.05 if age < 24 else 0.0)
            ts_score = min(1.0, max(0.0, base + intent_b + phone_b + wa_b + fresh_b))
            r = dict(r)
            r["ts_score"] = round(ts_score, 3)
            r["ts_has_high_intent"] = round(float(has_high_intent), 3)
            scored.append(r)

        sorted_rows = sorted(scored, key=lambda x: x["ts_score"], reverse=True)
        for i, r in enumerate(sorted_rows, 1):
            r["ts_rank"] = i

        logger.info(
            "[hq_pack_ts] TypeSafe scored %d rows. Top intent: %s (score=%.3f). "
            "has_high_intent_noul=%.2f. model=jev-latest.",
            len(sorted_rows),
            sorted_rows[0].get("intent") if sorted_rows else "?",
            sorted_rows[0].get("ts_score", 0.0) if sorted_rows else 0.0,
            float(has_high_intent),
        )
        return sorted_rows

    except Exception as exc:
        logger.warning(
            "[hq_pack_ts] TypeSafe scoring failed (fail-open, original sort): %s", exc
        )
        return rows


def _last10(value: object) -> str:
    """Normalise any phone shape to its last 10 digits ('' when not usable).

    Matching on the last 10 digits is deliberate: the hot queue carries a mix
    of `+91…`, `91…`, bare 10-digit and formatted numbers, and a prospect row
    that differs only by country prefix is still the same human being.
    """
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def _row_phones(row: dict) -> set[str]:
    """Every phone identity a hot-queue row could be sent to."""
    out: set[str] = set()
    direct = _last10(row.get("phone"))
    if direct:
        out.add(direct)
    wa = str(row.get("wa_link") or "")
    if "wa.me/" in wa:
        tail = wa.split("wa.me/", 1)[1].split("?", 1)[0].split("/", 1)[0]
        parsed = _last10(tail)
        if parsed:
            out.add(parsed)
    return out


def _existing_customer_phones() -> tuple[set[str], bool]:
    """Phones of active customers, plus whether the lookup actually succeeded.

    Returns `(phones, ok)`. `ok=False` means the client store could not be read,
    so the returned set is EMPTY and NOT trustworthy. Callers must surface that
    rather than silently behaving as if there were no customers — a silent
    fail-open here is how a paying customer ends up inside a prospecting blast.
    """
    try:
        from app.marketing import clients_store
    except Exception as exc:  # import-time failure = unverifiable, not "no customers"
        logger.warning("hot_queue_pack: clients_store import failed: %s", exc)
        return set(), False
    try:
        phones: set[str] = set()
        for c in clients_store.list_clients() or []:
            if str(c.get("status") or "active").lower() in {"churned", "cancelled", "deleted"}:
                continue
            digits = _last10(c.get("phone"))
            if digits:
                phones.add(digits)
        return phones, True
    except Exception as exc:
        logger.warning("hot_queue_pack: customer phone lookup failed: %s", exc)
        return set(), False


async def build_owner_pack(limit: int = 200, push_ntfy: bool = True) -> dict:
    """Build today's owner action pack + optional ntfy push. Never raises."""
    try:
        rows = reply_agent.hot_queue(limit=limit, scope="boss") or []
    except Exception as exc:  # never raise — defensive surface
        return {"ok": False, "error": f"hot_queue_unavailable: {exc}", "rows": 0}

    # Drop existing customers BEFORE any link/kit is built — a suppressed row
    # must never have a sendable wa.me URL attached to it.
    try:
        customer_phones, suppression_ok = _existing_customer_phones()
    except Exception as exc:  # pack contract: never raise, but never hide it either
        logger.error("hot_queue_pack: suppression aborted: %s", exc)
        customer_phones, suppression_ok = set(), False
    excluded_customers = 0
    if customer_phones:
        kept = []
        for x in rows:
            if _row_phones(x) & customer_phones:
                excluded_customers += 1
                continue
            kept.append(x)
        rows = kept
    suppression_state = "active" if suppression_ok else "unverified"

    # TypeSafe-powered lead ranking (R1 / TypeSafe integration priority: hot_queue_lead_ranking)
    # Fail-open: if TypeSafe absent/error, original freshness sort is preserved.
    # One API call per pack build (not per row) — quota-disciplined.
    rows = _typesafe_score_rows(rows)

    # Inject fallback UPI Payment Flows if card doesn't already have wa_link
    for x in rows:
        if not x.get("wa_link") and x.get("phone"):
            raw_phone = str(x.get("phone") or "").strip().lstrip("+")
            if raw_phone.startswith("91") and len(raw_phone) == 12:
                clean_phone = raw_phone
            elif len(raw_phone) == 10:
                clean_phone = f"91{raw_phone}"
            else:
                clean_phone = raw_phone
            vpa = x.get("vpa", "default.upi@bank")
            amount = x.get("amount", 499)
            kit = payment_kit(x.get("business_name", "Lead"), vpa, amount, "LeadGen Payment")
            from urllib.parse import quote
            x["wa_link"] = f"https://wa.me/{clean_phone}?text={quote(kit['wa_payment_msg'])}"
            if not x.get("draft"):
                x["draft"] = kit["wa_payment_msg"]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    csv_path = f"data/hot_queue_for_owner_{today}.csv"
    md_path = f"data/hot_queue_for_owner_{today}.md"

    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "rank",
                    "ts_score",
                    "ts_rank",
                    "business",
                    "from",
                    "niche",
                    "city",
                    "channel",
                    "intent",
                    "phone",
                    "wa_link",
                    "draft_preview",
                ]
            )
            for i, x in enumerate(rows, 1):
                wa = x.get("wa_link", "") or ""
                phone = wa.split("wa.me/")[1].split("?")[0] if "wa.me/" in wa else ""
                w.writerow(
                    [
                        i,
                        x.get("ts_score", ""),
                        x.get("ts_rank", ""),
                        (x.get("business_name") or "")[:40],
                        (x.get("from") or "")[:40],
                        x.get("niche", ""),
                        x.get("city", ""),
                        x.get("channel", ""),
                        x.get("intent", ""),
                        phone,
                        wa,
                        (x.get("draft") or "").replace("\r", " ").replace("\n", " ").strip()[:120],
                    ]
                )
    except Exception as exc:
        return {"ok": False, "error": f"csv_write_failed: {exc}", "rows": 0}

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Owner Hot-Queue Day Action Pack — {today}\n\n")
            f.write(
                f"**Total hot leads:** {len(rows)} | "
                f"**All have WA link + UPI deep-link pre-embedded**\n\n"
            )
            if excluded_customers:
                f.write(
                    f"> {excluded_customers} row(s) removed: phone belongs to an "
                    f"existing customer (prospecting blast guard).\n\n"
                )
            if suppression_state == "unverified":
                f.write(
                    "> **WARNING — customer suppression UNVERIFIED:** the client store "
                    "could not be read, so no customer was excluded. Verify before "
                    "sending this pack.\n\n"
                )
            # Show TypeSafe scoring note if rows were scored
            ts_scored = any(r.get("ts_score") is not None for r in rows)
            if ts_scored:
                top_score = rows[0].get("ts_score", 0.0) if rows else 0.0
                high_intent_p = rows[0].get("ts_has_high_intent", 0.5) if rows else 0.5
                f.write(
                    f"> **TypeSafe-scored (jev-1.13.0):** Leads sorted by contact urgency. "
                    f"Top lead urgency score: `{top_score:.3f}`. "
                    f"High-intent conversion probability: `{high_intent_p:.0%}`.\n\n"
                )
            f.write("## Top 15 (action these first)\n\n")
            for i, x in enumerate(rows[:15], 1):
                wa = x.get("wa_link", "") or ""
                phone = wa.split("wa.me/")[1].split("?")[0] if "wa.me/" in wa else "?"
                ts_badge = f" 🎯 `ts={x.get('ts_score', '?')}`" if x.get("ts_score") is not None else ""
                f.write(f"### {i}. {x.get('business_name', '?')}{ts_badge}\n")
                f.write(f"- **Phone:** `{phone}`\n")
                f.write(f"- **Intent:** {x.get('intent', '?')} | **Niche:** {x.get('niche', '?')}\n")
                f.write(f"- **City:** {x.get('city', '?')}\n")
                f.write(f"- **WA link:** <{wa}>\n")
                f.write(
                    f"- **Draft preview:** "
                    f"{(x.get('draft') or '')[:140]}\n\n"
                )
            f.write(
                f"\n---*\n*Generated by Hermes Owner OS. "
                f"Full CSV: `data/hot_queue_for_owner_{today}.csv`*\\n"
            )
    except Exception:
        pass  # md is nice-to-have

    ntfy_status = "skipped"
    if push_ntfy and rows:
        ntfy_status = await _push_ntfy(rows, today)

    ts_scored_count = sum(1 for r in rows if r.get("ts_score") is not None)
    return {
        "ok": True,
        "rows": len(rows),
        "csv": csv_path,
        "md": md_path,
        "ntfy": ntfy_status,
        "excluded_existing_customers": excluded_customers,
        "customer_suppression": suppression_state,
        "ts_scored": ts_scored_count,
        "ts_model": "jev-1.13.0" if ts_scored_count else None,
    }


async def _push_ntfy(rows: list, today: str) -> str:
    """Best-effort ntfy push to owner topic. ASCII-safe (no emoji header)."""
    try:
        token = os.environ.get("NTFY_TOKEN", "").strip()
        topic = os.environ.get(
            "NTFY_TOPIC", os.environ.get("NTFY_DEFAULT_TOPIC", "leadgen-d6b984bd")
        ).strip() or "leadgen-d6b984bd"
        base = os.environ.get("NTFY_URL", "http://ntfy:80").strip()
        if not base or not topic:
            return "skip_no_config"
        url = f"{base.rstrip('/')}/{topic}"
        top3 = rows[:3]
        lines = [
            f"Hot Queue Day Pack ready — {len(rows)} leads",
            "",
        ]
        for x in top3:
            wa = x.get("wa_link", "") or ""
            ph = wa.split("wa.me/")[1].split("?")[0] if "wa.me/" in wa else "?"
            lines.append(
                f"- {str(x.get('business_name', '?'))[:30]} "
                f"({x.get('city', '?')}) -> wa.me/{ph}"
            )
        lines += [
            "",
            f"Full: data/hot_queue_for_owner_{today}.md",
            f"CSV: data/hot_queue_for_owner_{today}.csv",
        ]
        body = "\n".join(lines).encode("ascii", "replace")
        headers = {
            "Title": f"{len(rows)} hot leads ready".encode("ascii", "replace"),
            "Priority": "high",
            "Tags": "fire,zap",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            url, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return f"sent_{r.status}"
    except Exception as exc:
        return f"failed: {str(exc)[:120]}"


def check_gates() -> dict[str, str]:
    """Compliance + operational gates snapshot for /admin/* and worker tasks.

    Contract (consumed by ``admin_api._gate_check``):
      ``{"<gate_name>": "pass" | "<reason>"}``
    ANY value != "pass" is treated as an OPEN gate and causes the admin
    endpoint to 403. Therefore this function MUST default to FAIL-CLOSED:
    if a primitive cannot be read, the gate reports a non-"pass" reason
    rather than silently passing.

    Gates composed (real primitives, not stubbed):

      * ``kill_fence``    — admin kill engaged? (`voice_launch.admin_kill_engaged`)
      * ``recording_ok``  — recording gate green? (`voice_launch.recording_gate_ok`)
      * ``campaign_on``   — campaign enabled flag? (`voice_launch.campaign_enabled`)
      * ``voice_window``  — TRAI 09:00–21:00 IST? (local-time math; pure)
      * ``emergency_stop``— `EMERGENCY_STOP=1`? (env, hard halt)
      * ``whatsapp_auto`` — WA auto-send gate (env, off by default)

    No new compliance gates are invented here — only canonical primitives
    are composed. Owner can extend the list (add a key) without re-wiring
    callers, because ``admin_api._gate_check`` is gate-name agnostic.
    """
    gates: dict[str, str] = {}

    # ---- 1. Kill fence (canonical: voice_launch admin_kill_engaged) ----
    try:
        from app.telephony import voice_launch

        kill = bool(voice_launch.admin_kill_engaged())
        gates["kill_fence"] = "pass" if not kill else "admin_kill_engaged"
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_gates: kill_fence unreadable (%s)", exc.__class__.__name__)
        gates["kill_fence"] = "unverified:kill_fence"

    # ---- 2. Recording gate (canonical: voice_launch.recording_gate_ok) ----
    try:
        from app.telephony import voice_launch as _vl

        rec_ok, rec_reason = _vl.recording_gate_ok()
        gates["recording_ok"] = "pass" if rec_ok else f"recording:{rec_reason or 'unavailable'}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_gates: recording unreadable (%s)", exc.__class__.__name__)
        gates["recording_ok"] = "unverified:recording"

    # ---- 3. Campaign enabled flag (master voice gate) ----
    try:
        from app.telephony import voice_launch as _vl2

        gates["campaign_on"] = "pass" if bool(_vl2.campaign_enabled()) else "campaign_disabled"
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_gates: campaign unreadable (%s)", exc.__class__.__name__)
        gates["campaign_on"] = "unverified:campaign"

    # ---- 4. Voice window (TRAI 09:00–21:00 IST, local time) ----
    try:
        hh = datetime.now().hour  # naive local; container TZ = IST on VPS
        in_window = 9 <= hh < 21
        gates["voice_window"] = "pass" if in_window else f"outside_ist_window(hour={hh})"
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_gates: voice_window unreadable (%s)", exc.__class__.__name__)
        gates["voice_window"] = "unverified:voice_window"

    # ---- 5. EMERGENCY_STOP (env-level, hard halt) ----
    if os.getenv("EMERGENCY_STOP", "0").strip().lower() in ("1", "true", "yes"):
        gates["emergency_stop"] = "active"

    # ---- 6. WhatsApp auto-send gate (legacy, off by default) ----
    wa = os.getenv("WHATSAPP_AUTO_SEND", "0").strip().lower()
    if wa in ("1", "true", "yes"):
        gates["whatsapp_auto"] = "pass"  # opt-in by owner
    # else: key absent = no signal = admin not blocked on WA

    return gates


__all__ = ["build_owner_pack", "check_gates"]
