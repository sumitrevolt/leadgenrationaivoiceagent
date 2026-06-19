"""
Webhooks API
Secure webhook endpoints for Twilio + Stripe.
(Exotel + Razorpay removed 2026-06-18 — provider is Vobiz; payments via manual UPI.)
"""

import hashlib
import hmac
import json
import os
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.base import get_async_db
from app.models.payment import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentGateway,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)
from app.utils.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


def _provision_minutes(
    client_id: str | None,
    plan_id: str | None = None,
    period_end: datetime | None = None,
    subscription_id: str | None = None,
    reset: bool = True,
) -> None:
    """Best-effort: refresh a client's plan calling-minutes after a paid pay/renew.

    Sets the client's plan (so the PLAN_MINUTES cap is right) and drops a usage
    watermark (mid-period renewal zeroes metered usage). NEVER raises — a billing
    hiccup must not 500 a provider webhook (Stripe would just retry).
    """
    try:
        if not client_id:
            return
        from app.billing import usage as _usage

        if plan_id:
            _usage.activate_plan(
                client_id, plan_id, subscription_id=subscription_id, period_end=period_end
            )
        if reset:
            _usage.reset_usage_period(client_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"webhook usage provisioning skipped for {client_id}: {e}")


async def verify_twilio_signature(
    request: Request, x_twilio_signature: str | None = Header(None, alias="X-Twilio-Signature")
) -> bool:
    """Verify Twilio webhook signature"""
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")

    if not auth_token:
        if settings.is_production:
            logger.error(
                "TWILIO_AUTH_TOKEN not set in production — refusing unverified webhook"
            )
            raise HTTPException(status_code=503, detail="Webhook verification not configured")
        logger.warning("TWILIO_AUTH_TOKEN not set - skipping signature verification (dev only)")
        return True

    if not x_twilio_signature:
        raise HTTPException(status_code=401, detail="Missing Twilio signature")

    # Behind a reverse proxy (Caddy -> 127.0.0.1:8000) request.url carries the INTERNAL
    # scheme/host, but Twilio signed the PUBLIC url. Reconstruct from public_base_url,
    # else every genuine Twilio webhook would 401 (self-DoS).
    public_url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        public_url += "?" + request.url.query
    form_data = await request.form()
    params = {k: str(v) for k, v in form_data.items()}

    try:
        from twilio.request_validator import RequestValidator

        valid = RequestValidator(auth_token).validate(public_url, params, x_twilio_signature)
    except ImportError:
        # Fallback: Twilio's documented algorithm (URL + sorted concatenated params),
        # HMAC-SHA1 -> base64 — using the PUBLIC url (not request.url).
        import base64

        data_string = public_url
        for key in sorted(params.keys()):
            data_string += key + params[key]
        digest = hmac.new(
            auth_token.encode("utf-8"), data_string.encode("utf-8"), hashlib.sha1
        ).digest()
        valid = hmac.compare_digest(
            base64.b64encode(digest).decode("utf-8"), x_twilio_signature
        )

    if not valid:
        logger.warning("Invalid Twilio signature received")
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")

    return True


@router.post("/twilio/incoming")
async def twilio_webhook(request: Request):
    """
    Twilio incoming call/SMS webhook
    Verifies signature in production
    """
    # Verify signature
    await verify_twilio_signature(request)

    form_data = await request.form()
    logger.info(f"Twilio webhook received: {dict(form_data)}")

    # Process the webhook
    call_sid = form_data.get("CallSid")
    form_data.get("From")
    form_data.get("To")
    form_data.get("CallStatus")

    # NOTE: inbound Twilio voice is handled via the telephony stream / voicebot path
    # and the /twilio/voice/{call_id} + /twilio/status/{call_id} routes in
    # app/telephony/webhooks.py — NOT here. A prior inline call_manager call used wrong
    # signatures (queue_call/handle_call_completed) and TypeError'd on every request
    # (silently swallowed) while also constructing a heavy CallManager per request. Ack only.
    logger.info(
        f"Twilio incoming: sid={call_sid} status={form_data.get('CallStatus')} "
        f"from={form_data.get('From')}"
    )

    return {"status": "received", "call_sid": call_sid}


