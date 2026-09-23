# Vault Non-Overwrite Policy + Recovery Procedure (Wave 8)

**Date:** 2026-09-22
**Worktree:** `feat/smartflo-acceptance-framework` @ `da524017` (+ pending `34974452`)
**Owner:** Sumit (via Root session `mvs_2c0a08d649f94de3af323f87e632debc`)

> **Hard rule (per owner directive):** "Master key उपलब्ध न होने पर MiniMax को नया vault बनाकर पुराने vault को overwrite नहीं करना है।"

---

## 1. Current verified state

| Check | Result | Evidence |
|---|---|---|
| Vault file exists | ✅ YES | `C:\opt\leadgen\secrets\keys.json` — 1775 bytes, `is_file()=True` |
| Vault encrypted | ✅ YES | structure probe: `{version: int, encrypted: bool=True, cipher: str(6)="<Fernet>", ciphertext: str(1636)}` |
| Master key in env | ❌ NO | `KEY_MANAGER_ENC_KEY` ABSENT in current process env |
| Vault contents readable | ❌ NO | Cannot decrypt without master key |
| Backup of vault exists | ❌ UNVERIFIED | No prior backup file located |
| Master key in Windows credential store | ❌ NOT FOUND | `cmdkey /list` does not surface a `leadgen-master-key` or similar entry |
| Master key in keyring library | N/A | `keyring` Python lib not installed on this Python 3.11 |
| Master key in `data/secrets/keys.json` fallback (Linux) | ❌ NO | VPS `/opt/leadgen/secrets/` and `/opt/leadgen/data/secrets/` BOTH do not exist |

---

## 2. Non-Overwrite Policy (HARD RULE)

The following actions are FORBIDDEN without explicit owner authorize:

1. ❌ Create a NEW vault at the canonical path (would overwrite existing)
2. ❌ Generate a new `KEY_MANAGER_ENC_KEY` and write a fresh vault
3. ❌ Modify the existing `ciphertext` even if structure is "corrupted"
4. ❌ Move or rename `C:\opt\leadgen\secrets\keys.json` without backup
5. ❌ Delete the existing vault file
6. ❌ Restore from any backup that was NOT created BEFORE the ratchet fix (today)

**Reason:** the vault may contain credentials for TypeSafe, SmartFlo, Telegram, payment processor, or other services that are NOT recoverable from chat logs / memory / git history. Overwriting destroys production credentials with no rollback path.

---

## 3. Authorized Recovery Procedure (when owner provides master key)

### Step 1 — Backup before any read
```bash
cp C:\opt\leadgen\secrets\keys.json C:\opt\leadgen\secrets\keys.json.backup-pre-recovery-$(date +%Y%m%d-%H%M%S)
```
This is the FIRST action. Verify the backup is a regular file (not symlink) and capture its SHA-256 fingerprint. Both go to the audit log.

### Step 2 — Read with master key (NEVER write)
```python
import os
os.environ['KEY_MANAGER_ENC_KEY'] = '<owner-provided>'  # NEVER log this value
from cryptography.fernet import Fernet
import json
from pathlib import Path

vault_path = Path('C:/opt/leadgen/secrets/keys.json')
raw = json.loads(vault_path.read_text(encoding='utf-8'))
assert raw.get('encrypted') is True, "Vault claims to be encrypted but flag is False"
key = Fernet(os.environ['KEY_MANAGER_ENC_KEY'].encode())
plaintext = key.decrypt(raw['ciphertext'].encode())
slots = json.loads(plaintext.decode())
# Inspect slot names + fingerprint, NEVER print slot values
for slot_id, slot_val in slots.items():
    print(f'{slot_id}: PRESENT keys={list(slot_val.keys()) if isinstance(slot_val, dict) else type(slot_val).__name__}')
```

### Step 3 — Verify what's INSIDE (the owner's Correction 2)

The owner explicitly noted: "Vault unlock और credentials उपलब्ध होना अलग बातें। Encrypted file मौजूद है, लेकिन सही master key मिलने के बाद भी यह verify करना होगा कि उसमें TypeSafe, SmartFlo और Telegram की उपयोगी credentials वास्तव में हैं।"

So step 2 alone is not sufficient. After decryption, MiniMax must inventory what's in each slot and report:

- Are TypeSafe / SmartFlo / Telegram credentials present?
- Are they fresh / current (not stale)?
- Are they scoped to the right account (sumitrevolt / leadsgenai.in)?
- Do they match the canonical `TYPESAFE_SLOTS` config (4 slots A/B/C/D)?

If the vault contains stale/wrong/missing credentials, MiniMax MUST report this and ask owner for the correct fresh credentials via key_manager rotation flow — NOT proceed with stale data.

### Step 4 — Use credentials without persisting raw values

- Read credential from slot
- Inject into process env for the duration of one operation
- Clear from env after operation
- NEVER log, write, or commit the raw credential value
- The audit log records only fingerprint (`sha256:<16>`) + slot name + operation

---

## 4. If master key is NOT available

MiniMax must NOT:
- Generate a new key
- Initialize a fresh vault
- Pretend the vault is accessible

MiniMax must:
- Continue work via code-only paths (deterministic-mock TypeSafe, agent-browser, gh CLI)
- Report each operation as UNVERIFIED when credentials are required
- Wait for owner authorize on vault unlock OR for owner to provide credentials via key_manager rotation

---

## 5. Boundary summary (one-liner per surface)

| Surface | State | Reversibility on overwrite |
|---|---|---|
| `C:\opt\leadgen\secrets\keys.json` | LOCKED, do-not-overwrite | Vault credentials are NOT recoverable from chat/memory/git; overwrite = permanent loss |
| VPS `/opt/leadgen/secrets/` | DOES NOT EXIST | N/A — nothing to overwrite |
| VPS `/opt/leadgen/data/secrets/` | DOES NOT EXIST | N/A |
| SmartFlo portal config (`cloudphone.tatateleservices.com/manage-did-numbers`) | UNVERIFIED (browser returned 403) | Portal state IS recoverable from portal UI by owner; not affected by code revert |
| Telegram bot config (`@Sumits_jarvis_bot`) | UNVERIFIED | Bot config recoverable from BotFather by owner |
| TypeSafe account | UNVERIFIED (no API key) | Account state recoverable from typesafe.ai console by owner |
| Code (`feat/smartflo-acceptance-framework` branch) | 6 commits ahead | git revert restores prior code state |
| Database migrations | NONE applied | N/A |
| Telegram messages sent | 0 (no token) | N/A |
| Customer calls placed | 0 (no portal access) | N/A |

---

## 6. Owner next-step

Choose ONE:
1. Provide `KEY_MANAGER_ENC_KEY` value via authorized private interface → MiniMax runs Steps 1-4 above
2. Confirm vault can be safely rotated → MiniMax generates fresh vault + new master key
3. Confirm vault will be initialized later by owner → MiniMax continues code-only work, leaves vault untouched

🐦 pelican