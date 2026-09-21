#!/usr/bin/env python3
"""Generate a KEYS_MASTER_KEY for the Key Manager (Fernet master key).

Owner runbook (P0 key manager hardening, 2026-09-21):

    # 1) Generate the master key (prints ONCE to the terminal — capture it now):
    python scripts/key_manager_gen_master.py

    # 2) Add it to /opt/leadgen/.env (append, do not paste keys into chat/git):
    #    KEYS_MASTER_KEY=<the printed value>
    #    chmod 600 /opt/leadgen/.env

    # 3) Restart the app + key-manager consumers:
    #    (canonical deploy path, or: docker compose -f docker-compose.vps.yml up -d app)

Security notes:
- The master key is EXTERNAL to the key store by design (keys.enc.json holds
  only Fernet ciphertexts). Losing it = keys unrecoverable: back it up in the
  owner's private secret store (same vault as the other .env secrets).
- Never commit it, never send it to Telegram/chat/logs, never print it twice.
"""

from __future__ import annotations

import sys

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("ERROR: 'cryptography' not installed (locked production dependency).", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    key = Fernet.generate_key().decode()
    print("KEYS_MASTER_KEY=" + key)
    print()
    print("Add this single line to /opt/leadgen/.env and restart the app.")
    print("Then provision the four TypeSafe slots (owner-only, via admin UI):")
    print("    typesafe_a / typesafe_b / typesafe_c / typesafe_d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
