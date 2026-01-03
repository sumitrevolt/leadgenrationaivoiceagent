"""
Sync Tasks
Background tasks for CRM synchronization
"""
from celery import shared_task
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

from app.integrations.hubspot import HubSpotIntegration
from app.integrations.google_sheets import GoogleSheetsIntegration
from app.models.base import get_db_session
from app.models.lead import Lead, LeadStatus
from app.models.call_log import CallLog
from app.models.campaign import Campaign
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@shared_task
def sync_to_crm():
    """
    Sync new leads and call data to CRM systems
    """
    logger.info("Running CRM sync")
    
    synced_count = 0
    errors = []
    
    try:
        with get_db_session() as db:
            # Get unsynced leads (leads without CRM IDs that have been qualified)
            unsynced_leads = db.query(Lead).filter(
                Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.APPOINTMENT, LeadStatus.INTERESTED]),
                Lead.created_at >= datetime.utcnow() - timedelta(days=1)  # Last 24 hours
            ).limit(100).all()
            
            for lead in unsynced_leads:
                # Get campaign to check sync settings
                campaign = None
                if lead.campaign_id:
                    campaign = db.query(Campaign).filter(Campaign.id == lead.campaign_id).first()
                
                lead_data = {
                    "company_name": lead.company_name,
                    "contact_name": lead.contact_name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "city": lead.city,
                    "industry": lead.industry,
                    "lead_score": lead.lead_score,
                    "status": lead.status.value if lead.status else "new",
                    "source": lead.source.value if lead.source else "voice_agent"
                }
                
                # Sync to HubSpot if configured
                if campaign and campaign.sync_to_hubspot and settings.hubspot_api_key:
                    try:
                        sync_to_hubspot.delay(lead_data)
                        synced_count += 1
                    except Exception as e:
                        errors.append(f"HubSpot sync failed for {lead.id}: {e}")
                
                # Sync to Google Sheets if configured
                if campaign and campaign.sync_to_sheets and campaign.spreadsheet_id:
                    try:
                        sync_to_sheets.delay(lead_data, campaign.spreadsheet_id)
                        synced_count += 1
                    except Exception as e:
                        errors.append(f"Sheets sync failed for {lead.id}: {e}")
            
    except Exception as e:
        logger.error(f"CRM sync error: {e}")
        return {"status": "failed", "error": str(e)}
    
    return {
        "status": "completed",
        "synced_count": synced_count,
        "errors": errors[:10]  # Limit error list
    }


@shared_task
def sync_to_hubspot(lead_data: dict):
    """
    Sync a single lead to HubSpot
    """
    try:
        hubspot = HubSpotIntegration()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            contact_id = loop.run_until_complete(
                hubspot.create_contact(lead_data)
            )
        finally:
            loop.close()
        
        return {
            "status": "completed",
            "hubspot_id": contact_id
        }
        
    except Exception as e:
        logger.error(f"HubSpot sync failed: {e}")
        return {"status": "failed", "error": str(e)}


@shared_task
def sync_to_sheets(lead_data: dict, spreadsheet_id: str):
    """
    Sync a single lead to Google Sheets
    """
    try:
        sheets = GoogleSheetsIntegration()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(
                sheets.append_lead(lead_data, spreadsheet_id)
            )
        finally:
            loop.close()
        
        return {"status": "completed"}
        
    except Exception as e:
        logger.error(f"Sheets sync failed: {e}")
        return {"status": "failed", "error": str(e)}


@shared_task
def batch_sync_leads(leads: list, target: str, config: dict):
    """
    Batch sync multiple leads to a target system
    """
    logger.info(f"Batch syncing {len(leads)} leads to {target}")
    
    success_count = 0
    failed_count = 0
    
    for lead in leads:
        try:
            if target == "hubspot":
                sync_to_hubspot.delay(lead)
            elif target == "sheets":
                sync_to_sheets.delay(lead, config.get("spreadsheet_id"))
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to queue sync for lead: {e}")
            failed_count += 1
    
    return {
        "status": "completed",
        "queued": success_count,
        "failed": failed_count
    }


