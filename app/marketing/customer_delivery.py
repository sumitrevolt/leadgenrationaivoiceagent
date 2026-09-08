"""Customer value-delivery — value-first, delivery-guaranteed (2026-07-05).

WHY: a paying customer (jiya makeover, ₹1,999) was GHOSTED — the system BUILT her
value (live mini-site, content pack, brand kit) but delivered NONE of it because
onboarding asked her to "describe your business" first and her reply was never
captured (silent single-thread failure). Council decision (docs/
CUSTOMER_DELIVERY_AUTOMATION_2026_07_05.md): on `paid`, DELIVER value first — don't
ask, don't wait — and never let a paid customer sit silently undelivered.

This module is the P0 delivery guarantee:
  - `deliver_client_value(client)` — WhatsApp the live mini-site link + what they
    got. GATED `AUTO_DELIVER_VALUE` (default OFF) so real customer sends are
    reviewed before going live; `force=True` for an operator-triggered single send.
  - `find_undelivered_paid_clients()` — read-only dead-man detector: paid+active
    clients not yet delivered (powers the founder alert + operator surface).
  - `run_delivery_sweep()` — the dead-man sweep (fail-LOUD: records stuck customers,
    never a silent swallow).

Delivery state lives on the client record: `delivery_state` in
{paid, assets_built, delivered, acknowledged} + `delivered_at`. "delivered" is set
ONLY after an actual send (never a backend flag like setup_done).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PAID_PLACEHOLDER_PLANS = {"", "free", "trial", "none", "pending"}
_STUCK_LOG = os.path.join("data", "delivery_stuck.jsonl")


def _flag_on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _is_self_brand(client: dict[str, Any]) -> bool:
    """LeadGen AI ka apna self-brand record (delivery target NAHI — ye company khud hai).
    Markers mirror auto_content._ensure_self_client."""
    if str(client.get("id") or "") == "leadgenai-self":
        return True
    if str(client.get("niche") or "").strip().lower() == "ai_marketing":
        return True
    return str(client.get("business_name") or "").strip().lower() in ("leadgen ai", "leadsgenai")


def _payment_evidence(client: dict[str, Any]) -> bool | None:
    """Tri-state: does an immutable Rule-46 invoice belong to this customer identity?

    True  = invoice found (real payment proof).
    False = invoice ledger read cleanly AND has real content, but none for this id.
    None  = ledger missing/empty/unreadable -> UNKNOWN, caller must fail-OPEN.

    WHY tri-state: a plan is SELECTED at signup before any money moves, so plan name
    alone is not payment proof (that is how synthetic "Test Biz" (plan=growth, zero
    invoices) paged the founder hourly as a PAID customer). But a hard fail-CLOSED
    here would silently STOP delivery for a real paying customer the moment the
    ledger is unreadable — the exact ghosting incident this module exists to prevent.
    So: only judge "not paid" when we have a FUNCTIONING ledger with real content;
    otherwise return None and let the caller fall back to the plan check.

    Identity mirrors `activation._client_has_payment_evidence`: legacy/recreated IDs
    keep invoice ownership via `billing_client_ids` (never mutate the invoice).
    """
    try:
        ids = {str(client.get("id") or "").strip()}
        aliases = client.get("billing_client_ids") or []
        if isinstance(aliases, (list, tuple, set)):
            ids.update(str(x or "").strip() for x in aliases)
        ids.discard("")
        if not ids:
            return None

        from app.billing import gst_invoice

        rows = gst_invoice._read()
        if not rows:
            # No ledger content = anomaly, NOT proof of non-payment. Fail-OPEN.
            return None
        return any(str(row.get("client_id") or "").strip() in ids for row in rows)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("payment-evidence lookup failed (fail-open to plan): %s", exc)
        return None


def is_paid_client(client: dict[str, Any]) -> bool:
    """Active client on a real (non-free/trial) plan = delivery-ELIGIBLE. Self-brand
    (LeadGen AI apna record) delivery target nahi — exclude.

    NOTE: plan is chosen at signup BEFORE money moves, so this is eligibility, not
    payment proof. For "did they actually pay" use `has_paid_evidence()`.
    """
    if not isinstance(client, dict):
        return False
    if _is_self_brand(client):
        return False
    if str(client.get("status") or "").lower() != "active":
        return False
    plan = str(client.get("plan") or "").strip().lower()
    return bool(plan) and plan not in _PAID_PLACEHOLDER_PLANS


def has_paid_evidence(client: dict[str, Any]) -> bool:
    """Delivery-eligible AND payment is not contradicted by a functioning invoice
    ledger. Used to gate the founder-paging dead-man alert so a never-invoiced
    tenant cannot masquerade as a paying customer.

    Fail-OPEN by design: if the ledger is unknown (None) we keep the client in the
    alert set — a real paying customer must NEVER be silently dropped from the
    dead-man detector just because the ledger hiccuped.
    """
    if not is_paid_client(client):
        return False
    return _payment_evidence(client) is not False


def mini_site_url(client: dict[str, Any]) -> str:
    """Live mini-site URL from the client's slug, or "" if none. Pure."""
    slug = str((client or {}).get("slug") or "").strip()
    if not slug:
        return ""
    try:
        from app.config import settings

        base = str(getattr(settings, "public_base_url", "") or "https://leadsgenai.in").rstrip("/")
    except Exception:
        base = "https://leadsgenai.in"
    return f"{base}/b/{slug}"


