from app.models.base import get_db_session, _get_sync_engine
from app.models.lead import Lead

engine = _get_sync_engine()
with get_db_session() as session:
    print('Total leads:', session.query(Lead).count())
    for lead in session.query(Lead).all()[:10]:
        print(f"  - {lead.company_name} | {lead.phone} | {lead.niche} | {lead.status}")