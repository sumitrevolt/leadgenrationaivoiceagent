"""
Scraping Tasks
Background tasks for lead scraping
"""
from celery import shared_task
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import json

from app.lead_scraper.scraper_manager import LeadScraperManager
from app.models.base import get_db_session
from app.models.campaign import Campaign, CampaignStatus
from app.models.lead import Lead, LeadStatus, LeadSource
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@shared_task(bind=True, max_retries=3)
def scrape_leads_task(self, niche: str, cities: list, max_leads: int = 100):
    """
    Background task to scrape leads
    """
    try:
        logger.info(f"Starting scrape task: {niche}, cities={cities}, max={max_leads}")
        
        scraper = LeadScraperManager()
        
        # Run async scraping in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            leads = loop.run_until_complete(
                scraper.scrape_leads(niche, cities, max_leads)
            )
        finally:
            loop.close()
        
        logger.info(f"Scrape completed: {len(leads)} leads found")
        
        return {
            "status": "completed",
            "leads_found": len(leads),
            "niche": niche
        }
        
    except Exception as e:
        logger.error(f"Scrape task failed: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


@shared_task
def scheduled_scrape():
    """
    Scheduled daily scraping for active campaigns
    """
    logger.info("Running scheduled scraping")
    
    campaigns_processed = 0
    total_leads_scraped = 0
    
    try:
        with get_db_session() as db:
            # Get active campaigns that need lead scraping
            active_campaigns = db.query(Campaign).filter(
                Campaign.status == CampaignStatus.RUNNING,
                Campaign.leads_scraped < Campaign.target_lead_count
            ).all()
            
            for campaign in active_campaigns:
                # Calculate how many leads we still need
                leads_needed = campaign.target_lead_count - campaign.leads_scraped
                if leads_needed <= 0:
                    continue
                
                # Parse target cities
                try:
                    target_cities = json.loads(campaign.target_cities) if campaign.target_cities else []
                except json.JSONDecodeError:
                    target_cities = campaign.target_cities.split(",") if campaign.target_cities else []
                
                if not target_cities:
                    target_cities = settings.platform_target_cities
                
                # Limit to 100 leads per scrape run
                max_leads = min(leads_needed, 100)
                
                # Queue scraping task for this campaign
                scrape_for_campaign.delay(
                    campaign_id=campaign.id,
                    niche=campaign.niche,
                    cities=target_cities,
                    max_leads=max_leads
                )
                
                campaigns_processed += 1
                logger.info(f"Queued scraping for campaign {campaign.name}: {max_leads} leads needed")
            
    except Exception as e:
        logger.error(f"Scheduled scrape error: {e}")
        return {"status": "failed", "error": str(e)}
    
    return {
        "status": "completed",
        "campaigns_processed": campaigns_processed
    }


@shared_task(bind=True, max_retries=2)
def scrape_for_campaign(self, campaign_id: str, niche: str, cities: list, max_leads: int = 100):
    """
    Scrape leads for a specific campaign and save to database
    """
    logger.info(f"Scraping for campaign {campaign_id}: {niche}, max={max_leads}")
    
    leads_saved = 0
    
    try:
        scraper = LeadScraperManager()
        
        # Run async scraping
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            scraped_leads = loop.run_until_complete(
                scraper.scrape_leads(niche, cities, max_leads)
            )
        finally:
            loop.close()
        
        # Save leads to database
        with get_db_session() as db:
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if not campaign:
                return {"status": "failed", "error": "Campaign not found"}
            
            for lead_data in scraped_leads:
                # Check for duplicate by phone
                existing = db.query(Lead).filter(
                    Lead.phone == lead_data.get("phone")
                ).first()
                
                if existing:
                    continue
                
                # Create new lead
                import uuid
                new_lead = Lead(
                    id=str(uuid.uuid4()),
                    company_name=lead_data.get("name", lead_data.get("company_name", "Unknown")),
                    contact_name=lead_data.get("contact_name", ""),
                    phone=lead_data.get("phone"),
                    email=lead_data.get("email"),
                    address=lead_data.get("address"),
                    city=lead_data.get("city"),
                    category=lead_data.get("category"),
                    niche=niche,
                    source=LeadSource.GOOGLE_MAPS,  # Default source
                    status=LeadStatus.NEW,
                    campaign_id=campaign_id,
                    assigned_to=campaign.client_id,
                    website=lead_data.get("website"),
                    tags=json.dumps(lead_data.get("tags", [])) if lead_data.get("tags") else None
                )
                
                db.add(new_lead)
                leads_saved += 1
            
            # Update campaign stats
            campaign.leads_scraped = (campaign.leads_scraped or 0) + leads_saved
            
            db.commit()
            
        logger.info(f"Saved {leads_saved} leads for campaign {campaign_id}")
        
        return {
            "status": "completed",
            "campaign_id": campaign_id,
            "leads_scraped": len(scraped_leads),
            "leads_saved": leads_saved
        }
        
    except Exception as e:
        logger.error(f"Campaign scraping failed: {e}")
        raise self.retry(exc=e, countdown=600)


@shared_task
def verify_phone_numbers(lead_ids: List[str] = None, limit: int = 100):
    """
    Verify phone numbers for leads
    """
    logger.info("Verifying phone numbers")
    
    verified_count = 0
    invalid_count = 0
    
    try:
        import phonenumbers
        
        with get_db_session() as db:
            query = db.query(Lead).filter(Lead.phone_verified == False)
            
            if lead_ids:
                query = query.filter(Lead.id.in_(lead_ids))
            
            leads = query.limit(limit).all()
            
            for lead in leads:
                try:
                    # Parse and validate phone number
                    parsed = phonenumbers.parse(lead.phone, "IN")
                    
                    if phonenumbers.is_valid_number(parsed):
                        # Format to E.164
                        lead.phone = phonenumbers.format_number(
                            parsed, phonenumbers.PhoneNumberFormat.E164
                        )
                        lead.phone_verified = True
                        verified_count += 1
                    else:
                        lead.status = LeadStatus.WRONG_NUMBER
                        invalid_count += 1
                        
                except Exception as e:
                    logger.debug(f"Invalid phone for lead {lead.id}: {e}")
                    invalid_count += 1
            
            db.commit()
            
    except ImportError:
        logger.warning("phonenumbers library not installed")
        return {"status": "failed", "error": "phonenumbers not installed"}
    except Exception as e:
        logger.error(f"Phone verification error: {e}")
        return {"status": "failed", "error": str(e)}
    
    return {
        "status": "completed",
        "verified": verified_count,
        "invalid": invalid_count
    }


@shared_task
def enrich_lead_data(lead_ids: List[str] = None, limit: int = 50):
    """
    Enrich lead data with additional information
    """
    logger.info("Enriching lead data")
    
    enriched_count = 0
    
    try:
        with get_db_session() as db:
            query = db.query(Lead).filter(
                Lead.email == None,  # Leads without email
                Lead.website != None  # But with website
            )
            
            if lead_ids:
                query = query.filter(Lead.id.in_(lead_ids))
            
            leads = query.limit(limit).all()
            
            for lead in leads:
                # Try to extract email from website
                if lead.website:
                    try:
                        import re
                        import httpx
                        
                        # Fetch website and look for email
                        response = httpx.get(lead.website, timeout=10, follow_redirects=True)
                        if response.status_code == 200:
                            # Find email patterns
                            emails = re.findall(
                                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                                response.text
                            )
                            if emails:
                                lead.email = emails[0]
                                lead.email_verified = False
                                enriched_count += 1
                    except Exception as e:
                        logger.debug(f"Could not enrich lead {lead.id}: {e}")
            
            db.commit()
            
    except Exception as e:
        logger.error(f"Lead enrichment error: {e}")
        return {"status": "failed", "error": str(e)}
    
    return {
        "status": "completed",
        "enriched_count": enriched_count
    }
