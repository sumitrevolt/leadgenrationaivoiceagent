# OmniRoute dual-governor review gate

## Goal

Require Claude and ChatGPT to approve the exact same sanitized proposal artifact before a DevTask may enter tests or staging.

## Boundary

- OmniRoute remains an untrusted text-only proposal source.
- Reviews persist only bounded metadata: governor, decision, proposal SHA-256, redacted summary, reviewer, timestamp, attestation version and nonce fingerprint.
- A new proposal resets old reviews by producing a new hash and empty review map.
- Missing, malformed, duplicated-governor, rejected, or mismatched-hash reviews fail closed.
- The generic transition endpoint and staging helper must enforce the same gate.
- Each governor gets one separate scoped HMAC secret; neither gets an admin token.
- Signed requests bind task/governor/decision/hash/summary/time/nonce, expire in five minutes, use row locking and reject replay.
- The submitter is loopback-only and never prints the secret or signing headers.
- No patch application, shell, Git, deploy, production data, or broad credential access is added.

## Contract-first steps

1. Pin hash, idempotent upsert, mismatch, rejection, and two-distinct-governor behavior.
2. Pin staging and generic-transition bypass resistance.
3. Add the review ledger helper and scoped HMAC review endpoint.
4. Hash runner output and preserve controlled metadata across worker reports.
5. Run targeted tests, production wiring check, secret scan, and diff review.
6. Add separate governor credentials, freshness/replay contracts, and a loopback-only submitter.
