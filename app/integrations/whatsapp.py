"""
WhatsApp Business API Integration
Send lead notifications and follow-ups via WhatsApp
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx
import json

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class WhatsAppMessage:
    """WhatsApp message data"""
    to: str
    message_type: str  # text, template, image, document
    content: str
    template_name: Optional[str] = None
    template_params: Optional[List[str]] = None


class WhatsAppIntegration:
    """
    WhatsApp Business API Integration
    
    Used for:
    - Sending hot lead alerts to sales team
    - Appointment confirmations
    - Lead follow-ups
    - Daily/weekly reports
    """
    
    def __init__(self):
        self.token = settings.whatsapp_business_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.base_url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}"
        
        if self.token:
            logger.info("📱 WhatsApp Integration initialized")
        else:
            logger.warning("WhatsApp credentials not configured")
    
    async def send_text_message(
        self,
        to_number: str,
        message: str
    ) -> Dict[str, Any]:
        """
        Send a simple text message
        
        Args:
            to_number: Recipient phone number (with country code)
            message: Message text
        """
        if not self.token:
            raise ValueError("WhatsApp not configured")
        
        # Ensure number format
        to_number = self._normalize_number(to_number)
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        return await self._send_message(payload)
    
    async def send_template_message(
        self,
        to_number: str,
        template_name: str,
        template_params: List[str],
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Send a pre-approved template message
        
        Template messages are required for initiating conversations
        """
        if not self.token:
            raise ValueError("WhatsApp not configured")
        
        to_number = self._normalize_number(to_number)
        
        # Build template components
        components = []
        if template_params:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": param}
                    for param in template_params
                ]
            })
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components
            }
        }
        
        return await self._send_message(payload)
    
    async def send_lead_alert(
        self,
        sales_team_number: str,
        lead_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send hot lead alert to sales team
        """
        message = f"""🔥 *NEW HOT LEAD!*

📞 *Company:* {lead_data.get('company_name', 'N/A')}
👤 *Contact:* {lead_data.get('contact_name', 'N/A')}
📱 *Phone:* {lead_data.get('phone', 'N/A')}
📍 *City:* {lead_data.get('city', 'N/A')}

🎯 *Lead Score:* {lead_data.get('lead_score', 0)}/100
💬 *Interest:* {lead_data.get('detected_intent', 'N/A')}

📝 *Key Points:*
{lead_data.get('notes', 'No additional notes')}

⏰ *Call Time:* {lead_data.get('call_time', 'N/A')}

Reply with 'CLAIM' to assign this lead to yourself."""
        
        return await self.send_text_message(sales_team_number, message)
    
    async def send_appointment_confirmation(
        self,
        to_number: str,
        client_name: str,
        appointment_date: str,
        appointment_time: str,
        meeting_link: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send appointment confirmation to lead
        """
        message = f"""✅ *Appointment Confirmed!*

Thank you for scheduling a meeting with *{client_name}*.

📅 *Date:* {appointment_date}
⏰ *Time:* {appointment_time}
"""
        if meeting_link:
            message += f"🔗 *Meeting Link:* {meeting_link}\n"
        
        message += "\nWe look forward to speaking with you!"
        
        return await self.send_text_message(to_number, message)
    
    async def send_callback_reminder(
        self,
        to_number: str,
        client_name: str,
        callback_time: str
    ) -> Dict[str, Any]:
        """
        Send callback reminder to sales team
        """
        message = f"""⏰ *CALLBACK REMINDER*

A lead requested a callback:

🏢 *Client:* {client_name}
📱 *Number:* {to_number}
⏰ *Requested Time:* {callback_time}

Please call them back at the requested time."""
        
        return await self.send_text_message(settings.smtp_user, message)  # Send to configured email as fallback
    
    async def send_daily_report(
        self,
        to_number: str,
        stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send daily campaign report
        """
        message = f"""📊 *DAILY CAMPAIGN REPORT*

📞 *Calls Made:* {stats.get('calls_made', 0)}
✅ *Connected:* {stats.get('calls_connected', 0)}
📈 *Connection Rate:* {stats.get('connection_rate', 0):.1%}

🎯 *Outcomes:*
  • Interested: {stats.get('interested', 0)}
  • Appointments: {stats.get('appointments', 0)}
  • Callbacks: {stats.get('callbacks', 0)}
  • Not Interested: {stats.get('not_interested', 0)}

🏆 *Hot Leads Today:* {stats.get('hot_leads', 0)}
💰 *Estimated Value:* ₹{stats.get('estimated_value', 0):,.0f}

Keep up the great work! 💪"""
        
        return await self.send_text_message(to_number, message)
    
    async def _send_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send message via WhatsApp API"""
        url = f"{self.base_url}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"WhatsApp message sent: {result.get('messages', [{}])[0].get('id')}")
                return result
                
            except httpx.HTTPStatusError as e:
                logger.error(f"WhatsApp API error: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"WhatsApp error: {e}")
                raise
    
    def _normalize_number(self, number: str) -> str:
        """Normalize phone number to WhatsApp format"""
        # Remove all non-digits
        digits = ''.join(filter(str.isdigit, number))
        
        # Add India country code if not present
        if len(digits) == 10:
            digits = "91" + digits
        elif digits.startswith("0"):
            digits = "91" + digits[1:]
        
        return digits


class WhatsAppWebhookHandler:
    """
    Handle incoming WhatsApp messages
    
    Can be used for:
    - Lead responses
    - Sales team commands (CLAIM, STATUS, etc.)
    - Two-way conversations
    """
    
    def __init__(self, integration: WhatsAppIntegration):
        self.whatsapp = integration
    
    async def handle_incoming_message(
        self,
        from_number: str,
        message_body: str,
        message_id: str
    ) -> Optional[str]:
        """
        Process incoming WhatsApp message
        
        Returns response message if any
        """
        message_lower = message_body.lower().strip()
        
        # Handle common commands
        if message_lower == "claim":
            return await self._handle_claim_command(from_number)
        elif message_lower == "status":
            return await self._handle_status_command(from_number)
        elif message_lower == "help":
            return self._get_help_message()
        
        return None
    
    async def _handle_claim_command(self, from_number: str) -> str:
        """Handle lead claim command from sales team"""
        # This would update the lead assignment in the database
        return "✅ Lead claimed successfully! The lead details have been assigned to you."
    
    async def _handle_status_command(self, from_number: str) -> str:
        """Handle status request"""
        return "📊 Campaign is running. Use the dashboard for detailed stats."
    
    def _get_help_message(self) -> str:
        """Return help message"""
        return """📖 *Available Commands:*

CLAIM - Claim the last hot lead
STATUS - Get current campaign status
HELP - Show this message

For detailed reports, visit the dashboard."""
