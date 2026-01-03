#!/usr/bin/env python3
"""
LeadGen AI Voice Agent - Quick Start Script
Run this to verify your installation and configuration
"""
import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_python_version():
    """Check Python version"""
    print("?? Checking Python version...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"? Python 3.10+ required, found {version.major}.{version.minor}")
        return False
    print(f"? Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_dependencies():
    """Check required dependencies"""
    print("\n?? Checking dependencies...")
    
    required = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pydantic", "Pydantic"),
        ("sqlalchemy", "SQLAlchemy"),
        ("httpx", "HTTPX"),
    ]
    
    optional = [
        ("twilio", "Twilio"),
        ("deepgram", "Deepgram"),
        ("openai", "OpenAI"),
        ("google.generativeai", "Google Gemini"),
        ("celery", "Celery"),
        ("redis", "Redis"),
    ]
    
    all_ok = True
    for module, name in required:
        try:
            __import__(module)
            print(f"  ? {name}")
        except ImportError:
            print(f"  ? {name} - REQUIRED")
            all_ok = False
    
    print("\n  Optional packages:")
    for module, name in optional:
        try:
            __import__(module)
            print(f"    ? {name}")
        except ImportError:
            print(f"    ??  {name} - not installed")
    
    return all_ok


def check_configuration():
    """Check configuration"""
    print("\n??  Checking configuration...")
    
    try:
        from app.config import settings
        
        checks = [
            ("App Name", settings.app_name, True),
            ("Environment", settings.app_env, True),
            ("Gemini API Key", bool(settings.gemini_api_key), False),
            ("OpenAI API Key", bool(settings.openai_api_key), False),
            ("Deepgram API Key", bool(settings.deepgram_api_key), False),
            ("Twilio Account SID", bool(settings.twilio_account_sid), False),
            ("Exotel API Key", bool(settings.exotel_api_key), False),
            ("Database URL", "localhost" not in settings.database_url, False),
        ]
        
        has_llm = settings.gemini_api_key or settings.openai_api_key
        has_telephony = settings.twilio_account_sid or settings.exotel_api_key
        
        for name, value, required in checks:
            if isinstance(value, bool):
                status = "?" if value else ("?" if required else "??")
                value_display = "configured" if value else "not configured"
            else:
                status = "?"
                value_display = value
            print(f"  {status} {name}: {value_display}")
        
        if not has_llm:
            print("\n  ??  Warning: No LLM API key configured. Voice agent won't work.")
        if not has_telephony:
            print("  ??  Warning: No telephony provider configured. Calls won't work.")
        
        return True
        
    except Exception as e:
        print(f"  ? Configuration error: {e}")
        return False


def check_database():
    """Check database connection"""
    print("\n???  Checking database...")
    
    try:
        from app.models.base import Base
        print("  ? Database models loaded")
        
        # Try to connect (will fail without actual DB, but that's OK)
        try:
            from app.models.base import _get_sync_engine
            engine = _get_sync_engine()
            if engine:
                print("  ? Database engine initialized")
            else:
                print("  ??  Database not configured (will use in-memory storage)")
        except Exception as e:
            print(f"  ??  Database connection not available: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ? Database error: {e}")
        return False


async def check_platform():
    """Check platform components"""
    print("\n?? Checking platform components...")
    
    try:
        from app.lead_scraper.scraper_manager import LeadScraperManager
        print("  ? Lead Scraper Manager")
    except Exception as e:
        print(f"  ? Lead Scraper: {e}")
    
    try:
        from app.voice_agent.agent import VoiceAgent
        print("  ? Voice Agent")
    except Exception as e:
        print(f"  ? Voice Agent: {e}")
    
    try:
        from app.platform.orchestrator import PlatformOrchestrator
        print("  ? Platform Orchestrator")
    except Exception as e:
        print(f"  ? Platform Orchestrator: {e}")
    
    return True


def print_summary():
    """Print summary and next steps"""
    print("\n" + "=" * 60)
    print("?? LEADGEN AI VOICE AGENT - READY FOR ACTION!")
    print("=" * 60)
    print("""
?? Next Steps:

1. Configure your .env file with API keys:
   cp .env.example .env
   # Edit .env with your keys

2. Start the development server:
   make dev
   # Or: uvicorn app.main:app --reload

3. Access the API:
   - Swagger UI: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health
   - Platform Stats: http://localhost:8000/api/platform/stats

4. For production deployment:
   - Review PRODUCTION_CHECKLIST.md
   - Deploy with: make deploy

?? Documentation:
   - README.md - Project overview
   - infrastructure/DEPLOYMENT.md - Deployment guide
   - PRODUCTION_CHECKLIST.md - Pre-launch checklist

?? Issues?
   - Check logs in logs/ directory
   - Ensure all required env vars are set
   - Verify database and Redis are running
""")


async def main():
    """Run all checks"""
    print("=" * 60)
    print("?? LEADGEN AI VOICE AGENT - SYSTEM CHECK")
    print("=" * 60)
    
    results = []
    
    results.append(check_python_version())
    results.append(check_dependencies())
    results.append(check_configuration())
    results.append(check_database())
    results.append(await check_platform())
    
    print_summary()
    
    if all(results):
        print("? All checks passed! Your system is ready.")
        return 0
    else:
        print("??  Some checks failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
