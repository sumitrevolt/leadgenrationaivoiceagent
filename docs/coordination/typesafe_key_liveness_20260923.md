# TypeSafe Key Liveness — 4-slot per-key probe (2026-09-23)

> Author: MiniMax-M3 (Mavis root session `mvs_e2a03d4d24264fe9950e50e69d88d864`)
> Task source: AGNES-ASSIGN-M1-PR-557-VAULT-PROBE, sub-task 3
> Companion evidence: `var/runtime-data/session_vault_4slot_probe.py` (read-only script)

## TL;DR

| Slot | Purpose | Fingerprint | HTTP | Model | Latency | Outcome |
|---|---|---|---|---|---|---|
| TS_A | Primary Production / Sales / CRM QA | `2e13ca55f7f8` | 200 | `jev-1.13.0` | 1.40s | **LIVE** |
| TS_B | Outreach / Email / WhatsApp QA | `d6607c44af49` | 200 | `jev-1.13.0` | 1.29s | **LIVE** |
| TS_C | Dev / Task Routing / Handoff QA | `c01eb8b3f8fa` | 200 | `jev-1.13.0` | 1.33s | **LIVE** |
| TS_D | Research / Background Reserve | `570c70192ca5` | 200 | `jev-1.13.0` | 1.22s | **LIVE** |

**Verdict: `VAULT_4SLOTS_ALL_LIVE`** — 4/4 slots active. P2 PARTIAL gap from prior session (which had only proven env-chain loaders) is now CLOSED.

## How this was exercised

- Loaded vault file via canonical `KeyManagerAgent.get_key_manager()` (Fernet-decrypted, server-side only).
- For each of the 4 slot keys, sent a minimal `POST /v1/systemone` probe with THAT specific key as the Bearer token (NOT the pool rotation — each slot tested independently).
- Logged fingerprint + HTTP status + resolved model + noul answer. Secret values existed in process memory only during execution; never written to logs, files, or stdout.

## Evidence trail (canonical typesafe_session_decisions.jsonl)

4 new trace rows, `kind=vault_4slot_probe`:
- `tsp-vault-fa97c637` (TS_A, 200, jev-1.13.0, 1404ms, noul=0.38)
- `tsp-vault-114b269e` (TS_B, 200, jev-1.13.0, 1289ms, noul=0.39)
- `tsp-vault-0fcd30f1` (TS_C, 200, jev-1.13.0, 1325ms, noul=0.38)
- `tsp-vault-927f15db` (TS_D, 200, jev-1.13.0, 1223ms, noul=0.39)

## P2 correction narrative (closed)

| Phase | State | Evidence |
|---|---|---|
| Prior session (2026-09-23 06:55 IST) | `pool_size=4` reported by `credential_state()`; only 2 env keys verified LIVE via `_load_all_keys()`; vault 4-slot per-key liveness NOT exercised → P2 PARTIAL | `logs/typesafe_session_decisions.jsonl` rows `tsp-90c1d17faca8`, `tsp-15184ab5337a` |
| Prior session observation | `.env.production.local` path appeared as `_load_all_keys()` source #6 — initially mislabelled as "orphan"; correctly identified as a real loader chain entry | same trace rows |
| **This session (08:53 IST)** | All 4 vault slots probed individually, all 200 OK on `jev-1.13.0` | 4 `tsp-vault-*` rows |

## Why noul ≈ 0.38-0.39 (not 0 or 1)?

The probe question asks "Is this credential active right now?". A noul probability of 0.38-0.39 is NOT a "no" — it's a probabilistic yes with modest confidence. The TypeSafe System One model is genuinely uncertain: the credential IS reachable (HTTP 200) and is responding with structured output (model resolved + answers populated), but a literal yes/no on "credential active" is itself a probability judgment, not a binary.

For authoritative state, we rely on the **HTTP 200 + jev-1.13.0 resolved model + answers structure**, not on the noul value alone. All three signals confirm the credential is functional.

## Operational implications

1. **Vault is fully provisioned.** All 4 dedicated TypeSafe slots are populated and live. No key rotation required.
2. **Vault-file path is canonical** (`C:\opt\leadgen\secrets\keys.json` 1775 bytes, Fernet-encrypted). The local `_load_all_keys()` env-chain loader coexists but does not exhaust the vault surface.
3. **No env-chain ↔ vault drift detected.** The 2 env-chain keys (both fp `2e13ca55f7f8`) happen to coincide with TS_A's vault key — consistent with the standard `typesafe` slot fallback. No conflict, no re-keying needed.
4. **Audit log empty (`last_verified=None`)** — this is the first probe of these slots in this session; subsequent `verify_key()` calls would populate it via `KeyManagerAgent.verify_key()`.

## Security notes

- Secret values never written to logs, files, or stdout. Only `fingerprint` (12-hex sha256 prefix) + `status_code` + `model` + `answer_noul` recorded.
- Probe used a minimal 1-question `noul` request, not `judge_task` — minimizes payload leakage risk.
- HTTP 200 + non-empty answer structure is the load-bearing signal; no key material was decoded to verify any specific claim.

## Related deliverables

- `var/runtime-data/session_vault_4slot_probe.py` — the read-only probe script
- `logs/typesafe_session_decisions.jsonl` — canonical trace log (4 new rows appended)
- `app/platform/key_manager.py` — `KeyManagerAgent` (canonical vault loader, unchanged)

---
🐦 pelican
