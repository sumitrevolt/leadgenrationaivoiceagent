"""
Webhooks API
Secure webhook endpoints for Twilio, Exotel, Stripe, and Razorpay
"""
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from typing import Optional
from datetime import datetime
from decimal import Decimal
import hmac
import hashlib
import os
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.base import get_async_db
from app.models.payment import (
    Subscription, Payment, Invoice, 
    PaymentGateway, SubscriptionStatus, PaymentStatus, InvoiceStatus
)
from app.config import settings
from app.utils.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


async def verify_twilio_signature(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature")
) -> bool:
    """Verify Twilio webhook signature"""
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set - skipping signature verification (UNSAFE for production)")
        return True
    
    if not x_twilio_signature:
        raise HTTPException(status_code=401, detail="Missing Twilio signature")
    
    # Get full URL and form data for signature validation
    url = str(request.url)
    form_data = await request.form()
    
    # Build the data string for signature
    data_string = url
    for key in sorted(form_data.keys()):
        data_string += key + form_data[key]
    
    # Compute expected signature
    expected_signature = hmac.new(
        auth_token.encode('utf-8'),
        data_string.encode('utf-8'),
        hashlib.sha1
    ).digest()
    
    import base64
    expected_signature_b64 = base64.b64encode(expected_signature).decode('utf-8')
    
    if not hmac.compare_digest(expected_signature_b64, x_twilio_signature):
        logger.warning("Invalid Twilio signature received")
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")
    
    return True


async def verify_exotel_signature(
    request: Request,
    x_exotel_signature: Optional[str] = Header(None, alias="X-Exotel-Signature")
) -> bool:
    """Verify Exotel webhook signature"""
    api_key = os.environ.get("EXOTEL_API_KEY", "")
    api_secret = os.environ.get("EXOTEL_API_SECRET", "")
    
    if not api_key or not api_secret:
        logger.warning("EXOTEL credentials not set - skipping signature verification (UNSAFE for production)")
        return True
    
    if not x_exotel_signature:
        raise HTTPException(status_code=401, detail="Missing Exotel signature")
    
    # Implement Exotel-specific signature verification
    # https://exotel.com/docs/api/signature-verification
    body = await request.body()
    
    expected_signature = hmac.new(
        api_secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, x_exotel_signature):
        logger.warning("Invalid Exotel signature received")
        raise HTTPException(status_code=401, detail="Invalid Exotel signature")
    
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
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    call_status = form_data.get("CallStatus")
    
    # TODO: Route to appropriate handler based on webhook type
    
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


@router.post("/exotel/incoming")
async def exotel_webhook(request: Request):
    """
    Exotel incoming call webhook
    Verifies signature in production
    """
    await verify_exotel_signature(request)
    
    body = await request.json()
    logger.info(f"Exotel webhook received: {body}")
    
    # Process the webhook
    call_sid = body.get("CallSid")
    from_number = body.get("From")
    
    return {"status": "received", "call_sid": call_sid}


@router.post("/exotel/status")
async def exotel_status_webhook(request: Request):
    """
    Exotel call status callback
    """
    await verify_exotel_signature(request)
    
    body = await request.json()
    logger.info(f"Exotel status webhook: {body}")
    
    return {"status": "received"}


# =============================================================================
# STRIPE WEBHOOKS
# =============================================================================

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_async_db)
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
            payload,
            stripe_signature,
            settings.stripe_webhook_secret
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
        logger.error(f"Error processing Stripe webhook {event_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_stripe_checkout_completed(data: dict, db: AsyncSession):
    """Handle checkout.session.completed event"""
    client_id = data.get("metadata", {}).get("client_id")
    plan_id = data.get("metadata", {}).get("plan_id")
    billing_cycle = data.get("metadata", {}).get("billing_cycle", "monthly")
    
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
    customer_id = data.get("customer")
    
    # Find subscription
    if stripe_subscription_id:
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
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
        paid_at=datetime.utcnow()
    )
    db.add(invoice)
    
    await db.commit()
    logger.info(f"Invoice paid: {stripe_invoice_id}")