def is_delivered(client: dict[str, Any]) -> bool:
    """True once value has actually been delivered (received-side, not a backend flag)."""
    return str((client or {}).get("delivery_state") or "").lower() in ("delivered", "acknowledged")


def is_activated(client: dict[str, Any]) -> bool:
    """Council's true North-Star: 'activated' = customer ne value RECEIVE + ACKNOWLEDGE
    ki (delivery message ka reply / engage), sirf 'sent' nahi. Instrumentation signal."""
    return str((client or {}).get("delivery_state") or "").lower() == "acknowledged"


def try_mark_acknowledged(from_number: str) -> bool:
    """Inbound message from a DELIVERED paid customer = acknowledgment (council:
    'delivered = acknowledged'). delivery_state delivered->acknowledged flip karo.
    READ-side (koi outbound nahi). True agar mark hua. Never raises. Message ko
    CONSUME nahi karta — caller normal reply-handling jaari rakhe."""
    digits = "".join(ch for ch in str(from_number or "") if ch.isdigit())[-10:]
    if not digits:
        return False
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            if not is_paid_client(c):
                continue
            cph = "".join(ch for ch in str(c.get("phone") or "") if ch.isdigit())[-10:]
            if cph and cph == digits and str(c.get("delivery_state") or "").lower() == "delivered":
                clients_store.update_client(
                    str(c.get("id") or ""),
                    delivery_state="acknowledged",
                    acknowledged_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
                logger.info("✅ customer acknowledged delivery: %s", c.get("business_name"))
                return True
    except Exception as exc:
        logger.warning("try_mark_acknowledged err: %s", exc)
    return False


def build_delivery_message(client: dict[str, Any]) -> str:
    """The WhatsApp value-delivery text: live mini-site link + what they got + next
    step. Pure (no side effects) so it is unit-testable. Value-first — no info-ask."""
    biz = str((client or {}).get("business_name") or "aapka business").strip() or "aapka business"
    url = mini_site_url(client)
    lines = [
        f"Namaste! 🎉 {biz} ke liye aapka LeadGen AI setup taiyaar hai —",
    ]
    if url:
        lines.append(f"👉 Aapki LIVE business site: {url}")
        lines.append(
            "(Ye link customers ko WhatsApp/Instagram pe share karein — enquiry seedhe aapke phone pe.)"
        )
    lines.append("📸 Aapke liye ready-to-post content bhi ban chuka hai — har hafte naya milega.")
    lines.append(
        "Koi badlaav chahiye (services/area/photos)? Bas isi message ka reply kar dijiye — main update kar dungi. 🙏"
    )
    return "\n".join(lines)


def find_undelivered_paid_clients() -> list[dict[str, Any]]:
    """Read-only dead-man detector: paid+active clients NOT yet delivered.
    Never raises — returns [] on any error."""
    out: list[dict[str, Any]] = []
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients(status="active"):
            # has_paid_evidence (not is_paid_client): a plan is selected pre-payment,
            # so a never-invoiced synthetic tenant must not page the founder as a
            # ghosted PAYING customer. Fail-OPEN when the ledger is unknown.
            if has_paid_evidence(c) and not is_delivered(c):
                out.append(c)
    except Exception as exc:
        logger.warning("find_undelivered_paid_clients err: %s", exc)
    return out


# Reasons that mean "intentionally gated / data missing" — NOT a delivery failure.
# These get logged as `delivery_gated` instead of `automation_failed` so they
# don't count toward the RED health-score flag (-35 per occurrence). The stuck
# record + ops_alerts + log WARNING are still emitted — fail-LOUD stays loud.
_GATE_REASONS = frozenset({"auto_delivery_off", "sweep_auto_off", "no_phone"})


def _record_stuck(client: dict[str, Any], reason: str) -> None:
    """Fail-LOUD: append a stuck-customer record (NOT a silent debug swallow) so a
    ghosted paying customer is always visible + alertable. Never raises."""
    try:
        os.makedirs("data", exist_ok=True)
        rec = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "client_id": str(client.get("id") or ""),
            "business_name": client.get("business_name"),
            "phone": client.get("phone"),
            "plan": client.get("plan"),
            "reason": reason,
        }
        with open(_STUCK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("delivery _record_stuck err: %s", exc)
    logger.warning(
        "🚨 PAID customer undelivered: %s (%s) — %s",
        client.get("business_name"),
        client.get("id"),
        reason,
    )
    try:
        from app.marketing import delivery_ledger

        # Gate reasons → delivery_gated (no health-score penalty);
        # real failures → automation_failed (RED flag, triggers SLA).
        event_type = "delivery_gated" if reason in _GATE_REASONS else "automation_failed"
        delivery_ledger.log_event(str(client.get("id") or ""), event_type, detail=reason)
    except Exception as le:  # pragma: no cover
        logger.debug("delivery _record_stuck ledger log skip: %s", le)
    # Fail-LOUD, for real: a jsonl line + a log WARNING is what let the original
    # jiya-makeover ghosting sit undiscovered for days. Page the founder's phone
    # directly (OPS_ALERTS-gated + per-client cooldown'd inside the helper — never
    # raises, never blocks this function even if ntfy itself is unconfigured).
    try:
        from app.platform import ops_alerts

        ops_alerts.alert_paid_customer_stuck(
            str(client.get("id") or ""), str(client.get("business_name") or ""), reason
        )
    except Exception as ae:  # pragma: no cover
        logger.debug("delivery _record_stuck ops_alerts skip: %s", ae)


async def deliver_client_value(client: dict[str, Any], force: bool = False) -> dict[str, Any]:
    """Value-first delivery: WhatsApp the live mini-site link + content note to the
    paying customer, then mark delivery_state='delivered'. GATED AUTO_DELIVER_VALUE
    (default OFF) unless force=True (operator single-send). Never raises; fail-LOUD."""
    res: dict[str, Any] = {"delivered": False, "client_id": str((client or {}).get("id") or "")}
    if not is_paid_client(client):
        res["skipped"] = "not_paid"
        return res
    if is_delivered(client):
        res["skipped"] = "already_delivered"
        res["delivered"] = True
        return res
    if not (force or _flag_on("AUTO_DELIVER_VALUE")):
        _record_stuck(client, "auto_delivery_off")
        res["skipped"] = "AUTO_DELIVER_VALUE off"
        return res
    phone = str(client.get("phone") or "").strip()
    if not phone:
        _record_stuck(client, "no_phone")
        res["skipped"] = "no_phone"
        return res
    try:
        from app.integrations.whatsapp import get_whatsapp_sender

        sender = get_whatsapp_sender()
        sent = await sender.send_text_message(phone, build_delivery_message(client))
        ok = bool(sent) and not (isinstance(sent, dict) and sent.get("error"))
        wa_err = str(sent.get("error") or "") if isinstance(sent, dict) else ""
    except Exception as exc:
        _record_stuck(client, f"send_error:{type(exc).__name__}")
        res["error"] = str(exc)
        return res
    if not ok:
        # NEW (gated, additive, default OFF): WhatsApp blocked/undeliverable (e.g.
        # recipient_not_on_whatsapp)? Deliver the SAME value-drop via email so a paid
        # customer is never silently lost. OFF-by-default = zero behaviour change
        # until DELIVERY_EMAIL_FALLBACK=1 (project convention: additive + inert).
        if _flag_on("DELIVERY_EMAIL_FALLBACK"):
            email_ok, note = await _try_email_delivery(client)
            if email_ok:
                try:
                    from app.marketing import clients_store

                    clients_store.update_client(
                        str(client.get("id") or ""),
                        delivery_state="delivered",
                        delivered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("delivery email-fallback state-update err: %s", exc)
                res["delivered"] = True
                res["channel"] = "email_fallback"
                logger.info(
                    "[delivery] WA blocked (%s) -> value delivered via EMAIL for %s",
                    wa_err or "blocked",
                    client.get("business_name"),
                )
                return res
            logger.info(
                "[delivery] email fallback did not deliver (%s; wa_err=%s)",
                note,
                wa_err or "?",
            )
        _record_stuck(client, wa_err or "send_failed")
        res["error"] = wa_err or "send_failed"
        return res
    try:
        from app.marketing import clients_store

        clients_store.update_client(
            str(client.get("id") or ""),
            delivery_state="delivered",
            delivered_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
    except Exception as exc:
        logger.warning("deliver_client_value state-update err: %s", exc)
    res["delivered"] = True
    return res


async def _try_email_delivery(client: dict[str, Any]) -> tuple[bool, str]:
    """WA blocked -> deliver the same value-drop message via email (additive; gated
    by DELIVERY_EMAIL_FALLBACK in the caller). Returns (sent, note). Never raises."""
    to_email = str(client.get("email") or client.get("contact_email") or "").strip()
    if not to_email:
        return False, "no_customer_email"
    try:
        from app.integrations.email_sender import EmailSender

        sender = EmailSender()
        biz = str(client.get("business_name") or "aapka business").strip() or "aapka business"
        subject = f"🎉 {biz} — aapka LeadGen AI setup ready hai"
        body = build_delivery_message(client)
        ok = bool(await sender.send_email([to_email], subject, body))
        return (True, "sent") if ok else (False, "email_send_failed")
    except Exception as exc:  # noqa: BLE001 - defensive, never raise into delivery
        logger.warning("[delivery] email fallback failed: %s", exc)
        return False, f"email_error:{type(exc).__name__}"


async def run_delivery_sweep(limit: int = 20) -> dict[str, Any]:
    """Dead-man sweep: find paid customers not yet delivered → deliver (if
    AUTO_DELIVER_VALUE) else record-loud for founder review. Returns a summary.
    Never raises. Registered for the scheduler (staff 'onboard'/dedicated job)."""
    res: dict[str, Any] = {"undelivered": 0, "delivered": 0, "stuck": 0}
    try:
        pending = find_undelivered_paid_clients()
        res["undelivered"] = len(pending)
        auto = _flag_on("AUTO_DELIVER_VALUE")
        for c in pending[: max(1, limit)]:
            if auto:
                r = await deliver_client_value(c)
                if r.get("delivered"):
                    res["delivered"] += 1
                else:
                    res["stuck"] += 1
            else:
                _record_stuck(c, "sweep_auto_off")
                res["stuck"] += 1
    except Exception as exc:
        logger.warning("run_delivery_sweep err: %s", exc)
        res["error"] = str(exc)
    return res


# --------------------------------------------------------------------------- #
# P1 #12 — Weekly "aapki marketing chal rahi hai" digest.
# The delivery message promises "har hafte naya content milega" — this backs that
# promise with a real weekly WhatsApp. HONEST metrics only (fable rule: no
# fabricated numbers) — fresh-content count is sourced from the content queue;
# mini-site views/leads are NOT tracked yet so they are omitted, never invented.
# Idempotent: max one digest per customer per 6 days (state file). Gated on the
# SAME AUTO_DELIVER_VALUE consent as delivery. Never raises; fail-loud on stuck.
# --------------------------------------------------------------------------- #
_DIGEST_STATE = os.path.join("data", "weekly_digest_state.json")
_DIGEST_MIN_DAYS = 6


def count_fresh_content(cid: str, days: int = 7) -> int:
    """How many content items were generated for this client in the last `days`.
    Real, sourced from data/content_queue/<cid>.jsonl. 0 on any error."""
    path = os.path.join("data", "content_queue", f"{cid}.jsonl")
    if not cid or not os.path.exists(path):
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    n = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    it = json.loads(line)
                except Exception:
                    continue
                ts = str(it.get("created_at") or it.get("date") or "")
                try:
                    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    if d.timestamp() >= cutoff:
                        n += 1
                except Exception:
                    # date-only "YYYY-MM-DD" without time — count if within window
                    if ts[:10] >= datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%d"):
                        n += 1
    except Exception as exc:
        logger.warning("count_fresh_content err: %s", exc)
    return n


def build_weekly_digest_message(client: dict[str, Any], fresh_count: int) -> str:
    """Weekly value WhatsApp — fresh content + mini-site reminder + share nudge.
    Pure (testable). Honest: only the real fresh_count, no invented views/leads."""
    biz = str((client or {}).get("business_name") or "aapka business").strip() or "aapka business"
    url = mini_site_url(client)
    lines = [f"Namaste! 📅 {biz} ki is hafte ki marketing update —"]
    if fresh_count > 0:
        lines.append(f"📸 {fresh_count} naye ready-to-post content pieces taiyaar hain.")
    else:
        lines.append("📸 Aapka content agent kaam kar raha hai — naye posts jald.")
    if url:
        lines.append(
            f"👉 Aapki site: {url} — ise WhatsApp/Instagram status pe share karein, zyada enquiry milegi."
        )
    lines.append("Koi badlaav ya nayi service add karni ho? Isi message ka reply kar dijiye. 🙏")
    return "\n".join(lines)


def _load_digest_state() -> dict[str, str]:
    try:
        if os.path.exists(_DIGEST_STATE):
            with open(_DIGEST_STATE, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_digest_state(state: dict[str, str]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_DIGEST_STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as exc:
        logger.warning("_save_digest_state err: %s", exc)


def _digest_due(cid: str, state: dict[str, str], now: datetime) -> bool:
    last = state.get(cid)
    if not last:
        return True
    try:
        d = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (now - d).days >= _DIGEST_MIN_DAYS
    except Exception:
        return True


async def run_weekly_digest_sweep(limit: int = 50) -> dict[str, Any]:
    """Weekly value digest to DELIVERED paid customers (once per >=6 days each).
    Called daily but self-throttling. Gated AUTO_DELIVER_VALUE (same consent as
    delivery). Never raises."""
    res: dict[str, Any] = {"due": 0, "sent": 0}
    if not _flag_on("AUTO_DELIVER_VALUE"):
        res["skipped"] = "AUTO_DELIVER_VALUE off"
        return res
    try:
        from app.integrations.whatsapp import get_whatsapp_sender
        from app.marketing import clients_store

        state = _load_digest_state()
        now = datetime.now(timezone.utc)
        sender = get_whatsapp_sender()
        sent = 0
        for c in clients_store.list_clients(status="active"):
            if not is_paid_client(c) or not is_delivered(c):
                continue  # only already-delivered real customers
            cid = str(c.get("id") or "")
            phone = str(c.get("phone") or "").strip()
            if not cid or not phone or not _digest_due(cid, state, now):
                continue
            res["due"] += 1
            msg = build_weekly_digest_message(c, count_fresh_content(cid))
            try:
                r = await sender.send_text_message(phone, msg)
                if bool(r) and not (isinstance(r, dict) and r.get("error")):
                    state[cid] = now.isoformat(timespec="seconds")
                    sent += 1
                else:
                    _record_stuck(c, "weekly_digest_send_failed")
            except Exception as exc:
                _record_stuck(c, f"weekly_digest_err:{type(exc).__name__}")
            if sent >= max(1, limit):
                break
        _save_digest_state(state)
        res["sent"] = sent
    except Exception as exc:
        logger.warning("run_weekly_digest_sweep err: %s", exc)
        res["error"] = str(exc)
    return res


# --------------------------------------------------------------------------- #
# P2 growth loop — mini-site view tracking (#20), monthly ROI receipt (#20),
# case study generator (#18), testimonial ask (#17). All HONEST (real data only,
# no fabricated metrics) + gated + config-driven (no unilateral financial offer).
# --------------------------------------------------------------------------- #
_VIEWS_LOG = os.path.join("data", "site_views.jsonl")
_MONTHLY_STATE = os.path.join("data", "monthly_receipt_state.json")
_TESTIMONIAL_STATE = os.path.join("data", "testimonial_state.json")


def record_site_view(client_id: str) -> None:
    """Append a mini-site view (real, for honest ROI receipts). Never raises."""
    cid = str(client_id or "").strip()
    if not cid:
        return
    try:
        os.makedirs("data", exist_ok=True)
        with open(_VIEWS_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"cid": cid, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                )
                + "\n"
            )
    except Exception as exc:
        logger.debug("record_site_view err: %s", exc)


def site_view_count(cid: str, days: int = 30) -> int:
    """Real mini-site view count for a client over `days`. 0 on error."""
    if not cid or not os.path.exists(_VIEWS_LOG):
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    n = 0
    try:
        with open(_VIEWS_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if str(r.get("cid")) != str(cid):
                    continue
                try:
                    d = datetime.fromisoformat(str(r.get("at") or "").replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    if d.timestamp() >= cutoff:
                        n += 1
                except Exception:
                    n += 1
    except Exception as exc:
        logger.warning("site_view_count err: %s", exc)
    return n


def build_monthly_receipt_message(client: dict[str, Any], views: int, content: int) -> str:
    """Monthly ROI receipt — REAL numbers only (site views + content made). Pure.
    Referral line sirf REFERRAL_REWARD env set ho tab (koi unilateral offer nahi)."""
    biz = str((client or {}).get("business_name") or "aapka business").strip() or "aapka business"
    url = mini_site_url(client)
    lines = [f"Namaste! 📊 {biz} ki is mahine ki report —"]
    if views > 0:
        lines.append(f"👀 Aapki site {views} baar dekhi gayi.")
    if content > 0:
        lines.append(f"📸 {content} naye content pieces bane.")
    if views == 0 and content == 0:
        lines.append(
            "Aapka marketing agent kaam kar raha hai — site share karte rahiye zyada reach ke liye."
        )
    if url:
        lines.append(f"👉 {url} — WhatsApp status/Instagram pe share = zyada enquiry.")
    reward = os.environ.get("REFERRAL_REWARD", "").strip()
    if reward:
        lines.append(
            f"🎁 Kisi dost (shop owner) ko refer karein — {reward}. Bas unka number reply me bhejein."
        )
    return "\n".join(lines)


def build_case_study(client: dict[str, Any]) -> dict[str, Any]:
    """HONEST case study from REAL delivered assets (live site + what was built).
    Founder tool (koi customer send nahi) — 338 warm leads pe attach karne ke liye.
    Testimonial tabhi include hota hai jab client record me actually ho."""
    biz = str((client or {}).get("business_name") or "").strip()
    niche = str((client or {}).get("niche") or "").strip()
    url = mini_site_url(client)
    cid = str((client or {}).get("id") or "")
    testimonial = str((client or {}).get("testimonial") or "").strip()
    headline = f"{biz or 'Ek local business'} ke liye 5 minute me poora AI marketing setup"
    proof: list[str] = []
    if url:
        proof.append(f"Live business site: {url}")
    fresh = count_fresh_content(cid, days=90)
    if fresh:
        proof.append(f"{fresh}+ ready-to-post content pieces")
    if testimonial:
        proof.append(f'Customer: "{testimonial[:200]}"')
    return {
        "client_id": cid,
        "business_name": biz,
        "niche": niche,
        "headline": headline,
        "proof_points": proof,
        "has_testimonial": bool(testimonial),
        "site_url": url,
    }


def _load_json_state(path: str) -> dict[str, str]:
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_json_state(path: str, state: dict[str, str]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as exc:
        logger.warning("_save_json_state err: %s", exc)


async def run_monthly_receipt_sweep(limit: int = 50) -> dict[str, Any]:
    """Monthly ROI receipt to delivered paid customers (once per >=28 days). Called
    from the daily content run (self-throttling). Gated AUTO_DELIVER_VALUE. Honest
    numbers only. Never raises."""
    res: dict[str, Any] = {"due": 0, "sent": 0}
    if not _flag_on("AUTO_DELIVER_VALUE"):
        res["skipped"] = "AUTO_DELIVER_VALUE off"
        return res
    try:
        from app.integrations.whatsapp import get_whatsapp_sender
        from app.marketing import clients_store

        state = _load_json_state(_MONTHLY_STATE)
        now = datetime.now(timezone.utc)
        sender = get_whatsapp_sender()
        sent = 0
        for c in clients_store.list_clients(status="active"):
            if not is_paid_client(c) or not is_delivered(c):
                continue
            cid = str(c.get("id") or "")
            phone = str(c.get("phone") or "").strip()
            if not cid or not phone:
                continue
            last = state.get(cid)
            if last:
                try:
                    d = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    if (now - d).days < 28:
                        continue
                except Exception:
                    pass
            res["due"] += 1
            msg = build_monthly_receipt_message(
                c, site_view_count(cid), count_fresh_content(cid, days=30)
            )
            try:
                r = await sender.send_text_message(phone, msg)
                if bool(r) and not (isinstance(r, dict) and r.get("error")):
                    state[cid] = now.isoformat(timespec="seconds")
                    sent += 1
            except Exception as exc:
                _record_stuck(c, f"monthly_receipt_err:{type(exc).__name__}")
            if sent >= max(1, limit):
                break
        _save_json_state(_MONTHLY_STATE, state)
        res["sent"] = sent
    except Exception as exc:
        logger.warning("run_monthly_receipt_sweep err: %s", exc)
        res["error"] = str(exc)
    return res


async def run_testimonial_sweep(limit: int = 20, min_days: int = 5) -> dict[str, Any]:
    """Ask ACTIVATED (acknowledged) customers for a testimonial, once each, only
    after >=min_days since delivery (so they've had time to see value). Gated
    AUTO_DELIVER_VALUE + AUTO_TESTIMONIAL. Never raises."""
    res: dict[str, Any] = {"asked": 0}
    if not (_flag_on("AUTO_DELIVER_VALUE") and _flag_on("AUTO_TESTIMONIAL")):
        res["skipped"] = "flag off"
        return res
    try:
        from app.integrations.whatsapp import get_whatsapp_sender
        from app.marketing import clients_store

        state = _load_json_state(_TESTIMONIAL_STATE)
        now = datetime.now(timezone.utc)
        sender = get_whatsapp_sender()
        asked = 0
        for c in clients_store.list_clients(status="active"):
            cid = str(c.get("id") or "")
            phone = str(c.get("phone") or "").strip()
            if (
                not is_paid_client(c)
                or not is_activated(c)
                or not cid
                or not phone
                or state.get(cid)
            ):
                continue
            da = c.get("delivered_at")
            if da:
                try:
                    d = datetime.fromisoformat(str(da).replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    if (now - d).days < min_days:
                        continue
                except Exception:
                    pass
            biz = str(c.get("business_name") or "aapka business")
            msg = (
                f"Namaste! 🙏 {biz} ke saath aapka experience kaisa raha? Ek chhoti si line "
                "feedback dijiye — aur agar accha laga to hum aapki success doosron ko dikha sakein? "
                "(Aapki permission ke bina naam public nahi karenge.)"
            )
            try:
                r = await sender.send_text_message(phone, msg)
                if bool(r) and not (isinstance(r, dict) and r.get("error")):
                    state[cid] = now.isoformat(timespec="seconds")
                    asked += 1
            except Exception:
                pass
            if asked >= max(1, limit):
                break
        _save_json_state(_TESTIMONIAL_STATE, state)
        res["asked"] = asked
    except Exception as exc:
        logger.warning("run_testimonial_sweep err: %s", exc)
        res["error"] = str(exc)
    return res


__all__ = [
    "is_paid_client",
    "mini_site_url",
    "is_delivered",
    "is_activated",
    "try_mark_acknowledged",
    "build_delivery_message",
    "find_undelivered_paid_clients",
    "deliver_client_value",
    "run_delivery_sweep",
    "count_fresh_content",
    "build_weekly_digest_message",
    "run_weekly_digest_sweep",
    "record_site_view",
    "site_view_count",
    "build_monthly_receipt_message",
    "build_case_study",
    "run_monthly_receipt_sweep",
    "run_testimonial_sweep",
]
