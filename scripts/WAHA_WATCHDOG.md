# `scripts/waha_watchdog.py` — WAHA session watchdog

Polls the WAHA (self-hosted WhatsApp) session, restarts it when it is `FAILED`/`STOPPED`,
and writes one health record per poll. It is the only thing on the VPS that reports WAHA
session state between app requests.

**Supervision status: none.** There is **no systemd unit and no cron entry** for this
script on the VPS. It is started by hand as a bare `python3 waha_watchdog.py` process, so:

- it dies with the shell/session that started it,
- it is not restarted after a VPS reboot or a crash,
- if it is not running, **nothing reports WAHA session state at all** — the health file
  just goes stale and looks unchanged.

Check whether it is running / restart it:

```bash
pgrep -af waha_watchdog                 # empty output = not running
cd /opt/leadgen && setsid nohup python3 scripts/waha_watchdog.py >>/tmp/waha_watchdog.out 2>&1 &
```

A systemd unit (`Restart=always`) is the right fix and is deliberately **not** created
here — it is an owner/VPS decision, same class as the other host-supervision changes.

## History (why the file is in git now)

It used to exist only on the VPS, so nothing could diff it. Two hardcoded host ports had
drifted apart: the checked-in WAHA compose
(`deploy/compose/docker-compose.waha.yml`) publishes `127.0.0.1:3111:3000`, while the copy
running on the VPS pointed at `3002`. Whichever side was wrong, the observable result was
the same — every poll wrote

```json
{"waha_status": "UNKNOWN", "raw": {"error": "Connection refused"}}
```

to `data/wa_health_check.json`: a false negative invisible for weeks, because an untracked
file cannot be reviewed, tested or diffed, and `UNKNOWN` (service unreachable) looked
exactly like an unreadable session status. The watchdog now distinguishes those states
explicitly and takes the URL from configuration instead of a literal.

## Configuration

Env var first, then the default shown (defaults match this VPS layout).

| Env var | Default | Meaning |
| --- | --- | --- |
| `WAHA_WATCHDOG_URL` | `http://127.0.0.1:3111` | WAHA base URL. The default is the **host-published** port from the checked-in WAHA compose (`127.0.0.1:3111:3000`); in-network the app talks to `waha:3000`. **If your VPS maps WAHA to a different host port, set this variable** — do not hardcode it in the script again. |
| `WAHA_WATCHDOG_SESSION` | `default` | WAHA session name. |
| `WAHA_WATCHDOG_ENV_FILE` | `/opt/leadgen/.env` | File the API key is read from when `WAHA_API_KEY` is not in the environment. |
| `WAHA_WATCHDOG_HEALTH_FILE` | `/opt/leadgen/data/wa_health_check.json` | Health record written on every poll. |
| `WAHA_WATCHDOG_LOG_FILE` | `/opt/leadgen/data/waha_watchdog.log` | Append-only log (also printed to stdout). |
| `WAHA_WATCHDOG_INTERVAL` | `60` | Seconds between polls (floor 5). |
| `WAHA_WATCHDOG_TIMEOUT` | `10` | Per-request timeout in seconds. |

The API key is **read, never carried**: `WAHA_API_KEY` from the environment, else from the
`.env` file above. There is no hardcoded fallback and none may be added.

## Health record

One JSON object per poll in `WAHA_WATCHDOG_HEALTH_FILE`:

```json
{
  "timestamp_ist": "2026-09-14T12:00:00+05:30",
  "waha_url": "http://127.0.0.1:3111",
  "state": "logged_out",
  "actionable": "owner_scan_qr",
  "reachable": true,
  "session_status": "SCAN_QR_CODE",
  "waha_status": "SCAN_QR_CODE",
  "raw": {"status": "SCAN_QR_CODE"}
}
```

`state` values and what they mean:

| `state` | `actionable` | Meaning |
| --- | --- | --- |
| `working` | `null` | Session linked and healthy. |
| `logged_out` | `owner_scan_qr` | WAHA answered, session is `SCAN_QR_CODE` / `UNPAIRED` / `NOT_CREATED` — **reachable**, owner must scan the QR. |
| `failed` / `stopped` | `watchdog_restart` | WAHA answered, session needs a restart; the watchdog POSTs `/restart`. `restart_ok` records the outcome, and a failed restart re-labels `actionable` to `restart_failed`. |
| `unreachable` | `check_waha_service` | No answer from WAHA (wrong port, container down). `raw.error` holds the reason. |
| `auth_error` | `check_waha_api_key` | WAHA answered with an HTTP error (usually 401) — the service is up, the key is wrong. |
| `unknown` | `inspect_session` | Answered with a status this script does not model. |

The legacy `waha_status` key is kept for continuity: it is the WAHA status when there is
one, otherwise the `state` in caps. A reader can therefore never again mistake
"unreachable" for "the session reported UNKNOWN".

**Note:** nothing in this repository reads `data/wa_health_check.json` today — the file is
the hand-inspection surface (and the log is the alert surface). If a dashboard or an
alert is meant to consume it, that consumer does not exist yet.

## Tests

`tests/test_waha_watchdog.py` fakes the HTTP layer (`urllib.request.urlopen`) and pins the
two states that used to be conflated: a reachable `SCAN_QR_CODE` session is reported as
`logged_out` (not an error), and a refused connection is reported as `unreachable`.

```bash
.venv/Scripts/python.exe -m pytest tests/test_waha_watchdog.py -q --timeout=120
```
