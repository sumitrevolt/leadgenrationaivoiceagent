# Enterprise Flywheel — External Unlocks (Phase 5)

> User paperwork / third-party approval required. Code stubs + flags exist; prod enable only after unlock.

## Checklist

| Item | Flag / module | User action | Verify |
|------|---------------|-------------|--------|
| DLT cold-calling | `compliance.py`, Vobiz | Udyam + DLT re-apply with Proprietorship cert | `VOBIZ_CALLER_ID` + test call |
| Vobiz DID recharge | `vobiz_handler.py` | Recharge + buy DID | `/api/webhooks/health` provider=vobiz |
| Meta WA auto-send | `WHATSAPP_AUTO_SEND` | App review + approved templates | `whatsapp_campaign` live send |
| NDNC live API | `dnd_checker.py` | Subscribe NDNC scrub provider | promo call DND verified=true |
| TRAI verbal consent | `CONSENT_CONFIRM` | DLT unlock first | `docs/TRAI_CONSENT_CONFIRM_SPEC.md` |
| Google Calendar OAuth | `calendar_booking.py` | OAuth creds per client | booking API non-sim |
| CRM pull (Zoho) | `CRM_SYNC_PULL` | Zoho search API creds | `POST /api/growth/crm/pull` |

## Already wired (enable when ready)

- `CONSENT_CONFIRM=1` — registered in `automation_flags.py`; inert until DLT
- `CRM_SYNC_PULL=1` — HubSpot pull via `crm_sync.pull_lead_status()`
- `MISSED_CALL_CALLBACK=1` — needs Vobiz inbound DID
- `SMS_DLT_ENABLED=1` — needs BSP creds + DLT templates

## Compliance (never disable)

- Promo calling window 9am–7pm IST (conservative)
- DND fail-closed for promotional
- AI disclosure at call start
- RFC8058 email unsubscribe
- `consent_ledger` cross-channel opt-out

## Recommended prod flags (full flywheel)

Run `python scripts/flywheel_flags_check.py` after setting in `.env`:

```
GROWTH_OPTIMIZER=1
CHANNEL_EXPERIMENTS=1
EVAL_GATE=1
SELF_IMPROVE_LOOP=1
CAMPAIGN_OPTIMIZER=1
PROCESS_AUTOSTART=1
NICHE_ROTATION=1
LEAD_HARVESTER=1
AUTO_EMAIL_OUTREACH=true
REPLY_AGENT=1
```

Celery worker + scheduler required for `SELF_IMPROVE_LOOP`.
