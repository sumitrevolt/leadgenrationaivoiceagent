# Revenue Generation Automation Max — SAFE (owner-locked 2026-08-05)

## Outcome lock
- **P0:** 2nd paid Marketing customer via Hot Queue `/app/inbox` + real ₹1,999 UPI ledger-proof + onboard/first-value.
- **P1:** Safe additive Automation Max wiring only (no rebuild).
- Fake payment / synthetic lead / readiness-only claim ≠ revenue.

## Workstreams (max 3)
| ID | Focus |
|----|--------|
| WS-GTM1 | Hot Queue ops path + UPI→onboard wire (P0) |
| WS-AM1 | Safe-pack flags + Mission Control/blueprint glue (P1) |
| WS-R3 | Estique / pay-truth 2nd customer ledger (keep) |

Parked: WS-PRF1 (PR #248 Draft), WS-CH1, WS-R1 observe-only.

## Exact safe-pack env keys (repo truth)
| Capability | Keys |
|------------|------|
| Flow Runner | `FLOW_RUNNER=1` (+ cron: `FLOW_AUTO_TRIGGERS=1`) |
| Process Engine | `PROCESS_ENGINE=1` + autostart tick: `PROCESS_AUTOSTART=1` |
| Revenue Trends | `REVENUE_TRENDS=1` |
| Draft-only content auto-submit | `CONTENT_APPROVAL_AUTO=1` (queue submit only — not publish/approve) |

Do **not** enable: cold WA, `REPLY_AUTO_SEND`, open `UPI_AUTO_ACTIVATE`, voice flips, `ALLOW_TOS_SCRAPE`, Creative OS / external-agent, auto social publish, compliance weaken, **`DUNNING_ENGINE`** (issue #307 owner: stays OFF / dormant — not in Automation-Max `WANT_SAFE` nor this Safe Pack).

## Automation-Max enabler vs Safe Pack (do not conflate)
- **Safe Pack** (`scripts/safe_pack_flags.py`): exact 6 keys above — Mission Control highlight / canary only.
- **Automation-Max VPS enabler** (`scripts/vps_enable_automation_max_flags.py`): broader draft/ops/health set (`WANT_SAFE`). As of 2026-08-10: `DUNNING_ENGINE` removed from default `WANT_SAFE` and classified `OWNER_GATED` (truthy enable refused). Script name ≠ authorization.

## P0 code contract
1. Pay-chase Hot Queue cards clearable via Done
2. UPI activate → `onboard_client(client_id)` (not AUTO_ONBOARD-gated sweep alone)
3. Inbox 1-click `/start` CTA for inquiry/payment_chase

## Implementation status (2026-08-05 session)
- **CODE_READY:** yes (branch commits)
- **MERGED / DEPLOYED / LEDGER_PAID / SAFE_PACK_CANARY_VERIFIED:** no
- **Code:** paychase Done/Park · UPI→`onboard_client(cid)` · inbox `/start` CTA · Safe Pack MC strip · canary tooling
- **Env:** Safe Pack stays OFF; not bundled with code deploy
- **Revenue:** still 1 paid (Jiya); readiness ≠ ledger PAID

## Verify
Targeted pytest + `prod_check` + separate evidence for any VPS env flips.
