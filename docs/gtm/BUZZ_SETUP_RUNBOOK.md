# Buzz Setup Runbook — End-to-End

**Status:** CODE-PRESENT, relay LIVE, Boss dry-run proven, real start WAIT owner
**Prod SHA:** `963ee800`
**Last verified:** 2026-08-15

## Kya hai Buzz?

Buzz = coding tools (Cursor, OpenCode, FreeBuff) + Boss coordination ka relay system.
Ye **32nd STAFF nahi hai** — ye ek interface hai existing control plane ka.

## Prerequisites

1. Desktop app running (Buzz Desktop)
2. Local relay at `ws://127.0.0.1:3100` ( canonical target)
3. Boss identity `1b13cecc` (canonical Boss)
4. `STAFF_BUS_ENABLED=OFF` (correct — bus is code-present, not live)

## Step 1: Relay Status Check

```bash
# Local relay liveness
curl -s http://127.0.0.1:3100/_liveness

# Expected: {"status":"ok"}
```

If relay is down:
```bash
# Restart relay (Desktop manages this)
# Or manual:
python scripts/buzz_local_workspace.py
```

## Step 2: Membership Verification

```bash
# Check canonical Boss membership
python scripts/buzz_canonicalize_boss.py --dry-run

# Expected: Boss 1b13cecc active on all 7 channels
```

If membership is wrong:
```bash
# Apply canonical membership
python scripts/buzz_canonicalize_boss.py --apply

# Rollback if needed
python scripts/buzz_canonicalize_boss.py --rollback
```

## Step 3: Harness Start (Owner One-Command)

**Verified 2026-08-15:** dry-run EXIT 0, relay LIVE `ws://127.0.0.1:3100`, `buzz-acp.exe` found at `%LOCALAPPDATA%\Buzz\buzz-acp.exe`.

Owner runs on their Windows machine:

```bash
python scripts/buzz_start_harness.py --agent Boss
```

This reads the private key from Windows Credential Manager (owner machine only), spawns `buzz-acp.exe` with `--subscribe mentions`, and logs to `%LOCALAPPDATA%\Buzz\harness-boss.log`.

**Then:** Wait ≥600s (7-8 min typical), post `@Boss status check` in `#admin` channel.

**Expected:** Boss replies within 7-8 minutes with correlated evidence.

If harness doesn't start:
- Check Buzz Desktop is signed in (credential store must have Boss key)
- Check `BUZZ_RELAY=ws://127.0.0.1:3100` in env
- Check `%LOCALAPPDATA%\Buzz\buzz-acp.exe` exists
- Check log at `%LOCALAPPDATA%\Buzz\harness-boss.log`

## Step 4: Canary Proof

After Boss harness starts:
1. Post `@Boss status check` in `#admin` channel
2. Wait ≥600 seconds (7-8 min typical)
3. Verify correlated reply with nonce match
4. Record evidence in `docs/evidence/`

## Step 5: Comb (Optional)

Only after Boss proof:
1. Comb = read-only reviewer infrastructure
2. Requires NIP-OA auth_tag (owner Desktop Save)
3. `auth_tag=null` = Comb WAIT

## Troubleshooting

| Symptom | Fix |
|---|---|
| Relay 404 | Desktop not running or port mismatch (3100 canonical) |
| 403 membership_required | Owner pubkey mismatch — re-run `buzz_canonicalize_boss.py` |
| 400 not a channel member | Channel memberships empty — re-run `buzz_local_workspace.py` |
| Boss no reply | Harness not started — run `buzz_start_harness.py --agent Boss` |
| Comb no reply | NIP-OA not minted — owner Desktop Save required |

## Flags

| Flag | Current | Notes |
|---|---|---|
| `STAFF_BUS_ENABLED` | OFF | Correct — bus is code-present, not live |
| `COORDINATION_HUB_ENABLED` | 1 | Live — thin Owner OS projection |
| `BOSS_DECISION_GOVERNANCE` | OFF | Wait owner auth |

## Evidence

- Relay liveness: `ws://127.0.0.1:3100/_liveness` = ok
- 31/31 synthetic canary: PASS (2026-08-12)
- Boss dry-run: EXIT 0 (canonical `1b13cecc`)
- Comb auth_tag: null (WAIT owner)
