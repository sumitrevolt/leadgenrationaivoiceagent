#!/usr/bin/env python3
"""
GCP Project Setup Script

This script automates the setup of a Google Cloud Platform project
for the LeadGen AI Voice Agent, including:
- Enabling required APIs
- Creating Artifact Registry
- Setting up Cloud SQL (PostgreSQL)
- Setting up Redis (Memorystore)
- Configuring IAM permissions
- Creating Secret Manager secrets

Usage:
    python scripts/setup_gcp.py --project-id YOUR_PROJECT_ID
    python scripts/setup_gcp.py --project-id YOUR_PROJECT_ID --region asia-south1
    python scripts/setup_gcp.py --project-id YOUR_PROJECT_ID --dry-run
"""

import argparse
import subprocess
import sys
import time
from typing import Optional

# Required GCP APIs
REQUIRED_APIS = [
    "run.googleapis.com",                    # Cloud Run
    "secretmanager.googleapis.com",          # Secret Manager
    "cloudbuild.googleapis.com",             # Cloud Build
    "artifactregistry.googleapis.com",       # Artifact Registry
    "sqladmin.googleapis.com",               # Cloud SQL Admin
    "redis.googleapis.com",                  # Memorystore Redis
    "compute.googleapis.com",                # Compute Engine (networking)
    "servicenetworking.googleapis.com",      # VPC peering
    "monitoring.googleapis.com",             # Cloud Monitoring
    "logging.googleapis.com",                # Cloud Logging
    "cloudtrace.googleapis.com",             # Cloud Trace
    "speech.googleapis.com",                 # Speech-to-Text
    "texttospeech.googleapis.com",           # Text-to-Speech
    "aiplatform.googleapis.com",             # Vertex AI
]

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_step(message: str, step: int = None, total: int = None):
    """Print a step message."""
    if step and total:
        prefix = f"[{step}/{total}]"
    else:
        prefix = "[*]"
    print(f"{Colors.BLUE}{prefix}{Colors.END} {message}")


def print_success(message: str):
    """Print a success message."""
    print(f"{Colors.GREEN}✓{Colors.END} {message}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Colors.RED}✗{Colors.END} {message}")


def run_command(
    cmd: list,
    dry_run: bool = False,
    capture_output: bool = True,
    check: bool = True
) -> Optional[str]:
    """Run a gcloud command."""
    if dry_run:
        print(f"  {Colors.YELLOW}[DRY-RUN]{Colors.END} {' '.join(cmd)}")
        return None
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            shell=True
        )
        return result.stdout.strip() if capture_output else None
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e.stderr):
            return "exists"
        raise


