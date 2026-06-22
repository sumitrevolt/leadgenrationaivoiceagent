#!/usr/bin/env python3
"""
GCP Secret Manager Setup Script

This script helps set up all required secrets in Google Cloud Secret Manager
for the LeadGen AI Voice Agent production deployment.

Usage:
    python scripts/setup_secrets.py --project-id YOUR_PROJECT_ID --env production

Requirements:
    - gcloud CLI installed and authenticated
    - google-cloud-secret-manager package installed
    - Proper IAM permissions (Secret Manager Admin)
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

try:
    from google.cloud import secretmanager
    from google.api_core.exceptions import AlreadyExists, NotFound
except ImportError:
    print("Error: google-cloud-secret-manager not installed.")
    print("Run: pip install google-cloud-secret-manager")
    sys.exit(1)


# Required secrets for production
REQUIRED_SECRETS = {
    # Core
    "secret-key": {
        "description": "Application secret key (min 32 chars)",
        "required": True,
        "generate": True,
    },
    "database-url": {
        "description": "PostgreSQL connection string",
        "required": True,
        "example": "postgresql+asyncpg://user:pass@host:5432/dbname",
    },
    "redis-url": {
        "description": "Redis connection string",
        "required": True,
        "example": "redis://host:6379/0",
    },
    
    # LLM API Keys (at least one required)
    "gemini-api-key": {
        "description": "Google Gemini API key",
        "required": False,
    },
    "openai-api-key": {
        "description": "OpenAI API key",
        "required": False,
    },
    "anthropic-api-key": {
        "description": "Anthropic API key",
        "required": False,
    },
    
    # Speech Services
    "deepgram-api-key": {
        "description": "Deepgram STT API key",
        "required": True,
    },
    "elevenlabs-api-key": {
        "description": "ElevenLabs TTS API key",
        "required": False,
    },
    "azure-speech-key": {
        "description": "Azure Speech Services key",
        "required": False,
    },
    
    # Telephony (at least one required)
    "twilio-account-sid": {
        "description": "Twilio Account SID",
        "required": False,
    },
    "twilio-auth-token": {
        "description": "Twilio Auth Token",
        "required": False,
    },
    "exotel-api-key": {
        "description": "Exotel API Key",
        "required": False,
    },
    "exotel-api-token": {
        "description": "Exotel API Token",
        "required": False,
    },
    
    # Integrations
    "hubspot-api-key": {
        "description": "HubSpot API key for CRM sync",
        "required": False,
    },
    "whatsapp-business-token": {
        "description": "WhatsApp Business API token",
        "required": False,
    },
    "google-maps-api-key": {
        "description": "Google Maps API key for lead scraping",
        "required": False,
    },
    
    # Email
    "smtp-password": {
        "description": "SMTP password for email notifications",
        "required": False,
    },
    
    # Monitoring
    "sentry-dsn": {
        "description": "Sentry DSN for error tracking",
        "required": True,
    },
}


def generate_secret_key(length: int = 64) -> str:
    """Generate a secure random secret key."""
    import secrets
    return secrets.token_urlsafe(length)


def create_secret(
    client: secretmanager.SecretManagerServiceClient,
    project_id: str,
    secret_id: str,
    environment: str,
) -> str:
    """Create a secret in Secret Manager if it doesn't exist."""
    parent = f"projects/{project_id}"
    full_secret_id = f"{environment}-{secret_id}"
    secret_name = f"{parent}/secrets/{full_secret_id}"
    
    try:
        client.get_secret(request={"name": secret_name})
        print(f"  ✓ Secret '{full_secret_id}' already exists")
        return secret_name
    except NotFound:
        pass
    
    try:
        secret = client.create_secret(
            request={
                "parent": parent,
                "secret_id": full_secret_id,
                "secret": {
                    "replication": {
                        "user_managed": {
                            "replicas": [{"location": "asia-south1"}]
                        }
                    },
                    "labels": {
                        "environment": environment,
                        "app": "leadgen-ai",
                        "managed_by": "setup-script",
                    },
                },
            }
        )
        print(f"  ✓ Created secret '{full_secret_id}'")
        return secret.name
    except AlreadyExists:
        print(f"  ✓ Secret '{full_secret_id}' already exists")
        return secret_name


def add_secret_version(
    client: secretmanager.SecretManagerServiceClient,
    secret_name: str,
    secret_value: str,
) -> None:
    """Add a new version to a secret."""
    client.add_secret_version(
        request={
            "parent": secret_name,
            "payload": {"data": secret_value.encode("UTF-8")},
        }
    )
    print(f"    → Added new version")


def get_latest_secret_version(
    client: secretmanager.SecretManagerServiceClient,
    secret_name: str,
) -> Optional[str]:
    """Get the latest version of a secret."""
    try:
        response = client.access_secret_version(
            request={"name": f"{secret_name}/versions/latest"}
        )
        return response.payload.data.decode("UTF-8")
    except NotFound:
        return None


def load_env_file(env_path: Path) -> dict:
    """Load environment variables from a .env file."""
    env_vars = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    # Remove quotes
                    value = value.strip().strip('"').strip("'")
                    env_vars[key.strip()] = value
    return env_vars


