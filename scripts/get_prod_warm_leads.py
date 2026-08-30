import os
import subprocess

SSH = os.environ.get("LEADGEN_SSH_BIN", r"C:\Program Files\Git\usr\bin\ssh.exe")
KEY = os.environ.get("LEADGEN_SSH_KEY", r"C:\Users\Ratanshila\.ssh\id_rsa")
HOST = os.environ.get("LEADGEN_VPS_HOST", "root@72.61.245.204")

REMOTE = r"""
U=$(docker exec leadgen_db printenv POSTGRES_USER)
D=$(docker exec leadgen_db printenv POSTGRES_DB)
docker exec leadgen_db psql -U "$U" -d "$D" -tAc "SELECT json_build_object('id', id, 'company_name', company_name, 'contact_name', contact_name, 'email', email, 'phone', phone, 'city', city, 'niche', niche, 'lead_score', lead_score, 'notes', notes) FROM leads WHERE email IS NOT NULL AND email != '' ORDER BY lead_score DESC, created_at DESC LIMIT 5;"
"""


def main():
    try:
        out = subprocess.run(
            [SSH, "-i", KEY, "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", HOST, "bash -s"],
            input=REMOTE.encode(),
            capture_output=True,
            timeout=90,
        )
        print(out.stdout.decode("utf-8", "replace"))
    except Exception as e:
        print(f"FAILED: {e}")


if __name__ == "__main__":
    main()