async def handle_stripe_invoice_failed(data: dict, db: AsyncSession):
    """Handle invoice.payment_failed event"""
    stripe_subscription_id = data.get("subscription")
    
    if stripe_subscription_id:
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            subscription.status = SubscriptionStatus.PAST_DUE
            await db.commit()
            logger.info(f"Subscription {subscription.id} marked as past_due")


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
        "unpaid": SubscriptionStatus.PAST_DUE
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
        trial_ends_at=datetime.fromtimestamp(data.get("trial_end")) if data.get("trial_end") else None,
        calls_limit=plan.calls_per_month if plan else 0,
        leads_limit=plan.leads_per_month if plan else 0
    )
    db.add(subscription)
    await db.commit()
    
    logger.info(f"Created subscription {subscription.id} from Stripe webhook")


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
        "unpaid": SubscriptionStatus.PAST_DUE
    }
    
    subscription.status = status_map.get(data.get("status"), subscription.status)
    subscription.current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0))
    subscription.current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0))
    
    if data.get("cancel_at_period_end"):
        subscription.cancelled_at = datetime.utcnow()
    
    await db.commit()
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


async def handle_stripe_payment_succeeded(data: dict, db: AsyncSession):
    """Handle payment_intent.succeeded event"""
    payment_intent_id = data.get("id")
    customer_id = data.get("customer")
    
    # Record payment
    payment = Payment(
        client_id=data.get("metadata", {}).get("client_id"),
        payment_gateway=PaymentGateway.STRIPE,
        gateway_payment_id=payment_intent_id,
        amount=Decimal(str(data.get("amount", 0))) / 100,
        currency=data.get("currency", "usd").upper(),
        status=PaymentStatus.COMPLETED,
        payment_method_type=data.get("payment_method_types", ["card"])[0] if data.get("payment_method_types") else "card",
        completed_at=datetime.utcnow(),
        gateway_response=data
    )
    db.add(payment)
    await db.commit()
    logger.info(f"Payment recorded: {payment_intent_id}")


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
        gateway_response=data
    )
    db.add(payment)
    await db.commit()
    logger.info(f"Payment failed: {payment_intent_id}")


# =============================================================================
# RAZORPAY WEBHOOKS
# =============================================================================

