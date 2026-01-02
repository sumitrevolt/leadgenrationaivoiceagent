"""
HubSpot CRM Integration
Sync leads and activities to HubSpot
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import httpx

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class HubSpotContact:
    """HubSpot contact data"""
    email: Optional[str]
    firstname: Optional[str]
    lastname: Optional[str]
    phone: Optional[str]
    company: Optional[str]
    city: Optional[str]
    state: Optional[str]
    lead_score: Optional[int]
    lead_source: Optional[str]
    properties: Dict[str, Any] = None


class HubSpotIntegration:
    """
    HubSpot CRM Integration
    
    Syncs:
    - Contacts (leads)
    - Companies
    - Deals
    - Call activities
    - Notes
    """
    
    def __init__(self):
        self.api_key = settings.hubspot_api_key
        self.base_url = "https://api.hubapi.com"
        
        if self.api_key:
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            logger.info("🟠 HubSpot Integration initialized")
        else:
            self.headers = None
            logger.warning("HubSpot API key not configured")
    
    async def create_contact(
        self,
        contact_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Create a new contact in HubSpot
        
        Returns:
            HubSpot contact ID
        """
        if not self.headers:
            raise ValueError("HubSpot not configured")
        
        # Map our fields to HubSpot properties
        properties = {
            "email": contact_data.get('email', ''),
            "firstname": contact_data.get('contact_name', '').split()[0] if contact_data.get('contact_name') else '',
            "lastname": ' '.join(contact_data.get('contact_name', '').split()[1:]) if contact_data.get('contact_name') else '',
            "phone": contact_data.get('phone', ''),
            "company": contact_data.get('company_name', ''),
            "city": contact_data.get('city', ''),
            "state": contact_data.get('state', ''),
            "lead_source": contact_data.get('source', 'AI Voice Agent'),
        }
        
        # Add custom properties if they exist
        if 'lead_score' in contact_data:
            properties['hs_lead_status'] = self._get_lead_status(contact_data['lead_score'])
        
        payload = {"properties": properties}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/contacts",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                
                # Handle duplicate contact
                if response.status_code == 409:
                    # Contact exists, get their ID
                    existing = await self.find_contact_by_phone(contact_data.get('phone', ''))
                    if existing:
                        return existing.get('id')
                
                response.raise_for_status()
                result = response.json()
                
                contact_id = result.get('id')
                logger.info(f"HubSpot contact created: {contact_id}")
                return contact_id
                
            except Exception as e:
                logger.error(f"Failed to create HubSpot contact: {e}")
                raise
    
    async def update_contact(
        self,
        contact_id: str,
        properties: Dict[str, Any]
    ) -> bool:
        """Update an existing contact"""
        if not self.headers:
            return False
        
        payload = {"properties": properties}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(
                    f"{self.base_url}/crm/v3/objects/contacts/{contact_id}",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                logger.debug(f"HubSpot contact {contact_id} updated")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update contact: {e}")
                return False
    
    async def find_contact_by_phone(
        self,
        phone: str
    ) -> Optional[Dict[str, Any]]:
        """Find contact by phone number"""
        if not self.headers:
            return None
        
        # Normalize phone number
        phone_digits = ''.join(filter(str.isdigit, phone))[-10:]
        
        payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "phone",
                    "operator": "CONTAINS_TOKEN",
                    "value": phone_digits
                }]
            }]
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/contacts/search",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                results = response.json().get('results', [])
                return results[0] if results else None
                
            except Exception as e:
                logger.error(f"Contact search failed: {e}")
                return None
    
    async def create_company(
        self,
        company_data: Dict[str, Any]
    ) -> Optional[str]:
        """Create a company in HubSpot"""
        if not self.headers:
            return None
        
        properties = {
            "name": company_data.get('company_name', ''),
            "city": company_data.get('city', ''),
            "state": company_data.get('state', ''),
            "industry": company_data.get('category', ''),
            "phone": company_data.get('phone', ''),
            "website": company_data.get('website', ''),
        }
        
        payload = {"properties": properties}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/companies",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                return response.json().get('id')
                
            except Exception as e:
                logger.error(f"Failed to create company: {e}")
                return None
    
    async def create_deal(
        self,
        contact_id: str,
        deal_name: str,
        amount: float = 0,
        stage: str = "appointmentscheduled"
    ) -> Optional[str]:
        """Create a deal linked to a contact"""
        if not self.headers:
            return None
        
        # First create the deal
        properties = {
            "dealname": deal_name,
            "amount": str(amount),
            "dealstage": stage,
            "pipeline": "default",
        }
        
        payload = {"properties": properties}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/deals",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                deal_id = response.json().get('id')
                
                # Associate deal with contact
                await self.associate_deal_to_contact(deal_id, contact_id)
                
                logger.info(f"HubSpot deal created: {deal_id}")
                return deal_id
                
            except Exception as e:
                logger.error(f"Failed to create deal: {e}")
                return None
    
    async def associate_deal_to_contact(
        self,
        deal_id: str,
        contact_id: str
    ) -> bool:
        """Associate a deal with a contact"""
        if not self.headers:
            return False
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return True
                
            except Exception as e:
                logger.error(f"Failed to associate deal: {e}")
                return False
    
    async def log_call_activity(
        self,
        contact_id: str,
        call_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Log a call as an engagement/activity
        """
        if not self.headers:
            return None
        
        # Calculate timestamps
        call_time = call_data.get('completed_at', datetime.now())
        if isinstance(call_time, str):
            call_time = datetime.fromisoformat(call_time)
        
        duration_ms = call_data.get('duration_seconds', 0) * 1000
        
        properties = {
            "hs_call_title": f"AI Voice Agent Call - {call_data.get('outcome', 'Unknown')}",
            "hs_call_body": self._format_call_body(call_data),
            "hs_call_direction": "OUTBOUND",
            "hs_call_disposition": self._map_disposition(call_data.get('outcome', '')),
            "hs_call_duration": str(duration_ms),
            "hs_call_status": "COMPLETED",
            "hs_call_from_number": call_data.get('from_number', ''),
            "hs_call_to_number": call_data.get('phone', ''),
            "hs_timestamp": str(int(call_time.timestamp() * 1000)),
        }
        
        if call_data.get('recording_url'):
            properties['hs_call_recording_url'] = call_data['recording_url']
        
        payload = {
            "properties": properties,
            "associations": [{
                "to": {"id": contact_id},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 194  # Call to Contact
                }]
            }]
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/calls",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                call_id = response.json().get('id')
                logger.info(f"HubSpot call logged: {call_id}")
                return call_id
                
            except Exception as e:
                logger.error(f"Failed to log call: {e}")
                return None
    
    async def add_note(
        self,
        contact_id: str,
        note_body: str
    ) -> Optional[str]:
        """Add a note to a contact"""
        if not self.headers:
            return None
        
        payload = {
            "properties": {
                "hs_note_body": note_body,
                "hs_timestamp": str(int(datetime.now().timestamp() * 1000))
            },
            "associations": [{
                "to": {"id": contact_id},
                "types": [{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 202  # Note to Contact
                }]
            }]
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/notes",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                return response.json().get('id')
                
            except Exception as e:
                logger.error(f"Failed to add note: {e}")
                return None
    
    def _get_lead_status(self, score: int) -> str:
        """Map lead score to HubSpot lead status"""
        if score >= 80:
            return "QUALIFIED"
        elif score >= 60:
            return "OPEN"
        elif score >= 40:
            return "IN_PROGRESS"
        else:
            return "NEW"
    
    def _map_disposition(self, outcome: str) -> str:
        """Map our outcome to HubSpot disposition"""
        mapping = {
            "interested": "CONNECTED",
            "appointment": "CONNECTED",
            "callback": "CONNECTED",
            "not_interested": "CONNECTED",
            "no_answer": "NO_ANSWER",
            "busy": "BUSY",
            "failed": "FAILED",
            "voicemail": "LEFT_VOICEMAIL"
        }
        return mapping.get(outcome.lower(), "CONNECTED")
    
    def _format_call_body(self, call_data: Dict[str, Any]) -> str:
        """Format call data as note body"""
        body = f"""**AI Voice Agent Call Summary**

📞 **Outcome:** {call_data.get('outcome', 'Unknown')}
⏱️ **Duration:** {call_data.get('duration_seconds', 0)} seconds
🎯 **Lead Score:** {call_data.get('lead_score', 0)}/100

**Qualification Data:**
"""
        qual_data = call_data.get('qualification_data', {})
        for key, value in qual_data.items():
            body += f"- {key}: {value}\n"
        
        if call_data.get('appointment_details'):
            body += f"\n📅 **Appointment:** {call_data['appointment_details']}"
        
        if call_data.get('callback_time'):
            body += f"\n⏰ **Callback Requested:** {call_data['callback_time']}"
        
        return body


class ZohoCRMIntegration:
    """
    Zoho CRM Integration (placeholder)
    Similar structure to HubSpot
    """
    
    def __init__(self):
        self.client_id = settings.zoho_client_id
        self.client_secret = settings.zoho_client_secret
        self.refresh_token = settings.zoho_refresh_token
        
        if all([self.client_id, self.client_secret, self.refresh_token]):
            logger.info("🔵 Zoho CRM Integration initialized")
        else:
            logger.warning("Zoho CRM credentials not configured")
    
    async def create_lead(self, lead_data: Dict[str, Any]) -> Optional[str]:
        """Create a lead in Zoho CRM"""
        # Implementation similar to HubSpot
        # Uses Zoho API v2
        pass
    
    async def update_lead(self, lead_id: str, data: Dict[str, Any]) -> bool:
        """Update a lead in Zoho"""
        pass
    
    async def log_call(self, lead_id: str, call_data: Dict[str, Any]) -> bool:
        """Log call activity in Zoho"""
        pass
