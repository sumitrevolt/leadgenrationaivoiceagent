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
Do not claim provider zero-data retention unless it is specifically verified for the
chosen provider and request path.