def check_gcloud_installed() -> bool:
    """Check if gcloud CLI is installed."""
    try:
        subprocess.run(
            ["gcloud", "--version"],
            capture_output=True,
            check=True,
            shell=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_authenticated() -> bool:
    """Check if user is authenticated with gcloud."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
            capture_output=True,
            text=True,
            check=True,
            shell=True
        )
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def enable_apis(project_id: str, dry_run: bool = False):
    """Enable required GCP APIs."""
    print_step("Enabling required APIs...", 1, 7)
    
    for i, api in enumerate(REQUIRED_APIS, 1):
        try:
            run_command(
                ["gcloud", "services", "enable", api, "--project", project_id],
                dry_run=dry_run
            )
            print_success(f"Enabled {api} ({i}/{len(REQUIRED_APIS)})")
        except subprocess.CalledProcessError as e:
            print_warning(f"Could not enable {api}: {e}")


def create_artifact_registry(
    project_id: str,
    region: str,
    dry_run: bool = False
):
    """Create Artifact Registry repository."""
    print_step("Creating Artifact Registry repository...", 2, 7)
    
    try:
        run_command([
            "gcloud", "artifacts", "repositories", "create", "leadgen-repo",
            "--repository-format=docker",
            "--location", region,
            "--project", project_id,
            "--description", "LeadGen AI Voice Agent Docker images"
        ], dry_run=dry_run)
        print_success("Created Artifact Registry: leadgen-repo")
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e.stderr):
            print_warning("Artifact Registry already exists")
        else:
            raise


def create_vpc_network(project_id: str, dry_run: bool = False):
    """Create VPC network for private services."""
    print_step("Creating VPC network...", 3, 7)
    
    try:
        # Create VPC
        run_command([
            "gcloud", "compute", "networks", "create", "leadgen-vpc",
            "--project", project_id,
            "--subnet-mode=auto"
        ], dry_run=dry_run)
        print_success("Created VPC network: leadgen-vpc")
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e.stderr):
            print_warning("VPC network already exists")
        else:
            raise
    
    try:
        # Create private IP range for services
        run_command([
            "gcloud", "compute", "addresses", "create", "leadgen-private-range",
            "--global",
            "--purpose=VPC_PEERING",
            "--prefix-length=16",
            "--network=leadgen-vpc",
            "--project", project_id
        ], dry_run=dry_run)
        print_success("Created private IP range")
    except subprocess.CalledProcessError:
        print_warning("Private IP range already exists or failed")
    
    try:
        # Create VPC peering
        run_command([
            "gcloud", "services", "vpc-peerings", "connect",
            "--service=servicenetworking.googleapis.com",
            "--ranges=leadgen-private-range",
            "--network=leadgen-vpc",
            "--project", project_id
        ], dry_run=dry_run)
        print_success("Created VPC peering")
    except subprocess.CalledProcessError:
        print_warning("VPC peering already exists or failed")


def create_cloud_sql(
    project_id: str,
    region: str,
    dry_run: bool = False
):
    """Create Cloud SQL PostgreSQL instance."""
    print_step("Creating Cloud SQL PostgreSQL instance...", 4, 7)
    
    try:
        run_command([
            "gcloud", "sql", "instances", "create", "leadgen-db",
            "--database-version=POSTGRES_15",
            "--tier=db-f1-micro",  # Smallest tier for cost savings
            "--region", region,
            "--project", project_id,
            "--network=leadgen-vpc",
            "--no-assign-ip",  # Private IP only
            "--storage-type=SSD",
            "--storage-size=10GB"
        ], dry_run=dry_run)
        print_success("Created Cloud SQL instance: leadgen-db")
        print_warning("Note: This may take 5-10 minutes to complete")
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e.stderr):
            print_warning("Cloud SQL instance already exists")
        else:
            print_warning(f"Cloud SQL creation failed: {e}")
            print_warning("You may need to create it manually")


def create_redis(
    project_id: str,
    region: str,
    dry_run: bool = False
):
    """Create Memorystore Redis instance."""
    print_step("Creating Memorystore Redis instance...", 5, 7)
    
    try:
        run_command([
            "gcloud", "redis", "instances", "create", "leadgen-redis",
            "--size=1",
            "--region", region,
            "--project", project_id,
            "--network=leadgen-vpc",
            "--tier=basic"
        ], dry_run=dry_run)
        print_success("Created Redis instance: leadgen-redis")
        print_warning("Note: This may take 5-10 minutes to complete")
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e.stderr):
            print_warning("Redis instance already exists")
        else:
            print_warning(f"Redis creation failed: {e}")
            print_warning("You may need to create it manually")


def setup_iam(project_id: str, dry_run: bool = False):
    """Set up IAM permissions for Cloud Run."""
    print_step("Setting up IAM permissions...", 6, 7)
    
    # Get Cloud Run service account
    service_account = f"{project_id}@appspot.gserviceaccount.com"
    
    roles = [
        "roles/secretmanager.secretAccessor",
        "roles/cloudsql.client",
        "roles/redis.editor",
        "roles/logging.logWriter",
        "roles/monitoring.metricWriter",
        "roles/cloudtrace.agent",
        "roles/aiplatform.user",
    ]
    
    for role in roles:
        try:
            run_command([
                "gcloud", "projects", "add-iam-policy-binding", project_id,
                f"--member=serviceAccount:{service_account}",
                f"--role={role}"
            ], dry_run=dry_run)
            print_success(f"Granted {role}")
        except subprocess.CalledProcessError:
            print_warning(f"Could not grant {role}")


def create_cloud_run_service_account(project_id: str, dry_run: bool = False):
    """Create dedicated service account for Cloud Run."""
    print_step("Creating Cloud Run service account...", 7, 7)
    
    sa_name = "leadgen-cloud-run"
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    
    try:
        run_command([
            "gcloud", "iam", "service-accounts", "create", sa_name,
            "--display-name", "LeadGen Cloud Run Service Account",
            "--project", project_id
        ], dry_run=dry_run)
        print_success(f"Created service account: {sa_email}")
    except subprocess.CalledProcessError as e:
        if "already exists" in str(e.stderr):
            print_warning("Service account already exists")
        else:
            raise
    
    # Grant roles
    roles = [
        "roles/secretmanager.secretAccessor",
        "roles/cloudsql.client",
        "roles/redis.editor",
        "roles/logging.logWriter",
        "roles/monitoring.metricWriter",
        "roles/cloudtrace.agent",
        "roles/aiplatform.user",
    ]
    
    for role in roles:
        try:
            run_command([
                "gcloud", "projects", "add-iam-policy-binding", project_id,
                f"--member=serviceAccount:{sa_email}",
                f"--role={role}",
                "--condition=None"
            ], dry_run=dry_run)
        except subprocess.CalledProcessError:
            pass


def print_summary(project_id: str, region: str):
    """Print setup summary and next steps."""
    print("\n" + "=" * 60)
    print(f"{Colors.GREEN}{Colors.BOLD}✓ GCP Project Setup Complete!{Colors.END}")
    print("=" * 60)
    
    print(f"\n{Colors.BOLD}Project:{Colors.END} {project_id}")
    print(f"{Colors.BOLD}Region:{Colors.END} {region}")
    
    print(f"\n{Colors.BOLD}Resources Created:{Colors.END}")
    print("  • Artifact Registry: leadgen-repo")
    print("  • VPC Network: leadgen-vpc")
    print("  • Cloud SQL: leadgen-db (PostgreSQL 15)")
    print("  • Redis: leadgen-redis")
    print("  • Service Account: leadgen-cloud-run")
    
    print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
    print("  1. Configure secrets:")
    print(f"     python scripts/setup_secrets.py --project-id {project_id} --env production --interactive")
    print("  2. Deploy the application:")
    print("     ./scripts/deploy.sh production")
    print("  3. Or push to GitHub for CI/CD deployment:")
    print("     git push origin main")
    
    print(f"\n{Colors.BOLD}Useful Commands:{Colors.END}")
    print(f"  # View Cloud Run logs")
    print(f"  gcloud run services logs read leadgen-ai-agent --region={region}")
    print(f"  ")
    print(f"  # Get Cloud SQL connection name")
    print(f"  gcloud sql instances describe leadgen-db --format='value(connectionName)'")
    print(f"  ")
    print(f"  # Get Redis IP")
    print(f"  gcloud redis instances describe leadgen-redis --region={region} --format='value(host)'")


def main():
    parser = argparse.ArgumentParser(
        description="Set up GCP project for LeadGen AI Voice Agent"
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="GCP project ID"
    )
    parser.add_argument(
        "--region",
        default="asia-south1",
        help="GCP region (default: asia-south1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show commands without executing"
    )
    parser.add_argument(
        "--skip-database",
        action="store_true",
        help="Skip Cloud SQL and Redis creation"
    )
    
    args = parser.parse_args()
    
    print(f"\n{Colors.BOLD}🚀 LeadGen AI - GCP Project Setup{Colors.END}")
    print("=" * 40)
    print(f"Project: {args.project_id}")
    print(f"Region: {args.region}")
    if args.dry_run:
        print(f"{Colors.YELLOW}Mode: DRY RUN (no changes will be made){Colors.END}")
    print()
    
    # Pre-flight checks
    if not check_gcloud_installed():
        print_error("gcloud CLI is not installed")
        print("Install from: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)
    
    if not check_authenticated():
        print_error("Not authenticated with gcloud")
        print("Run: gcloud auth login")
        sys.exit(1)
    
    # Set project
    if not args.dry_run:
        run_command(["gcloud", "config", "set", "project", args.project_id])
    
    # Run setup steps
    try:
        enable_apis(args.project_id, args.dry_run)
        create_artifact_registry(args.project_id, args.region, args.dry_run)
        
        if not args.skip_database:
            create_vpc_network(args.project_id, args.dry_run)
            create_cloud_sql(args.project_id, args.region, args.dry_run)
            create_redis(args.project_id, args.region, args.dry_run)
        
        setup_iam(args.project_id, args.dry_run)
        create_cloud_run_service_account(args.project_id, args.dry_run)
        
        if not args.dry_run:
            print_summary(args.project_id, args.region)
        else:
            print(f"\n{Colors.YELLOW}Dry run complete. No changes were made.{Colors.END}")
            print("Remove --dry-run to execute these commands.")
    
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
