#!/usr/bin/env python3
"""
Create Initial Admin User Script - Direct Database Insert
Uses bcrypt for proper password hashing
"""
import asyncio
import os
import sys
import uuid
import bcrypt

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


async def create_admin_user():
    """Create a super admin user using direct SQL."""
    
    database_url = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://postgres:postgres@localhost:5432/voice_agent"
    )
    
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Admin credentials
    user_id = str(uuid.uuid4())
    email = "admin@leadgen.ai"
    password = "LeadGen2026!"
    
    # Hash password with bcrypt
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    async with async_session() as session:
        # Check if user already exists
        result = await session.execute(
            text("SELECT id FROM users WHERE email = :email"), 
            {"email": email}
        )
        existing = result.fetchone()
        
        if existing:
            print(f"✓ Admin user already exists: {email}")
            # Update password hash and role - use lowercase (enum values in DB)
            await session.execute(
                text("""
                    UPDATE users SET 
                        password_hash = :hash, 
                        role = 'super_admin', 
                        status = 'active', 
                        is_verified = :verified,
                        is_2fa_enabled = false
                    WHERE email = :email
                """),
                {"hash": password_hash, "verified": True, "email": email}
            )
            await session.commit()
            print("  Password and role updated!")
        else:
            # Insert new admin user - use lowercase (enum values in DB)
            await session.execute(
                text("""
                    INSERT INTO users (
                        id, email, password_hash, password_salt, 
                        first_name, last_name, role, status, 
                        is_verified, is_2fa_enabled, created_at, updated_at
                    ) VALUES (
                        :id, :email, :hash, '', 
                        :first, :last, 'super_admin', 'active', 
                        :verified, false, NOW(), NOW()
                    )
                """),
                {
                    "id": user_id,
                    "email": email,
                    "hash": password_hash,
                    "first": "Admin",
                    "last": "User",
                    "verified": True
                }
            )
            await session.commit()
            print("✅ Admin user created!")
        
        print("=" * 50)
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Role: SUPER_ADMIN")
        print("=" * 50)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin_user())
