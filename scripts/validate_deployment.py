#!/usr/bin/env python3
"""
Pre-Deployment Validation Script

Validates that all requirements are met before deploying to production.
Run this script before every production deployment.

Usage:
    python scripts/validate_deployment.py
    python scripts/validate_deployment.py --env production --strict

Exit codes:
    0 - All checks passed
    1 - Critical checks failed (do not deploy)
    2 - Warning checks failed (review before deploying)
"""

import argparse
import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Tuple, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class CheckStatus(Enum):
    PASS = "✅"
    WARN = "⚠️"
    FAIL = "❌"
    SKIP = "⏭️"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None


@dataclass
class ValidationReport:
    checks: List[CheckResult] = field(default_factory=list)
    
    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)
    
    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)
    
    @property
    def failures(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)
    
    @property
    def skipped(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.SKIP)
    
    def add(self, result: CheckResult):
        self.checks.append(result)
    
    def print_report(self):
        print("\n" + "=" * 70)
        print("  Pre-Deployment Validation Report")
        print("=" * 70 + "\n")
        
        for check in self.checks:
            print(f"{check.status.value} {check.name}")
            print(f"   {check.message}")
            if check.details:
                for line in check.details.split("\n"):
                    print(f"   {line}")
            print()
        
        print("=" * 70)
        print(f"  Results: {self.passed} passed, {self.warnings} warnings, "
              f"{self.failures} failed, {self.skipped} skipped")
        print("=" * 70)


def run_command(cmd: List[str], capture: bool = True) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=60,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def check_python_version(report: ValidationReport):
    """Check Python version is 3.11+."""
    import sys
    version = sys.version_info
    if version >= (3, 11):
        report.add(CheckResult(
            "Python Version",
            CheckStatus.PASS,
            f"Python {version.major}.{version.minor}.{version.micro}",
        ))
    elif version >= (3, 10):
        report.add(CheckResult(
            "Python Version",
            CheckStatus.WARN,
            f"Python {version.major}.{version.minor}.{version.micro} (3.11+ recommended)",
        ))
    else:
        report.add(CheckResult(
            "Python Version",
            CheckStatus.FAIL,
            f"Python {version.major}.{version.minor}.{version.micro} (3.11+ required)",
        ))


def check_dependencies(report: ValidationReport):
    """Check all required packages are installed."""
    try:
        import pkg_resources
        
        requirements_file = Path("requirements.txt")
        if not requirements_file.exists():
            report.add(CheckResult(
                "Dependencies",
                CheckStatus.FAIL,
                "requirements.txt not found",
            ))
            return
        
        with open(requirements_file) as f:
            requirements = [
                line.strip() for line in f 
                if line.strip() and not line.startswith("#")
            ]
        
        missing = []
        for req in requirements:
            try:
                # Parse requirement name (before any version specifier)
                name = req.split(">=")[0].split("==")[0].split("<")[0].split("[")[0].strip()
                pkg_resources.require(name)
            except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict) as e:
                missing.append(name)
        
        if missing:
            report.add(CheckResult(
                "Dependencies",
                CheckStatus.FAIL,
                f"Missing {len(missing)} packages",
                "Missing: " + ", ".join(missing[:5]) + ("..." if len(missing) > 5 else ""),
            ))
        else:
            report.add(CheckResult(
                "Dependencies",
                CheckStatus.PASS,
                f"All {len(requirements)} packages installed",
            ))
    except Exception as e:
        report.add(CheckResult(
            "Dependencies",
            CheckStatus.WARN,
            f"Could not verify: {e}",
        ))


