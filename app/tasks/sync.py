"""
Sync Tasks
Background tasks for CRM synchronization
"""
from celery import shared_task
import asyncio

from app.integrations.hubspot import HubSpotIntegration
from app.integrations.google_sheets import GoogleSheetsIntegration
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@shared_task
def sync_to_crm():
    """
    Sync new leads and call data to CRM systems
    """
    logger.info("Running CRM sync")
    
    # TODO: Get unsynced leads and calls from database
    # Sync to configured CRM systems
    
    return {"status": "completed"}


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
    
    # TODO: Implement import logic for different CRMs
    
    return {"status": "completed", "source": source}