@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Razorpay webhook endpoint for payment events.
    Handles: payment.captured, subscription.activated, subscription.cancelled
    """
    if not settings.razorpay_webhook_secret:
        logger.warning("RAZORPAY_WEBHOOK_SECRET not set - skipping webhook processing")
        return {"status": "webhook_secret_not_configured"}
    
    if not x_razorpay_signature:
        raise HTTPException(status_code=401, detail="Missing Razorpay signature")
    
    payload = await request.body()
    
    # Verify signature
    expected_signature = hmac.new(
        settings.razorpay_webhook_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, x_razorpay_signature):
        logger.error("Invalid Razorpay webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        event_data = json.loads(payload.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    event_type = event_data.get("event")
    entity = event_data.get("payload", {})
    
    logger.info(f"Razorpay webhook received: {event_type}")
    
    try:
        if event_type == "payment.captured":
            await handle_razorpay_payment_captured(entity, db)
        
        elif event_type == "payment.failed":
            await handle_razorpay_payment_failed(entity, db)
        
        elif event_type == "subscription.activated":
            await handle_razorpay_subscription_activated(entity, db)
        
        elif event_type == "subscription.charged":
            await handle_razorpay_subscription_charged(entity, db)
        
        elif event_type == "subscription.cancelled":
            await handle_razorpay_subscription_cancelled(entity, db)
        
        elif event_type == "subscription.halted":
            await handle_razorpay_subscription_halted(entity, db)
        
        elif event_type == "order.paid":
            await handle_razorpay_order_paid(entity, db)
        
        else:
            logger.info(f"Unhandled Razorpay event type: {event_type}")
        
        return {"status": "success", "event_type": event_type}
        
    except Exception as e:
        logger.error(f"Error processing Razorpay webhook {event_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def handle_razorpay_payment_captured(entity: dict, db: AsyncSession):
    """Handle payment.captured event"""
    payment_data = entity.get("payment", {}).get("entity", {})
    payment_id = payment_data.get("id")
    order_id = payment_data.get("order_id")
    
    # Get client_id from notes
    notes = payment_data.get("notes", {})
    client_id = notes.get("client_id")
    
    # Check if payment already exists
    result = await db.execute(
        select(Payment).where(Payment.gateway_payment_id == payment_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.status = PaymentStatus.COMPLETED
        existing.completed_at = datetime.utcnow()
        await db.commit()
        return
    
    # Create payment record
    payment = Payment(
        client_id=client_id,
        payment_gateway=PaymentGateway.RAZORPAY,
        gateway_payment_id=payment_id,
        gateway_order_id=order_id,
        amount=Decimal(str(payment_data.get("amount", 0))) / 100,
        currency=payment_data.get("currency", "INR").upper(),
        status=PaymentStatus.COMPLETED,
        payment_method_type=payment_data.get("method"),
        completed_at=datetime.utcnow(),
        gateway_response=payment_data
    )
    
    # Add card/UPI details if available
    if payment_data.get("method") == "card":
        card = payment_data.get("card", {})
        payment.payment_method_last4 = card.get("last4")
        payment.payment_method_brand = card.get("network")
    elif payment_data.get("method") == "upi":
        payment.payment_method_type = "upi"
    
    db.add(payment)
    
    # Handle balance top-up
    if notes.get("type") == "balance_topup" and client_id:
        amount = Decimal(str(payment_data.get("amount", 0))) / 100
        result = await db.execute(
            select(Subscription).where(Subscription.client_id == client_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.balance = (subscription.balance or Decimal("0")) + amount
    
    await db.commit()
    logger.info(f"Razorpay payment captured: {payment_id}")


async def handle_razorpay_payment_failed(entity: dict, db: AsyncSession):
    """Handle payment.failed event"""
    payment_data = entity.get("payment", {}).get("entity", {})
    payment_id = payment_data.get("id")
    
    notes = payment_data.get("notes", {})
    client_id = notes.get("client_id")
    
    payment = Payment(
        client_id=client_id,
        payment_gateway=PaymentGateway.RAZORPAY,
        gateway_payment_id=payment_id,
        gateway_order_id=payment_data.get("order_id"),
        amount=Decimal(str(payment_data.get("amount", 0))) / 100,
        currency=payment_data.get("currency", "INR").upper(),
        status=PaymentStatus.FAILED,
        failure_code=payment_data.get("error_code"),
        failure_message=payment_data.get("error_description"),
        gateway_response=payment_data
    )
    db.add(payment)
    await db.commit()
    logger.info(f"Razorpay payment failed: {payment_id}")


async def handle_razorpay_subscription_activated(entity: dict, db: AsyncSession):
    """Handle subscription.activated event"""
    sub_data = entity.get("subscription", {}).get("entity", {})
    razorpay_sub_id = sub_data.get("id")
    
    notes = sub_data.get("notes", {})
    client_id = notes.get("client_id")
    plan_id = notes.get("plan_id", "starter")
    
    if not client_id:
        logger.warning(f"Subscription activated without client_id: {razorpay_sub_id}")
        return
    
    # Check if subscription exists
    result = await db.execute(
        select(Subscription).where(Subscription.razorpay_subscription_id == razorpay_sub_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.status = SubscriptionStatus.ACTIVE
        existing.current_period_start = datetime.fromtimestamp(sub_data.get("current_start", 0))
        existing.current_period_end = datetime.fromtimestamp(sub_data.get("current_end", 0))
        await db.commit()
        return
    
    # Create new subscription
    from app.billing.subscription import PRICING_PLANS
    plan = PRICING_PLANS.get(plan_id)
    
    subscription = Subscription(
        client_id=client_id,
        plan_id=plan_id,
        plan_name=plan.name if plan else plan_id,
        status=SubscriptionStatus.ACTIVE,
        payment_gateway=PaymentGateway.RAZORPAY,
        razorpay_subscription_id=razorpay_sub_id,
        razorpay_customer_id=sub_data.get("customer_id"),
        base_price=Decimal(str(plan.monthly_price)) if plan else Decimal("0"),
        currency="INR",
        started_at=datetime.utcnow(),
        current_period_start=datetime.fromtimestamp(sub_data.get("current_start", 0)) if sub_data.get("current_start") else None,
        current_period_end=datetime.fromtimestamp(sub_data.get("current_end", 0)) if sub_data.get("current_end") else None,
        calls_limit=plan.calls_per_month if plan else 0,
        leads_limit=plan.leads_per_month if plan else 0
    )
    db.add(subscription)
    await db.commit()
    
    logger.info(f"Created subscription {subscription.id} from Razorpay webhook")


async def handle_razorpay_subscription_charged(entity: dict, db: AsyncSession):
    """Handle subscription.charged event (recurring payment)"""
    sub_data = entity.get("subscription", {}).get("entity", {})
    razorpay_sub_id = sub_data.get("id")
    payment_data = entity.get("payment", {}).get("entity", {})
    
    result = await db.execute(
        select(Subscription).where(Subscription.razorpay_subscription_id == razorpay_sub_id)
    )
    subscription = result.scalar_one_or_none()
    
    if subscription:
        # Reset usage for new period
        subscription.calls_used = 0
        subscription.leads_generated = 0
        subscription.appointments_booked = 0
        subscription.current_period_start = datetime.fromtimestamp(sub_data.get("current_start", 0))
        subscription.current_period_end = datetime.fromtimestamp(sub_data.get("current_end", 0))
        
        # Record payment
        if payment_data.get("id"):
            payment = Payment(
                client_id=subscription.client_id,
                subscription_id=subscription.id,
                payment_gateway=PaymentGateway.RAZORPAY,
                gateway_payment_id=payment_data.get("id"),
                amount=Decimal(str(payment_data.get("amount", 0))) / 100,
                currency="INR",
                status=PaymentStatus.COMPLETED,
                completed_at=datetime.utcnow()
            )
            db.add(payment)
        
        await db.commit()
        logger.info(f"Subscription {subscription.id} charged")


async def handle_razorpay_subscription_cancelled(entity: dict, db: AsyncSession):
    """Handle subscription.cancelled event"""
    sub_data = entity.get("subscription", {}).get("entity", {})
    razorpay_sub_id = sub_data.get("id")
    
    result = await db.execute(
        select(Subscription).where(Subscription.razorpay_subscription_id == razorpay_sub_id)
    )
    subscription = result.scalar_one_or_none()
    
    if subscription:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        subscription.ended_at = datetime.fromtimestamp(sub_data.get("ended_at", 0)) if sub_data.get("ended_at") else datetime.utcnow()
        await db.commit()
        logger.info(f"Subscription {subscription.id} cancelled")


async def handle_razorpay_subscription_halted(entity: dict, db: AsyncSession):
    """Handle subscription.halted event (payment failed)"""
    sub_data = entity.get("subscription", {}).get("entity", {})
    razorpay_sub_id = sub_data.get("id")
    
    result = await db.execute(
        select(Subscription).where(Subscription.razorpay_subscription_id == razorpay_sub_id)
    )
    subscription = result.scalar_one_or_none()
    
    if subscription:
        subscription.status = SubscriptionStatus.PAST_DUE
        await db.commit()
        logger.info(f"Subscription {subscription.id} halted due to payment failure")


async def handle_razorpay_order_paid(entity: dict, db: AsyncSession):
    """Handle order.paid event (one-time payment)"""
    order_data = entity.get("order", {}).get("entity", {})
    payment_data = entity.get("payment", {}).get("entity", {})
    
    notes = order_data.get("notes", {})
    client_id = notes.get("client_id")
    
    if notes.get("type") == "balance_topup" and client_id:
        amount = Decimal(str(order_data.get("amount", 0))) / 100
        
        result = await db.execute(
            select(Subscription).where(Subscription.client_id == client_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            subscription.balance = (subscription.balance or Decimal("0")) + amount
            await db.commit()
            logger.info(f"Added {amount} INR to balance for client {client_id}")