@shared_task
def import_from_crm(source: str, config: dict):
    """
    Import leads from external CRM
    """
    logger.info(f"Importing leads from {source}")
    
    imported_count = 0
    errors = []
    
    try:
        with get_db_session() as db:
            if source == "hubspot" and settings.hubspot_api_key:
                hubspot = HubSpotIntegration()
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Get contacts from HubSpot
                    contacts = loop.run_until_complete(
                        hubspot.get_contacts(
                            limit=config.get("limit", 100),
                            after=config.get("after")
                        )
                    )
                    
                    for contact in contacts:
                        # Check if lead already exists
                        existing = db.query(Lead).filter(
                            Lead.phone == contact.get("phone")
                        ).first()
                        
                        if not existing and contact.get("phone"):
                            new_lead = Lead(
                                id=str(uuid.uuid4()),
                                company_name=contact.get("company", "Unknown"),
                                contact_name=contact.get("name", ""),
                                phone=contact.get("phone"),
                                email=contact.get("email"),
                                city=contact.get("city"),
                                source=LeadSource.IMPORT,
                                status=LeadStatus.NEW
                            )
                            db.add(new_lead)
                            imported_count += 1
                    
                    db.commit()
                    
                finally:
                    loop.close()
                    
            elif source == "sheets":
                sheets = GoogleSheetsIntegration()
                spreadsheet_id = config.get("spreadsheet_id", settings.default_spreadsheet_id)
                
                if not spreadsheet_id:
                    return {"status": "failed", "error": "No spreadsheet ID provided"}
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Get leads from Google Sheets
                    rows = loop.run_until_complete(
                        sheets.get_leads(spreadsheet_id, config.get("sheet_name", "Leads"))
                    )
                    
                    for row in rows:
                        phone = row.get("phone") or row.get("Phone") or row.get("mobile")
                        if not phone:
                            continue
                        
                        # Check if lead already exists
                        existing = db.query(Lead).filter(Lead.phone == phone).first()
                        
                        if not existing:
                            new_lead = Lead(
                                id=str(uuid.uuid4()),
                                company_name=row.get("company_name") or row.get("Company") or "Unknown",
                                contact_name=row.get("contact_name") or row.get("Name") or "",
                                phone=phone,
                                email=row.get("email") or row.get("Email"),
                                city=row.get("city") or row.get("City"),
                                source=LeadSource.IMPORT,
                                status=LeadStatus.NEW
                            )
                            db.add(new_lead)
                            imported_count += 1
                    
                    db.commit()
                    
                finally:
                    loop.close()
            else:
                return {"status": "failed", "error": f"Unknown source: {source}"}
                    
    except Exception as e:
        logger.error(f"Import error: {e}")
        return {"status": "failed", "error": str(e)}
    
    return {
        "status": "completed",
        "source": source,
        "imported_count": imported_count,
        "errors": errors[:10]
    }


@shared_task
def sync_call_outcomes():
    """
    Sync call outcomes to CRM systems
    """
    logger.info("Syncing call outcomes to CRM")
    
    synced_count = 0
    
    try:
        with get_db_session() as db:
            # Get recent completed calls that need syncing
            recent_calls = db.query(CallLog).filter(
                CallLog.status == "completed",
                CallLog.created_at >= datetime.utcnow() - timedelta(hours=6)
            ).limit(50).all()
            
            for call in recent_calls:
                # Get lead and campaign
                lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
                if not lead:
                    continue
                
                campaign = None
                if call.campaign_id:
                    campaign = db.query(Campaign).filter(Campaign.id == call.campaign_id).first()
                
                # Prepare call outcome data
                outcome_data = {
                    "lead_id": lead.id,
                    "phone": lead.phone,
                    "call_outcome": call.outcome.value if call.outcome else None,
                    "call_duration": call.duration_seconds,
                    "lead_score": call.lead_score,
                    "is_hot_lead": call.is_hot_lead,
                    "appointment_scheduled": call.appointment_scheduled,
                    "appointment_date": call.appointment_date.isoformat() if call.appointment_date else None,
                    "call_date": call.initiated_at.isoformat() if call.initiated_at else None,
                    "summary": call.summary
                }
                
                # Update lead status in CRM if configured
                if campaign and campaign.sync_to_hubspot and settings.hubspot_api_key:
                    try:
                        update_hubspot_contact.delay(lead.phone, outcome_data)
                        synced_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to sync call outcome to HubSpot: {e}")
                        
    except Exception as e:
        logger.error(f"Call outcome sync error: {e}")
        return {"status": "failed", "error": str(e)}
    
    return {"status": "completed", "synced_count": synced_count}


@shared_task
def update_hubspot_contact(phone: str, data: dict):
    """
    Update a HubSpot contact with call outcome data
    """
    try:
        hubspot = HubSpotIntegration()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                hubspot.update_contact_by_phone(phone, data)
            )
        finally:
            loop.close()
        
        return {"status": "completed", "result": result}
        
    except Exception as e:
        logger.error(f"HubSpot update failed: {e}")
        return {"status": "failed", "error": str(e)}


# Add missing imports at module level
import uuid
from app.models.lead import LeadSource
