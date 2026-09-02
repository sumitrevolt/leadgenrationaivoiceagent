# Boss harness canary — owner click (not agent sandbox)

Canonical Boss pubkey prefix: **`1b13cecc`**. Comb Desktop Save **sirf** iske baad.

## Already READY (agent)

```text
python scripts/buzz_start_harness.py --agent Boss --dry-run
```

Dry-run prints relay + harness + command, **private key nahi padhta**, process start nahi. Local relay default `ws://127.0.0.1:3100` when `BUZZ_RELAY` set.

## Owner real start (sandbox agents yahan rukte hain)

Credential Manager se Boss key read + long-running ACP spawn = Desktop/owner machine. Agent sandbox isko block karta hai — yahi expected.

```text
python scripts/buzz_start_harness.py --agent Boss
```

Phir Buzz **`#admin`** me `@Boss` canary. Wait **≥600s**. Stop = ek reply + Evidence line.

Comb: CODE-READY. Save pehle = silent second identity. Todo 5 reply ke baad hi Desktop Save.

Hub live `COORDINATION_HUB_ENABLED=1` — interface, **32nd STAFF nahi**, production control plane nahi.

## Do not

- Agent session se real start
- `--dry-run` ko “Boss LIVE” mat bolo
- Voice/Swara path
- Buzz ping-pong / 4th workstream
