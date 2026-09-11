---
name: leadgen-email-deliverability
description: Email outreach + deliverability hardening — account ban se bachao. Use jab SMTP disabled ho, bulk-send se suspension hua ho, caps chahiye, bounce-handling missing ho, warmup chahiye, ya outreach jobs ko provider-error pe fail-fast karna ho.
---

# LeadGen Email Deliverability

> Enterprise audit skill. Goal: outreach se sender account block na ho. `cold-email`/`cold-email-craft` = copy; **yeh = sending-SAFETY layer**. Pehle `context-first`.

## Mission
Safe daily caps, opt-out, provider-error taxonomy, admin visibility — taaki bulk-send se account suspend na ho.

## Repo truth
- **SMTP**: Hostinger `admin@leadsgenai.in` (`smtp.hostinger.com:465`). `AUTO_EMAIL_OUTREACH=true` → Rohan roz 10:30 personalized Hinglish cold-email + Day-3/7 followups.
- **Caps/safety**: 25/day cap, `OUTREACH_VERIFY_MX=1` (MX-verified), `EMAIL_WARMUP=1` + `WARMUP_START_DATE` ramp, bounce auto-pause.
- **Auth**: SPF/DKIM/DMARC ALL SET.
- **WhatsApp**: bulk auto = ban → 1-click human send only (`WHATSAPP_AUTO_SEND` OFF).

## Workflow
1. Saare email senders/SMTP-configs/queues/templates/campaigns/followup-jobs identify.
2. Sends classify: transactional / onboarding / marketing / outreach / internal-alert.
3. Provider error taxonomy: disabled-account / auth-fail / quota / rate-limit / bounce / transient.
4. Per-domain, per-account, per-campaign, global daily caps enforce.
5. Opt-out / unsubscribe / suppression / retry tested.

## Enterprise checks
- `554 Disabled` ya account-level error → batch IMMEDIATELY stop (fail-fast, infinite loop nahi).
- Bulk job kabhi unlimited loop na chale (cap hard).
- Failed SMTP creds campaign-execution se PEHLE visible.
- Templates spammy-claim avoid + business identity include.
- Test-mode galti se real outreach na bheje.

## Output
Sender risk report · safe sending policy · fail-fast patch plan · tests (caps + suppression + provider errors) · readiness /100.

## Related repo skills (duplicate mat banao)
`cold-email` + `cold-email-craft` (copy/craft) · `emails` (templates) · `leadgen-lead-pipeline-quality` (lead source/dedupe) · `leadgen-automation-reliability` (Rohan job reliability) · `leadgen-observability` (SMTP-disabled alert).
