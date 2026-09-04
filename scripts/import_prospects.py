import json
import codecs
import uuid
from app.models.base import get_db_session, _get_sync_engine
from app.models.lead import Lead, LeadSource, LeadStatus, lead_exists_for_phone

engine = _get_sync_engine()

with get_db_session() as session:
    f = codecs.open(r'C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\data\prospects.jsonl', 'r', 'utf-8')
    for line in f:
        rec = json.loads(line)
        phone = rec.get('phone', '')
        phone10 = ''.join(c for c in phone if c.isdigit())
        if phone10.startswith('91') and len(phone10) == 12:
            phone10 = phone10[2:]
        elif phone10.startswith('0') and len(phone10) == 11:
            phone10 = phone10[1:]
        
        if len(phone10) != 10:
            continue
            
        if lead_exists_for_phone(session, phone10):
            bname = rec['business_name']
            print(f'SKIP DUP: {bname}')
            continue
            
        lead = Lead(
            id=rec.get('id', str(uuid.uuid4())),
            company_name=rec['business_name'][:255],
            phone=phone10,
            email=rec.get('email', None),
            address=rec.get('address', None),
            city=rec.get('city', None),
            status=LeadStatus.NEW,
            source=LeadSource.GOOGLE_MAPS,
            niche=rec.get('niche', 'restaurant'),
            website=rec.get('website', None),
        )
        session.add(lead)
        session.commit()
        bname = rec['business_name']
        print(f'INSERTED: {bname}')
    
    from sqlalchemy import func
    count = session.query(func.count()).select_from(Lead).scalar()
    print(f'TOTAL LEADS IN DB: {count}')