#!/usr/bin/env python3
"""
Create Initial Admin User Script
Run this after deploying to create the first super admin user.
"""

import asyncio
import sys
import os
import getpass
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Import models
from app.models.user import User, UserRole, UserStatus


async def create_admin_user(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    database_url: str = None
):
    """Create a super admin user."""
    
    # Get database URL
    if not database_url:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("Error: DATABASE_URL environment variable not set")
            sys.exit(1)
    
    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Create engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if user already exists
        result = await session.execute(
            select(User).where(User.email == email)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"User with email {email} already exists!")
            if existing.role != UserRole.SUPER_ADMIN:
                print(f"Upgrading to SUPER_ADMIN role...")
                existing.role = UserRole.SUPER_ADMIN
                existing.status = UserStatus.ACTIVE
                existing.is_verified = True
                await session.commit()
                print("User upgraded successfully!")
            return existing
        
        # Create new user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.SUPER_ADMIN,
            status=UserStatus.ACTIVE,
            is_verified=True
        )
        user.set_password(password)
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        print(f"✓ Super admin user created successfully!")
        print(f"  Email: {email}")
        print(f"  Name: {first_name} {last_name}")
        print(f"  Role: SUPER_ADMIN")
        print(f"  ID: {user.id}")
        
        return user


def main():
    print("\n" + "=" * 50)
    print("  AuraLeads - Create Super Admin User")
    print("=" * 50 + "\n")
    
    # Get user input
    email = input("Email: ").strip()
    if not email:
        print("Error: Email is required")
        sys.exit(1)
    
    first_name = input("First Name: ").strip()
    if not first_name:
        print("Error: First name is required")
        sys.exit(1)
    
    last_name = input("Last Name: ").strip()
    if not last_name:
        print("Error: Last name is required")
        sys.exit(1)
    
    password = getpass.getpass("Password: ")
    if len(password) < 8:
        print("Error: Password must be at least 8 characters")
        sys.exit(1)
    
    password_confirm = getpass.getpass("Confirm Password: ")
    if password != password_confirm:
        print("Error: Passwords do not match")
        sys.exit(1)
    
    print("\nCreating user...")
    asyncio.run(create_admin_user(email, password, first_name, last_name))
    print("\n✓ Done! You can now log in to the admin panel.\n")


if __name__ == "__main__":
    main()
