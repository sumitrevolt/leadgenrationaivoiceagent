"""Video generation wrapper for daily social posts.

Uses existing video_pipeline.py + reel_video.py to generate branded videos.
Runs in worker (heavy CPU) — never in web process.
"""

from app.utils.logger import setup_logger
import asyncio
import os

logger = setup_logger(__name__)

# Video specs for daily social posts
OWN_BRAND_SPEC = {
    "business_name": "LeadGen AI",
    "niche": "ai_marketing",
    "slides": [
        "🤖 LeadGen AI — AI Voice Agent for Local Businesses",
        "📞 Automated calls + marketing — ₹1,999/mo",
        "💡 New customers aayein, turant response mile",
        "🚀 Free demo available — visit leadsgenai.in",
    ],
    "offer": "Free demo + audit",
    "ratio": "9:16",  # Reel/Shorts format
}

CLIENT_TEMPLATES = {
    "residential_solar": {
        "slides": [
            "☀️ Solar lagao, bijli bill 80% bachao",
            "📞 Free survey + ROI report — turant call karein",
            "💰 EMI available — ₹0 down payment",
            "🔧 25 saal warranty — sarkari subsidy sahit",
        ],
        "offer": "Free solar survey",
    },
    "home_renovation": {
        "slides": [
            "🏠 Ghar banayen ya renovate karein — expert team",
            "📞 Free estimate + 3D design — 24h mein",
            "💎 Quality material + on-time delivery",
            "📱 WhatsApp pe photos bhejein — instant quote",
        ],
        "offer": "Free estimate + 3D design",
    },
    "general_local": {
        "slides": [
            "🏢 {business_name} — aapke area ka expert",
            "📞 Call ya WhatsApp karo — turant response",
            "💡 Free consultation — no obligation",
            "⭐ 500+ happy customers — trust karo",
        ],
        "offer": "Free consultation",
    },
}


async def generate_daily_videos():
    """Generate videos for own brand + active clients.
    
    Returns dict with video paths for posting.
    """
    from app.marketing.video_pipeline import render_creative_video
    
    results = {"own_brand": None, "clients": []}
    
    # 1. Own brand video
    own_result = await render_creative_video(
        recipe="generic",
        business_name=OWN_BRAND_SPEC["business_name"],
        niche=OWN_BRAND_SPEC["niche"],
        slides=OWN_BRAND_SPEC["slides"],
        offer=OWN_BRAND_SPEC["offer"],
        client_id="leadgenai-self",
        ratio=OWN_BRAND_SPEC["ratio"],
    )
    
    if "error" not in own_result:
        results["own_brand"] = own_result["path"]
        logger.info(f"[video_gen] Own brand video generated: {own_result['path']}")
    else:
        logger.warning(f"[video_gen] Own brand video failed: {own_result['error']}")
        results["own_brand"] = None
    
    # 2. Client videos (sample — production would query active clients)
    # For now: generate 2 sample client videos
    sample_clients = [
        {
            "id": "client-solar-001",
            "business_name": "SolarPower India",
            "niche": "residential_solar",
            "ratio": "9:16",
        },
        {
            "id": "client-renovate-001",
            "business_name": "HomeRenew",
            "niche": "home_renovation",
            "ratio": "9:16",
        },
    ]
    
    for client in sample_clients:
        template = CLIENT_TEMPLATES.get(client["niche"], CLIENT_TEMPLATES["general_local"])
        slides = [s.format(business_name=client["business_name"]) for s in template["slides"]]
        
        client_result = await render_creative_video(
            recipe="generic",
            business_name=client["business_name"],
            niche=client["niche"],
            slides=slides,
            offer=template["offer"],
            client_id=client["id"],
            ratio=client["ratio"],
        )
        
        if "error" not in client_result:
            results["clients"].append({
                "client_id": client["id"],
                "business_name": client["business_name"],
                "video_path": client_result["path"],
            })
            logger.info(f"[video_gen] Client {client['business_name']} video: {client_result['path']}")
        else:
            logger.warning(f"[video_gen] Client {client['business_name']} video failed: {client_result['error']}")
            results["clients"].append({
                "client_id": client["id"],
                "business_name": client["business_name"],
                "video_path": None,
                "error": client_result["error"],
            })
    
    return results


def sync_generate_daily_videos():
    """Synchronous wrapper for Celery beat entry."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(generate_daily_videos())


__all__ = ["generate_daily_videos", "sync_generate_daily_videos", "OWN_BRAND_SPEC", "CLIENT_TEMPLATES"]