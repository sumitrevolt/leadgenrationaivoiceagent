# Owner Decision Pack — Outbound Calling DID Plumbing (PLT-163)

**日期**: 2026-09-15
**工作流**: 工作流 2（系统设计，决策部分）· 只读研究，无代码改动
**参与成员**: did-research（Explore agent，read-only）；主理人汇编
**证据标签**: CODE-PRESENT（本地代码核实）· PRODUCTION-PROVEN（生产实测，引自 docs 记录）· ASSUMED（owner/console 侧未证实）

---

## TL;DR

- Call loop ab **idempotency-stuck NAHI** hai (PLT-162/164 verified) — ab real blocker sirf **provider DID ownership** hai: Vobiz `from=918069879757` ko "not owned by this account" reject karta hai.
- **Smallest unblocking action (minutes)**: Smartflo console me DID `+918069879757` ka destination VOICE Bot pe set karo → `.env` me `TELEPHONY_PROVIDER=tata_smartflo` + `TATA_SMARTFLO_ENABLED=1` → restart. Loop **transactional lane** pe turant chalega.
- Promotional (cold) calls ke liye 140-DID/channels ya DLT_APPROVED chahiye — Jio 30ch SIP order (Call Soft 0820879109003) in-flight hai (ASSUMED).

---

## 1. Outbound-number knob (CODE-PRESENT)

| Config | File | Notes |
|---|---|---|
| `VOBIZ_CALLER_ID` (fallback `VOBIZ_SIP_USER`) | `app/config.py:94-97`; used at `app/telephony/vobiz_handler.py:138` | Vobiz `from` number. Code side change = `/opt/leadgen/.env` edit + restart. |
| `TELEPHONY_PROVIDER` | `scripts/fire_calls.py:59-71`; default `vobiz` (`config.py:87`) | Provider routing. |
| `TATA_SMARTFLO_ENABLED` + `TATA_SMARTFLO_API_TOKEN`/`_API_KEY` | `app/api/telephony_vobiz.py:288-326` | Smartflo stream routing. |
| `JIO_SIP_HOST/USER/PASS/DID` + `JIO_TRUNK_ENABLED` | `app/telephony/trunks.py:86-106` | Jio = **alag rail** (FreeSWITCH gateway), Vobiz env swap NAHI. |

## 2. DID switching path (CODE-PRESENT)

- Vobiz DID add/swap ke liye **koi code/UI nahi** — console-only (Vobiz dashboard). Status-only endpoint: `GET /api/telephony/vobiz/status` (`telephony_vobiz.py:755-802`).
- Matlab: naya owned DID milne par code-side kaam sirf `.env` + restart hai.

## 3. Smartflo interim fallback (viable, with gates)

`TELEPHONY_PROVIDER=tata_smartflo` loop ko CallManager/queue dialer pe route karta hai (`fire_calls.py:335-340`), same dial_gate + ComplianceGate + kill-switch (`tata_smartflo_handler.py:205-274`). Gates:

1. **Smartflo portal DID→destination set hona zaroori** — `GET /v1/my_number` abhi `destination:null` (PRODUCTION-PROVEN, `7_DAY_REVENUE_PLAN.md:157-162`; 2026-09-12 root-cause proven). API se destination set nahi hota (422 proven).
2. TRAI window pre-check har batch se pehle (`campaign_compliance.py:23-43`).
3. Readiness score ≥70 gate (`campaign_compliance.py:46-59`).
4. `918069879757` non-140 DID → **transactional lane only** (`trunks.py:104/125`); promotional ke liye `DLT_APPROVED=1` chahiye (`compliance.py:409-410`).

## 4. Failure blast-radius — PLT-165 interaction (CODE-PRESENT, confirmed independently)

Generic FAIL me `mark_called` nahi hota (sirf success karta hai, `fire_calls.py:224-227`) → DB poison nahi. LEKIN launch-spine ON hone par FAIL branch (`fire_calls.py:235-240`) `release_session_slot` / `session_idem_release` nahi karta (compliance branch `:228-234` karta hai) → har provider FAIL ek session slot + 24h idem claim `lead:{phone}` hold karta hai (`voice_launch.py:1043-1058`) → wahi lead aage batch me `SKIP(already_dispatched_this_session)` + session cap-out (`fire_calls.py:208-213`). **Yehi PLT-165 fix ka target hai** (agent plt165-fix apply kar raha hai).

## 5. Compliance constraints for any Jio-DID switch (CODE-PRESENT)

- TRAI windows: promo 09:00–19:00 IST (clamped ≤21:00), txn 09:00–21:00 (`compliance.py:241-253`, `campaign_compliance.py:30-33`).
- DND prod me fail-CLOSED (`compliance.py:174-195`) — Jio DID bhi isi gate se guzarta hai.
- Jio mobile SIP DID = non-140 → **transactional/service lanes ONLY, cold promo forbidden** (`trunks.py:37-41,104`; `JIO_SIP_SETUP_PLAN.md:5`).
- `DIAL_TEST_MODE` default ON promo ko non-allowlisted numbers pe block karta hai (`dial_gate.py:62-72,219-223`).

## 6. Smallest unblocking actions (ranked)

| # | Action | Channel | Time | Unblocks |
|---|--------|---------|------|----------|
| 1 | Smartflo console: DID `+918069879757` destination → VOICE Bot endpoint | owner console | minutes | txn calls via Smartflo |
| 2 | `.env`: `TELEPHONY_PROVIDER=tata_smartflo` + `TATA_SMARTFLO_ENABLED=1` + restart (canonical `deploy_vps.sh`) | owner deploy | minutes | loop live on txn |
| 3 | Jio Call Soft 0820879109003 delivery confirm (DID + SIP creds) | owner/vendor | days | 30ch SIP + 140 lane options |
| 4 | Vobiz console: account pe truly-owned number confirm (911171366938 revoked ke hisaab se, PRODUCTION-PROVEN per `docs/HERMES_OWNER_ADMIN_STATUS_2026-08-30.md:39`) | owner console | — | Vobiz rail valid from-number |

## ⚠️ 待完善 / 已知局限

- Smartflo/portal truth `destination:null` reading docs se (2026-09-12 PROVEN) hai — commit se pehle **live re-probe** karna (`GET /v1/my_number` from VPS).
- Vobiz "not owned" error live log se; account-owned-number list sirf console se confirmed hoga.
- Jio order status = ASSUMED.

## 📚 数据来源

- did-research agent read-only report (file:line cited inline).
- `scripts/fire_calls.py` · `app/api/telephony_vobiz.py` · `app/telephony/vobiz_handler.py` · `app/telephony/trunks.py` · `app/telephony/tata_smartflo_handler.py` · `app/api/compliance.py` · `app/api/campaign_compliance.py` · `app/dial_gate.py` (paths per agent citations) · `7_DAY_REVENUE_PLAN.md:157-162` · `docs/HERMES_OWNER_ADMIN_STATUS_2026-08-30.md:39` · `JIO_SIP_SETUP_PLAN.md`.

---

> 本 pack human owner console/vendor actions require karta hai — AI side ki sab kuch CODE-PRESENT/LOCAL level par verified hai; production claims docs-se-carried hain, commit se pehle live re-probe karo.
