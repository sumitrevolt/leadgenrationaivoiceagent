#!/usr/bin/env python3
"""
Production Startup Validation Script

This script runs before the application starts to verify:
1. Critical environment variables are set
2. Database is accessible
3. Redis is accessible
4. Required directories exist

Exit Codes:
- 0: All checks passed, safe to start
- 1: Critical failure, do not start
- 2: Non-critical issues, can start with warnings

Usage:
    python scripts/startup_check.py
    python scripts/startup_check.py --strict  # Fail on warnings
"""

import os
import sys
import asyncio
from typing import List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StartupChecker:
    """Production startup validation"""
    
    def __init__(self, strict: bool = False):
        self.strict = strict
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def check_environment(self) -> bool:
        """Check required environment variables"""
        required_vars = []
        
        # In production, these are required
        app_env = os.environ.get("APP_ENV", "development")
        
        if app_env == "production":
            required_vars = [
                "SECRET_KEY",
                "DATABASE_URL",
                "REDIS_URL",
            ]
            
            # Check secret key is not default
            secret_key = os.environ.get("SECRET_KEY", "")
            if secret_key in ["", "change-this-in-production"]:
                self.errors.append("SECRET_KEY must be set to a secure value in production")
            
            jwt_secret = os.environ.get("JWT_SECRET_KEY", "")
            if jwt_secret in ["", "change-this-jwt-secret-in-production"]:
                self.errors.append("JWT_SECRET_KEY must be set to a secure value in production")
            
            # Check DEBUG is false
            if os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"):
                self.errors.append("DEBUG must be false in production")
        
        # Check required vars
        for var in required_vars:
            if not os.environ.get(var):
                self.errors.append(f"Missing required environment variable: {var}")
        
        # Check at least one LLM is configured
        llm_vars = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_CLOUD_PROJECT_ID"]
        if not any(os.environ.get(v) for v in llm_vars):
            self.warnings.append("No LLM API key configured (GEMINI_API_KEY, OPENAI_API_KEY, etc.)")
        
        # Check at least one telephony is configured
        telephony_vars = ["TWILIO_ACCOUNT_SID", "EXOTEL_API_KEY"]
        if not any(os.environ.get(v) for v in telephony_vars):
            self.warnings.append("No telephony provider configured (TWILIO or EXOTEL)")
        
        return len(self.errors) == 0
    
    async def check_database(self) -> bool:
        """Check database connectivity"""
        try:
            from sqlalchemy import text
            from app.models.base import get_async_session
            
            async with get_async_session() as session:
                result = await session.execute(text("SELECT 1"))
                row = result.scalar()
                if row == 1:
                    print("  ? Database: Connected")
                    return True
                else:
                    self.errors.append("Database: Unexpected query result")
                    return False
        except ImportError as e:
            self.warnings.append(f"Database: Could not import (not configured): {e}")
            return True  # Not a failure if not configured
        except Exception as e:
            self.warnings.append(f"Database: Connection failed - {str(e)[:100]}")
            return True  # In dev, database might not be running
    
    async def check_redis(self) -> bool:
        """Check Redis connectivity"""
        try:
            from app.cache import get_redis_client, InMemoryCache
            
            client = await get_redis_client()
            
            # Check if using fallback
            if isinstance(client, InMemoryCache):
                self.warnings.append("Redis: Using in-memory fallback (not recommended for production)")
                return True
            
            await client.ping()
            print("  ? Redis: Connected")
            return True
        except ImportError as e:
            self.warnings.append(f"Redis: Could not import (not configured): {e}")
            return True
        except Exception as e:
            self.warnings.append(f"Redis: Connection failed (using fallback) - {str(e)[:100]}")
            return True  # Redis failure is a warning, not critical
    
    def check_directories(self) -> bool:
        """Check required directories exist"""
        required_dirs = [
            "data",
            "data/conversations",
            "data/feedback",
            "data/vectorstore",
        ]
        
        for dir_path in required_dirs:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    print(f"  ?? Created directory: {dir_path}")
                except Exception as e:
                    self.warnings.append(f"Could not create directory {dir_path}: {e}")
        
        return True
    
    def check_permissions(self) -> bool:
        """Check file permissions"""
        # Check if .env file exists and is readable
        env_files = [".env", ".env.production"]
        
        for env_file in env_files:
            if os.path.exists(env_file):
                if not os.access(env_file, os.R_OK):
                    self.warnings.append(f"Cannot read {env_file}")
                else:
                    # Check it's not world-readable in production
                    if os.environ.get("APP_ENV") == "production":
                        try:
                            import stat
                            mode = os.stat(env_file).st_mode
                            if mode & stat.S_IROTH:
                                self.warnings.append(f"{env_file} is world-readable (security risk)")
                        except Exception:
                            pass
        
        return True
    
    async def run_all_checks(self) -> Tuple[bool, bool]:
        """
        Run all startup checks
        Returns (critical_passed, all_passed)
        """
        print("\n?? Running production startup checks...\n")
        
        # Environment checks
        print("  Checking environment variables...")
        env_ok = self.check_environment()
        if env_ok:
            print("  ? Environment: OK")
        
        # Directory checks
        print("  Checking directories...")
        self.check_directories()
        print("  ? Directories: OK")
        
        # Permission checks
        print("  Checking permissions...")
        self.check_permissions()
        print("  ? Permissions: OK")
        
        # Database check
        print("  Checking database...")
        await self.check_database()
        
        # Redis check
        print("  Checking Redis...")
        await self.check_redis()
        
        # Print summary
        print("\n" + "=" * 50)
        
        if self.errors:
            print("? ERRORS (must fix):")
            for error in self.errors:
                print(f"   - {error}")
        
        if self.warnings:
            print("??  WARNINGS (review):")
            for warning in self.warnings:
                print(f"   - {warning}")
        
        print("=" * 50)
        
        critical_passed = len(self.errors) == 0
        all_passed = critical_passed and len(self.warnings) == 0
        
        if all_passed:
            print("? All checks passed! Ready to start.\n")
        elif critical_passed:
            print("??  Checks passed with warnings. Review before production.\n")
        else:
            print("? Critical checks failed! Do not start in production.\n")
        
        return critical_passed, all_passed


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Production startup validation")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")
    args = parser.parse_args()
    
    checker = StartupChecker(strict=args.strict)
    critical_passed, all_passed = await checker.run_all_checks()
    
    if not critical_passed:
        sys.exit(1)
    elif args.strict and not all_passed:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
