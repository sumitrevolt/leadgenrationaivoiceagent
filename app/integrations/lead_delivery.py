"""
Unified Lead Delivery Service
==============================
Jab koi lead "qualified" ho jaye, ye service usse automatically saare
configured channels par deliver kar deta hai:

  - WhatsApp : client ke number par formatted lead alert bhejta hai
  - Google Sheets : lead ko client ki sheet me ek row ke roop me append karta hai
  - HubSpot : contact create/update karta hai + optionally ek deal banata hai
  - Email : lead client ko email par bhejta hai

Har channel try/except + hasattr/getattr defensive checks ke saath wrapped hai.
Agar koi channel configured nahi hai (keys missing), to wo "skipped" ho jata hai —
service kabhi crash nahi karta.
"""

from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================================================================
# RESULT DATA STRUCTURES
# =============================================================================


@dataclass
class DeliveryResult:
    """
    Ek lead ki delivery ka result — kaunsa channel succeed/fail/skip hua.

    succeeded : channels jo successfully deliver hue
    failed    : channels jo error ke karan fail hue (dict: channel -> error str)
    skipped   : channels jo configured nahi the (skipped)
    """

    lead_ref: str = ""
    succeeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def any_delivered(self) -> bool:
        """True agar kam se kam ek channel par lead deliver hui"""
        return len(self.succeeded) > 0

    def mark_success(self, channel: str, info: Any = None):
        self.succeeded.append(channel)
        if info is not None:
            self.details[channel] = info

    def mark_failed(self, channel: str, error: str):
        self.failed[channel] = error

    def mark_skipped(self, channel: str):
        self.skipped.append(channel)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_ref": self.lead_ref,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "details": self.details,
            "any_delivered": self.any_delivered,
        }


# =============================================================================
# LEAD DELIVERY SERVICE
# =============================================================================


