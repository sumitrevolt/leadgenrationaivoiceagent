"""
Data Service Layer
Business logic for B2B Intelligence Platform data operations
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_credits import (
    CREDIT_COSTS,
    APIKey,
    APIUsageLog,
    APIUsageType,
    CreditTransaction,
    CreditTransactionType,
    DataCredits,
)
from app.models.lead import Lead
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class DataService:
    """Service for B2B data platform operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== COMPANY SEARCH ====================

    async def search_companies(
        self,
        client_id: str,
        niche: str | None = None,
        city: str | None = None,
        state: str | None = None,
        min_score: int | None = None,
        verified_only: bool = False,
        has_email: bool = False,
        has_phone: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Search companies in the database.
        Searches are FREE - credits consumed on export/enrichment only.
        """
        query = select(Lead)

        # Build filters
        filters = []
        if niche:
            filters.append(Lead.niche == niche)
        if city:
            filters.append(Lead.city.ilike(f"%{city}%"))
        if state:
            filters.append(Lead.state.ilike(f"%{state}%"))
        if min_score:
            filters.append(Lead.lead_score >= min_score)
        if verified_only:
            filters.append(Lead.verified)
        if has_email:
            filters.append(Lead.email.isnot(None))
        if has_phone:
            filters.append(Lead.phone.isnot(None))

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(Lead)
        if filters:
            count_query = count_query.where(and_(*filters))
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.order_by(Lead.lead_score.desc()).offset(offset).limit(limit)

        result = await self.db.execute(query)
        leads = result.scalars().all()

        # Convert to preview format (limited data without consuming credits)
        companies = [self._lead_to_preview(lead) for lead in leads]

        return companies, total

    def _lead_to_preview(self, lead: Lead) -> dict[str, Any]:
        """Convert lead to preview format (partial data - no credits)"""
        return {
            "id": lead.id,
            "company_name": lead.company_name,
            "city": lead.city,
            "state": lead.state,
            "niche": lead.niche,
            "category": lead.category,
            "lead_score": lead.lead_score,
            "verified": lead.verified,
            "has_email": bool(lead.email),
            "has_phone": bool(lead.phone),
            # Phone and email are masked - need credits to reveal
            "phone_masked": self._mask_phone(lead.phone) if lead.phone else None,
            "email_masked": self._mask_email(lead.email) if lead.email else None,
        }

    def _mask_phone(self, phone: str) -> str:
        """Mask phone number: +91 98765XXXXX"""
        if len(phone) > 5:
            return phone[:-5] + "XXXXX"
        return "XXXXX"

    def _mask_email(self, email: str) -> str:
        """Mask email: jo***@example.com"""
        if "@" in email:
            local, domain = email.split("@", 1)
            if len(local) > 2:
                return f"{local[:2]}***@{domain}"
        return "***@***.com"

    # ==================== COMPANY ENRICHMENT ====================

    async def enrich_company(
        self,
        client_id: str,
        company_id: str,
        api_key_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """
        Get full company details (consumes 2 credits).
        Returns (company_data, error_message)
        """
        # Check credits
        has_credits, credits_account = await self._check_and_deduct_credits(
            client_id, APIUsageType.COMPANY_ENRICH
        )
        if not has_credits:
            return None, "Insufficient credits"

        # Get company
        result = await self.db.execute(select(Lead).where(Lead.id == company_id))
        lead = result.scalar_one_or_none()

        if not lead:
            # Refund credits
            await self._refund_credits(client_id, CREDIT_COSTS[APIUsageType.COMPANY_ENRICH])
            return None, "Company not found"

        # Log usage
        await self._log_usage(
            client_id=client_id,
            api_key_id=api_key_id,
            usage_type=APIUsageType.COMPANY_ENRICH,
            credits=CREDIT_COSTS[APIUsageType.COMPANY_ENRICH],
            endpoint="/data/companies/{id}/enrich",
            result_count=1,
        )

        # Return full data
        company = self._lead_to_full(lead)
        return company, ""

    def _lead_to_full(self, lead: Lead) -> dict[str, Any]:
        """Convert lead to full format (all data)"""
        return {
            "id": lead.id,
            "company_name": lead.company_name,
            "website": lead.website,
            "industry": lead.industry,
            "employee_count": lead.employee_count,
            "contact_name": lead.contact_name,
            "phone": lead.phone,  # Full phone
            "email": lead.email,  # Full email
            "designation": lead.designation,
            "address": lead.address,
            "city": lead.city,
            "state": lead.state,
            "country": lead.country,
            "pincode": lead.pincode,
            "category": lead.category,
            "niche": lead.niche,
            "lead_score": lead.lead_score,
            "verified": lead.verified,
            "phone_verified": lead.phone_verified,
            "email_verified": lead.email_verified,
            "source": lead.source.value if lead.source else None,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        }

    # ==================== BULK EXPORT ====================

    async def export_companies(
        self,
        client_id: str,
        company_ids: list[str],
        api_key_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Export multiple companies (1 credit per company).
        Returns (companies, error_message)
        """
        credits_needed = len(company_ids) * CREDIT_COSTS[APIUsageType.COMPANY_EXPORT]

        # Check credits
        credits_account = await self._get_credits_account(client_id)
        if not credits_account or not credits_account.has_credits(credits_needed):
            return (
                [],
                f"Insufficient credits. Need {credits_needed}, have {credits_account.balance if credits_account else 0}",
            )

        # Get companies
        result = await self.db.execute(select(Lead).where(Lead.id.in_(company_ids)))
        leads = result.scalars().all()

        if not leads:
            return [], "No companies found"

        # Deduct credits for actual found companies
        actual_credits = len(leads) * CREDIT_COSTS[APIUsageType.COMPANY_EXPORT]
        credits_account.deduct(actual_credits)

        # Log transaction
        await self._log_credit_transaction(
            client_id=client_id,
            credit_account_id=credits_account.id,
            tx_type=CreditTransactionType.USAGE,
            amount=-actual_credits,
            balance_after=credits_account.balance,
            description=f"Exported {len(leads)} companies",
            usage_type=APIUsageType.COMPANY_EXPORT,
        )

        # Log usage
        await self._log_usage(
            client_id=client_id,
            api_key_id=api_key_id,
            usage_type=APIUsageType.COMPANY_EXPORT,
            credits=actual_credits,
            endpoint="/data/companies/export",
            result_count=len(leads),
        )

        await self.db.commit()

        companies = [self._lead_to_full(lead) for lead in leads]
        return companies, ""

    # ==================== MARKET REPORTS ====================

    async def generate_report(
        self,
        client_id: str,
        report_type: str,  # "basic", "detailed", "custom"
        niche: str,
        city: str | None = None,
        api_key_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """
        Generate market intelligence report.
        """
        # Map report type to usage type
        type_map = {
            "basic": APIUsageType.REPORT_BASIC,
            "detailed": APIUsageType.REPORT_DETAILED,
            "custom": APIUsageType.REPORT_CUSTOM,
        }
        usage_type = type_map.get(report_type, APIUsageType.REPORT_BASIC)

        # Check credits
        has_credits, credits_account = await self._check_and_deduct_credits(client_id, usage_type)
        if not has_credits:
            return None, f"Insufficient credits. Need {CREDIT_COSTS[usage_type]}"

        # Generate report
        report = await self._generate_market_report(niche, city, report_type)

        # Log usage
        await self._log_usage(
            client_id=client_id,
            api_key_id=api_key_id,
            usage_type=usage_type,
            credits=CREDIT_COSTS[usage_type],
            endpoint="/data/reports",
            result_count=1,
        )

        await self.db.commit()

        return report, ""

    async def _generate_market_report(
        self, niche: str, city: str | None, report_type: str
    ) -> dict[str, Any]:
        """Generate market intelligence report using aggregated data"""
        # Build query
        filters = [Lead.niche == niche]
        if city:
            filters.append(Lead.city.ilike(f"%{city}%"))

        # Get statistics
        query = select(
            func.count(Lead.id).label("total_companies"),
            func.avg(Lead.lead_score).label("avg_score"),
            func.count(Lead.id).filter(Lead.verified).label("verified_count"),
            func.count(Lead.id).filter(Lead.email.isnot(None)).label("with_email"),
            func.count(Lead.id).filter(Lead.phone.isnot(None)).label("with_phone"),
        ).where(and_(*filters))

        result = await self.db.execute(query)
        stats = result.one()

        # Get city breakdown
        city_query = (
            select(Lead.city, func.count(Lead.id).label("count"))
            .where(Lead.niche == niche)
            .group_by(Lead.city)
            .order_by(func.count(Lead.id).desc())
            .limit(10)
        )

        city_result = await self.db.execute(city_query)
        cities = [{"city": row.city, "count": row.count} for row in city_result]

        # Get score distribution
        score_query = select(
            func.count(Lead.id).filter(Lead.lead_score >= 70).label("high"),
            func.count(Lead.id)
            .filter(and_(Lead.lead_score >= 40, Lead.lead_score < 70))
            .label("medium"),
            func.count(Lead.id).filter(Lead.lead_score < 40).label("low"),
        ).where(and_(*filters))

        score_result = await self.db.execute(score_query)
        scores = score_result.one()

        report = {
            "report_type": report_type,
            "niche": niche,
            "city": city,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_companies": stats.total_companies,
                "avg_quality_score": round(float(stats.avg_score or 0), 1),
                "verified_percentage": round(
                    (
                        (stats.verified_count / stats.total_companies * 100)
                        if stats.total_companies
                        else 0
                    ),
                    1,
                ),
                "with_email_percentage": round(
                    (
                        (stats.with_email / stats.total_companies * 100)
                        if stats.total_companies
                        else 0
                    ),
                    1,
                ),
                "with_phone_percentage": round(
                    (
                        (stats.with_phone / stats.total_companies * 100)
                        if stats.total_companies
                        else 0
                    ),
                    1,
                ),
            },
            "quality_distribution": {
                "high_quality": scores.high,
                "medium_quality": scores.medium,
                "low_quality": scores.low,
            },
            "top_cities": cities,
        }

        if report_type in ["detailed", "custom"]:
            # Add more detailed insights for premium reports
            top_companies_query = (
                select(Lead).where(and_(*filters)).order_by(Lead.lead_score.desc()).limit(20)
            )

            top_result = await self.db.execute(top_companies_query)
            top_companies = [self._lead_to_preview(l) for l in top_result.scalars()]
            report["top_companies"] = top_companies

        return report

    # ==================== API KEY MANAGEMENT ====================

    async def create_api_key(
        self,
        client_id: str,
        name: str,
        scopes: list[str] = None,
        rate_limit_per_minute: int = 60,
        expires_in_days: int | None = None,
    ) -> tuple[str, APIKey]:
        """Create a new API key. Returns (raw_key, api_key_model)"""
        # Generate secure key
        if scopes is None:
            scopes = ["read"]
        raw_key = f"ldg_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]

        api_key = APIKey(
            id=str(uuid.uuid4()),
            client_id=client_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=json.dumps(scopes),
            rate_limit_per_minute=rate_limit_per_minute,
            expires_at=(
                datetime.utcnow() + timedelta(days=expires_in_days) if expires_in_days else None
            ),
        )

        self.db.add(api_key)
        await self.db.commit()

        return raw_key, api_key

    async def validate_api_key(self, raw_key: str) -> APIKey | None:
        """Validate API key and return the key model if valid"""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.key_hash == key_hash,
                    APIKey.is_active == 1,
                    or_(APIKey.expires_at.is_(None), APIKey.expires_at > datetime.utcnow()),
                )
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key:
            api_key.last_used_at = datetime.utcnow()
            await self.db.commit()

        return api_key

    async def list_api_keys(self, client_id: str) -> list[dict[str, Any]]:
        """List all API keys for a client"""
        result = await self.db.execute(select(APIKey).where(APIKey.client_id == client_id))
        keys = result.scalars().all()

        return [
            {
                "id": k.id,
                "name": k.name,
                "prefix": k.key_prefix,
                "scopes": json.loads(k.scopes) if k.scopes else [],
                "is_active": bool(k.is_active),
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ]

    async def revoke_api_key(self, client_id: str, key_id: str) -> bool:
        """Revoke an API key"""
        result = await self.db.execute(
            select(APIKey).where(and_(APIKey.id == key_id, APIKey.client_id == client_id))
        )
        api_key = result.scalar_one_or_none()

        if api_key:
            api_key.is_active = 0
            await self.db.commit()
            return True
        return False

    # ==================== CREDIT MANAGEMENT ====================

    async def _get_credits_account(self, client_id: str) -> DataCredits | None:
        """Get or create credits account for client"""
        result = await self.db.execute(
            select(DataCredits).where(DataCredits.client_id == client_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            # Create new account with starter credits
            account = DataCredits(
                id=str(uuid.uuid4()),
                client_id=client_id,
                balance=100,  # Free starter credits
                lifetime_credits=100,
            )
            self.db.add(account)
            await self.db.commit()

        return account

    async def _check_and_deduct_credits(
        self, client_id: str, usage_type: APIUsageType
    ) -> tuple[bool, DataCredits | None]:
        """Check if client has credits and deduct if so"""
        credits_needed = CREDIT_COSTS[usage_type]
        account = await self._get_credits_account(client_id)

        if not account or not account.has_credits(credits_needed):
            return False, account

        account.deduct(credits_needed)

        # Log transaction
        await self._log_credit_transaction(
            client_id=client_id,
            credit_account_id=account.id,
            tx_type=CreditTransactionType.USAGE,
            amount=-credits_needed,
            balance_after=account.balance,
            description=f"Used for {usage_type.value}",
            usage_type=usage_type,
        )

        return True, account

    async def _refund_credits(self, client_id: str, amount: int) -> None:
        """Refund credits to client"""
        account = await self._get_credits_account(client_id)
        if account:
            account.balance += amount
            await self._log_credit_transaction(
                client_id=client_id,
                credit_account_id=account.id,
                tx_type=CreditTransactionType.REFUND,
                amount=amount,
                balance_after=account.balance,
                description="Refund for failed operation",
            )

    async def add_credits(
        self,
        client_id: str,
        amount: int,
        tx_type: CreditTransactionType = CreditTransactionType.PURCHASE,
        description: str = "",
        reference_id: str | None = None,
    ) -> DataCredits:
        """Add credits to client account"""
        account = await self._get_credits_account(client_id)
        account.add(amount)

        await self._log_credit_transaction(
            client_id=client_id,
            credit_account_id=account.id,
            tx_type=tx_type,
            amount=amount,
            balance_after=account.balance,
            description=description,
            reference_id=reference_id,
        )

        await self.db.commit()
        return account

    async def get_credit_balance(self, client_id: str) -> dict[str, Any]:
        """Get credit balance summary"""
        account = await self._get_credits_account(client_id)

        return {
            "balance": account.balance,
            "lifetime_credits": account.lifetime_credits,
            "used_credits": account.used_credits,
            "monthly_limit": account.monthly_limit,
            "monthly_used": account.monthly_used,
            "last_used_at": account.last_used_at.isoformat() if account.last_used_at else None,
        }

    async def _log_credit_transaction(
        self,
        client_id: str,
        credit_account_id: str,
        tx_type: CreditTransactionType,
        amount: int,
        balance_after: int,
        description: str = "",
        reference_id: str | None = None,
        usage_type: APIUsageType | None = None,
    ) -> None:
        """Log a credit transaction"""
        tx = CreditTransaction(
            id=str(uuid.uuid4()),
            credit_account_id=credit_account_id,
            client_id=client_id,
            transaction_type=tx_type,
            amount=amount,
            balance_after=balance_after,
            description=description,
            reference_id=reference_id,
            usage_type=usage_type,
        )
        self.db.add(tx)

    async def _log_usage(
        self,
        client_id: str,
        usage_type: APIUsageType,
        credits: int,
        endpoint: str,
        result_count: int,
        api_key_id: str | None = None,
        query_params: dict | None = None,
        response_time_ms: int | None = None,
    ) -> None:
        """Log API usage"""
        log = APIUsageLog(
            id=str(uuid.uuid4()),
            client_id=client_id,
            api_key_id=api_key_id,
            usage_type=usage_type,
            credits_consumed=credits,
            endpoint=endpoint,
            query_params=json.dumps(query_params) if query_params else None,
            result_count=result_count,
            response_time_ms=response_time_ms,
        )
        self.db.add(log)

    # ==================== ANALYTICS ====================

    async def get_usage_stats(self, client_id: str, days: int = 30) -> dict[str, Any]:
        """Get usage statistics for a client"""
        since = datetime.utcnow() - timedelta(days=days)

        # Get usage by type
        usage_query = (
            select(
                APIUsageLog.usage_type,
                func.count(APIUsageLog.id).label("count"),
                func.sum(APIUsageLog.credits_consumed).label("credits"),
            )
            .where(and_(APIUsageLog.client_id == client_id, APIUsageLog.created_at >= since))
            .group_by(APIUsageLog.usage_type)
        )

        result = await self.db.execute(usage_query)
        usage_by_type = {
            row.usage_type.value: {"count": row.count, "credits": row.credits} for row in result
        }

        # Get daily usage
        daily_query = (
            select(
                func.date(APIUsageLog.created_at).label("date"),
                func.sum(APIUsageLog.credits_consumed).label("credits"),
            )
            .where(and_(APIUsageLog.client_id == client_id, APIUsageLog.created_at >= since))
            .group_by(func.date(APIUsageLog.created_at))
        )

        daily_result = await self.db.execute(daily_query)
        daily_usage = [{"date": str(row.date), "credits": row.credits} for row in daily_result]

        return {
            "period_days": days,
            "usage_by_type": usage_by_type,
            "daily_usage": daily_usage,
        }
