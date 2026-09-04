"""Video generation wrapper for daily social posts.

Uses existing video_pipeline.py + reel_video.py to generate branded videos.
Runs in worker (heavy CPU) — never in web process.
"""

import asyncio
import os

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Video specs for our two distinct products (AGENTS.md Charter)
# Product 1: AI Automated Marketing (MAIN Product — ₹1,999/mo)
PRODUCT_1_MARKETING_SPEC = {
    "business_name": "LeadGen AI",
    "niche": "ai_marketing",
    "slides": [
        "Customer acquisition autopilot for local Indian businesses",
        "Free SEO audit, Google reviews & daily social posting",
        "Instant WhatsApp inquiries triage with 500 min voice callback",
        "Start today at just 1,999 per month on leadsgenai.in",
    ],
    "offer": "Free Site Audit & Demo",
    "ratio": "9:16",
}

# Product 2: AI Voice Calling Agent (Standalone Telecaller — ₹4,999/mo)
PRODUCT_2_VOICE_AGENT_SPEC = {
    "business_name": "LeadGen AI",
    "niche": "ai_telecaller",
    "slides": [
        "100% Autonomous AI Telecaller for Indian businesses",
        "Zero latency Hindi & Hinglish natural voice calling",
        "TRAI & DLT compliant 9am to 7pm safe calling window",
        "Instant lead qualification in 10 seconds — demo at leadsgenai.in",
    ],
    "offer": "Free Live Telecaller Demo",
    "ratio": "9:16",
}

# Backwards-compatible alias for existing daily social loop
OWN_BRAND_SPEC = PRODUCT_1_MARKETING_SPEC

CLIENT_TEMPLATES = {
    "residential_solar": {
        "slides": [
            "Solar lagao, bijli bill 80% bachao",
            "Free survey + ROI report — turant call karein",
            "EMI available — 0 down payment",
            "25 saal warranty — sarkari subsidy sahit",
        ],
        "offer": "Free solar survey",
    },
    "home_renovation": {
        "slides": [
            "Ghar banayen ya renovate karein — expert team",
            "Free estimate + 3D design — 24h mein",
            "Quality material + on-time delivery",
            "WhatsApp pe photos bhejein — instant quote",
        ],
        "offer": "Free estimate + 3D design",
    },
    "general_local": {
        "slides": [
            "{business_name} — aapke area ka expert",
            "Call ya WhatsApp karo — turant response",
            "Free consultation — no obligation",
            "500+ happy customers — trust karo",
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


async def generate_both_product_videos():
    """Generates enterprise videos for BOTH LeadGen AI products:
    1. Product 1: AI Automated Marketing (Main Product — ₹1,999/mo)
    2. Product 2: AI Voice Calling Agent (Standalone Telecaller — ₹4,999/mo)
    """
    from app.marketing.video_pipeline import render_creative_video

    outputs = {}

    logger.info("[video_gen] Generating Product 1: AI Marketing Autopilot...")
    p1 = await render_creative_video(
        recipe="generic",
        business_name=PRODUCT_1_MARKETING_SPEC["business_name"],
        niche=PRODUCT_1_MARKETING_SPEC["niche"],
        slides=PRODUCT_1_MARKETING_SPEC["slides"],
        offer=PRODUCT_1_MARKETING_SPEC["offer"],
        client_id="leadgenai-self",
        ratio=PRODUCT_1_MARKETING_SPEC["ratio"],
    )
    outputs["product1_marketing"] = p1.get("path")
    logger.info(f"[video_gen] Product 1 Video: {p1.get('path')}")

    logger.info("[video_gen] Generating Product 2: AI Voice Calling Agent...")
    p2 = await render_creative_video(
        recipe="generic",
        business_name=PRODUCT_2_VOICE_AGENT_SPEC["business_name"],
        niche=PRODUCT_2_VOICE_AGENT_SPEC["niche"],
        slides=PRODUCT_2_VOICE_AGENT_SPEC["slides"],
        offer=PRODUCT_2_VOICE_AGENT_SPEC["offer"],
        client_id="leadgenai-self",
        ratio=PRODUCT_2_VOICE_AGENT_SPEC["ratio"],
    )
    outputs["product2_telecaller"] = p2.get("path")
    logger.info(f"[video_gen] Product 2 Video: {p2.get('path')}")

    return outputs


def sync_generate_daily_videos():
    """Synchronous wrapper for Celery beat entry."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(generate_daily_videos())


__all__ = [
    "CLIENT_TEMPLATES",
    "OWN_BRAND_SPEC",
    "PRODUCT_1_MARKETING_SPEC",
    "PRODUCT_2_VOICE_AGENT_SPEC",
    "generate_both_product_videos",
    "generate_daily_videos",
    "sync_generate_daily_videos",
]


if __name__ == "__main__":
    out = asyncio.run(generate_both_product_videos())
    print("\n=== FINISHED RENDERING BOTH PRODUCT VIDEOS ===")
    for k, v in out.items():
        print(f"{k}: {v}")

