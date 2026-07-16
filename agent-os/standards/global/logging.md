# Logging

```python
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
```

- One logger per module, always via `setup_logger(__name__)`. Sentry auto-attaches in production.
- Never log secrets or PII — delivery/email logs keep provider/status/class + counts only, never recipient address or body (ADR-092).
- Loud beats silent: a gate/canary that changes behaviour must announce itself in logs and results (dry-run flag lesson, ADR-098).
