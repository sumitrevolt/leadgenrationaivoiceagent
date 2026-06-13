# Secrets Management — SOPS + age

## Why SOPS?

Plain `.env` files on the VPS are readable by anyone with SSH access and are never safe to commit.
SOPS (Secrets OPerationS) encrypts individual values using an **age** keypair, so:

- The encrypted file (`secrets/.env.enc.yaml`) **can be committed** — values are ciphertext.
- Decryption requires the age **private key**, which lives only on the VPS (`~/.config/sops/age/keys.txt`).
- No third-party secrets manager, no AWS KMS cost — fully free, self-hosted.

Current stack: plain `.env` (working). SOPS is **opt-in** via `USE_SOPS=1`.

---

## Quick-start: Setup (VPS, one-time)

### 1. Install sops + age, generate keypair

```bash
cd /opt/leadgen
bash scripts/sops_setup.sh
```

Output will include a line like:
```
age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```

### 2. Put public key in `.sops.yaml`

Edit `.sops.yaml` (already in repo) — replace the placeholder:
```yaml
age: >-
  age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```
Commit this file (public key only — safe).

### 3. Encrypt your `.env`

```bash
cd /opt/leadgen
bash scripts/sops_encrypt_env.sh
```

Creates `secrets/.env.enc.yaml`. This file is safe to commit.

---

## Deploy: Decrypt at startup

```bash
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
cd /opt/leadgen
bash scripts/sops_decrypt_env.sh
docker compose -f docker-compose.vps.yml up -d --force-recreate app
```

Or use the Python loader (see below).

---

## Python loader: `app/utils/secrets.py`

### Gate: `USE_SOPS=1`

Without this env var, the loader is a **complete no-op** — zero behaviour change.

### Functions

| Function | Description |
|---|---|
| `load_encrypted_env()` | Decrypt + load vars into `os.environ`. Returns `bool`. Never raises. |
| `get_secret(name, default="")` | `os.getenv` wrapper. Never raises. |

### Optional early-startup integration

Add to the **very top** of `app/main.py` (before other imports that read env):

```python
# Optional: load encrypted secrets if USE_SOPS=1
try:
    from app.utils.secrets import load_encrypted_env
    load_encrypted_env()
except Exception:
    pass  # always safe, but belt+suspenders
```

This is additive — if `USE_SOPS` is not set, the call returns `False` immediately.

### Environment variables used by the loader

| Variable | Default | Purpose |
|---|---|---|
| `USE_SOPS` | `0` | Master gate. Set to `1` to enable. |
| `SOPS_AGE_KEY_FILE` | `~/.config/sops/age/keys.txt` | Path to age private key. |
| `SOPS_ENC_FILE` | Auto-detected | Path to `secrets/.env.enc.yaml`. |
| `SOPS_CONFIG_FILE` | Auto-detected | Path to `.sops.yaml`. |

---

## Adoption steps (recommended order)

1. **Now**: Run `sops_setup.sh`, update `.sops.yaml`, encrypt once, commit `secrets/.env.enc.yaml`.
2. **Verify**: `sops_decrypt_env.sh` restores `.env` correctly on VPS.
3. **Opt-in**: Set `USE_SOPS=1` in `.env`; add `load_encrypted_env()` call in `main.py`.
4. **CI/CD**: Inject age private key as GitHub secret (`AGE_SECRET_KEY`); decrypt in `deploy-vps.yml` before `docker compose up`.

---

## Rollback

SOPS is purely additive. To roll back:

1. Unset `USE_SOPS` (or set to `0`).
2. App continues using plain `.env` exactly as before.
3. No code changes required.

The encrypted file can stay committed — it does not interfere with anything when `USE_SOPS` is off.

---

## Security notes

- **Never** commit the private key (`keys.txt`) or any unencrypted `.env`.
- `.env` and `keys.txt` are already in `.gitignore`.
- `secrets/.env.enc.yaml` is safe to commit (all values are ciphertext).
- Rotate: run `sops_encrypt_env.sh` after any `.env` change.
- If the private key is compromised: generate a new keypair, re-encrypt `.env` with the new public key, update `.sops.yaml`.
