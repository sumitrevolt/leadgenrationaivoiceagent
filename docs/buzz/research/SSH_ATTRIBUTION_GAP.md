---
title: "Root Key Is Shared — No Change on the VPS Is Attributable"
tags: [leadgen, security, ssh, audit, open]
status: active
created: 2026-08-03
---

# Finding: prod changes cannot be attributed to an actor

Surfaced 2026-08-03 while investigating an unexplained `.env` edit. The edit turned out to be less
important than what the investigation revealed about the audit trail.

## What we could establish

- Both WhatsApp gates flipped `0 → 1` **together**, in a surgical in-place edit at lines 498 and 629.
  No appended duplicate block, so it was hand-edited, not script-generated.
- Bounded window: still `0` at `.env.bak-be-20260803_060555` (06:05:55Z), already `1` at
  `.env.bak-predeploy5` (07:46:58Z).
- Key set was otherwise **identical** — nothing added, removed, or renamed. Values only.
- The same flag was toggled to `1` and reverted twice on 08-01
  (`.env.bak-wa2-…381`, `.env.bak-wa3-…479`). Someone had been experimenting with it before.
- **No automated writer is plausible.** No `.env` writer exists anywhere under `app/`. Every match in
  the repo lives in manually-invoked `scripts/`. The obvious suspect, `scripts/activate_waha_vps.sh`,
  writes `WHATSAPP_AUTO_SEND=0` at line 46 — exculpatory, not incriminating.

## What we could NOT establish, and why

**Who did it.** 189 root logins across 5 IPs, all using one shared key. Sumit's workstation drives
SSH from that key, and so do the Cursor / OpenCode / Claude sessions running on that same machine.
The logs physically cannot distinguish the human typing from an agent acting on his behalf.

A tempting theory — a root login at 07:46:57Z, one second before the backup — was **rejected**:
backup mtime semantics are inconsistent across these files (some preserve source mtime, the repo's
own convention uses plain `cp`), so the one-second adjacency is not sound evidence. The bounded
window is all the evidence supports.

## The actual finding

`leadgen-deploy` — the hardened path `CURRENT_STATE.md` declares canonical, with root reserved for
break-glass — went **completely unused**. Break-glass root is the routine path right now.

Until the human and the agents stop sharing one key, **no change on this box is attributable to an
actor.** That is a standing gap, independent of any single incident, and it will make every future
investigation end the same way.

## Open action items for Sumit

1. **Rotate the exposed `GEMINI_API_KEY`.** Root's `.bash_history` line 3 contains it inline in a
   `curl … | sh` deploy invocation, plaintext on disk. Rotate, then scrub the line.
2. Decide whether the WhatsApp gates being open is intentional. If yes, `CURRENT_STATE.md` should be
   corrected so the docs stop disagreeing with reality. If no, close them.
3. Split agent SSH access from the human's root key, and move routine work onto `leadgen-deploy`.

Until item 3 lands, agents should state in their reports what they ran on the box and when, so a
human-readable trail exists even though the system-level one is ambiguous.