class LeadDelivery:
    """
    Unified lead-delivery orchestrator.

    Integration classes ko lazily import karta hai (import-safe), taaki ek
    integration module ka import error baaki sab ko na todhe. Har integration
    instance try/except me banta hai.

    Usage:
        delivery = get_lead_delivery()
        result = await delivery.deliver_lead(lead, client_config)
    """

    def __init__(self):
        # Per-channel master enable flags (.env). Default True — jiske keys
        # configured honge wahi actually deliver karega, baaki skip ho jayega.
        self.whatsapp_enabled = getattr(settings, "delivery_whatsapp_enabled", True)
        self.sheets_enabled = getattr(settings, "delivery_sheets_enabled", True)
        self.hubspot_enabled = getattr(settings, "delivery_hubspot_enabled", True)
        self.email_enabled = getattr(settings, "delivery_email_enabled", True)

        # Default notify target (jab client_config me number/email na ho)
        self.default_notify = getattr(settings, "client_notify_default", "") or ""

        # Lazily-created integration instances (cache)
        self._whatsapp = None
        self._sheets = None
        self._hubspot = None
        self._email = None

        logger.info("🚚 LeadDelivery service initialized")

    # ---------------------------------------------------------------------
    # Integration accessors (lazy + import-safe)
    # ---------------------------------------------------------------------

    def _get_whatsapp(self):
        if self._whatsapp is None:
            try:
                from app.integrations.whatsapp import get_whatsapp_sender

                self._whatsapp = get_whatsapp_sender()  # dual-engine: self-host or Cloud API
            except Exception as e:
                logger.error(f"WhatsApp integration load error: {e}")
                self._whatsapp = False  # sentinel: load failed
        return self._whatsapp or None

    def _get_sheets(self):
        if self._sheets is None:
            try:
                from app.integrations.google_sheets import GoogleSheetsIntegration

                self._sheets = GoogleSheetsIntegration()
            except Exception as e:
                logger.error(f"Google Sheets integration load error: {e}")
                self._sheets = False
        return self._sheets or None

    def _get_hubspot(self):
        if self._hubspot is None:
            try:
                from app.integrations.hubspot import HubSpotIntegration

                self._hubspot = HubSpotIntegration()
            except Exception as e:
                logger.error(f"HubSpot integration load error: {e}")
                self._hubspot = False
        return self._hubspot or None

    def _get_email(self):
        if self._email is None:
            try:
                from app.integrations.email_sender import EmailSender

                self._email = EmailSender()
            except Exception as e:
                logger.error(f"Email integration load error: {e}")
                self._email = False
        return self._email or None

    # ---------------------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------------------

    async def deliver_lead(
        self,
        lead: dict[str, Any],
        client_config: dict[str, Any] | None = None,
    ) -> DeliveryResult:
        """
        Ek qualified lead ko saare configured channels par deliver karta hai.

        Args:
            lead: lead dict. Fields: business/company_name, contact, phone,
                  city, niche, score (Hot/Warm/Cold), qualification, source.
            client_config: optional per-client overrides. Supported keys:
                  - whatsapp_number / notify_whatsapp : client WhatsApp number
                  - email / notify_email              : client email
                  - spreadsheet_id                    : client ki Google Sheet id
                  - create_deal (bool)                : HubSpot deal banaye ya na
                  - deal_amount (float)               : deal value
                  - channels (list[str])              : sirf in channels par bhejo

        Returns:
            DeliveryResult — kaunse channels succeeded/failed/skipped.
        """
        client_config = client_config or {}
        lead = lead or {}

        lead_ref = (
            lead.get("business") or lead.get("company_name") or lead.get("phone") or "unknown-lead"
        )
        result = DeliveryResult(lead_ref=str(lead_ref))

        # Optional channel whitelist from client_config
        allowed = client_config.get("channels")

        def _wanted(channel: str) -> bool:
            return allowed is None or channel in allowed

        # Run channels. Har channel apne andar try/except handle karta hai.
        if _wanted("whatsapp"):
            await self._deliver_whatsapp(lead, client_config, result)
        if _wanted("sheets"):
            await self._deliver_sheets(lead, client_config, result)
        if _wanted("hubspot"):
            await self._deliver_hubspot(lead, client_config, result)
        if _wanted("zoho"):
            await self._deliver_zoho(lead, client_config, result)
        if _wanted("email"):
            await self._deliver_email(lead, client_config, result)

        logger.info(
            f"Lead '{result.lead_ref}' delivery done — "
            f"ok={result.succeeded} skipped={result.skipped} failed={list(result.failed)}"
        )
        return result

    async def deliver_batch(
        self,
        leads: list[dict[str, Any]],
        client_config: dict[str, Any] | None = None,
    ) -> list[DeliveryResult]:
        """
        Multiple leads ko deliver karta hai. Har lead independently process hoti
        hai — ek lead fail ho to baaki continue rehti hain.
        """
        results: list[DeliveryResult] = []
        for lead in leads or []:
            try:
                res = await self.deliver_lead(lead, client_config)
            except Exception as e:
                # Defensive: deliver_lead vaise to internally safe hai
                logger.error(f"Batch deliver_lead crashed for a lead: {e}")
                res = DeliveryResult(lead_ref=str(lead.get("business") or "unknown"))
                res.mark_failed("all", str(e))
            results.append(res)
        logger.info(f"Batch delivery complete: {len(results)} leads processed")
        return results

    # ---------------------------------------------------------------------
    # CHANNEL: WHATSAPP
    # ---------------------------------------------------------------------

    async def _deliver_whatsapp(
        self,
        lead: dict[str, Any],
        client_config: dict[str, Any],
        result: DeliveryResult,
    ):
        channel = "whatsapp"
        if not self.whatsapp_enabled:
            logger.info(f"{channel}: skipped (disabled via DELIVERY_WHATSAPP_ENABLED)")
            result.mark_skipped(channel)
            return

        try:
            wa = self._get_whatsapp()
            if wa is None:
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            # Token na ho to configured nahi hai
            if not getattr(wa, "token", None):
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            to_number = (
                client_config.get("whatsapp_number")
                or client_config.get("notify_whatsapp")
                or self.default_notify
            )
            if not to_number:
                logger.info(f"{channel}: skipped (no client notify number)")
                result.mark_skipped(channel)
                return

            message = self._format_lead_message(lead)

            if hasattr(wa, "send_text_message"):
                resp = await wa.send_text_message(to_number, message)
                logger.info(f"{channel}: lead sent to {to_number}")
                result.mark_success(channel, resp)
            else:
                logger.info(f"{channel}: skipped (send_text_message unavailable)")
                result.mark_skipped(channel)

        except Exception as e:
            logger.error(f"{channel}: delivery failed: {e}")
            result.mark_failed(channel, str(e))

    # ---------------------------------------------------------------------
    # CHANNEL: GOOGLE SHEETS
    # ---------------------------------------------------------------------

    async def _deliver_sheets(
        self,
        lead: dict[str, Any],
        client_config: dict[str, Any],
        result: DeliveryResult,
    ):
        channel = "sheets"
        if not self.sheets_enabled:
            logger.info(f"{channel}: skipped (disabled via DELIVERY_SHEETS_ENABLED)")
            result.mark_skipped(channel)
            return

        try:
            sheets = self._get_sheets()
            if sheets is None:
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            # gspread client na bana ho to configured nahi
            if not getattr(sheets, "client", None):
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            spreadsheet_id = client_config.get("spreadsheet_id") or getattr(
                sheets, "default_spreadsheet", None
            )
            if not spreadsheet_id:
                logger.info(f"{channel}: skipped (no spreadsheet id)")
                result.mark_skipped(channel)
                return

            if hasattr(sheets, "append_lead"):
                row_data = self._to_sheet_lead(lead)
                ok = await sheets.append_lead(row_data, spreadsheet_id=spreadsheet_id)
                if ok:
                    logger.info(f"{channel}: lead appended to {spreadsheet_id}")
                    result.mark_success(channel, {"spreadsheet_id": spreadsheet_id})
                else:
                    logger.error(f"{channel}: append_lead returned False")
                    result.mark_failed(channel, "append_lead returned False")
            else:
                logger.info(f"{channel}: skipped (append_lead unavailable)")
                result.mark_skipped(channel)

        except Exception as e:
            logger.error(f"{channel}: delivery failed: {e}")
            result.mark_failed(channel, str(e))

    # ---------------------------------------------------------------------
    # CHANNEL: HUBSPOT
    # ---------------------------------------------------------------------

    async def _deliver_hubspot(
        self,
        lead: dict[str, Any],
        client_config: dict[str, Any],
        result: DeliveryResult,
    ):
        channel = "hubspot"
        if not self.hubspot_enabled:
            logger.info(f"{channel}: skipped (disabled via DELIVERY_HUBSPOT_ENABLED)")
            result.mark_skipped(channel)
            return

        try:
            hs = self._get_hubspot()
            if hs is None:
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            # headers None ho to api key configured nahi
            if not getattr(hs, "headers", None):
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            if not hasattr(hs, "create_contact"):
                logger.info(f"{channel}: skipped (create_contact unavailable)")
                result.mark_skipped(channel)
                return

            contact_data = self._to_hubspot_contact(lead)
            contact_id = await hs.create_contact(contact_data)

            if not contact_id:
                logger.error(f"{channel}: contact create returned no id")
                result.mark_failed(channel, "no contact id returned")
                return

            info: dict[str, Any] = {"contact_id": contact_id}
            logger.info(f"{channel}: contact created/updated id={contact_id}")

            # Optionally ek deal bhi banao
            want_deal = client_config.get("create_deal", False)
            if want_deal and hasattr(hs, "create_deal"):
                try:
                    deal_name = (
                        f"{lead.get('business') or lead.get('company_name') or 'Lead'} "
                        f"- {lead.get('niche', 'Opportunity')}"
                    )
                    amount = float(client_config.get("deal_amount", 0) or 0)
                    deal_id = await hs.create_deal(contact_id, deal_name, amount=amount)
                    if deal_id:
                        info["deal_id"] = deal_id
                        logger.info(f"{channel}: deal created id={deal_id}")
                except Exception as de:
                    # Deal fail hone par bhi contact success count hoga
                    logger.error(f"{channel}: deal creation failed: {de}")
                    info["deal_error"] = str(de)

            result.mark_success(channel, info)

        except Exception as e:
            logger.error(f"{channel}: delivery failed: {e}")
            result.mark_failed(channel, str(e))

    # ---------------------------------------------------------------------
    # CHANNEL: ZOHO CRM (Indian SMB native)
    # ---------------------------------------------------------------------

    async def _deliver_zoho(
        self,
        lead: dict[str, Any],
        client_config: dict[str, Any],
        result: DeliveryResult,
    ):
        channel = "zoho"
        try:
            from app.integrations.zoho_crm import ZohoCRM

            # Per-client creds (client_config) ya global settings fallback.
            z = ZohoCRM(
                client_id=str(client_config.get("zoho_client_id") or ""),
                client_secret=str(client_config.get("zoho_client_secret") or ""),
                refresh_token=str(client_config.get("zoho_refresh_token") or ""),
                dc=str(client_config.get("zoho_dc") or ""),
            )
            if not z.enabled:
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return
            rid = await z.upsert_lead(
                lead, note=str(lead.get("qualification") or lead.get("notes") or "")
            )
            if rid:
                logger.info(f"{channel}: lead upserted id={rid}")
                result.mark_success(channel, {"record_id": rid})
            else:
                result.mark_failed(channel, "upsert returned no id")
        except Exception as e:
            logger.error(f"{channel}: delivery failed: {e}")
            result.mark_failed(channel, str(e))

    # ---------------------------------------------------------------------
    # CHANNEL: EMAIL
    # ---------------------------------------------------------------------

    async def _deliver_email(
        self,
        lead: dict[str, Any],
        client_config: dict[str, Any],
        result: DeliveryResult,
    ):
        channel = "email"
        if not self.email_enabled:
            logger.info(f"{channel}: skipped (disabled via DELIVERY_EMAIL_ENABLED)")
            result.mark_skipped(channel)
            return

        try:
            mailer = self._get_email()
            if mailer is None:
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            # SMTP creds na ho to configured nahi
            if not (getattr(mailer, "user", None) and getattr(mailer, "password", None)):
                logger.info(f"{channel}: skipped (not configured)")
                result.mark_skipped(channel)
                return

            to_email = (
                client_config.get("email")
                or client_config.get("notify_email")
                or self.default_notify
            )
            # default_notify ek number bhi ho sakta hai — basic email check
            if not to_email or "@" not in str(to_email):
                logger.info(f"{channel}: skipped (no client email)")
                result.mark_skipped(channel)
                return

            if hasattr(mailer, "send_email"):
                subject = (
                    f"🎯 New Qualified Lead: "
                    f"{lead.get('business') or lead.get('company_name') or 'Lead'}"
                )
                body = self._format_lead_message(lead)
                ok = await mailer.send_email([to_email], subject, body)
                if ok:
                    logger.info(f"{channel}: lead emailed to {to_email}")
                    result.mark_success(channel, {"to": to_email})
                else:
                    logger.error(f"{channel}: send_email returned False")
                    result.mark_failed(channel, "send_email returned False")
            else:
                logger.info(f"{channel}: skipped (send_email unavailable)")
                result.mark_skipped(channel)

        except Exception as e:
            logger.error(f"{channel}: delivery failed: {e}")
            result.mark_failed(channel, str(e))

    # ---------------------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------------------

    def _format_lead_message(self, lead: dict[str, Any]) -> str:
        """
        Clean WhatsApp/email text banata hai lead ke fields se.
        Fields: business, contact, phone, city, niche, score, qualification, source.
        """
        business = lead.get("business") or lead.get("company_name") or "N/A"
        contact = lead.get("contact") or lead.get("contact_name") or "N/A"
        phone = lead.get("phone") or "N/A"
        city = lead.get("city") or "N/A"
        niche = lead.get("niche") or lead.get("category") or "N/A"
        score = lead.get("score") or lead.get("lead_score") or "N/A"
        source = lead.get("source") or "N/A"
        qualification = lead.get("qualification") or lead.get("notes") or "No notes"

        # Score ke hisab se emoji
        score_str = str(score)
        emoji = (
            "🔥" if score_str.lower() == "hot" else ("🌤️" if score_str.lower() == "warm" else "❄️")
        )

        message = f"""{emoji} *NEW QUALIFIED LEAD*

🏢 *Business:* {business}
👤 *Contact:* {contact}
📱 *Phone:* {phone}
📍 *City:* {city}
🏷️ *Niche:* {niche}
🎯 *Score:* {score_str}
🔗 *Source:* {source}

📝 *Qualification Notes:*
{qualification}

— Delivered by LeadGen AI Voice Agent"""

        return message

    def _to_sheet_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        """
        Lead dict ko GoogleSheetsIntegration.append_lead ke expected keys me map karta hai.
        """
        return {
            "id": lead.get("id", ""),
            "company_name": lead.get("business") or lead.get("company_name", ""),
            "contact_name": lead.get("contact") or lead.get("contact_name", ""),
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "city": lead.get("city", ""),
            "state": lead.get("state", ""),
            "category": lead.get("niche") or lead.get("category", ""),
            "source": lead.get("source", ""),
            "lead_score": lead.get("score") or lead.get("lead_score", ""),
            "call_status": lead.get("call_status", "qualified"),
            "outcome": lead.get("outcome", "qualified"),
            "notes": lead.get("qualification") or lead.get("notes", ""),
        }

    def _to_hubspot_contact(self, lead: dict[str, Any]) -> dict[str, Any]:
        """
        Lead dict ko HubSpotIntegration.create_contact ke expected keys me map karta hai.
        """
        return {
            "email": lead.get("email", ""),
            "contact_name": lead.get("contact") or lead.get("contact_name", ""),
            "phone": lead.get("phone", ""),
            "company_name": lead.get("business") or lead.get("company_name", ""),
            "city": lead.get("city", ""),
            "state": lead.get("state", ""),
            "category": lead.get("niche") or lead.get("category", ""),
            "source": lead.get("source", "AI Voice Agent"),
            # HubSpot _get_lead_status() expects numeric score; agar Hot/Warm/Cold
            # string hai to use numeric me map kar dete hain.
            "lead_score": self._score_to_number(lead.get("score") or lead.get("lead_score")),
        }

    @staticmethod
    def _score_to_number(score: Any) -> int:
        """Hot/Warm/Cold ya numeric score ko 0-100 numeric me normalize karta hai."""
        if score is None:
            return 0
        if isinstance(score, (int, float)):
            return int(score)
        s = str(score).strip().lower()
        if s in ("hot",):
            return 85
        if s in ("warm",):
            return 60
        if s in ("cold",):
            return 30
        # numeric-as-string?
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0


# =============================================================================
# SINGLETON
# =============================================================================

_lead_delivery_instance: LeadDelivery | None = None


def get_lead_delivery() -> LeadDelivery:
    """Process-wide singleton LeadDelivery instance return karta hai."""
    global _lead_delivery_instance
    if _lead_delivery_instance is None:
        _lead_delivery_instance = LeadDelivery()
    return _lead_delivery_instance