def check_env_vars(report: ValidationReport, env: str):
    """Check required environment variables are set."""
    required_vars = [
        "SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    ]
    
    # At least one LLM required
    llm_vars = ["GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    
    # At least one telephony required
    telephony_vars = ["TWILIO_ACCOUNT_SID", "EXOTEL_API_KEY"]
    
    # Production-specific
    production_vars = ["SENTRY_DSN", "DEEPGRAM_API_KEY"]
    
    missing = []
    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)
    
    # Check LLM
    if not any(os.environ.get(v) for v in llm_vars):
        missing.append("(at least one LLM: GEMINI/OPENAI/ANTHROPIC)")
    
    # Check telephony
    if not any(os.environ.get(v) for v in telephony_vars):
        missing.append("(at least one telephony: TWILIO/EXOTEL)")
    
    # Production checks
    if env == "production":
        for var in production_vars:
            if not os.environ.get(var):
                missing.append(var)
        
        # Check DEBUG is false
        if os.environ.get("DEBUG", "").lower() in ("true", "1", "yes"):
            report.add(CheckResult(
                "Debug Mode",
                CheckStatus.FAIL,
                "DEBUG must be false in production",
            ))
        else:
            report.add(CheckResult(
                "Debug Mode",
                CheckStatus.PASS,
                "Debug mode disabled",
            ))
    
    if missing:
        report.add(CheckResult(
            "Environment Variables",
            CheckStatus.FAIL if env == "production" else CheckStatus.WARN,
            f"Missing {len(missing)} required variables",
            "Missing: " + ", ".join(missing[:5]),
        ))
    else:
        report.add(CheckResult(
            "Environment Variables",
            CheckStatus.PASS,
            "All required variables set",
        ))


def check_tests(report: ValidationReport, strict: bool):
    """Run test suite and check results."""
    code, stdout, stderr = run_command([
        sys.executable, "-m", "pytest", 
        "tests/test_production_ready.py",
        "-v", "--tb=short", "-q"
    ])
    
    if code == 0:
        # Count passed tests
        passed = stdout.count(" passed")
        report.add(CheckResult(
            "Production Tests",
            CheckStatus.PASS,
            f"All tests passed",
        ))
    elif code == 5:
        report.add(CheckResult(
            "Production Tests",
            CheckStatus.WARN,
            "No tests found or collected",
        ))
    else:
        report.add(CheckResult(
            "Production Tests",
            CheckStatus.FAIL if strict else CheckStatus.WARN,
            f"Tests failed (exit code {code})",
            (stderr or stdout)[:200] if stderr or stdout else None,
        ))


def check_docker(report: ValidationReport):
    """Check Docker configuration."""
    dockerfile = Path("Dockerfile.production")
    
    if not dockerfile.exists():
        report.add(CheckResult(
            "Dockerfile",
            CheckStatus.FAIL,
            "Dockerfile.production not found",
        ))
        return
    
    with open(dockerfile) as f:
        content = f.read()
    
    issues = []
    
    # Check for HEALTHCHECK
    if "HEALTHCHECK" not in content:
        issues.append("Missing HEALTHCHECK instruction")
    
    # Check for non-root user
    if "USER" not in content or "root" in content.lower():
        if "USER app" not in content and "USER nonroot" not in content:
            issues.append("Should run as non-root user")
    
    # Check for multi-stage build
    if content.count("FROM") < 2:
        issues.append("Consider multi-stage build for smaller image")
    
    if issues:
        report.add(CheckResult(
            "Dockerfile",
            CheckStatus.WARN,
            f"{len(issues)} suggestions",
            "\n".join(f"- {i}" for i in issues),
        ))
    else:
        report.add(CheckResult(
            "Dockerfile",
            CheckStatus.PASS,
            "Dockerfile.production looks good",
        ))


def check_migrations(report: ValidationReport):
    """Check database migrations are up to date."""
    # Check if alembic.ini exists
    if not Path("alembic.ini").exists():
        report.add(CheckResult(
            "Database Migrations",
            CheckStatus.SKIP,
            "alembic.ini not found",
        ))
        return
    
    # Check if there are pending migrations
    code, stdout, stderr = run_command([
        sys.executable, "-m", "alembic", "check"
    ])
    
    if "Target database is not up to date" in (stdout + stderr):
        report.add(CheckResult(
            "Database Migrations",
            CheckStatus.WARN,
            "Pending migrations detected",
            "Run: alembic upgrade head",
        ))
    elif code != 0:
        report.add(CheckResult(
            "Database Migrations",
            CheckStatus.SKIP,
            "Could not check migrations (database not accessible)",
        ))
    else:
        report.add(CheckResult(
            "Database Migrations",
            CheckStatus.PASS,
            "Migrations up to date",
        ))


def check_security(report: ValidationReport):
    """Check for security issues."""
    issues = []
    
    # Check for .env file in git
    code, stdout, stderr = run_command(["git", "ls-files", ".env"])
    if stdout.strip():
        issues.append(".env file is tracked in git!")
    
    # Check .gitignore
    gitignore = Path(".gitignore")
    if gitignore.exists():
        with open(gitignore) as f:
            content = f.read()
        if ".env" not in content:
            issues.append(".env not in .gitignore")
    else:
        issues.append(".gitignore file missing")
    
    # Check for hardcoded secrets in code
    secret_patterns = ["sk-", "AIza", "AKIA"]
    code, stdout, stderr = run_command([
        "git", "grep", "-l", "-E", "|".join(secret_patterns), "--", "*.py"
    ])
    if stdout.strip():
        issues.append(f"Potential hardcoded secrets in: {stdout.strip()[:100]}")
    
    if issues:
        report.add(CheckResult(
            "Security",
            CheckStatus.FAIL,
            f"{len(issues)} security issues",
            "\n".join(f"- {i}" for i in issues),
        ))
    else:
        report.add(CheckResult(
            "Security",
            CheckStatus.PASS,
            "No obvious security issues",
        ))


def check_terraform(report: ValidationReport):
    """Check Terraform configuration."""
    tf_dir = Path("infrastructure/terraform")
    
    if not tf_dir.exists():
        report.add(CheckResult(
            "Terraform",
            CheckStatus.SKIP,
            "Terraform directory not found",
        ))
        return
    
    # Check for terraform.tfstate in git
    code, stdout, stderr = run_command([
        "git", "ls-files", str(tf_dir / "*.tfstate")
    ])
    if stdout.strip():
        report.add(CheckResult(
            "Terraform",
            CheckStatus.FAIL,
            "terraform.tfstate tracked in git!",
            "State files contain sensitive data",
        ))
        return
    
    # Check for required modules
    required_modules = ["monitoring", "secrets", "cloud_run", "database"]
    modules_dir = tf_dir / "modules"
    
    if modules_dir.exists():
        existing_modules = [d.name for d in modules_dir.iterdir() if d.is_dir()]
        missing = [m for m in required_modules if m not in existing_modules]
        
        if missing:
            report.add(CheckResult(
                "Terraform",
                CheckStatus.WARN,
                f"Missing modules: {', '.join(missing)}",
            ))
        else:
            report.add(CheckResult(
                "Terraform",
                CheckStatus.PASS,
                "All required Terraform modules present",
            ))
    else:
        report.add(CheckResult(
            "Terraform",
            CheckStatus.WARN,
            "Terraform modules directory not found",
        ))


def check_documentation(report: ValidationReport):
    """Check required documentation exists."""
    required_docs = [
        ("README.md", "Project README"),
        ("PRODUCTION_CHECKLIST.md", "Production checklist"),
        ("infrastructure/DEPLOYMENT.md", "Deployment guide"),
    ]
    
    missing = []
    for path, name in required_docs:
        if not Path(path).exists():
            missing.append(name)
    
    if missing:
        report.add(CheckResult(
            "Documentation",
            CheckStatus.WARN,
            f"Missing: {', '.join(missing)}",
        ))
    else:
        report.add(CheckResult(
            "Documentation",
            CheckStatus.PASS,
            "All required documentation present",
        ))


def check_api_endpoints(report: ValidationReport):
    """Check critical API endpoints are defined."""
    # Check multiple files for required endpoints
    files_to_check = [
        Path("app/main.py"),
        Path("app/api/health.py"),
    ]
    
    all_content = ""
    for file_path in files_to_check:
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                all_content += f.read() + "\n"
    
    if not all_content:
        report.add(CheckResult(
            "API Endpoints",
            CheckStatus.FAIL,
            "No API files found",
        ))
        return
    
    required_endpoints = [
        ("/health", "Health check endpoint"),
        ("/metrics", "Metrics endpoint"),
    ]
    
    missing = []
    for endpoint, name in required_endpoints:
        if endpoint not in all_content:
            missing.append(name)
    
    if missing:
        report.add(CheckResult(
            "API Endpoints",
            CheckStatus.WARN,
            f"Missing endpoints: {', '.join(missing)}",
        ))
    else:
        report.add(CheckResult(
            "API Endpoints",
            CheckStatus.PASS,
            "Required endpoints configured",
        ))


def main():
    parser = argparse.ArgumentParser(
        description="Validate deployment requirements"
    )
    parser.add_argument(
        "--env",
        choices=["development", "staging", "production"],
        default=os.environ.get("APP_ENV", "development"),
        help="Target environment",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running tests",
    )
    
    args = parser.parse_args()
    
    print(f"\n🔍 Validating deployment for: {args.env}")
    print(f"   Strict mode: {'enabled' if args.strict else 'disabled'}\n")
    
    report = ValidationReport()
    
    # Run all checks
    check_python_version(report)
    check_dependencies(report)
    check_env_vars(report, args.env)
    
    if not args.skip_tests:
        check_tests(report, args.strict)
    
    check_docker(report)
    check_migrations(report)
    check_security(report)
    check_terraform(report)
    check_documentation(report)
    check_api_endpoints(report)
    
    # Print report
    report.print_report()
    
    # Determine exit code
    if report.failures > 0:
        print("\n❌ DEPLOYMENT BLOCKED: Critical issues found")
        sys.exit(1)
    elif report.warnings > 0 and args.strict:
        print("\n⚠️ DEPLOYMENT BLOCKED (strict mode): Warnings present")
        sys.exit(2)
    elif report.warnings > 0:
        print("\n⚠️ WARNINGS PRESENT: Review before deploying")
        sys.exit(0)
    else:
        print("\n✅ ALL CHECKS PASSED: Ready for deployment")
        sys.exit(0)


if __name__ == "__main__":
    main()
