# PR A — Tier-0 runtime-data code migration (design)

**Status:** design, not yet implemented · **Date:** 2026-07-28 · **Depends on:** #148, #159 (merged)

## 1. Why this PR exists

The runtime-data *foundation* shipped in #148: a resolver, a store manifest, a
deployment preflight, a mutable-path scanner and a debt ratchet. What did **not**
ship is any store actually using it. Measured on `aa93f3c`:

```
scanner summary        CANONICAL_RUNTIME_PATH = 1   (of 1127 findings)
app/ consumers of      app/telephony/voice_launch.py:280 — and that call validates
runtime_data                                          the kill file's path POLICY,
                                                      it does not resolve the store

gst_invoice.py     _STORE       = os.path.join("data", "invoices.jsonl")
upi_payments.py    _STORE       = os.path.join("data", "upi_payments.json")
email_unsub.py     _STORE       = Path('data') / 'email_suppression.jsonl'
dpdp.py            _AUDIT_FILE  = os.path.join("data", "dpdp_audit.jsonl")
clients_store.py   _CLIENTS_FILE= os.path.join("data", "marketing_clients.jsonl")
voice_launch.py    _kill_file   = Path(_env("VOICE_LAUNCH_KILL_FILE", "data/voice_launch_kill.json"))
platform_dial.py   _cfg_path    = Path(os.environ.get("PLATFORM_DIAL_CONFIG", "data/platform_dial.json"))
```

So copying `/opt/leadgen/data` to an external root would produce a copy nobody
reads, while the application keeps writing inside the checkout. A cutover marker
claiming `EXTERNAL_VERIFIED` on top of that would be false. **The code must move
before the data does.**

## 2. Authority state machine (the contract every migrated store obeys)

```
LEADGEN_RUNTIME_DATA_DIR unset
    -> LEGACY authority. The legacy in-checkout path is the sole read AND write
       target. Production behaviour is byte-for-byte unchanged, which is why
       merging PR A changes nothing in production.

LEADGEN_RUNTIME_DATA_DIR set, RUNTIME_DATA_CUTOVER_ENABLED unset/false
    -> MIGRATION-VALIDATION. The canonical target may be inspected, copied to
       and tested against. Production writers do NOT switch. This is the state
       the bulk copy runs in.

LEADGEN_RUNTIME_DATA_DIR set, RUNTIME_DATA_CUTOVER_ENABLED=1, marker VALID
    -> CANONICAL authority. External path is the only authority. No legacy
       write. No silent legacy read fallback: missing or malformed canonical
       data FAILS CLOSED.
```

The legacy fallback is a **bounded pre-cutover compatibility path**, never a
permanent "new path missing, quietly read the old one" rule — that rule is how a
cutover turns into split-brain nobody notices for a week.

## 3. Shared helper — `app/platform/runtime_data_authority.py` (new)

One function decides for every store, so eleven modules cannot drift apart:

```python
authority_path(store_id, *segments, legacy: str) -> Path
    # returns the ACTIVE path for this store under the state machine above
authority_mode() -> "LEGACY" | "MIGRATION_VALIDATION" | "CANONICAL"
authority_lock(store_id, *segments, legacy: str) -> Path   # beside the resolved file
authority_tmp(store_id, *segments, legacy: str, suffix: str) -> Path
```

Rules baked in, not left to call sites:

* resolved **at operation time**, never captured at import (a module constant is
  what makes a path impossible to redirect from a fixture that runs later);
* reads and writes call the **same** function — they cannot pick different roots;
* lock and temp files are derived from the **resolved** target, so five
  containers coordinate on one mount instead of taking five private locks;
* `store_path()`'s traversal rejection and production policy (absolute, exists,
  writable, outside the checkout) apply unchanged;
* in CANONICAL mode a missing file raises rather than reading the legacy copy.

## 4. The eleven Tier-0 stores