@router.post("/twilio/status")
async def twilio_status_webhook(request: Request):
    """
    Twilio call status callback
    """
    await verify_twilio_signature(request)

    form_data = await request.form()
    logger.info(f"Twilio status webhook: {dict(form_data)}")

    return {"status": "received"}


# NOTE: Exotel webhooks removed 2026-06-18 (provider is now Vobiz). The Vobiz
# answer/status callbacks live in app/telephony/webhooks.py (/vobiz/*).


# =============================================================================
# STRIPE WEBHOOKS
# =============================================================================


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Stripe webhook endpoint for payment events.
    Handles: checkout.session.completed, invoice.paid, customer.subscription.*
    """
    if not settings.stripe_webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not set - skipping webhook processing")
        return {"status": "webhook_secret_not_configured"}

    if not stripe_signature:
        raise HTTPException(status_code=401, detail="Missing Stripe signature")

    payload = await request.body()

    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key

        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid Stripe payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid Stripe signature: {e}")
        raise HTTPException(status_code=401, detail="Invalid signature")
    except ImportError:
        logger.error("stripe package not installed")
        raise HTTPException(status_code=500, detail="Stripe not configured")

    event_type = event.type
    event_data = event.data.object

    logger.info(f"Stripe webhook received: {event_type}")

    # Idempotency: Stripe delivers at-least-once and RETRIES the same event id.
    # Without this guard the balance_topup branch (handle_stripe_checkout_completed)
    # does `balance += amount` on every delivery → double-credit. Atomic claim;
    # fail-open (Redis down = process anyway); released below on processing failure.
    evt_id = getattr(event, "id", "") or ""
    idem_key = f"stripe:{evt_id}"
    try:
        from app.billing import idempotency as _idem

        if evt_id and await _idem.seen_before(idem_key):
            logger.info(f"Stripe event {evt_id} already processed — skipping (idempotent)")
            return {"status": "duplicate_skipped", "event_type": event_type}
    except Exception:
        pass

    try:
        if event_type == "checkout.session.completed":
            await handle_stripe_checkout_completed(event_data, db)

        elif event_type == "invoice.paid":
            await handle_stripe_invoice_paid(event_data, db)

        elif event_type == "invoice.payment_failed":
            await handle_stripe_invoice_failed(event_data, db)

        elif event_type == "customer.subscription.created":
            await handle_stripe_subscription_created(event_data, db)

        elif event_type == "customer.subscription.updated":
            await handle_stripe_subscription_updated(event_data, db)

        elif event_type == "customer.subscription.deleted":
            await handle_stripe_subscription_deleted(event_data, db)

        elif event_type == "payment_intent.succeeded":
            await handle_stripe_payment_succeeded(event_data, db)

        elif event_type == "payment_intent.payment_failed":
            await handle_stripe_payment_failed(event_data, db)

        else:
            logger.info(f"Unhandled Stripe event type: {event_type}")

        return {"status": "success", "event_type": event_type}

    except Exception as e:
        # Processing failed AFTER the idempotency claim — release it so Stripe's
        # retry reprocesses (never silently lose a payment event).
        try:
            from app.billing import idempotency as _idem

            await _idem.forget(idem_key)
        except Exception:
            pass
        logger.error(f"Error processing Stripe webhook {event_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_stripe_checkout_completed(data: dict, db: AsyncSession):
    """Handle checkout.session.completed event"""
    client_id = data.get("metadata", {}).get("client_id")
    data.get("metadata", {}).get("plan_id")
    data.get("metadata", {}).get("billing_cycle", "monthly")

    if not client_id:
        logger.warning("Checkout completed without client_id in metadata")
        return

    # Check if this is a subscription or one-time payment
    if data.get("subscription"):
        # Subscription will be created via subscription.created webhook
        logger.info(f"Checkout completed for subscription: {data.get('subscription')}")
    else:
        # One-time payment (e.g., balance top-up)
        if data.get("metadata", {}).get("type") == "balance_topup":
            amount = Decimal(data.get("metadata", {}).get("amount", "0"))

            # Update client balance
            result = await db.execute(
                select(Subscription).where(Subscription.client_id == client_id)
            )
            subscription = result.scalar_one_or_none()
            if subscription:
                subscription.balance = (subscription.balance or Decimal("0")) + amount
                await db.commit()
                logger.info(f"Added {amount} to balance for client {client_id}")


async def handle_stripe_invoice_paid(data: dict, db: AsyncSession):
    """Handle invoice.paid event"""
    stripe_invoice_id = data.get("id")
    stripe_subscription_id = data.get("subscription")
    data.get("customer")

    # Find subscription
    if stripe_subscription_id:
        result = await db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            # Reset usage for new period
            subscription.calls_used = 0
            subscription.leads_generated = 0
            subscription.appointments_booked = 0
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_period_start = datetime.fromtimestamp(data.get("period_start", 0))
            subscription.current_period_end = datetime.fromtimestamp(data.get("period_end", 0))

    # Create invoice record
    invoice = Invoice(
        client_id=subscription.client_id if subscription else None,
        subscription_id=subscription.id if subscription else None,
        invoice_number=data.get("number", f"INV-{stripe_invoice_id[:8]}"),
        stripe_invoice_id=stripe_invoice_id,
        status=InvoiceStatus.PAID,
        subtotal=Decimal(str(data.get("subtotal", 0))) / 100,
        tax_amount=Decimal(str(data.get("tax", 0) or 0)) / 100,
        total=Decimal(str(data.get("total", 0))) / 100,
        amount_paid=Decimal(str(data.get("amount_paid", 0))) / 100,
        amount_due=Decimal("0"),
        currency=data.get("currency", "usd").upper(),
        hosted_invoice_url=data.get("hosted_invoice_url"),
        pdf_url=data.get("invoice_pdf"),
        paid_at=datetime.utcnow(),
    )
    db.add(invoice)

    await db.commit()

    # After commit (write lock released) -> provision the renewed period's minutes.
    if subscription:
        _provision_minutes(
            subscription.client_id,
            subscription.plan_id,
            subscription.current_period_end,
            stripe_subscription_id,
        )
    logger.info(f"Invoice paid: {stripe_invoice_id}")
    if subscription and subscription.client_id:
        try:
            from app.platform import customer_webhooks

            customer_webhooks.fire_emit(
                str(subscription.client_id),
                "payment.received",
                {
                    "client_id": str(subscription.client_id),
                    "plan_id": subscription.plan_id,
                    "gateway": "stripe",
                    "invoice_id": stripe_invoice_id,
                    "amount_paid": float(data.get("amount_paid", 0) or 0) / 100,
                    "currency": (data.get("currency") or "usd").upper(),
                },
            )
        except Exception:
            pass


async def handle_stripe_invoice_failed(data: dict, db: AsyncSession):
    """Handle invoice.payment_failed event"""
    stripe_subscription_id = data.get("subscription")

    if stripe_subscription_id:
        result = await db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.status = SubscriptionStatus.PAST_DUE
            await db.commit()
            logger.info(f"Subscription {subscription.id} marked as past_due")
            # Dunning hook (best-effort, kabhi raise nahi) — recovery sequence open karo.
            try:
                from app.billing import dunning

                await dunning.on_payment_failed(
                    str(subscription.client_id),
                    gateway="stripe",
                    reason="invoice.payment_failed",
                    subscription_id=str(subscription.id),
                )
            except Exception as e:
                logger.debug(f"[webhooks] dunning hook skip: {e}")


async def handle_stripe_subscription_created(data: dict, db: AsyncSession):
    """Handle customer.subscription.created event"""
    stripe_subscription_id = data.get("id")
    customer_id = data.get("customer")

    # Get metadata
    metadata = data.get("metadata", {})
    client_id = metadata.get("client_id")
    plan_id = metadata.get("plan_id", "starter")

    if not client_id:
        logger.warning(f"Subscription created without client_id: {stripe_subscription_id}")
        return

    # Determine status
    status_map = {
        "trialing": SubscriptionStatus.TRIAL,
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELLED,
        "unpaid": SubscriptionStatus.PAST_DUE,
        "paused": SubscriptionStatus.PAUSED,
    }
    status = status_map.get(data.get("status"), SubscriptionStatus.ACTIVE)

    # Check if subscription already exists
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.status = status
        await db.commit()
        return

    # Create new subscription
    from app.billing.subscription import PRICING_PLANS

    plan = PRICING_PLANS.get(plan_id)

    subscription = Subscription(
        client_id=client_id,
        plan_id=plan_id,
        plan_name=plan.name if plan else plan_id,
        status=status,
        payment_gateway=PaymentGateway.STRIPE,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=customer_id,
        base_price=Decimal(str(plan.monthly_price)) if plan else Decimal("0"),
        currency="USD",
        started_at=datetime.utcnow(),
        current_period_start=datetime.fromtimestamp(data.get("current_period_start", 0)),
        current_period_end=datetime.fromtimestamp(data.get("current_period_end", 0)),
        trial_ends_at=(
            datetime.fromtimestamp(data.get("trial_end")) if data.get("trial_end") else None
        ),
        calls_limit=plan.calls_per_month if plan else 0,
        leads_limit=plan.leads_per_month if plan else 0,
    )
    db.add(subscription)
    await db.commit()

    # New paid subscription -> provision the plan's calling minutes.
    _provision_minutes(client_id, plan_id, subscription.current_period_end, stripe_subscription_id)

    logger.info(f"Created subscription {subscription.id} from Stripe webhook")
    try:
        from app.platform import customer_webhooks

        customer_webhooks.fire_emit(
            str(client_id),
            "subscription.activated",
            {
                "client_id": str(client_id),
                "plan_id": plan_id,
                "gateway": "stripe",
                "stripe_subscription_id": stripe_subscription_id,
            },
        )
    except Exception:
        pass


async def handle_stripe_subscription_updated(data: dict, db: AsyncSession):
    """Handle customer.subscription.updated event"""
    stripe_subscription_id = data.get("id")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return

    status_map = {
        "trialing": SubscriptionStatus.TRIAL,
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELLED,
        "unpaid": SubscriptionStatus.PAST_DUE,
        "paused": SubscriptionStatus.PAUSED,
    }

    subscription.status = status_map.get(data.get("status"), subscription.status)
    subscription.current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0))
    subscription.current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0))

    if data.get("cancel_at_period_end"):
        subscription.cancelled_at = datetime.utcnow()

    await db.commit()

    # Renewal/reactivation -> refresh plan minutes; pause/cancel leaves usage as-is.
    if subscription.status == SubscriptionStatus.ACTIVE:
        _provision_minutes(
            subscription.client_id,
            subscription.plan_id,
            subscription.current_period_end,
            stripe_subscription_id,
        )

    logger.info(f"Updated subscription {subscription.id}")


async def handle_stripe_subscription_deleted(data: dict, db: AsyncSession):
    """Handle customer.subscription.deleted event"""
    stripe_subscription_id = data.get("id")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.ended_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Subscription {subscription.id} cancelled")
        try:
            from app.platform import customer_webhooks

            customer_webhooks.fire_emit(
                str(subscription.client_id),
                "subscription.cancelled",
                {
                    "client_id": str(subscription.client_id),
                    "plan_id": subscription.plan_id,
                    "gateway": "stripe",
                    "stripe_subscription_id": stripe_subscription_id,
                },
            )
        except Exception:
            pass


async def handle_stripe_payment_succeeded(data: dict, db: AsyncSession):
    """Handle payment_intent.succeeded event"""
    payment_intent_id = data.get("id")
    data.get("customer")

    # Record payment
    payment = Payment(
        client_id=data.get("metadata", {}).get("client_id"),
        payment_gateway=PaymentGateway.STRIPE,
        gateway_payment_id=payment_intent_id,
        amount=Decimal(str(data.get("amount", 0))) / 100,
        currency=data.get("currency", "usd").upper(),
        status=PaymentStatus.COMPLETED,
        payment_method_type=(
            data.get("payment_method_types", ["card"])[0]
            if data.get("payment_method_types")
            else "card"
        ),
        completed_at=datetime.utcnow(),
        gateway_response=data,
    )
    db.add(payment)
    await db.commit()
    logger.info(f"Payment recorded: {payment_intent_id}")
    cid = data.get("metadata", {}).get("client_id")
    if cid:
        try:
            from app.platform import customer_webhooks

            customer_webhooks.fire_emit(
                str(cid),
                "payment.received",
                {
                    "client_id": str(cid),
                    "gateway": "stripe",
                    "payment_intent_id": payment_intent_id,
                    "amount": float(Decimal(str(data.get("amount", 0))) / 100),
                    "currency": (data.get("currency") or "usd").upper(),
                },
            )
        except Exception:
            pass


async def handle_stripe_payment_failed(data: dict, db: AsyncSession):
    """Handle payment_intent.payment_failed event"""
    payment_intent_id = data.get("id")

    payment = Payment(
        client_id=data.get("metadata", {}).get("client_id"),
        payment_gateway=PaymentGateway.STRIPE,
        gateway_payment_id=payment_intent_id,
        amount=Decimal(str(data.get("amount", 0))) / 100,
        currency=data.get("currency", "usd").upper(),
        status=PaymentStatus.FAILED,
        failure_code=data.get("last_payment_error", {}).get("code"),
        failure_message=data.get("last_payment_error", {}).get("message"),
        gateway_response=data,
    )
    db.add(payment)
    await db.commit()
    logger.info(f"Payment failed: {payment_intent_id}")
    # Dunning hook (best-effort)
    try:
        cid = data.get("metadata", {}).get("client_id")
        if cid:
            from app.billing import dunning

            await dunning.on_payment_failed(
                str(cid),
                amount=float(Decimal(str(data.get("amount", 0))) / 100),
                gateway="stripe",
                reason=str(data.get("last_payment_error", {}).get("code") or "payment_failed"),
            )
    except Exception as e:
        logger.debug(f"[webhooks] dunning hook skip: {e}")


# =============================================================================
# RAZORPAY WEBHOOKS — removed 2026-06-18 (no online gateway; manual UPI only).
# The /razorpay route + all handle_razorpay_* handlers were deleted. The unified
# /billing/webhook now rejects X-Razorpay-Signature with 400.
# =============================================================================


# =============================================================================
# WHATSAPP CLOUD API WEBHOOK (Meta) — inbound replies -> reply_agent drafts
# =============================================================================
def _wa_verify_token() -> str:
    """Meta webhook GET-handshake token (settings -> env fallback)."""
    tok = ""
    try:
        tok = (settings.whatsapp_verify_token or "").strip()
    except Exception:
        tok = ""
    return tok or os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()


@router.get("/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """Meta webhook verification handshake (echo hub.challenge if verify token matches).

    PUBLIC — Meta GETs this with hub.mode=subscribe&hub.verify_token=..&hub.challenge=..
    """
    from fastapi.responses import PlainTextResponse

    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    expected = _wa_verify_token()
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    return PlainTextResponse("verification_failed", status_code=403)


@router.post("/whatsapp")
async def whatsapp_webhook_inbound(request: Request):
    """Inbound WhatsApp messages from the official Meta Cloud API.

    - App-Secret signature verified (X-Hub-Signature-256); unconfigured -> allowed (warn).
    - Each inbound TEXT -> ``reply_agent.whatsapp_reply()`` => intent classify + Hinglish
      draft saved to ``data/reply_drafts.jsonl`` (1-click human send).
    - 'STOP' / 'UNSUBSCRIBE' / 'band karo' -> opt-out (suppress), no draft.
    - 'failed' delivery status -> recipient auto-suppressed (bounce protection).
    Always returns 200 JSON (Meta retries on non-2xx). NEVER raises.
    """
    raw = b""
    try:
        raw = await request.body()
    except Exception:
        pass

    try:
        from app.integrations.whatsapp import verify_meta_signature

        sig = request.headers.get("X-Hub-Signature-256") or request.headers.get(
            "x-hub-signature-256"
        )
        verified = verify_meta_signature(raw, sig)
    except Exception as _ve:
        logger.error(f"whatsapp webhook: signature verification error: {_ve}")
        verified = False
    if not verified:
        logger.warning("whatsapp webhook: bad/unverified signature, ignoring payload")
        return {"ok": False, "reason": "bad_signature"}

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    res = {"ok": True, "messages": 0, "drafted": 0, "suppressed": 0, "statuses": 0}
    _opt_out = ("stop", "unsubscribe", "stop promotions", "band karo", "band kardo")
    try:
        from app.platform import reply_agent

        try:
            from app.marketing import wa_campaign_runner as _runner
        except Exception:
            _runner = None

        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = (change or {}).get("value", {}) or {}
                for msg in value.get("messages", []) or []:
                    res["messages"] += 1
                    frm = str(msg.get("from", "")).strip()
                    text = ""
                    if msg.get("type") == "text":
                        text = str((msg.get("text") or {}).get("body", "")).strip()
                    if text.lower() in _opt_out:
                        if _runner is not None:
                            try:
                                _runner.suppress(frm, reason="opt_out_inbound")
                            except Exception:
                                pass
                        # TCCCPR: revocation sab commercial comms pe — voice ledger bhi.
                        try:
                            from app.telephony.consent_ledger import record_opt_out

                            record_opt_out(frm, reason="wa_stop", channel="whatsapp")
                        except Exception:
                            pass
                        res["suppressed"] += 1
                        continue
                    # WhatsApp Flow response (nfm_reply type) -> lead capture
                    if msg.get("type") == "interactive":
                        interactive = msg.get("interactive") or {}
                        if interactive.get("type") == "nfm_reply":
                            try:
                                from app.marketing.whatsapp_flows import handle_flow_response
                                import json as _json
                                nfm = interactive.get("nfm_reply") or {}
                                resp_json = nfm.get("response_json") or "{}"
                                flow_data = _json.loads(resp_json) if isinstance(resp_json, str) else resp_json
                                await handle_flow_response(flow_data, from_number=frm)
                            except Exception as e:
                                logger.info("wa flow response err: %s", e)

                    if text:
                        try:
                            rec = await reply_agent.whatsapp_reply(frm, text, msg.get("id", ""))
                            if rec:
                                res["drafted"] += 1
                        except Exception as e:
                            logger.info("whatsapp reply_agent err: %s", e)
                for st in value.get("statuses", []) or []:
                    res["statuses"] += 1
                    if st.get("status") == "failed" and _runner is not None:
                        recipient = str(st.get("recipient_id", "")).strip()
                        errs = st.get("errors") or []
                        reason = (
                            errs[0].get("title") if errs else "delivery_failed"
                        ) or "delivery_failed"
                        try:
                            _runner.record_failure(recipient, str(reason))
                        except Exception:
                            pass
    except Exception as e:
        logger.info("whatsapp webhook parse err: %s", e)
    return res
