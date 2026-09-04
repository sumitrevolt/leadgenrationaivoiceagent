## Code Review: Security and Correctness Audit

### 概要
FastAPI SaaS monolith, LeadGen AI. Focused on telephony hooks, manual payment reconciliation, and multi-tenant RAG. Critical infrastructure uses fail-closed patterns for telephony and manual UPI verification.

### 严重问题
| # | 文件 | 行 | 问题 | 严重度 |
|---|------|------|-------|---------|
| 1 | app/telephony/telephony_readiness.py | 66 | False-green readiness check for caller_id. Only checks presence, not account-ownership. | 🟠 High |
| 2 | app/telephony/stream_token.py | 28 | Hardcoded fallback for `_secret()`. | 🟡 Medium |
| 3 | app/voice_agent/free_ai.py | 1155 | Realtime race concurrency leak: cancels the loser, but not awaiting the cleanup or handling potential response stream leaks on the loser's aclose(). | 🟡 Medium |
| 4 | app/telephony/voice_launch.py | 1082 | `record_provider_result` trip_circuit can be bypassed by non-provider errors during high-frequency retries. | 🟡 Medium |

### 改进建议
| # | 文件 | 行 | 建议 | 类别 |
|---|------|------|------|------|
| 1 | app/telephony/telephony_readiness.py | 66 | Replace simple `_env("VOBIZ_CALLER_ID")` check with an outbound verification probe using the dialer. | Correctness |
| 2 | app/telephony/stream_token.py | 28 | Remove hardcoded secret; force `VOBIZ_STREAM_SECRET` via validator. | Security |
| 3 | app/voice_agent/free_ai.py | 1155 | Add explicit `try/except/finally` around stream loser cleanup to ensure resource closure. | Performance |

### 做得好的地方
- `app/api/billing.html`: The Stripe webhook stub effectively prevents accidental entitlement granting because the implementation logic was physically removed, not just disabled.
- `app/telephony/answer_token.py`: HMAC-based answer-URL tokens effectively prevent CRM DoS via IDOR (e.g., press-9 opt-out).

### 结论
Needs Discussion: Focus on the false-green telephony readiness report and the outbound dialer loop logic.
