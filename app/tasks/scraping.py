"""
Scraping Tasks
Background tasks for lead scraping
"""
from celery import shared_task
import asyncio

from app.lead_scraper.scraper_manager import LeadScraperManager
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
    
    # TODO: Get active campaigns from database
    # For each active campaign that needs leads, run scraping
    
    return {"status": "completed"}
