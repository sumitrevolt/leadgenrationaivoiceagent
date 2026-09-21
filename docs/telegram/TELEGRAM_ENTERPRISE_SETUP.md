# LeadGen AI — Enterprise-Grade Telegram Setup (Product 1 + Product 2)

> Canonical machine-readable spec: [`config/telegram/setup_spec.yaml`](../config/telegram/setup_spec.yaml)
> Bootstrap script: [`scripts/telegram_setup.py`](../scripts/telegram_setup.py)
> Edit the YAML, not this doc. This doc is the human-facing design + runbook.

**Scope:** Both products of the LeadGen AI platform —
- **Product 1 — AI Automated Marketing** (Main ₹1,999/mo · Combo/Advanced ₹5,999/mo; voice callback is a 500-min feature)
- **Product 2 — AI Voice Calling Agent** (₹4,999 / ₹9,999 / ₹19,999 per niche-band/mo; DLT-gated for cold outbound)

**Principle:** Opt-in only. No scraping, no bulk-add, no cold-DM. Bots disclose they are automated. No PII/tokens in chat. Mirrors the platform's hard compliance gates (DND fail-closed, TRAI window, AI-disclosure, consent ledger, manual-UPI truth, tenant isolation).

---

## 1. Recommended scalable structure

To avoid chat sprawl as volume grows, use a **hub-supergroup-with-topics** pattern per product, plus broadcast + internal chats:

```
Per product (P1, P2):
  ┌─ Announcements CHANNEL (public, broadcast-only)        ← releases / status / pricing
  └─ "<Product> Hub" SUPERGROUP (public community OR private) with TOPICS:
        #community   #support   #feedback   (#announcements mirror, admin-only post)
Cross-product (platform):
  ┌─ Internal Ops SUPERGROUP (private, team-only)           ← incidents / deploys / bot-status
  └─ Owner Alerts SUPERGROUP (private, founder+bot)         ← health / payment / kill-switch mirror
```

This keeps **admin overhead low** (one bot, one supergroup per product) while still giving users distinct spaces via Topics. The explicit "one chat per function" layout in §2 is the conservative alternative if you prefer separate invite links per function.

---

## 2. Groups & channels (canonical list — 10 entities)

### Product 1 — AI Automated Marketing

| # | Name | Kind | Access | Purpose | Target audience |
|---|------|------|--------|---------|-----------------|
| 1 | `LeadGen AI Marketing · Announcements` (`@LeadGenAIMarketingNews`) | Channel | **public** | One-way releases, pricing, maintenance, compliance/DPDP, outage | All subscribers (customers + prospects + public) |
| 2 | `LeadGen AI Marketing · Community` (`@LeadGenAIMarketingCommunity`) | Supergroup | **public** | Peer discussions, use-cases, wins, growth tactics | Customers + trial + interested SMB owners |
| 3 | `LeadGen AI Marketing · Support` | Supergroup | **private** | Ticketed support: bugs, billing, incidents | Paying customers (verified post-UPI) |
| 4 | `LeadGen AI Marketing · Feedback` | Supergroup | **private** | Feature requests, beta, product feedback | Customers + selected power users |

### Product 2 — AI Voice Calling Agent

| # | Name | Kind | Access | Purpose | Target audience |
|---|------|------|--------|---------|-----------------|
| 5 | `LeadGen AI Voice Agent · Announcements` (`@LeadGenAIVoiceNews`) | Channel | **public** | Voice releases, provider/quality notices, DLT/compliance, outage | All subscribers (customers + prospects + public) |
| 6 | `LeadGen AI Voice Agent · Community` (`@LeadGenAIVoiceCommunity`) | Supergroup | **public** | AI-telecalling scripts, niche-band strategy, voice quality | Customers + trial + interested SMB owners |
| 7 | `LeadGen AI Voice Agent · Support` | Supergroup | **private** | Call routing, DLT templates, billing, incidents | Paying customers (verified post-UPI) |
| 8 | `LeadGen AI Voice Agent · Feedback` | Supergroup | **private** | Voice-feature requests, beta voices, pronunciation feedback | Customers + selected power users |

### Cross-product (platform-level, team-only)

| # | Name | Kind | Access | Purpose | Target audience |
|---|------|------|--------|---------|-----------------|
| 9 | `LeadGen AI · Internal Ops` | Supergroup | **private** | Internal coordination, incident war-room, deploy notices, bot status, decisions | Team only (founder, dev, support, PM) |
| 10 | `LeadGen AI · Owner Alerts` | Supergroup | **private** | Critical alerts mirror to founder (health, payment, incident, kill-switch) — Telegram mirror of the ntfy owner feed | Founder only (+ bot) |

---

## 3. Admin roles (global matrix)

| Role | Scope | Key permissions |
|------|-------|-----------------|
| **Founder / Owner** | all chats | full, manage admins, delete, ban, post, pin |
| **Product Manager** | announcements (P1,P2), feedback, internal | post, pin, moderate, manage topics |
| **Community Manager** | community, feedback | moderate, manage topics, pin, ban |
| **Support Lead** | support | full support, escalate, ban |
| **Support Agent** | support | reply, close ticket, label |
| **Dev / Ops** | internal, owner alerts | post, bot status, deploy notice |
| **LeadGenBot (welcome/consent)** | community, support, feedback | send (no admin) |
| **LeadGenBot (moderation)** | community, support, feedback | delete msgs, ban (no admin-promote) |
| **LeadGenBot (ticket intake)** | support | send (no admin) |
| **LeadGenBot (broadcast)** | announcements | post via CMS (no admin) |

