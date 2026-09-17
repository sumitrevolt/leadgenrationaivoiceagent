# DEPLOY SAFE — LeadGen AI canonical deploy runbook

> **Owner:** M6 (see `deliverables/software-company/crore-strategy-ARCH-2026-09-16.md` §M6)
> **Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN`

Goal: **"har deploy pe kuch break na ho"** — a deploy must either succeed visibly or
fail loudly. It must never *look* like it succeeded while running old code.

---

## 1. The one truth you must know

| Fact | Reality | Label |
|---|---|---|
| Prod app server | **systemd unit `leadgen`** → `127.0.0.1:8000` (`uvicorn app.main:app --workers 2`) | `PRODUCTION-PROVEN` |
| App deploy step | **`systemctl restart leadgen`** | `PRODUCTION-PROVEN` |
| `leadgen_app` container | **DOES NOT EXIST** | `PRODUCTION-PROVEN` |
| Single deploy authority | `scripts/deploy_vps.sh` | `CODE-PRESENT` |
| PM2 for the app | **NOT USED** (systemd supervises) | `PRODUCTION-PROVEN` |

---

## 2. ⛔ The guaranteed false-success path (NEVER do this)

```bash
# ❌ ABSOLUTELY NOT — this is a GUARANTEED FALSE SUCCESS:
docker compose up -d app
```

Why it is false:

1. `docker-compose.vps.yml` still publishes `127.0.0.1:8000:8080`.
2. Port 8000 is **already bound by the systemd unit**.
3. The recreate **fails to bind**, but the **already-running process keeps serving OLD code**.
4. A later `curl 127.0.0.1:8000/health` returns **200** → looks healthy.
5. The script reports success; **nothing moved**.

This class produced the DND fail-open false alarm historically. It is pinned by
`tests/test_no_app_container_drift.py` (20 tests). Keep it green.

> `scripts/deploy_vps.sh` deliberately **excludes `app`** from its `SERVICES` list.
> The containers it rolls are `worker scheduler worker-heavy worker-video` (etc.); the
> app is served by the systemd unit.

---

## 3. Correct deploy procedure

```bash
# 0) Preflight — refuses the false-success path + checks preconditions
bash scripts/deploy_preflight.sh "$(git rev-parse --short HEAD)"

# 1) Deploy (single authority). NEVER 'latest' — always a SHA.
bash scripts/deploy_vps.sh "$(git rev-parse --short HEAD)"
```

`deploy_vps.sh` (contract):

1. refuses `APP_VERSION=latest` (must be a SHA),
2. `source _runtime_data_guard.sh` — protects `invoices.jsonl`, `consent_ledger.jsonl`,
   and the 182 MB DPDP recordings,
3. `git pull` (live checkout moves),
4. builds the app image pinned to `APP_VERSION=$VER`,
5. `docker compose up -d worker scheduler worker-heavy worker-video …` (**app NOT in list**),
6. `alembic upgrade`,
7. **`systemctl restart leadgen`** ← the actual app deploy step,
8. verifies `/health.version == $VER`,
9. per-container skew check (resolve by compose **service** name + exact
   `com.docker.compose.service` label),
10. smoke + `deploy_image_retention.py` + rollback tag,
11. **exit 0 only if ALL pass**, else non-zero.

---

## 4. `/health.version` gate

The deploy is only "done" when `GET /health` returns `version == the deployed SHA`.

```bash
VER="$(git rev-parse --short HEAD)"
curl -fsS http://127.0.0.1:8000/health | jq -r .version   # must equal $VER
```

If it does not match, the deploy **must exit non-zero** — never report success.

---

## 5. Known open risk B3 (residual)

`deploy_vps.sh`'s container-skew check can FATAL against **hashed** container names
even when image tags match → false deploy-failure noise. **Largely already hardened**
(`_resolve_compose_container()` resolves by compose service name + exact label —
2026-09-15 prod fix). **Residual:** confirm on the next real deploy. Label: `PARTIAL`.

---

## 6. Log rotation

Both layers are shipped (belt + suspenders):

* App: `app/utils/logging_rotation.py` → `RotatingFileHandler` (10 MB × 5 backups),
  wired into `app/utils/logger.py`.
* OS: `deploy/logrotate/leadgen` → daily, rotate 14, `maxsize 10M`, compressed.

Install the logrotate policy once on the VPS:

```bash
sudo cp deploy/logrotate/leadgen /etc/logrotate.d/leadgen
sudo logrotate -d /etc/logrotate.d/leadgen   # dry-run
```

---

## 7. Rollback

```bash
# image rollback tag is created by deploy_vps.sh; roll back to the previous SHA image
bash scripts/deploy_vps.sh "<previous-sha>"
```

`systemctl restart leadgen` picks up the re-pinned image after the compose services roll.

---

## 8. Quick checklist

- [ ] `bash scripts/deploy_preflight.sh <sha>` exits 0
- [ ] `APP_VERSION` is a SHA (never `latest`)
- [ ] No `docker compose up -d ... app` anywhere in `scripts/`
- [ ] `systemctl restart leadgen` ran
- [ ] `/health.version == <sha>`
- [ ] per-container skew check passed
- [ ] logrotate policy installed
