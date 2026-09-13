# HANDOFF -> Telegram enterprise wiring (for the next agent, e.g. FreeBuff)

Date: 2026-09-13. Repo: `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent`.
Owner account: Telegram "sumit daryanani". Bot: **@Leadsgenai1_bot** (id 8889560331); token in prod `.env`.

## TL;DR of the current state
- **10 chats created** on the owner's account (2 channels + 8 supergroups).
- **1/10 fully wired**: `@Leadsgenai1_bot` = **administrator** in "LeadGen AI Marketing - Community"
  (authoritative chat_id **-1004475752582**, verified via Bot API).
- `setup_spec.yaml` holds ids captured from the Telegram-Web URL. **Warning:** for SUPERGROUPS the web
  URL id differs from the Bot API `chat_id` -> replace with the authoritative ids from `getUpdates`.
- The prod route `/telegram/setup` is live (HTTP 200) on image `d08f07c5`.

## THE ONLY REMAINING STEP: add the bot as ADMIN to the other 9 chats
Automation on this box CANNOT do it (see "Why automation failed"). Do it in the Telegram Desktop UI.

### Step-by-step (Telegram Desktop), per chat
1. Open the chat (left list / search).
2. Click the **"..."** (More actions) button at the **top-right** of the chat header.
3. Choose **"Manage Group"** (or **"Manage Channel"** for channels).
4. Click **"Administrators"**.
5. Click **"Add Admin"**.
6. In the search box type **`Leadsgenai1_bot`** -> click the result **"Leadgenai" (bot)**.
7. Click **"Add Admin" / "Save"** (blue, top-right). You should see "Leadgenai ... is now an administrator".
8. (If the bot does not appear in "Add Admin": first add it via **"Add Members"/"Add Subscribers"**, then promote.)

### The 9 chats to wire
| # | Chat | Type |
|---|---|---|
| 1 | LeadGen AI Marketing - Announcements | Channel |
| 2 | LeadGen AI Marketing - Support | Group |
| 3 | LeadGen AI Marketing - Feedback | Group |
| 4 | LeadGen AI Voice Agent - Announcements | Channel |
| 5 | LeadGen AI Voice Agent - Community | Group |
| 6 | LeadGen AI Voice Agent - Support | Group |
| 7 | LeadGen AI Voice Agent - Feedback | Group |
| 8 | LeadGen AI - Internal Ops | Group |
| 9 | LeadGen AI - Owner Alerts | Group |

## THEN run (agent commands)
```bash
# 1. authoritative chat_ids from the bot's own updates (my_chat_member events)
docker exec leadgen_app python3 -c "import os,json,urllib.request;t=os.environ['TELEGRAM_BOT_TOKEN'];r=json.loads(urllib.request.urlopen('https://api.telegram.org/bot'+t+'/getUpdates?limit=100',timeout=20).read());[print((m.get('chat') or {}).get('id'),'|',(m.get('chat') or {}).get('title')) for u in r['result'] for m in [u.get('message') or u.get('channel_post') or u.get('my_chat_member')] if m]"

# 2. put those ids into config/telegram/setup_spec.yaml (each entity's chat_id)

# 3. apply the enterprise config (descriptions / forum topics / pinned message / invite links)
TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply

# 4. verify (bot must be admin for these calls to succeed)
docker exec leadgen_app python3 -c "import os,json,urllib.request;t=os.environ['TELEGRAM_BOT_TOKEN'];print(json.loads(urllib.request.urlopen('https://api.telegram.org/bot'+t+'/getChatAdministrators?chat_id=<ID>',timeout=15).read())['ok'])"
```

## Why automation failed (evidence, so nobody re-tries blindly)
- **Telegram Desktop (UIA):** the main window exposes only persistent controls; its menus/popups are
  NOT in the UIA tree -> no programmatic access to "Manage Group -> Administrators -> Add Admin".
- **Telegram Desktop (synthetic clicks / vision):** `SetCursorPos+mouse_event` did not open the "..." menu;
  `autoglm-image-recognition` coordinates varied between calls (1445,93 vs 1523,80) -> unreliable.
- **Telegram Web** (browser-automatable): the "Add Members"/"Add Admin" selection + Save/Enter did NOT
  register the bot (Bot API `getChat`/`getChatAdministrators` still says "chat not found"); the picker
  only checks a box and shows the member as "selected" without applying.
- **ChatGPT Computer Use:** reported "Telegram Desktop bridge unavailable" (Windows not supported).
=> **Manual UI add is the only reliable path** (proven: Marketing - Community).

## Alternative (Path B, no manual UI)
If `my.telegram.org` login works later (owner hit a rate-limit on 2026-09-13): obtain
`TELEGRAM_API_ID` + `TELEGRAM_API_HASH` + a one-time login code -> `python scripts/telegram_wire_bot.py --apply`
will add the bot + promote it to admin in ALL chats programmatically and write back the ids.

## Other pending items (non-Telegram), for admin follow-up
- **Smartflo/Tata:** the account is INACTIVE (API 401) and the free trial EXPIRED -> all outbound voice
  calls are dead. Owner action: buy/activate a Tata Smartflo plan. (Escalation email ready at
  `docs/reports/SMARTFLO_ESCALATION_20260912.md`.)
- **Dependabot:** default branch shows 1 critical / 4 high / 9 moderate; admin-dashboard has 2 moderate
  (react-router 6.x, fix = breaking 7.x). Needs a controlled upgrade pass.
- **Failing Hermes cron:** `revenue-autopilot-driver` (job 527c8915ee14) posting to Telegram; diagnosed
  P0 on 2026-08-29 (provider auth/rate-limit). Pause + rotate keys.
- **Repo:** several workers' uncommitted changes present; a concurrent worker was active in `/opt/leadgen`.
- **Prod:** healthy on image `d08f07c5`; 6 `dev_workers` rows (cli_operations/engineering/platform/guardian/sales/success) healthy.

## Key files
- `config/telegram/setup_spec.yaml` (10 entities + ids)
- `scripts/telegram_setup.py` (apply), `scripts/telegram_create_chats.py` (create), `scripts/telegram_wire_bot.py` (Path B)
- `docs/TELEGRAM_BOT_WIRING_RUNBOOK.md`, `docs/FIX_LEDGER_2026-09-13.md`, `progress.md`
