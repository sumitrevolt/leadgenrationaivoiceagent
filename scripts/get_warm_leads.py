import asyncio
import json
from sqlalchemy import select
from app.models.base import get_async_session
from app.models.lead import Lead

async def get_warm_leads():
    async with get_async_session() as session:
        # High lead score or hot leads or contacted/qualified status
        q = (
            select(Lead)
            .where(
                (Lead.email.isnot(None)) & (Lead.email != "")
            )
            .order_by(Lead.lead_score.desc())
            .limit(10)
        )
        leads = (await session.execute(q)).scalars().all()
        
        result = []
        for l in leads:
            result.append({
                "company": l.company_name,
                "contact": l.contact_name,
                "email": l.email,
                "score": l.lead_score,
                "status": l.status.value if l.status else None,
                "notes": l.notes,
                "qualification": l.qualification_data
            })
            
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(get_warm_leads())