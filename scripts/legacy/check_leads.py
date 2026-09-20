from app.models.base import get_db_session
from app.models.lead import Lead
from sqlalchemy import func, or_

with get_db_session() as db:
    total_with_phone = db.query(Lead).filter(Lead.phone.isnot(None), Lead.phone != "").count()
    uncontacted = db.query(Lead).filter(
        Lead.phone.isnot(None), Lead.phone != ""
    ).filter(or_(Lead.call_attempts.is_(None), Lead.call_attempts == 0)).count()
    with_score = db.query(Lead).filter(Lead.lead_score.isnot(None), Lead.lead_score > 0).count()
    by_niche = db.query(Lead.niche, func.count()).group_by(Lead.niche).all()

    print(f"=== LEADS ANALYSIS ===")
    print(f"Total leads with phone: {total_with_phone}")
    print(f"Uncontacted (0 attempts): {uncontacted}")
    print(f"With lead_score: {with_score}")
    print(f"\nBy niche:")
    for niche, count in by_niche:
        print(f"  {niche or 'None'}: {count}")

    top_leads = db.query(Lead).filter(
        Lead.phone.isnot(None), Lead.phone != ""
    ).filter(or_(Lead.call_attempts.is_(None), Lead.call_attempts == 0)) \
        .order_by(Lead.lead_score.desc()).limit(10).all()

    print(f"\nTop 10 uncontacted leads by score:")
    for l in top_leads:
        print(f"  {l.phone} | score={l.lead_score} | niche={l.niche} | attempts={l.call_attempts}")
