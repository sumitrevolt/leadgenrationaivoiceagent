# LeadGen daily owner brief -> stdout (Hermes cron --no-agent delivers verbatim).
# READ-ONLY prod probe: pulls headline money/pipeline/ops numbers over SSH.

import os
import subprocess
import sys

GOAL_TOTAL = int(os.environ.get("SPRINT_GOAL_INR", "500000"))
GOAL_DAYS = int(os.environ.get("SPRINT_GOAL_DAYS", "7"))

SSH = os.environ.get("LEADGEN_SSH_BIN", r"C:\Program Files\Git\usr\bin\ssh.exe")
KEY = os.environ.get("LEADGEN_SSH_KEY", r"C:\Users\Ratanshila\.ssh\id_rsa")
HOST = os.environ.get("LEADGEN_VPS_HOST", "root@72.61.245.204")

REMOTE = r"""
U=$(docker exec leadgen_db printenv POSTGRES_USER)
D=$(docker exec leadgen_db printenv POSTGRES_DB)
q(){ docker exec leadgen_db psql -U "$U" -d "$D" -tAc "$1"; }
echo "HEALTH $(docker exec leadgen_app curl -s -m 5 http://localhost:8080/health | head -c 300)"
echo "QUEUE_CELERY $(docker exec leadgen_redis redis-cli llen celery)"
echo "QUEUE_DLQ $(docker exec leadgen_redis redis-cli llen dlq:failed_tasks)"
echo "LEADS_24H $(q "select count(*) from leads where created_at > now() - interval '24 hours'")"
echo "LEADS_TOTAL $(q "select count(*) from leads")"
echo "HOT_7D $(q "select count(*) from leads where is_hot_lead and created_at > now() - interval '7 days'")"
echo "HOT_OPEN $(q "select count(*) from leads where is_hot_lead and status not in ('converted','lost','closed')")"
echo "CALLS_24H $(q "select count(*) from call_logs where initiated_at > now() - interval '24 hours'")"
echo "ANSWERED_24H $(q "select count(*) from call_logs where initiated_at > now() - interval '24 hours' and answered_at is not null")"
echo "APPT_7D $(q "select count(*) from call_logs where appointment_scheduled and created_at > now() - interval '7 days'")"
echo "ACTIVE_SUBS $(q "select count(*) from subscriptions where status='active'")"
echo "SUB_MRR_INR $(q "select coalesce(sum(base_price),0) from subscriptions where status='active'")"
echo "CLIENT_COMMIT_INR $(q "select coalesce(sum(monthly_amount),0)/100 from clients where status='active'")"
echo "CLIENTS_ACTIVE $(q "select count(*) from clients where status='active'")"
"""


def _probe():
    try:
        out = subprocess.run(
            [SSH, "-i", KEY, "-o", "ConnectTimeout=15", "-o", "BatchMode=yes",
             HOST, "bash -s"],
            input=REMOTE.encode(), capture_output=True, timeout=90,
        )
        return out.stdout.decode("utf-8", "replace").splitlines()
    except Exception as e:  # noqa: BLE001
        print(f"BRIEF FAILED: {e}")
        sys.exit(1)


def main():
    lines = _probe()
    m = {}
    health_raw = ""
    for ln in lines:
        if ln.startswith("HEALTH "):
            health_raw = ln[7:]
        elif " " in ln:
            k, _, v = ln.partition(" ")
            m[k.strip()] = v.strip()

    def n(key):
        try:
            return int(float(m.get(key, "0")))
        except ValueError:
            return 0

    def s(key):
        return m.get(key, "?")

    per_day = GOAL_TOTAL // GOAL_DAYS
    sub_mrr = n("SUB_MRR_INR")
    client_mrr = n("CLIENT_COMMIT_INR")
    celery_q = n("QUEUE_CELERY")
    dlq = n("QUEUE_DLQ")

    print("=" * 48)
    print(" LEADGEN DAILY BRIEF - goal Rs %s / %d din" % (format(GOAL_TOTAL, ","), GOAL_DAYS))
    print("=" * 48)
    print("MONEY   : Subs MRR = Rs %s (%d active) | Client commitments = Rs %s/mo (%d clients)"
          % (format(sub_mrr, ","), n("ACTIVE_SUBS"), format(client_mrr, ","), n("CLIENTS_ACTIVE")))
    print("PACE    : Goal ke liye ~Rs %s/day chahiye | abhi MRR baseline = Rs %s"
          % (format(per_day, ","), format(max(sub_mrr, client_mrr), ",")))
    print("PIPELINE: new leads 24h = %d (total %d) | HOT open = %d | hot 7d = %d"
          % (n("LEADS_24H"), n("LEADS_TOTAL"), n("HOT_OPEN"), n("HOT_7D")))
    print("CALLS   : 24h = %d placed / %d answered | appointments 7d = %d"
          % (n("CALLS_24H"), n("ANSWERED_24H"), n("APPT_7D")))
    print("OPS     : celery q = %d | DLQ = %d" % (celery_q, dlq))
    hv = ""
    for part in health_raw.split(","):
        p = part.strip().strip("{}\"")
        if p.startswith(("version", "environment")):
            hv += p.replace("\":\"", "=").rstrip("\"") + " "
    print("SYS     : %s" % (hv.strip() or health_raw[:120]))
    print("-" * 48)
    print("ACTION  : Hot Queue -> https://leadsgenai.in/app/inbox")
    if dlq > 0:
        print("WARN    : DLQ=%d - failed tasks dekho!" % dlq)
    elif celery_q > 500:
        print("WARN    : celery backlog %d - worker check karo" % celery_q)


if __name__ == "__main__":
    main()
