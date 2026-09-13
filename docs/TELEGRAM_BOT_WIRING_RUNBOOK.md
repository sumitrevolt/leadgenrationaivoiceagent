# Telegram bot wiring runbook - 2026-09-13

Context: the 10 enterprise chats are **created** on the owner's account (`LeadGen AI *`).
What remains: make the bot an **admin** in each, capture each `chat_id`, then run `telegram_setup.py --apply`
so the bot can set descriptions / forum topics / pins / invite links.

Bot: **@Leadsgenai1_bot** (id 8889560331, name "Leadgenai"), token lives in the prod `.env`.

## Why this step can't be fully automated from the agent
- The Telegram **Bot API cannot create chats** and **cannot self-add** to chats.
- The agent proved it can drive Telegram Desktop via UI Automation to *create* chats, but the
  "Add Admin / Add member" control isn't exposed by name -> the admin-add must be done in the UI (or via a user session).

## Option A - manual (2-1 min, ~5 minutes total)
For each of the 10 chats:
1. Open the chat in Telegram Desktop.
2. Group: `... menu (top-right) -> Manage Group -> Administrators -> Add Admin -> search ``@Leadsgenai1_bot`` -> Add`.
   Channel: `... menu -> Manage Channel -> Administrators -> Add Admin -> ``@Leadsgenai1_bot`` -> Add`.
3. Post any message in the chat (so the bot receives an update with the chat id).
Then:
```
# on the VPS, read the ids the bot just received:
docker exec leadgen_app python3 -c "import os,json,urllib.request;t=os.environ['TELEGRAM_BOT_TOKEN'];r=json.loads(urllib.request.urlopen('https://api.telegram.org/bot'+t+'/getUpdates?limit=100',timeout=20).read());[print(u.get('message',{}).get('chat',{}).get('id'), u.get('message',{}).get('chat',{}).get('title')) for u in r['result'] if u.get('message')]"
```
Paste the ids into `config/telegram/setup_spec.yaml` (each entity's `chat_id:`), then:
```
TELEGRAM_SETUP_ENABLED=1 python scripts/telegram_setup.py --apply
```

## Option B - programmatic (once a user session exists)
`scripts/telegram_create_chats.py --apply --write-spec` already creates chats + writes chat_ids when given
`TELEGRAM_API_ID`/`TELEGRAM_API_HASH` + a one-time login. With a session, the bot can be added to each chat
programmatically (channels.InviteToChannel / EditAdmin) and the whole flow is automated.

## Chats to wire (10)
| chat | type |
|---|---|
| LeadGen AI Marketing - Announcements | channel |
| LeadGen AI Voice Agent - Announcements | channel |
| LeadGen AI Marketing - Community | group |
| LeadGen AI Marketing - Support | group |
| LeadGen AI Marketing - Feedback | group |
| LeadGen AI Voice Agent - Community | group |
| LeadGen AI Voice Agent - Support | group |
| LeadGen AI Voice Agent - Feedback | group |
| LeadGen AI - Internal Ops | group |
| LeadGen AI - Owner Alerts | group |
