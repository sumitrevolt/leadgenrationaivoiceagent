"""
Growth Engine - Billionaire Mode
Automated Lead Generation for High-Ticket Niches
"""
import asyncio
import csv
import os
from datetime import datetime
from typing import List, Dict

from app.lead_scraper.google_maps import GoogleMapsScraper, BusinessLead
from app.niches import NICHES
from app.utils.logger import setup_logger

logger = setup_logger("growth_engine")

# Output directory for leads
OUTPUT_DIR = "revenue_pipeline"
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def run_growth_engine():
    """
    Main execution loop for the Growth Engine
    Target: 20 High-Ticket Niches
    """
    logger.info("🚀 Starting Growth Engine - Billionaire Mode")
    
    scraper = GoogleMapsScraper()
    
    # Target Cities (Tier 1 & 2 cities in India)
    # Ideally this would also be configurable, but starting with high-probability zones
    cities = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune"] 
    
    total_leads_count = 0
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    master_csv_file = os.path.join(OUTPUT_DIR, f"master_leads_{timestamp}.csv")
    
    # Initialize Master CSV
    with open(master_csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Niche", "City", "Business Name", "Phone", "Rating", 
            "Reviews", "Address", "Website", "Lead Score", "Action"
        ])
    
    for niche_key, niche_data in NICHES.items():
        niche_name = niche_data["name"]
        keywords = niche_data["keywords"]
        avg_value = niche_data["avg_deal_value"]
        
        logger.info(f"\n💰 Targeting Niche: {niche_name} (Value: {avg_value})")
        
        for city in cities:
            logger.info(f"  📍 Scouting {city}...")
            
            # Use the first keyword for search to keep it simple
            search_query = keywords[0]
            
            try:
                # Limit to 10 results per city per niche for initial run to avoid blocks
                leads: List[BusinessLead] = await scraper.search_businesses(
                    query=search_query,
                    location=city,
                    max_results=10 
                )
                
                logger.info(f"     ✅ Found {len(leads)} potential leads in {city}")
                
                # Append to Master CSV
                with open(master_csv_file, mode="a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    for lead in leads:
                        # Simple Heuristic Scoring
                        score = 0
                        if lead.phone: score += 50
                        if lead.website: score += 20
                        if lead.reviews_count and lead.reviews_count > 10: score += 10
                        if lead.rating and lead.rating > 4.0: score += 10
                        
                        # Determine Action
                        action = "COLD CALL" if score >= 60 else "RESEARCH"
                        
                        writer.writerow([
                            niche_name,
                            city,
                            lead.name,
                            lead.phone,
                            lead.rating,
                            lead.reviews_count,
                            lead.address,
                            lead.website,
                            score,
                            action
                        ])
                        
                total_leads_count += len(leads)
                
                # Sleep to respect rate limits / avoid bot detection
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"     ❌ Error scouting {city} for {niche_name}: {e}")
                
    logger.info(f"\n✨ Growth Engine Run Complete")
    logger.info(f"📊 Total Leads Generated: {total_leads_count}")
    logger.info(f"📁 Data saved to: {master_csv_file}")
    logger.info("💵 Next Step: Upload CSV to Campaign Manager and start dialing.")

if __name__ == "__main__":
    asyncio.run(run_growth_engine())
