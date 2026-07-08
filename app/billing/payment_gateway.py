"""
Payment Gateway Service
Stripe gateway only. (Razorpay removed 2026-06-18 — India payments via manual UPI.)
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.config import settings
from app.models.payment import PaymentGateway
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _record_stripe_failure(note: str = "") -> None:
    """Best-effort Integration Health signal. Never raise on billing paths."""
    try:
        from app.platform import integration_health

        integration_health.record_failure("stripe", note)
    except Exception:
        pass


def _record_stripe_success() -> None:
    """Best-effort Integration Health signal. Never raise on billing paths."""
    try:
        from app.platform import integration_health

        integration_health.record_success("stripe")
    except Exception:
        pass


class PaymentGatewayBase(ABC):
    """Abstract base class for payment gateways"""

    @abstractmethod
    async def create_customer(
        self,
        email: str,
        name: str,
        phone: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a customer in the payment gateway"""
        pass

    @abstractmethod
    async def create_checkout_session(
        self,
        customer_id: str,
        plan_id: str,
        amount: Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a checkout session for one-time or subscription payment"""
        pass

    @abstractmethod
    async def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        payment_method_id: str | None = None,
        trial_days: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a subscription"""
        pass

    @abstractmethod
    async def cancel_subscription(
        self, subscription_id: str, cancel_at_period_end: bool = True
    ) -> dict[str, Any]:
        """Cancel a subscription"""
        pass

    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Get subscription details"""
        pass

    @abstractmethod
    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str | None = None,
        payment_method_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a payment intent for one-time payment"""
        pass

    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Verify webhook signature and return parsed event"""
        pass

    @abstractmethod
    async def get_invoices(self, customer_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get customer invoices"""
        pass

    @abstractmethod
    async def refund_payment(
        self, payment_id: str, amount: Decimal | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        """Refund a payment (full or partial)"""
        pass


class StripeGateway(PaymentGatewayBase):
    """Stripe payment gateway implementation"""

    def __init__(self):
        self.gateway_type = PaymentGateway.STRIPE
        self._client = None

    @property
    def client(self):
        """Lazy load Stripe client"""
        if self._client is None:
            try:
                import stripe

                stripe.api_key = settings.stripe_secret_key
                self._client = stripe
                logger.info("? Stripe client initialized")
            except ImportError:
                logger.error("stripe package not installed")
                _record_stripe_failure("package_not_installed")
                raise ImportError("stripe package required: pip install stripe")
        return self._client

    async def create_customer(
        self,
        email: str,
        name: str,
        phone: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe customer"""
        try:
            customer = self.client.Customer.create(
                email=email, name=name, phone=phone, metadata=metadata or {}
            )
            logger.info(f"Created Stripe customer: {customer.id}")
            _record_stripe_success()
            return {
                "customer_id": customer.id,
                "email": customer.email,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            _record_stripe_failure("create_customer")
            raise

    async def create_checkout_session(
        self,
        customer_id: str,
        plan_id: str,
        amount: Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe Checkout Session"""
        try:
            # Convert amount to cents/paisa
            amount_minor = int(round(amount * 100))

            is_subscription = "subscription" in (metadata or {}).get("type", "")
            price_data: dict[str, Any] = {
                "currency": currency.lower(),
                "product_data": {"name": f"Plan: {plan_id}"},
                "unit_amount": amount_minor,
            }
            if is_subscription:
                # Stripe rejects a subscription-mode Checkout Session unless the line
                # item carries a recurring interval (BILL-001 council fix 2026-06-26).
                price_data["recurring"] = {"interval": "month"}

            session = self.client.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{"price_data": price_data, "quantity": 1}],
                mode="subscription" if is_subscription else "payment",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {},
            )

            logger.info(f"Created Stripe checkout session: {session.id}")
            _record_stripe_success()
            return {
                "session_id": session.id,
                "checkout_url": session.url,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe checkout session: {e}")
            _record_stripe_failure("create_checkout_session")
            raise

    async def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        payment_method_id: str | None = None,
        trial_days: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe subscription"""
        try:
            params = {
                "customer": customer_id,
                "items": [{"price": plan_id}],
                "metadata": metadata or {},
            }

            if trial_days > 0:
                params["trial_period_days"] = trial_days

            if payment_method_id:
                params["default_payment_method"] = payment_method_id

            subscription = self.client.Subscription.create(**params)

            logger.info(f"Created Stripe subscription: {subscription.id}")
            _record_stripe_success()
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "trial_end": (
                    datetime.fromtimestamp(subscription.trial_end)
                    if subscription.trial_end
                    else None
                ),
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe subscription: {e}")
            _record_stripe_failure("create_subscription")
            raise

    async def cancel_subscription(
        self, subscription_id: str, cancel_at_period_end: bool = True
    ) -> dict[str, Any]:
        """Cancel a Stripe subscription"""
        try:
            if cancel_at_period_end:
                subscription = self.client.Subscription.modify(
                    subscription_id, cancel_at_period_end=True
                )
            else:
                subscription = self.client.Subscription.delete(subscription_id)

            logger.info(f"Cancelled Stripe subscription: {subscription_id}")
            _record_stripe_success()
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "canceled_at": (
                    datetime.fromtimestamp(subscription.canceled_at)
                    if subscription.canceled_at
                    else None
                ),
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to cancel Stripe subscription: {e}")
            _record_stripe_failure("cancel_subscription")
            raise

    async def pause_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Pause a Stripe subscription (pause_collection -> behavior 'void')."""
        try:
            subscription = self.client.Subscription.modify(
                subscription_id, pause_collection={"behavior": "void"}
            )
            logger.info(f"Paused Stripe subscription: {subscription_id}")
            _record_stripe_success()
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "paused": bool(getattr(subscription, "pause_collection", None)),
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to pause Stripe subscription: {e}")
            _record_stripe_failure("pause_subscription")
            raise

    async def resume_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Resume a paused Stripe subscription (clear pause_collection)."""
        try:
            subscription = self.client.Subscription.modify(subscription_id, pause_collection="")
            logger.info(f"Resumed Stripe subscription: {subscription_id}")
            _record_stripe_success()
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "paused": bool(getattr(subscription, "pause_collection", None)),
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to resume Stripe subscription: {e}")
            _record_stripe_failure("resume_subscription")
            raise

    async def create_billing_portal_session(
        self, customer_id: str, return_url: str
    ) -> dict[str, Any]:
        """Create a Stripe Billing Portal session (hosted card / invoice management)."""
        try:
            session = self.client.billing_portal.Session.create(
                customer=customer_id, return_url=return_url
            )
            logger.info(f"Created Stripe billing portal session for {customer_id}")
            _record_stripe_success()
            return {
                "portal_url": session.url,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe billing portal session: {e}")
            _record_stripe_failure("create_billing_portal_session")
            raise

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Get Stripe subscription details"""
        try:
            subscription = self.client.Subscription.retrieve(subscription_id)
            _record_stripe_success()
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to get Stripe subscription: {e}")
            _record_stripe_failure("get_subscription")
            raise

    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str | None = None,
        payment_method_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a Stripe PaymentIntent"""
        try:
            amount_minor = int(round(amount * 100))

            params = {
                "amount": amount_minor,
                "currency": currency.lower(),
                "metadata": metadata or {},
            }

            if customer_id:
                params["customer"] = customer_id
            if payment_method_id:
                params["payment_method"] = payment_method_id
                params["confirm"] = True

            intent = self.client.PaymentIntent.create(**params)

            logger.info(f"Created Stripe PaymentIntent: {intent.id}")
            _record_stripe_success()
            return {
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "status": intent.status,
                "amount": float(amount),
                "currency": currency,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe PaymentIntent: {e}")
            _record_stripe_failure("create_payment_intent")
            raise

    async def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        """Verify Stripe webhook signature"""
        try:
            event = self.client.Webhook.construct_event(
                payload, signature, settings.stripe_webhook_secret
            )

            logger.info(f"Verified Stripe webhook: {event.type}")
            _record_stripe_success()
            return {
                "event_id": event.id,
                "event_type": event.type,
                "data": event.data.object,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to verify Stripe webhook: {e}")
            raise

    async def get_invoices(self, customer_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get Stripe invoices for a customer"""
        try:
            invoices = self.client.Invoice.list(customer=customer_id, limit=limit)
            _record_stripe_success()

            return [
                {
                    "invoice_id": inv.id,
                    "number": inv.number,
                    "status": inv.status,
                    "amount_due": inv.amount_due / 100,
                    "amount_paid": inv.amount_paid / 100,
                    "currency": inv.currency.upper(),
                    "hosted_invoice_url": inv.hosted_invoice_url,
                    "invoice_pdf": inv.invoice_pdf,
                    "created": datetime.fromtimestamp(inv.created),
                    "gateway": self.gateway_type.value,
                }
                for inv in invoices.data
            ]
        except Exception as e:
            logger.error(f"Failed to get Stripe invoices: {e}")
            _record_stripe_failure("get_invoices")
            raise

    async def refund_payment(
        self, payment_id: str, amount: Decimal | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        """Refund a Stripe payment"""
        try:
            params = {"payment_intent": payment_id}

            if amount:
                params["amount"] = int(round(amount * 100))
            if reason:
                params["reason"] = reason

            refund = self.client.Refund.create(**params)

            logger.info(f"Created Stripe refund: {refund.id}")
            _record_stripe_success()
            return {
                "refund_id": refund.id,
                "status": refund.status,
                "amount": refund.amount / 100,
                "gateway": self.gateway_type.value,
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe refund: {e}")
            _record_stripe_failure("refund_payment")
            raise


# RazorpayGateway removed 2026-06-18 — no online India gateway; payments via
# manual UPI. The factory below routes everything to Stripe.


class PaymentGatewayFactory:
    """
    Payment gateway factory.

    Razorpay removed 2026-06-18 — there is no online India gateway anymore
    (payments via manual UPI). Stripe is the only online gateway, so every
    selection routes to Stripe regardless of currency/country.
    """

    _stripe: StripeGateway | None = None

    @classmethod
    def get_gateway(
        cls,
        gateway: PaymentGateway | None = None,
        currency: str | None = None,
        country_code: str | None = None,
    ) -> PaymentGatewayBase:
        """Get the payment gateway. Always Stripe (Razorpay removed)."""
        return cls._get_stripe()

    @classmethod
    def _get_stripe(cls) -> StripeGateway:
        """Get or create Stripe gateway instance"""
        if cls._stripe is None:
            cls._stripe = StripeGateway()
        return cls._stripe

    @classmethod
    def get_gateway_for_client(
        cls, phone_number: str | None = None, country_code: str | None = None
    ) -> PaymentGatewayBase:
        """Get the payment gateway for a client. Always Stripe (Razorpay removed)."""
        return cls._get_stripe()


# Convenience functions
def get_stripe_gateway() -> StripeGateway:
    """Get Stripe gateway instance"""
    return PaymentGatewayFactory._get_stripe()


def get_payment_gateway(
    currency: str | None = None, country_code: str | None = None
) -> PaymentGatewayBase:
    """Get the payment gateway (always Stripe — Razorpay removed)."""
    return PaymentGatewayFactory.get_gateway(currency=currency, country_code=country_code)
