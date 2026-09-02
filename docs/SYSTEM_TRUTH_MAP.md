# SYSTEM TRUTH MAP

| Domain | Canonical implementation | Runtime | Database/store | Worker | API | Dashboard | Manual fallback | Health signal |
| ------ | ------------------------ | ------- | -------------- | ------ | --- | --------- | --------------- | ------------- |
| Leads | `app/models/lead.py` | Local & VPS | Postgres | `leadgen_worker` | `/api/admin_ops.py` (leads_ready) | Admin -> Hot Queue | `Admin -> Prospects/Leads` | `prod_check.py` wiring |
| CRM | `Client` model (`app/models/client.py`) | VPS | Postgres | None | `/api/admin_ops.py` | Admin -> Sabhi Clients | Impersonation | Admin -> Dashboard count |
| Sales / Payment | `app/billing/subscription.py` (UPI manual) | VPS | Postgres (BillingRecord) | `leadgen_worker` | `activation.py` API | Control Center | `UPI_AUTO_ACTIVATE` manual | `test_billing_truth` OK |
| WhatsApp / Comm | `app.platform.auto_outreach` | VPS | Celery Queue | `leadgen_worker` | `/api/whatsapp.py` | Admin -> Hot Queue | Manual Draft/WhatsApp WA.me links | Sentry/otel hook |
| Voice | `app/api/telephony_vobiz.py` | VPS | Vobiz Trunk API | `leadgen_worker` | `/api/telephony_vobiz.py` | `call_log.py` | Admin -> `Customer Ko Call` | `agent_tester` |
| Video | Factory `video_ad_cycle.enabled` | VPS | `video_*` events | `leadgen_worker_video` | Scheduler | Admin -> Creative Prod | `build_creative_video_task` / manual | DLQ depth=0 |
| Buzz / Tools | `app/api/automation_flags.py` | Desktop | Registry json | None | `buzz_*.py` | Admin -> Control Center | MCP CLI | `_liveness=ok` |