**Rule:** bots get *restricted* admin (delete/ban only, never `promote_administrators`). Human admins are assigned per chat; founder is the only `manage_admins`.

---

## 4. Moderation guidelines + escalation SOP

**Join policy:** voluntary opt-in only. No scraping member lists, no bulk-add, no cold-DM. (DPDP + TRAI TCCCPR.)

**On join (community/support/feedback):** `LeadGenBot` posts rules + a consent notice; member must tap `/start` (or react) before posting. Every automated reply labels itself as a bot (AI disclosure).

**Anti-abuse:**
- Spam / phishing / scam → `bot_mod` auto-deletes + bans; Community Manager reviews the ban.
- Harassment / illegal → ban + report to Telegram.

**PII rule:** no PII in chat. Support uses a **ticket ID**, never raw customer data. **Secret-free everywhere** — no tokens / OTP / passwords in any chat (bot strips + warns). This is mandatory in Internal Ops too.

**Escalation:** `Support` → `Internal Ops` → `Founder` (war-room if incident). Unresolved support > 24h escalates to Internal Ops.

**Opt-out:** respect leave/unsubscribe; never message a member who departed.

**Incident:** Internal Ops war-room → Announcements channel status post → Owner Alerts mirror.

---

## 5. Compliance gates (never weaken)

| Gate | Requirement |
|------|-------------|
| DPDP Act 2023 | Lawful purpose, consent, data minimization, erasure on leave |
| TRAI TCCCPR | No UCC; opt-in; honor DND + 09:00–21:00 for any outbound to IN numbers |
| AI disclosure | Every automated reply labels itself as a bot |
| Payment truth | Manual UPI only; never claim "auto-paid" |
| No cold outreach | No cold Telegram/WhatsApp adds (mirrors existing platform ban) |
| Tenant isolation | No cross-customer PII leakage in shared groups |

---

## 6. How to CREATE the chats

> **Hard limitation:** the Telegram **Bot API cannot create channels or groups** — only a user account (or a Telethon session) can. So the owner creates them (manual, 2 min) or runs the optional Telethon snippet below, then fills `chat_id` in the spec and runs the bootstrap to configure them.

### Option A — Manual (recommended, 2 min)
1. In the Telegram app, create the **Announcements channel** (public → set `@handle`).
2. Create each **supergroup** (community = public; support/feedback/internal/owner = private).
3. For community/support/feedback hubs, enable **Topics** (⋯ → Manage → Topics).
4. Add **LeadGenBot** as admin (post + manage topics + delete + ban as needed).
5. Open each chat, copy its **`chat_id`** (bot can reply with it, or forward a message to `@userinfobot`), and paste into `config/telegram/setup_spec.yaml` under that group's `chat_id`.
6. Run the bootstrap (§7) to set descriptions, topics, intros, invite links.

### Option B — Telethon auto-create (optional, owner runs locally)
Requires `pip install telethon` + `API_ID` / `API_HASH` from my.telegram.org + a one-time phone login. Clearly **owner-run, not sandbox**:

```python
# scripts/telegram_create_telethon.py  (owner-run, needs: pip install telethon)
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.functions.messages import CreateChatRequest
import yaml, os

spec = yaml.safe_load(open("config/telegram/setup_spec.yaml"))
api_id = int(os.environ["TELEGRAM_API_ID"]); api_hash = os.environ["TELEGRAM_API_HASH"]

async def main():
    async with TelegramClient("founder_session", api_id, api_hash) as c:
        for prod in spec["products"]:
            for g in prod["groups"]:
                if g["kind"] == "channel":
                    r = await c(CreateChannelRequest(g["name"], g["purpose"][:0] or "announcements", megagroup=False))
                else:
                    r = await c(CreateChatRequest(g["name"], []))  # empty -> creates group; add bot after
                cid = r.chats[0].id
                print(f"{g['name']}: chat_id={cid}  -> paste into setup_spec.yaml")
        # cross_product groups similarly ...

import asyncio; asyncio.run(main())
```

> This snippet is **illustrative** — owner adapts + runs locally. The sandbox does NOT create chats (no user session, no creds).

---

## 7. Configure via the bootstrap script

```bash
# 1) Validate the spec parses
python scripts/telegram_setup.py --validate

# 2) Dry run (no network) — see what will happen
python scripts/telegram_setup.py --plan

# 3) Live configure (owner sets token + enables; needs chat_id filled per group)
TELEGRAM_SETUP_ENABLED=1 TELEGRAM_BOT_TOKEN=xxxx \
    python scripts/telegram_setup.py --apply
```

The script will, per chat with a `chat_id`:
- `setChatDescription` (purpose + audience + access)
- `createForumTopic` for each topic (supergroups only)
- `sendMessage` + `pinChatMessage` the intro
- `exportChatInviteLink` for private chats (printed for you to distribute)

Fail-closed: disabled unless `TELEGRAM_SETUP_ENABLED=1`; refuses network without `TELEGRAM_BOT_TOKEN`; `--plan` never touches the network.

---

## 8. Owner checklist (next steps)

- [ ] Create the 10 chats (manual §6A, or Telethon §6B)
- [ ] Add `LeadGenBot` as restricted admin to each
- [ ] Fill `chat_id` for all 10 in `config/telegram/setup_spec.yaml`
- [ ] `python scripts/telegram_setup.py --apply` (with token + enabled)
- [ ] Rotate private invite links monthly; enable join-request approval
- [ ] Wire `Owner Alerts` to the existing ntfy owner feed (`scripts/send_owner_ntfy.py` mirror)
- [ ] Confirm `LeadGenBot` strips secrets + labels AI replies in every chat
