# Config & Environment

- Static config: `from app.config import settings` (pydantic-settings, reads `.env`). Runtime-flippable flags: `os.getenv` at call-time.
- Never `os.environ.get()` for values that may live only in `.env` — pydantic-settings loads them, plain environ does not.
- Secrets live ONLY in `.env` (gitignored) — never in code, docs, or scripts. Env var NAMES are ok to reference.
- **Ports:** app listens on 8080 inside the network, published as 8000 on host. Container-to-container URL = `http://app:8080/...`; host/curl = `127.0.0.1:8000`. Writing 8000 in-network = silent ECONNREFUSED.