| store_id | module (writer/reader) | legacy path | target subpath |
|---|---|---|---|
| billing.invoices | `app/billing/gst_invoice.py` | `data/invoices.jsonl` (+`.lock`) | `billing/invoices.jsonl` |
| billing.upi_payments | `app/platform/upi_payments.py`, `app/platform/upi_config.py` | `data/upi_payments.json`, `data/platform_upi.json` | `billing/` |
| compliance.email_suppression | `app/platform/email_unsub.py` | `data/email_suppression.jsonl` | `compliance/email_suppression.jsonl` |
| compliance.wa_suppression | `app/marketing/wa_campaign_runner.py` | `data/wa_suppression.jsonl` | `compliance/` |
| compliance.consent_ledger | `app/telephony/consent_ledger.py` | `data/consent_ledger.jsonl` | `compliance/` |
| compliance.voice_suppression | `app/telephony/consent_ledger.py` | `data/voice_suppression.jsonl` | `compliance/` |
| compliance.dpdp_audit | `app/platform/dpdp.py` | `data/dpdp_audit.jsonl`, `data/dpdp_requests.jsonl` | `compliance/` |
| customers.identity | `app/marketing/clients_store.py` | `data/marketing_clients.jsonl` (+`.lock`, `.tmp`) | `customers/marketing_clients.jsonl` |
| telephony.calling_safety_config | `app/platform/platform_dial.py`, `app/telephony/dial_gate.py` | `data/platform_dial.json`, `data/dial_test_mode.json` | `telephony/` |
| telephony.dial_suppression | `app/telephony/call_feedback.py`, `app/telephony/dial_gate.py` | `data/dial_blocklist.json` | `telephony/dial_blocklist.json` |
| telephony.voice_kill_switch | `app/telephony/voice_launch.py` | `data/voice_launch_kill.json` (+`.tmp_kill`) | `telephony/voice_launch_kill.json` |

Per-store env overrides (`VOICE_LAUNCH_KILL_FILE`, `PLATFORM_DIAL_CONFIG`,
`DIAL_BLOCKLIST_FILE`, `DIAL_TEST_MODE_CONFIG`) keep their **existing
precedence**: an explicitly configured absolute path still wins. Only the
*default* moves from the checkout to the resolved authority.

## 5. Test matrix — ten contracts per store

1. env unset resolves the **exact** legacy path (production behaviour unchanged);
2. canonical env resolves under `/srv/leadgen-runtime/<target>`;
3. a root inside the Git checkout fails closed;
4. relative / missing / unwritable roots fail closed per resolver policy;
5. writes land only on the selected authority;
6. reads and writes cannot select different roots;
7. in CANONICAL mode, missing canonical data does **not** fall back to legacy;
8. lock and temp files sit beside the resolved target;
9. existing JSON/JSONL content stays byte- and record-compatible;
10. tenant isolation and public function signatures unchanged.

Shared parametrised harness + per-store specifics. Calling-safety stores also
re-assert: kill reader stays fail-closed, `VOICE_LAUNCH_KILL=1` keeps final
precedence, `PLATFORM_DIAL_DAILY=0` untouched.

## 6. Tier-0 ratchet

A new gate over the existing scanner: **for these eleven store ids, the
production writer/reader modules must contain zero uncontrolled
checkout-backed path findings.** Unlike the global debt ratchet (which only
forbids growth), this one demands the number reach zero and stay there.

## 7. Manifest transition — and why the gate does not weaken

PR A moves the eleven from `LEGACY_IN_CHECKOUT` to `DUAL_READ_PRE_CUTOVER`
(state already defined in the manifest). `EXTERNAL_VERIFIED` stays illegal until
copied data, checksums, marker, env activation and live write proof exist.

`DUAL_READ_PRE_CUTOVER` is not in `BLOCKING_STATES`, so `blocker_count` drops
21 → 10. That does **not** open the deploy gate — `deploy_denied()` additionally
requires `mode == EXTERNAL_VERIFIED`, which itself requires host **and** app
paths configured plus a VALID marker plus zero blockers, and separately requires
`RUNTIME_DATA_CUTOVER_ENABLED`. With the env unset the mode stays
`LEGACY_CHECKOUT_BACKED` and the deploy stays denied. Verified in
`scripts/runtime_data_preflight.py:163-188`.

## 8. Non-goals for PR A

No data copy · no marker · no env activation · no compose change · no
`/app/data:ro` · no dual-write · no behaviour change in production, because the
runtime root stays unset until the cutover window.

## 9. Suggested batching inside PR A

| batch | stores | why first/last |
|---|---|---|
| A1 | `telephony.voice_kill_switch`, `telephony.calling_safety_config`, `telephony.dial_suppression` | smallest files, already env-overridable, and the calling-safety contract gets the most test scrutiny — the right place to prove the pattern |
| A2 | `compliance.*` (email/wa/consent/voice suppression, dpdp_audit) | statutory ledgers; append-only semantics, no rewrite races |
| A3 | `billing.invoices`, `billing.upi_payments`, `customers.identity` | money and identity; invoice numbering and the `.lock`/`.tmp` companions need the most careful review |
```
