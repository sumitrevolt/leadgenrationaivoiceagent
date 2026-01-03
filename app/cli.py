"""
LeadGen AI Voice Agent - Command Line Interface
"""
import argparse
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """Main CLI entrypoint"""
    parser = argparse.ArgumentParser(
        prog="leadgen",
        description="LeadGen AI Voice Agent - B2B Lead Generation Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  leadgen server              Start the API server
  leadgen server --port 8080  Start on custom port
  leadgen platform start      Start the automation platform
  leadgen platform status     Check platform status
  leadgen db upgrade          Run database migrations
  leadgen test                Run test suite
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start the API server")
    server_parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    server_parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    
    # Platform commands
    platform_parser = subparsers.add_parser("platform", help="Platform management")
    platform_subparsers = platform_parser.add_subparsers(dest="platform_command")
    platform_subparsers.add_parser("start", help="Start the automation platform")
    platform_subparsers.add_parser("stop", help="Stop the automation platform")
    platform_subparsers.add_parser("status", help="Check platform status")
    platform_subparsers.add_parser("stats", help="Show platform statistics")
    
    # Database commands
    db_parser = subparsers.add_parser("db", help="Database management")
    db_subparsers = db_parser.add_subparsers(dest="db_command")
    db_subparsers.add_parser("upgrade", help="Run database migrations")
    db_subparsers.add_parser("downgrade", help="Rollback last migration")
    db_subparsers.add_parser("reset", help="Reset database (WARNING: destructive)")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run tests")
    test_parser.add_argument("--coverage", action="store_true", help="Run with coverage")
    test_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    # Version command
    subparsers.add_parser("version", help="Show version")
    
    # Health check
    subparsers.add_parser("health", help="Check system health")
    
    args = parser.parse_args()
    
    if args.command == "server":
        run_server(args)
    elif args.command == "platform":
        run_platform_command(args)
    elif args.command == "db":
        run_db_command(args)
    elif args.command == "test":
        run_tests(args)
    elif args.command == "version":
        show_version()
    elif args.command == "health":
        asyncio.run(check_health())
    else:
        parser.print_help()


def run_server(args):
    """Start the API server"""
    import uvicorn
    
    print(f"?? Starting LeadGen AI Voice Agent on {args.host}:{args.port}")
    
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
    )


def run_platform_command(args):
    """Handle platform commands"""
    import httpx
    
    base_url = os.environ.get("LEADGEN_API_URL", "http://localhost:8000")
    
    if args.platform_command == "start":
        print("?? Starting automation platform...")
        try:
            response = httpx.post(f"{base_url}/api/platform/start", timeout=30)
            if response.status_code == 200:
                print("? Platform started successfully")
            else:
                print(f"? Failed to start: {response.text}")
        except httpx.ConnectError:
            print("? Cannot connect to API server. Is it running?")
    
    elif args.platform_command == "stop":
        print("?? Stopping automation platform...")
        try:
            response = httpx.post(f"{base_url}/api/platform/stop", timeout=30)
            if response.status_code == 200:
                print("? Platform stopped")
            else:
                print(f"? Failed to stop: {response.text}")
        except httpx.ConnectError:
            print("? Cannot connect to API server")
    
    elif args.platform_command == "status":
        try:
            response = httpx.get(f"{base_url}/api/platform/status", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"?? Platform Status: {data.get('status', 'unknown')}")
                print(f"   Running: {data.get('is_running', False)}")
                print(f"   Mode: {data.get('mode', 'unknown')}")
            else:
                print(f"? Error: {response.text}")
        except httpx.ConnectError:
            print("? Cannot connect to API server")
    
    elif args.platform_command == "stats":
        try:
            response = httpx.get(f"{base_url}/api/platform/stats", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print("?? Platform Statistics:")
                print(f"   Total Tenants: {data.get('total_tenants', 0)}")
                print(f"   Active Tenants: {data.get('active_tenants', 0)}")
                print(f"   Total Calls Made: {data.get('total_calls_made', 0)}")
                print(f"   Total Leads Generated: {data.get('total_leads_generated', 0)}")
            else:
                print(f"? Error: {response.text}")
        except httpx.ConnectError:
            print("? Cannot connect to API server")
    else:
        print("Unknown platform command. Use: start, stop, status, stats")


def run_db_command(args):
    """Handle database commands"""
    import subprocess
    
    if args.db_command == "upgrade":
        print("?? Running database migrations...")
        result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
        print(result.stdout)
        if result.returncode == 0:
            print("? Migrations complete")
        else:
            print(f"? Migration failed: {result.stderr}")
    
    elif args.db_command == "downgrade":
        print("?? Rolling back last migration...")
        result = subprocess.run(["alembic", "downgrade", "-1"], capture_output=True, text=True)
        print(result.stdout)
        if result.returncode == 0:
            print("? Rollback complete")
        else:
            print(f"? Rollback failed: {result.stderr}")
    
    elif args.db_command == "reset":
        confirm = input("?? This will DELETE all data. Type 'yes' to confirm: ")
        if confirm.lower() == "yes":
            print("??? Resetting database...")
            subprocess.run(["alembic", "downgrade", "base"])
            subprocess.run(["alembic", "upgrade", "head"])
            print("? Database reset complete")
        else:
            print("? Cancelled")
    else:
        print("Unknown db command. Use: upgrade, downgrade, reset")


def run_tests(args):
    """Run test suite"""
    import subprocess
    
    cmd = ["python", "-m", "pytest", "tests/"]
    
    if args.verbose:
        cmd.append("-v")
    
    if args.coverage:
        cmd.extend(["--cov=app", "--cov-report=term-missing"])
    
    print("?? Running tests...")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def show_version():
    """Show version information"""
    print("LeadGen AI Voice Agent")
    print("Version: 1.0.0")
    print("Python: " + sys.version.split()[0])
    print("Repository: https://github.com/sumitrevolt/leadgenrationaivoiceagent")


async def check_health():
    """Check system health"""
    import httpx
    
    print("?? Checking system health...\n")
    
    checks = {
        "API Server": "http://localhost:8000/health",
        "Platform": "http://localhost:8000/api/platform/status",
    }
    
    async with httpx.AsyncClient(timeout=5) as client:
        for name, url in checks.items():
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    print(f"? {name}: Healthy")
                else:
                    print(f"?? {name}: Unhealthy (HTTP {response.status_code})")
            except httpx.ConnectError:
                print(f"? {name}: Not reachable")
            except Exception as e:
                print(f"? {name}: Error - {e}")
    
    # Check Redis
    try:
        import redis
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        print("? Redis: Connected")
    except Exception:
        print("?? Redis: Not available (using in-memory fallback)")
    
    # Check Database
    try:
        from app.config import settings
        print(f"?? Database URL: {'Configured' if 'postgresql' in settings.database_url else 'SQLite/Default'}")
    except Exception:
        print("?? Database: Configuration not loaded")
    
    print("\n? Health check complete")


if __name__ == "__main__":
    main()
