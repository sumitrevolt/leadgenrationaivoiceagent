"""
Exotel Integration
Handles outbound calls via Exotel (India-focused)
"""
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass
import httpx
import base64

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class ExotelCallResult:
    """Result of an Exotel call operation"""
    call_sid: str
    status: str
    from_number: str
    to_number: str
    duration: Optional[int]
    recording_url: Optional[str]
    price: Optional[float]


class ExotelHandler:
    """
    Exotel telephony handler (India-focused)
    
    Exotel is preferred for Indian numbers due to:
    - Better connectivity
    - Lower costs
    - DND compliance support
    - Regional language support
    """
    
    def __init__(self):
        self.sid = settings.exotel_sid
        self.token = settings.exotel_token
        self.subdomain = settings.exotel_subdomain
        self.caller_id = settings.exotel_caller_id
        
        if self.sid and self.token:
            self.base_url = f"https://{self.sid}:{self.token}@{self.subdomain}.exotel.com/v1/Accounts/{self.sid}"
            self.auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
            logger.info("📞 Exotel Handler initialized")
        else:
            self.base_url = None
            logger.warning("Exotel credentials not configured")
    
    async def make_call(
        self,
        to_number: str,
        call_id: str,
        app_id: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Initiate an outbound call via Exotel
        
        Args:
            to_number: Indian phone number (10 digits)
            call_id: Internal call ID
            app_id: Exotel App ID for call flow
            webhook_url: Status callback URL
            
        Returns:
            Exotel Call SID
        """
        if not self.base_url:
            raise ValueError("Exotel not configured")
        
        # Normalize Indian number
        to_number = self._normalize_indian_number(to_number)
        
        url = f"{self.base_url}/Calls/connect.json"
        
        data = {
            "From": to_number,
            "CallerId": self.caller_id,
            "CallType": "trans",  # Transactional call
            "TimeLimit": 300,  # 5 minute limit
            "Record": "true"
        }
        
        if app_id:
            data["Url"] = f"http://my.exotel.com/{self.sid}/exoml/start_voice/{app_id}"
        
        if webhook_url:
            data["StatusCallback"] = webhook_url
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    data=data,
                    headers={"Authorization": f"Basic {self.auth}"},
                    timeout=30.0
                )
                response.raise_for_status()
                
                result = response.json()
                call_sid = result.get("Call", {}).get("Sid")
                
                logger.info(f"Exotel call initiated: {call_sid}")
                return call_sid
                
            except Exception as e:
                logger.error(f"Exotel call failed: {e}")
                raise
    
    async def get_call_status(self, call_sid: str) -> Optional[ExotelCallResult]:
        """Get status of an Exotel call"""
        if not self.base_url:
            return None
        
        url = f"{self.base_url}/Calls/{call_sid}.json"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Basic {self.auth}"},
                    timeout=15.0
                )
                response.raise_for_status()
                
                data = response.json().get("Call", {})
                
                return ExotelCallResult(
                    call_sid=data.get("Sid"),
                    status=data.get("Status"),
                    from_number=data.get("From"),
                    to_number=data.get("To"),
                    duration=int(data.get("Duration", 0)),
                    recording_url=data.get("RecordingUrl"),
                    price=float(data.get("Price", 0)) if data.get("Price") else None
                )
                
            except Exception as e:
                logger.error(f"Failed to get call status: {e}")
                return None
    
    async def hangup_call(self, call_sid: str) -> bool:
        """Terminate an active call"""
        if not self.base_url:
            return False
        
        url = f"{self.base_url}/Calls/{call_sid}.json"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    data={"Status": "completed"},
                    headers={"Authorization": f"Basic {self.auth}"},
                    timeout=15.0
                )
                response.raise_for_status()
                logger.info(f"Call {call_sid} terminated")
                return True
                
            except Exception as e:
                logger.error(f"Failed to hangup call: {e}")
                return False
    
    async def get_recording(self, call_sid: str) -> Optional[str]:
        """Get recording URL for a call"""
        status = await self.get_call_status(call_sid)
        return status.recording_url if status else None
    
    async def check_dnd_status(self, phone_number: str) -> Dict[str, Any]:
        """
        Check if number is on DND (Do Not Disturb) list
        
        This is CRITICAL for compliance in India
        """
        if not self.base_url:
            return {"status": "unknown", "error": "Exotel not configured"}
        
        phone_number = self._normalize_indian_number(phone_number)
        url = f"{self.base_url}/Numbers/{phone_number}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Basic {self.auth}"},
                    timeout=15.0
                )
                response.raise_for_status()
                
                data = response.json().get("Numbers", {})
                
                return {
                    "phone": phone_number,
                    "is_dnd": data.get("DND", False),
                    "operator": data.get("Operator"),
                    "circle": data.get("Circle"),
                    "type": data.get("Type")  # landline, mobile
                }
                
            except Exception as e:
                logger.error(f"DND check failed: {e}")
                return {"status": "error", "error": str(e)}
    
    def _normalize_indian_number(self, number: str) -> str:
        """Normalize to 10-digit Indian format"""
        # Remove all non-digits
        digits = ''.join(filter(str.isdigit, number))
        
        # Remove country code if present
        if digits.startswith('91') and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith('0') and len(digits) == 11:
            digits = digits[1:]
        
        return digits
    
    async def send_sms(
        self,
        to_number: str,
        message: str,
        sender_id: Optional[str] = None
    ) -> bool:
        """
        Send SMS via Exotel
        
        Useful for:
        - Follow-up after calls
        - Appointment confirmations
        - Lead nurturing
        """
        if not self.base_url:
            return False
        
        to_number = self._normalize_indian_number(to_number)
        url = f"{self.base_url}/Sms/send.json"
        
        data = {
            "From": sender_id or self.caller_id,
            "To": to_number,
            "Body": message
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    data=data,
                    headers={"Authorization": f"Basic {self.auth}"},
                    timeout=15.0
                )
                response.raise_for_status()
                logger.info(f"SMS sent to {to_number}")
                return True
                
            except Exception as e:
                logger.error(f"SMS failed: {e}")
                return False


class ExotelCallFlow:
    """
    Manages Exotel ExoML call flows
    """
    
    def __init__(self, handler: ExotelHandler):
        self.handler = handler
    
    def generate_greeting_flow(
        self,
        greeting_text: str,
        gather_url: str,
        language: str = "hi-IN"
    ) -> str:
        """
        Generate ExoML for greeting with input gathering
        
        Exotel uses XML-based ExoML similar to TwiML
        """
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather action="{gather_url}" method="POST" timeout="5" numDigits="1">
        <Say voice="female" language="{language}">{greeting_text}</Say>
    </Gather>
    <Say voice="female" language="{language}">
        Sorry, I didn't get that. Goodbye!
    </Say>
</Response>"""
    
    def generate_play_and_gather(
        self,
        audio_url: str,
        gather_url: str
    ) -> str:
        """Generate ExoML to play audio and gather input"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather action="{gather_url}" method="POST" timeout="5">
        <Play>{audio_url}</Play>
    </Gather>
</Response>"""
    
    def generate_hangup(self, final_message: str, language: str = "hi-IN") -> str:
        """Generate ExoML for ending call with message"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="{language}">{final_message}</Say>
    <Hangup/>
</Response>"""
