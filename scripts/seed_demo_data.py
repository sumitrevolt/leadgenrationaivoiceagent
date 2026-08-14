"""
Seed Demo Data
==============
Creates all tables (via Base.metadata.create_all on the SYNC engine) and inserts
realistic demo data so the customer + admin dashboards render real numbers:

    ~10 client companies, ~6 agents, ~8 campaigns, ~40 call logs, ~26 leads,
    plus billing records (MRR + telephony cost) for the admin revenue/cost charts.

Niches: solar / dental / real-estate. Indian cities. Amounts in INR (paise).

Idempotent-ish: if clients already exist, the script skips inserting and just
prints the current counts. Use --force to wipe-and-reseed the demo rows.

Run:
    # uses DATABASE_URL from .env / app.config (Postgres by default)
    python -m scripts.seed_demo_data

    # quick local run against a throwaway sqlite file:
    #   PowerShell:  $env:DATABASE_URL="sqlite:///demo.db"; python -m scripts.seed_demo_data
    #   bash:        DATABASE_URL="sqlite:///demo.db" python -m scripts.seed_demo_data

    # force a re-seed of demo rows:
    python -m scripts.seed_demo_data --force
"""

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, time, timedelta

# Make "app" importable when run directly (python scripts/seed_demo_data.py)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


RNG = random.Random(2026)


def _uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Demo reference data                                                          #
# --------------------------------------------------------------------------- #
CITIES = ["Mumbai", "Pune", "Delhi", "Bangalore", "Hyderabad", "Ahmedabad", "Chennai"]

NICHES = ["solar", "dental", "real-estate"]

BUSINESSES = {
    "solar": [
        "Sharma Solar Solutions",
        "SunVolt Energy",
        "GreenRay Solar",
        "Aditya Solar Power",
        "EcoSun Systems",
        "Surya Renewables",
        "BrightWatt Solar",
        "Tejas Solar Hub",
    ],
    "dental": [
        "Smile Care Dental",
        "Dr. Mehta Dental Clinic",
        "Perfect Smile Studio",
        "DentaWorld Clinic",
        "City Dental Care",
        "Bright Dental Hub",
        "Oral Health Centre",
        "Pearl Dental Clinic",
    ],
    "real-estate": [
        "Gokhale Realty",
        "Prime Properties",
        "Skyline Estates",
        "Urban Nest Realtors",
        "Capital Homes",
        "Greenfield Properties",
        "Metro Realty Group",
        "Anand Estate Agents",
    ],
}

CLIENT_COMPANIES = [
    ("SunVolt Solar Pvt Ltd", "solar"),
    ("Prestige Realty Group", "real-estate"),
    ("SmileCare Dental", "dental"),
    ("Aditya Solar Power", "solar"),
    ("Urban Nest Realtors", "real-estate"),
    ("Perfect Smile Studio", "dental"),
    ("GreenRay Solar", "solar"),
    ("Skyline Estates", "real-estate"),
    ("City Dental Care", "dental"),
    ("BrightWatt Solar", "solar"),
]

CONTACTS = [
    "Rajesh Sharma",
    "Priya Mehta",
    "Amit Gokhale",
    "Sneha Iyer",
    "Vikram Singh",
    "Pooja Nair",
    "Rahul Desai",
    "Anita Rao",
    "Suresh Patil",
    "Kavya Reddy",
    "Manish Joshi",
    "Neha Kulkarni",
]

AGENT_NAMES = ["Aarav", "Diya", "Kabir", "Anaya", "Vivaan", "Ishaan"]

PLAN_AMOUNTS_PAISE = {
    "starter": 1500000,  # Rs.15,000
    "growth": 2500000,  # Rs.25,000
    "enterprise": 3500000,
}


def _phone() -> str:
    return f"{RNG.randint(70, 99)}{RNG.randint(10000000, 99999999):08d}"[:10]