def env_key_to_secret_id(env_key: str) -> str:
    """Convert environment variable key to secret ID."""
    return env_key.lower().replace("_", "-")


def main():
    parser = argparse.ArgumentParser(
        description="Set up GCP Secret Manager secrets for LeadGen AI"
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="GCP Project ID",
    )
    parser.add_argument(
        "--env",
        choices=["development", "staging", "production"],
        default="production",
        help="Environment name",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file to read values from",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for missing secret values",
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"  LeadGen AI - Secret Manager Setup")
    print(f"  Project: {args.project_id}")
    print(f"  Environment: {args.env}")
    print(f"{'='*60}\n")
    
    # Load .env file if it exists
    env_vars = load_env_file(args.env_file)
    if env_vars:
        print(f"📁 Loaded {len(env_vars)} variables from {args.env_file}\n")
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    # Initialize client
    if not args.dry_run:
        client = secretmanager.SecretManagerServiceClient()
    else:
        client = None
    
    # Mapping from secret ID to env var name
    secret_to_env = {
        "secret-key": "SECRET_KEY",
        "database-url": "DATABASE_URL",
        "redis-url": "REDIS_URL",
        "gemini-api-key": "GEMINI_API_KEY",
        "openai-api-key": "OPENAI_API_KEY",
        "anthropic-api-key": "ANTHROPIC_API_KEY",
        "deepgram-api-key": "DEEPGRAM_API_KEY",
        "elevenlabs-api-key": "ELEVENLABS_API_KEY",
        "azure-speech-key": "AZURE_SPEECH_KEY",
        "twilio-account-sid": "TWILIO_ACCOUNT_SID",
        "twilio-auth-token": "TWILIO_AUTH_TOKEN",
        "exotel-api-key": "EXOTEL_API_KEY",
        "exotel-api-token": "EXOTEL_API_TOKEN",
        "hubspot-api-key": "HUBSPOT_API_KEY",
        "whatsapp-business-token": "WHATSAPP_BUSINESS_TOKEN",
        "google-maps-api-key": "GOOGLE_MAPS_API_KEY",
        "smtp-password": "SMTP_PASSWORD",
        "sentry-dsn": "SENTRY_DSN",
    }
    
    created_count = 0
    updated_count = 0
    skipped_count = 0
    missing_required = []
    
    for secret_id, config in REQUIRED_SECRETS.items():
        env_key = secret_to_env.get(secret_id, secret_id.upper().replace("-", "_"))
        value = env_vars.get(env_key) or os.environ.get(env_key)
        
        print(f"\n📌 {secret_id}")
        print(f"   {config['description']}")
        
        # Generate secret key if needed
        if not value and config.get("generate"):
            value = generate_secret_key()
            print(f"   🔐 Generated new secret key")
        
        # Prompt if interactive and no value
        if not value and args.interactive:
            if config["required"]:
                value = input(f"   Enter value (required): ").strip()
            else:
                value = input(f"   Enter value (optional, press Enter to skip): ").strip()
        
        if not value:
            if config["required"]:
                print(f"   ⚠️  MISSING (required)")
                missing_required.append(secret_id)
            else:
                print(f"   ⏭️  Skipped (optional)")
                skipped_count += 1
            continue
        
        if args.dry_run:
            print(f"   Would create/update with value: {'*' * min(len(value), 20)}...")
            created_count += 1
            continue
        
        # Create secret and add version
        secret_name = create_secret(client, args.project_id, secret_id, args.env)
        
        # Check if value already exists
        existing = get_latest_secret_version(client, secret_name)
        if existing == value:
            print(f"   ⏭️  Value unchanged")
            skipped_count += 1
        else:
            add_secret_version(client, secret_name, value)
            if existing:
                updated_count += 1
            else:
                created_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"{'='*60}")
    print(f"  ✅ Created: {created_count}")
    print(f"  🔄 Updated: {updated_count}")
    print(f"  ⏭️  Skipped: {skipped_count}")
    
    if missing_required:
        print(f"\n  ❌ Missing Required Secrets:")
        for secret_id in missing_required:
            print(f"     - {secret_id}")
        print(f"\n  Run with --interactive to provide values")
        sys.exit(1)
    
    print(f"\n✅ Secret Manager setup complete!")
    
    # Print Cloud Run configuration hint
    print(f"\n{'='*60}")
    print(f"  Next Steps")
    print(f"{'='*60}")
    print(f"""
  1. Ensure Cloud Run service account has Secret Manager access:
     
     gcloud projects add-iam-policy-binding {args.project_id} \\
       --member="serviceAccount:YOUR_SERVICE_ACCOUNT@{args.project_id}.iam.gserviceaccount.com" \\
       --role="roles/secretmanager.secretAccessor"

  2. Deploy with Terraform to configure Cloud Run with secrets:
     
     cd infrastructure/terraform
     terraform plan -var="project_id={args.project_id}"
     terraform apply -var="project_id={args.project_id}"
""")


if __name__ == "__main__":
    main()
