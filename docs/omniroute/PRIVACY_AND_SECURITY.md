# OmniRoute privacy and security

## Data classes

| Class | Gateway rule |
| --- | --- |
| PUBLIC | Approved provider is allowed. |
| INTERNAL_SANITIZED | Approved provider after secret/PII redaction. |
| CUSTOMER_SANITIZED | Not enabled for OmniRoute without provider-specific privacy approval. |
| SENSITIVE_LOCAL_ONLY | Do not send externally. |
| PROHIBITED_EXTERNAL | Reject; no fallback. |

`app/platform/safe_ai_payload.py` masks phone, email, GST, PAN, addresses, WhatsApp
identifiers, API keys and OAuth-like tokens. `free_ai.py` applies masking and performs
provider safety checks before external provider dispatch. The tested default behavior
is fail-safe for the optional OmniRoute client: it is unavailable unless both flag and
local API key are present.

Never send `.env` data, credentials, customer records, raw logs, raw transcripts,
payment details, access headers, cookies, or dashboard-exported secrets to OmniRoute.
Never grant OmniRoute or an underlying provider a repo/worktree mount, shell, Git,
browser, MCP, database, Redis, VPS, or production credential. Code excerpts are
allowlisted repo-relative paths, maximum eight per packet; `.git`, `.env`, `data`,
`logs`, `memory`, secrets, backups, absolute paths, and traversal are rejected.
Provider output is `UNTRUSTED_PROVIDER_OUTPUT`: it may be reviewed by a governor but
cannot drive control flow or authorize any side effect.
Review records contain bounded metadata only and redact secret-shaped text. Separate
32+ character Claude/ChatGPT secrets HMAC-sign the exact task, decision, artifact hash,
summary, timestamp and nonce. Five-minute expiry, 30-second future-skew tolerance,
constant-time comparison, row locking and nonce-fingerprint replay detection fail closed.
The loopback-only submitter never returns a root secret and each governor needs only its
own scoped credential, not an admin token. Promotion still requires both authenticated
governors on the current proposal SHA-256. This proves credential possession, not model
cognition; the trusted governor process remains responsible for real review.

The automated Claude reviewer is a one-artifact, no-tools process in a neutral temporary
directory. It receives proposal text through stdin, not a repository path, and receives
no project/API/signing secrets. Its strict JSON verdict must echo the locally computed
SHA-256 before the parent process can submit it. The untrusted-data rule is system-level,
and the parent independently rejects non-string JSON fields. A Codex `read-only` sandbox is not used
for ChatGPT governance because it can still read local files; that lane stays manual and
fails closed until a tool-less transport exists.
Do not claim provider zero-data retention unless it is specifically verified for the
chosen provider and request path.