# --------------------------------------------------------------------------- #
# Seeding                                                                      #
# --------------------------------------------------------------------------- #
def seed(force: bool = False) -> int:
    # Import here so the module is import-safe even if deps are missing until run.
    from sqlalchemy.orm import sessionmaker

    from app.models import (
        Agent,
        AgentStatus,
        BillingRecord,
        BillingRecordStatus,
        BillingRecordType,
        CallDirection,
        CallLog,
        CallOutcome,
        Campaign,
        CampaignStatus,
        CampaignType,
        Client,
        ClientStatus,
        Lead,
        LeadSource,
        LeadStatus,
        SubscriptionPlan,
    )
    from app.models.base import Base, _get_sync_engine

    engine = _get_sync_engine()
    if engine is None:
        print("[!] Could not initialize the sync DB engine. Check DATABASE_URL / driver.")
        print("    Tip: for a quick local run set DATABASE_URL=sqlite:///demo.db")
        return 1

    print(f"[i] Using engine: {engine.url}")

    # Defensive: kuch model definitions me ek hi index do baar aa sakta hai
    # (column index=True + explicit Index) -> "index already exists" error.
    # create_all se pehle duplicate-named indexes metadata se hata do.
    for _table in Base.metadata.tables.values():
        _seen = set()
        for _idx in list(_table.indexes):
            if _idx.name in _seen:
                _table.indexes.discard(_idx)
            else:
                _seen.add(_idx.name)

    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("[+] Tables ensured (Base.metadata.create_all).")

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    try:
        existing_clients = db.query(Client).count()
        if existing_clients and not force:
            print(f"[=] Data already present ({existing_clients} clients). Skipping seed.")
            print("    Re-run with --force to wipe demo rows and reseed.")
            _print_summary(db, Client, Agent, Campaign, CallLog, Lead, BillingRecord)
            return 0

        if force and existing_clients:
            print(
                "[i] --force: deleting existing rows (call_logs, leads, billing, campaigns, agents, clients)..."
            )
            for model in (CallLog, Lead, BillingRecord, Campaign, Agent, Client):
                db.query(model).delete()
            db.commit()

        now = datetime.utcnow()

        # ----- clients (~10) -----
        clients = []
        for i, (company, niche) in enumerate(CLIENT_COMPANIES):
            plan = RNG.choice(
                [SubscriptionPlan.STARTER, SubscriptionPlan.GROWTH, SubscriptionPlan.ENTERPRISE]
            )
            status = (
                ClientStatus.ACTIVE
                if i % 4 != 0
                else RNG.choice([ClientStatus.ACTIVE, ClientStatus.PAUSED])
            )
            amount = PLAN_AMOUNTS_PAISE[plan.value]
            c = Client(
                id=_uid(),
                business_name=company,
                business_type="sme",
                industry=niche,
                contact_name=RNG.choice(CONTACTS),
                contact_email=f"contact{i}@{company.split()[0].lower()}.example.com",
                contact_phone=_phone(),
                city=RNG.choice(CITIES),
                state="Maharashtra",
                country="India",
                plan=plan,
                status=status,
                monthly_amount=amount,
                calls_this_month=RNG.randint(80, 600),
                leads_this_month=RNG.randint(20, 200),
                created_at=now - timedelta(days=RNG.randint(40, 240)),
            )
            db.add(c)
            clients.append(c)
        db.flush()
        print(f"[+] Inserted {len(clients)} clients.")

        # ----- agents (~6) -----
        agents = []
        statuses = [
            AgentStatus.CALLING,
            AgentStatus.CALLING,
            AgentStatus.SCRAPING,
            AgentStatus.IDLE,
            AgentStatus.CALLING,
            AgentStatus.ERROR,
        ]
        for i, name in enumerate(AGENT_NAMES):
            cl = RNG.choice(clients)
            a = Agent(
                id=_uid(),
                name=name,
                agent_code=f"AG-{i + 1:02d}",
                current_client_id=cl.id,
                current_client_name=cl.business_name,
                status=statuses[i % len(statuses)],
                niche=cl.industry,
                calls_made=RNG.randint(80, 360),
                leads_found=RNG.randint(12, 75),
                appointments_booked=RNG.randint(5, 40),
                talk_time_seconds=RNG.randint(3000, 40000),
                created_at=now - timedelta(days=RNG.randint(30, 120)),
                last_active_at=now - timedelta(minutes=RNG.randint(1, 240)),
            )
            db.add(a)
            agents.append(a)
        db.flush()
        print(f"[+] Inserted {len(agents)} agents.")

        # ----- campaigns (~8) -----
        campaigns = []
        for i in range(8):
            cl = clients[i % len(clients)]
            niche = cl.industry
            st = RNG.choices(
                [CampaignStatus.RUNNING, CampaignStatus.PAUSED, CampaignStatus.COMPLETED],
                weights=[60, 20, 20],
            )[0]
            target = RNG.randint(300, 1500)
            called = RNG.randint(100, target)
            qualified = int(called * RNG.uniform(0.08, 0.2))
            cp = Campaign(
                id=_uid(),
                name=f"{niche.title()} Drive {i + 1}",
                description=f"Outbound campaign for {cl.business_name}",
                type=CampaignType.COLD_OUTREACH,
                status=st,
                client_id=cl.id,
                client_name=cl.business_name,
                niche=niche,
                target_lead_count=target,
                script_language="hinglish",
                working_hours_start=time(10, 0),
                working_hours_end=time(18, 0),
                leads_scraped=target,
                leads_called=called,
                leads_connected=int(called * 0.6),
                leads_qualified=qualified,
                appointments_booked=int(qualified * 0.4),
                created_at=now - timedelta(days=RNG.randint(10, 90)),
            )
            db.add(cp)
            campaigns.append(cp)
        db.flush()
        print(f"[+] Inserted {len(campaigns)} campaigns.")

        # ----- leads (~26) -----
        leads = []
        for i in range(26):
            cl = RNG.choice(clients)
            niche = cl.industry if cl.industry in BUSINESSES else RNG.choice(NICHES)
            cp = RNG.choice([c for c in campaigns if c.client_id == cl.id] or campaigns)
            score = RNG.choices(
                [RNG.randint(70, 95), RNG.randint(40, 69), RNG.randint(0, 39)], weights=[34, 44, 22]
            )[0]
            status = RNG.choice(
                [
                    LeadStatus.NEW,
                    LeadStatus.CONTACTED,
                    LeadStatus.QUALIFIED,
                    LeadStatus.APPOINTMENT,
                    LeadStatus.CALLBACK,
                ]
            )
            lead = Lead(
                id=_uid(),
                company_name=RNG.choice(BUSINESSES[niche]),
                contact_name=RNG.choice(CONTACTS),
                phone=_phone(),
                email=f"lead{i}@example.com",
                city=RNG.choice(CITIES),
                state="Maharashtra",
                country="India",
                niche=niche,
                category=niche,
                lead_score=score,
                is_hot_lead=score >= 70,
                status=status,
                source=RNG.choice(
                    [
                        LeadSource.GOOGLE_MAPS,
                        LeadSource.JUSTDIAL,
                        LeadSource.INDIAMART,
                        LeadSource.LINKEDIN,
                    ]
                ),
                assigned_to=cl.id,
                campaign_id=cp.id,
                call_attempts=RNG.randint(1, 4),
                created_at=now - timedelta(days=RNG.randint(0, 12)),
            )
            lead.set_qualification_data(
                {
                    "interest_level": (
                        "high" if score >= 70 else ("medium" if score >= 40 else "low")
                    ),
                    "budget_range": RNG.choice(["Rs.50k-1L", "Rs.1L-3L", "Rs.3L+"]),
                    "timeline": RNG.choice(["this week", "this month", "next quarter"]),
                }
            )
            db.add(lead)
            leads.append(lead)
        db.flush()
        print(f"[+] Inserted {len(leads)} leads.")

        # ----- call logs (~40) -----
        outcomes_connected = [
            CallOutcome.APPOINTMENT,
            CallOutcome.CALLBACK,
            CallOutcome.INTERESTED,
            CallOutcome.NOT_INTERESTED,
        ]
        outcomes_missed = [CallOutcome.NO_ANSWER, CallOutcome.BUSY, CallOutcome.VOICEMAIL]
        n_calls = 0
        for i in range(40):
            lead = RNG.choice(leads)
            cp = RNG.choice([c for c in campaigns if c.id == lead.campaign_id] or campaigns)
            connected = RNG.random() < 0.62
            if connected:
                dur = RNG.randint(35, 230)
                outcome = RNG.choice(outcomes_connected)
                status = "completed"
            else:
                dur = 0
                outcome = RNG.choice(outcomes_missed)
                status = "failed"
            initiated = now - timedelta(days=RNG.randint(0, 6), minutes=RNG.randint(0, 600))
            log = CallLog(
                id=_uid(),
                call_sid=f"DEMO-{i:04d}",
                provider="demo",
                direction=CallDirection.OUTBOUND,
                lead_id=lead.id,
                campaign_id=cp.id,
                client_id=lead.assigned_to,
                from_number="02240001000",
                to_number=lead.phone,
                initiated_at=initiated,
                answered_at=(initiated + timedelta(seconds=8)) if connected else None,
                ended_at=(initiated + timedelta(seconds=dur)) if connected else None,
                duration_seconds=dur,
                talk_duration=max(0, dur - 8) if connected else 0,
                status=status,
                outcome=outcome,
                lead_score=lead.lead_score,
                is_hot_lead=lead.is_hot_lead,
                call_cost=int((dur / 60.0) * 65) if connected else 0,  # ~Rs.0.65/min in paise
                created_at=initiated,
            )
            db.add(log)
            n_calls += 1
        db.flush()
        print(f"[+] Inserted {n_calls} call logs.")

        # ----- billing records (MRR + telephony cost) for current + last 5 months -----
        n_billing = 0
        for cl in clients:
            for back in range(6):
                m = now.month - back
                y = now.year
                while m <= 0:
                    m += 12
                    y -= 1
                # subscription (revenue)
                db.add(
                    BillingRecord(
                        id=_uid(),
                        client_id=cl.id,
                        client_name=cl.business_name,
                        record_type=BillingRecordType.SUBSCRIPTION,
                        status=(
                            BillingRecordStatus.PAID if back > 0 else BillingRecordStatus.INVOICED
                        ),
                        period_year=y,
                        period_month=m,
                        amount=cl.monthly_amount,
                        cost=0,
                        quantity=1,
                        description=f"{cl.plan.value.title()} plan - {y}-{m:02d}",
                        created_at=datetime(y, m, 1),
                    )
                )
                # telephony (cost)
                db.add(
                    BillingRecord(
                        id=_uid(),
                        client_id=cl.id,
                        client_name=cl.business_name,
                        record_type=BillingRecordType.TELEPHONY,
                        status=BillingRecordStatus.PAID,
                        period_year=y,
                        period_month=m,
                        amount=0,
                        cost=RNG.randint(200000, 600000),  # Rs.2k-6k in paise
                        quantity=RNG.randint(200, 900),
                        description=f"Telephony usage - {y}-{m:02d}",
                        created_at=datetime(y, m, 1),
                    )
                )
                n_billing += 2
        db.commit()
        print(f"[+] Inserted {n_billing} billing records.")

        print("\n========== SEED COMPLETE ==========")
        _print_summary(db, Client, Agent, Campaign, CallLog, Lead, BillingRecord)
        return 0

    except Exception as e:
        db.rollback()
        print(f"[!] Seeding failed: {e!r}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        db.close()


def _print_summary(db, Client, Agent, Campaign, CallLog, Lead, BillingRecord) -> None:
    print("Current row counts:")
    print(f"  clients        : {db.query(Client).count()}")
    print(f"  agents         : {db.query(Agent).count()}")
    print(f"  campaigns      : {db.query(Campaign).count()}")
    print(f"  leads          : {db.query(Lead).count()}")
    print(f"  call_logs      : {db.query(CallLog).count()}")
    print(f"  billing_records: {db.query(BillingRecord).count()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo data for the dashboards.")
    parser.add_argument("--force", action="store_true", help="Wipe existing demo rows and reseed.")
    args = parser.parse_args()
    return seed(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
