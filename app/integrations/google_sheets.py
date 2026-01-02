"""
Google Sheets Integration
Sync leads and reports to Google Sheets
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import json

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SheetData:
    """Data structure for sheet operations"""
    spreadsheet_id: str
    sheet_name: str
    data: List[List[Any]]


class GoogleSheetsIntegration:
    """
    Google Sheets Integration
    
    Used for:
    - Lead storage and tracking
    - Campaign reports
    - Call logs
    - Real-time dashboards (via Sheet formulas)
    """
    
    # Standard sheet headers
    LEAD_HEADERS = [
        "ID", "Company Name", "Contact Name", "Phone", "Email",
        "City", "State", "Category", "Source", "Lead Score",
        "Call Status", "Outcome", "Notes", "Created At", "Last Updated"
    ]
    
    CALL_LOG_HEADERS = [
        "Call ID", "Lead ID", "Phone", "Campaign", "Duration (s)",
        "Outcome", "Lead Score", "Appointment", "Callback Time",
        "Recording URL", "Timestamp"
    ]
    
    def __init__(self):
        self.credentials_path = settings.google_sheets_credentials
        self.default_spreadsheet = settings.default_spreadsheet_id
        self.client = None
        
        self._init_client()
    
    def _init_client(self):
        """Initialize Google Sheets client"""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            
            if self.credentials_path:
                scopes = [
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
                
                credentials = Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=scopes
                )
                
                self.client = gspread.authorize(credentials)
                logger.info("📊 Google Sheets Integration initialized")
            else:
                logger.warning("Google Sheets credentials not configured")
                
        except ImportError:
            logger.error("gspread not installed. Run: pip install gspread")
        except Exception as e:
            logger.error(f"Google Sheets init error: {e}")
    
    async def create_spreadsheet(
        self,
        title: str,
        share_with: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Create a new spreadsheet
        
        Returns:
            Spreadsheet ID
        """
        if not self.client:
            raise ValueError("Google Sheets not configured")
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.create,
                title
            )
            
            # Share with specified emails
            if share_with:
                for email in share_with:
                    await asyncio.to_thread(
                        spreadsheet.share,
                        email,
                        perm_type='user',
                        role='writer'
                    )
            
            logger.info(f"Created spreadsheet: {spreadsheet.id}")
            return spreadsheet.id
            
        except Exception as e:
            logger.error(f"Failed to create spreadsheet: {e}")
            raise
    
    async def add_leads_sheet(
        self,
        spreadsheet_id: Optional[str] = None
    ) -> bool:
        """
        Add a 'Leads' sheet with proper headers
        """
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client:
            raise ValueError("Google Sheets not configured")
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            # Create or get Leads sheet
            try:
                sheet = await asyncio.to_thread(
                    spreadsheet.worksheet,
                    "Leads"
                )
            except:
                sheet = await asyncio.to_thread(
                    spreadsheet.add_worksheet,
                    title="Leads",
                    rows=1000,
                    cols=len(self.LEAD_HEADERS)
                )
            
            # Add headers
            await asyncio.to_thread(
                sheet.update,
                'A1',
                [self.LEAD_HEADERS]
            )
            
            # Format header row
            await asyncio.to_thread(
                sheet.format,
                'A1:O1',
                {
                    "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
                }
            )
            
            logger.info("Leads sheet created/updated")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add leads sheet: {e}")
            return False
    
    async def append_lead(
        self,
        lead_data: Dict[str, Any],
        spreadsheet_id: Optional[str] = None
    ) -> bool:
        """
        Append a single lead to the Leads sheet
        """
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client:
            raise ValueError("Google Sheets not configured")
        
        row = [
            lead_data.get('id', ''),
            lead_data.get('company_name', ''),
            lead_data.get('contact_name', ''),
            lead_data.get('phone', ''),
            lead_data.get('email', ''),
            lead_data.get('city', ''),
            lead_data.get('state', ''),
            lead_data.get('category', ''),
            lead_data.get('source', ''),
            lead_data.get('lead_score', 0),
            lead_data.get('call_status', 'pending'),
            lead_data.get('outcome', ''),
            lead_data.get('notes', ''),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ]
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            sheet = await asyncio.to_thread(
                spreadsheet.worksheet,
                "Leads"
            )
            
            await asyncio.to_thread(
                sheet.append_row,
                row
            )
            
            logger.debug(f"Lead appended: {lead_data.get('company_name')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to append lead: {e}")
            return False
    
    async def append_leads_batch(
        self,
        leads: List[Dict[str, Any]],
        spreadsheet_id: Optional[str] = None
    ) -> int:
        """
        Append multiple leads in batch
        
        Returns:
            Number of leads added
        """
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client or not leads:
            return 0
        
        rows = []
        for lead in leads:
            rows.append([
                lead.get('id', ''),
                lead.get('company_name', ''),
                lead.get('contact_name', ''),
                lead.get('phone', ''),
                lead.get('email', ''),
                lead.get('city', ''),
                lead.get('state', ''),
                lead.get('category', ''),
                lead.get('source', ''),
                lead.get('lead_score', 0),
                lead.get('call_status', 'pending'),
                lead.get('outcome', ''),
                lead.get('notes', ''),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ])
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            sheet = await asyncio.to_thread(
                spreadsheet.worksheet,
                "Leads"
            )
            
            await asyncio.to_thread(
                sheet.append_rows,
                rows
            )
            
            logger.info(f"Batch added {len(rows)} leads")
            return len(rows)
            
        except Exception as e:
            logger.error(f"Batch append failed: {e}")
            return 0
    
    async def update_lead_status(
        self,
        lead_id: str,
        status: str,
        outcome: str,
        lead_score: int,
        notes: str = "",
        spreadsheet_id: Optional[str] = None
    ) -> bool:
        """
        Update an existing lead's status
        """
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client:
            return False
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            sheet = await asyncio.to_thread(
                spreadsheet.worksheet,
                "Leads"
            )
            
            # Find the lead by ID
            cell = await asyncio.to_thread(
                sheet.find,
                lead_id
            )
            
            if cell:
                row = cell.row
                # Update status columns (K, L, M, O)
                updates = [
                    {'range': f'K{row}', 'values': [[status]]},
                    {'range': f'L{row}', 'values': [[outcome]]},
                    {'range': f'J{row}', 'values': [[lead_score]]},
                    {'range': f'M{row}', 'values': [[notes]]},
                    {'range': f'O{row}', 'values': [[datetime.now().isoformat()]]}
                ]
                
                await asyncio.to_thread(
                    sheet.batch_update,
                    updates
                )
                
                logger.debug(f"Lead {lead_id} updated")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to update lead: {e}")
            return False
    
    async def add_call_log_sheet(
        self,
        spreadsheet_id: Optional[str] = None
    ) -> bool:
        """Add Call Logs sheet"""
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client:
            return False
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            try:
                sheet = await asyncio.to_thread(
                    spreadsheet.worksheet,
                    "Call Logs"
                )
            except:
                sheet = await asyncio.to_thread(
                    spreadsheet.add_worksheet,
                    title="Call Logs",
                    rows=1000,
                    cols=len(self.CALL_LOG_HEADERS)
                )
            
            await asyncio.to_thread(
                sheet.update,
                'A1',
                [self.CALL_LOG_HEADERS]
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add call log sheet: {e}")
            return False
    
    async def log_call(
        self,
        call_data: Dict[str, Any],
        spreadsheet_id: Optional[str] = None
    ) -> bool:
        """Log a completed call"""
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client:
            return False
        
        row = [
            call_data.get('call_id', ''),
            call_data.get('lead_id', ''),
            call_data.get('phone', ''),
            call_data.get('campaign_id', ''),
            call_data.get('duration_seconds', 0),
            call_data.get('outcome', ''),
            call_data.get('lead_score', 0),
            call_data.get('appointment_details', ''),
            call_data.get('callback_time', ''),
            call_data.get('recording_url', ''),
            datetime.now().isoformat()
        ]
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            sheet = await asyncio.to_thread(
                spreadsheet.worksheet,
                "Call Logs"
            )
            
            await asyncio.to_thread(
                sheet.append_row,
                row
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log call: {e}")
            return False
    
    async def get_leads_for_calling(
        self,
        limit: int = 100,
        spreadsheet_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leads that are pending calling
        """
        spreadsheet_id = spreadsheet_id or self.default_spreadsheet
        
        if not self.client:
            return []
        
        try:
            spreadsheet = await asyncio.to_thread(
                self.client.open_by_key,
                spreadsheet_id
            )
            
            sheet = await asyncio.to_thread(
                spreadsheet.worksheet,
                "Leads"
            )
            
            # Get all data
            records = await asyncio.to_thread(
                sheet.get_all_records
            )
            
            # Filter pending leads
            pending_leads = [
                record for record in records
                if record.get('Call Status', '').lower() == 'pending'
            ]
            
            return pending_leads[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get leads: {e}")
            return []
