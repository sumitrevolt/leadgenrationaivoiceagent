import uuid
from datetime import datetime

from sqlalchemy import inspect, text

from app.models.base import _get_sync_engine, get_db_session
from app.models.lead import Lead, LeadSource, LeadStatus

# Ensure engine is initialized
engine = _get_sync_engine()
insp = inspect(engine)
print("leads table exists:", 'leads' in insp.get_table_names())

# Try inserting a lead directly
try:
    with get_db_session() as session:
        lead = Lead(
            id=str(uuid.uuid4()),
            company_name="Test Biz",
            phone="919876543210",
            email=None,
            address="Test Addr",
            city="Pune",
            status=LeadStatus.NEW,
            source=LeadSource.GOOGLE_MAPS,
        )
        session.add(lead)
        session.commit()
        print("INSERTED OK")
        print("Leads count:", session.query(Lead).count())
except Exception as e:
    print("DB ERROR:", repr(e))
