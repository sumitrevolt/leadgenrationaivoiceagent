"""
Payment Gateway Service
Unified interface for Stripe (International) and Razorpay (India)
"""
import hmac
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime
import uuid

from app.config import settings
from app.utils.logger import setup_logger
from app.models.payment import PaymentGateway, SubscriptionStatus, PaymentStatus

logger = setup_logger(__name__)


class PaymentGatewayBase(ABC):
    """Abstract base class for payment gateways"""
    
    @abstractmethod
    async def create_customer(
        self,
        email: str,
        name: str,
        phone: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a checkout session for one-time or subscription payment"""
        pass
    
    @abstractmethod
    async def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        payment_method_id: Optional[str] = None,
        trial_days: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a subscription"""
        pass
    
    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True
    ) -> Dict[str, Any]:
        """Cancel a subscription"""
        pass
    
    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details"""
        pass
    
    @abstractmethod
    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        customer_id: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a payment intent for one-time payment"""
        pass
    
    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """Verify webhook signature and return parsed event"""
        pass
    
    @abstractmethod
    async def get_invoices(
        self,
        customer_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get customer invoices"""
        pass
    
    @abstractmethod
    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
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
                raise ImportError("stripe package required: pip install stripe")
        return self._client
    
    async def create_customer(
        self,
        email: str,
        name: str,
        phone: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Stripe customer"""
        try:
            customer = self.client.Customer.create(
                email=email,
                name=name,
                phone=phone,
                metadata=metadata or {}
            )
            logger.info(f"Created Stripe customer: {customer.id}")
            return {
                "customer_id": customer.id,
                "email": customer.email,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise
    
    async def create_checkout_session(
        self,
        customer_id: str,
        plan_id: str,
        amount: Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout Session"""
        try:
            # Convert amount to cents/paisa
            amount_minor = int(amount * 100)
            
            session = self.client.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": f"Plan: {plan_id}",
                        },
                        "unit_amount": amount_minor,
                    },
                    "quantity": 1,
                }],
                mode="subscription" if "subscription" in (metadata or {}).get("type", "") else "payment",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {}
            )
            
            logger.info(f"Created Stripe checkout session: {session.id}")
            return {
                "session_id": session.id,
                "checkout_url": session.url,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe checkout session: {e}")
            raise
    
    async def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        payment_method_id: Optional[str] = None,
        trial_days: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "trial_end": datetime.fromtimestamp(subscription.trial_end) if subscription.trial_end else None,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe subscription: {e}")
            raise
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True
    ) -> Dict[str, Any]:
        """Cancel a Stripe subscription"""
        try:
            if cancel_at_period_end:
                subscription = self.client.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True
                )
            else:
                subscription = self.client.Subscription.delete(subscription_id)
            
            logger.info(f"Cancelled Stripe subscription: {subscription_id}")
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "canceled_at": datetime.fromtimestamp(subscription.canceled_at) if subscription.canceled_at else None,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to cancel Stripe subscription: {e}")
            raise
    
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get Stripe subscription details"""
        try:
            subscription = self.client.Subscription.retrieve(subscription_id)
            return {
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
                "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to get Stripe subscription: {e}")
            raise
    
    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        customer_id: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Stripe PaymentIntent"""
        try:
            amount_minor = int(amount * 100)
            
            params = {
                "amount": amount_minor,
                "currency": currency.lower(),
                "metadata": metadata or {}
            }
            
            if customer_id:
                params["customer"] = customer_id
            if payment_method_id:
                params["payment_method"] = payment_method_id
                params["confirm"] = True
            
            intent = self.client.PaymentIntent.create(**params)
            
            logger.info(f"Created Stripe PaymentIntent: {intent.id}")
            return {
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "status": intent.status,
                "amount": float(amount),
                "currency": currency,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe PaymentIntent: {e}")
            raise
    
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """Verify Stripe webhook signature"""
        try:
            event = self.client.Webhook.construct_event(
                payload,
                signature,
                settings.stripe_webhook_secret
            )
            
            logger.info(f"Verified Stripe webhook: {event.type}")
            return {
                "event_id": event.id,
                "event_type": event.type,
                "data": event.data.object,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to verify Stripe webhook: {e}")
            raise
    
    async def get_invoices(
        self,
        customer_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get Stripe invoices for a customer"""
        try:
            invoices = self.client.Invoice.list(
                customer=customer_id,
                limit=limit
            )
            
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
                    "gateway": self.gateway_type.value
                }
                for inv in invoices.data
            ]
        except Exception as e:
            logger.error(f"Failed to get Stripe invoices: {e}")
            raise
    
    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Refund a Stripe payment"""
        try:
            params = {"payment_intent": payment_id}
            
            if amount:
                params["amount"] = int(amount * 100)
            if reason:
                params["reason"] = reason
            
            refund = self.client.Refund.create(**params)
            
            logger.info(f"Created Stripe refund: {refund.id}")
            return {
                "refund_id": refund.id,
                "status": refund.status,
                "amount": refund.amount / 100,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Stripe refund: {e}")
            raise


class RazorpayGateway(PaymentGatewayBase):
    """Razorpay payment gateway implementation (India)"""
    
    def __init__(self):
        self.gateway_type = PaymentGateway.RAZORPAY
        self._client = None
    
    @property
    def client(self):
        """Lazy load Razorpay client"""
        if self._client is None:
            try:
                import razorpay
                self._client = razorpay.Client(
                    auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
                )
                logger.info("? Razorpay client initialized")
            except ImportError:
                logger.error("razorpay package not installed")
                raise ImportError("razorpay package required: pip install razorpay")
        return self._client
    
    async def create_customer(
        self,
        email: str,
        name: str,
        phone: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Razorpay customer"""
        try:
            customer = self.client.customer.create({
                "name": name,
                "email": email,
                "contact": phone,
                "notes": metadata or {}
            })
            logger.info(f"Created Razorpay customer: {customer['id']}")
            return {
                "customer_id": customer["id"],
                "email": customer["email"],
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Razorpay customer: {e}")
            raise
    
    async def create_checkout_session(
        self,
        customer_id: str,
        plan_id: str,
        amount: Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Razorpay order (equivalent to checkout session)"""
        try:
            # Razorpay uses paisa (100 paisa = 1 INR)
            amount_minor = int(amount * 100)
            
            order = self.client.order.create({
                "amount": amount_minor,
                "currency": currency.upper(),
                "receipt": f"order_{uuid.uuid4().hex[:8]}",
                "notes": {
                    **(metadata or {}),
                    "plan_id": plan_id,
                    "success_url": success_url,
                    "cancel_url": cancel_url
                }
            })
            
            logger.info(f"Created Razorpay order: {order['id']}")
            return {
                "order_id": order["id"],
                "amount": float(amount),
                "currency": currency,
                "key_id": settings.razorpay_key_id,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Razorpay order: {e}")
            raise
    
    async def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        payment_method_id: Optional[str] = None,
        trial_days: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Razorpay subscription"""
        try:
            params = {
                "plan_id": plan_id,
                "customer_id": customer_id,
                "total_count": 12,  # Maximum billing cycles
                "notes": metadata or {}
            }
            
            if trial_days > 0:
                params["start_at"] = int((datetime.now().timestamp()) + (trial_days * 86400))
            
            subscription = self.client.subscription.create(params)
            
            logger.info(f"Created Razorpay subscription: {subscription['id']}")
            return {
                "subscription_id": subscription["id"],
                "status": subscription["status"],
                "current_start": datetime.fromtimestamp(subscription.get("current_start", 0)) if subscription.get("current_start") else None,
                "current_end": datetime.fromtimestamp(subscription.get("current_end", 0)) if subscription.get("current_end") else None,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Razorpay subscription: {e}")
            raise
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True
    ) -> Dict[str, Any]:
        """Cancel a Razorpay subscription"""
        try:
            subscription = self.client.subscription.cancel(
                subscription_id,
                {"cancel_at_cycle_end": 1 if cancel_at_period_end else 0}
            )
            
            logger.info(f"Cancelled Razorpay subscription: {subscription_id}")
            return {
                "subscription_id": subscription["id"],
                "status": subscription["status"],
                "ended_at": datetime.fromtimestamp(subscription.get("ended_at", 0)) if subscription.get("ended_at") else None,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to cancel Razorpay subscription: {e}")
            raise
    
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get Razorpay subscription details"""
        try:
            subscription = self.client.subscription.fetch(subscription_id)
            return {
                "subscription_id": subscription["id"],
                "status": subscription["status"],
                "plan_id": subscription.get("plan_id"),
                "current_start": datetime.fromtimestamp(subscription.get("current_start", 0)) if subscription.get("current_start") else None,
                "current_end": datetime.fromtimestamp(subscription.get("current_end", 0)) if subscription.get("current_end") else None,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to get Razorpay subscription: {e}")
            raise
    
    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        customer_id: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a Razorpay order (equivalent to payment intent)"""
        try:
            amount_minor = int(amount * 100)
            
            order = self.client.order.create({
                "amount": amount_minor,
                "currency": currency.upper(),
                "receipt": f"payment_{uuid.uuid4().hex[:8]}",
                "notes": metadata or {}
            })
            
            logger.info(f"Created Razorpay order: {order['id']}")
            return {
                "order_id": order["id"],
                "amount": float(amount),
                "currency": currency,
                "key_id": settings.razorpay_key_id,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Razorpay order: {e}")
            raise
    
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """Verify Razorpay webhook signature"""
        try:
            # Razorpay uses HMAC SHA256
            expected_signature = hmac.new(
                settings.razorpay_webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_signature, signature):
                raise ValueError("Invalid webhook signature")
            
            import json
            event_data = json.loads(payload.decode('utf-8'))
            
            logger.info(f"Verified Razorpay webhook: {event_data.get('event')}")
            return {
                "event_type": event_data.get("event"),
                "data": event_data.get("payload", {}).get("payment", {}).get("entity", {}),
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to verify Razorpay webhook: {e}")
            raise
    
    async def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str
    ) -> bool:
        """Verify Razorpay payment signature (for frontend callback)"""
        try:
            params = {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature
            }
            self.client.utility.verify_payment_signature(params)
            return True
        except Exception as e:
            logger.error(f"Payment signature verification failed: {e}")
            return False
    
    async def get_invoices(
        self,
        customer_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get Razorpay invoices for a customer"""
        try:
            invoices = self.client.invoice.all({"customer_id": customer_id, "count": limit})
            
            return [
                {
                    "invoice_id": inv["id"],
                    "status": inv.get("status"),
                    "amount": inv.get("amount", 0) / 100,
                    "amount_paid": inv.get("amount_paid", 0) / 100,
                    "currency": inv.get("currency", "INR"),
                    "short_url": inv.get("short_url"),
                    "created_at": datetime.fromtimestamp(inv.get("created_at", 0)),
                    "gateway": self.gateway_type.value
                }
                for inv in invoices.get("items", [])
            ]
        except Exception as e:
            logger.error(f"Failed to get Razorpay invoices: {e}")
            raise
    
    async def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Refund a Razorpay payment"""
        try:
            params = {}
            if amount:
                params["amount"] = int(amount * 100)
            if reason:
                params["notes"] = {"reason": reason}
            
            refund = self.client.payment.refund(payment_id, params)
            
            logger.info(f"Created Razorpay refund: {refund['id']}")
            return {
                "refund_id": refund["id"],
                "status": refund.get("status"),
                "amount": refund.get("amount", 0) / 100,
                "gateway": self.gateway_type.value
            }
        except Exception as e:
            logger.error(f"Failed to create Razorpay refund: {e}")
            raise


class PaymentGatewayFactory:
    """
    Factory to select appropriate payment gateway based on currency/country
    """
    
    _stripe: Optional[StripeGateway] = None
    _razorpay: Optional[RazorpayGateway] = None
    
    @classmethod
    def get_gateway(
        cls,
        gateway: Optional[PaymentGateway] = None,
        currency: Optional[str] = None,
        country_code: Optional[str] = None
    ) -> PaymentGatewayBase:
        """
        Get appropriate payment gateway.
        
        Priority:
        1. Explicitly specified gateway
        2. Currency-based selection (INR -> Razorpay, others -> Stripe)
        3. Country-based selection (IN -> Razorpay, others -> Stripe)
        4. Default from settings
        """
        # Explicit gateway
        if gateway == PaymentGateway.STRIPE:
            return cls._get_stripe()
        elif gateway == PaymentGateway.RAZORPAY:
            return cls._get_razorpay()
        
        # Auto-detection based on currency
        if settings.auto_detect_payment_gateway:
            if currency and currency.upper() == "INR":
                return cls._get_razorpay()
            elif currency and currency.upper() in ["USD", "EUR", "GBP", "AUD", "CAD"]:
                return cls._get_stripe()
            
            # Country-based fallback
            if country_code and country_code.upper() == "IN":
                return cls._get_razorpay()
            elif country_code:
                return cls._get_stripe()
        
        # Default based on settings
        if settings.default_currency.upper() == "INR":
            return cls._get_razorpay()
        return cls._get_stripe()
    
    @classmethod
    def _get_stripe(cls) -> StripeGateway:
        """Get or create Stripe gateway instance"""
        if cls._stripe is None:
            cls._stripe = StripeGateway()
        return cls._stripe
    
    @classmethod
    def _get_razorpay(cls) -> RazorpayGateway:
        """Get or create Razorpay gateway instance"""
        if cls._razorpay is None:
            cls._razorpay = RazorpayGateway()
        return cls._razorpay
    
    @classmethod
    def get_gateway_for_client(
        cls,
        phone_number: Optional[str] = None,
        country_code: Optional[str] = None
    ) -> PaymentGatewayBase:
        """
        Get gateway based on client's phone number country code.
        Useful for auto-detecting Indian vs International clients.
        """
        if phone_number:
            try:
                import phonenumbers
                parsed = phonenumbers.parse(phone_number)
                if parsed.country_code == 91:  # India
                    return cls._get_razorpay()
            except Exception:
                pass
        
        if country_code and country_code.upper() == "IN":
            return cls._get_razorpay()
        
        return cls.get_gateway()


# Convenience functions
def get_stripe_gateway() -> StripeGateway:
    """Get Stripe gateway instance"""
    return PaymentGatewayFactory._get_stripe()


def get_razorpay_gateway() -> RazorpayGateway:
    """Get Razorpay gateway instance"""
    return PaymentGatewayFactory._get_razorpay()


def get_payment_gateway(
    currency: Optional[str] = None,
    country_code: Optional[str] = None
) -> PaymentGatewayBase:
    """Get appropriate payment gateway"""
    return PaymentGatewayFactory.get_gateway(currency=currency, country_code=country_code)
