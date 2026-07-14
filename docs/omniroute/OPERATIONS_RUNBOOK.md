# OmniRoute operations runbook

## Safe status check

Use the Node 22 executable explicitly:

```bash
export PATH="/root/.nvm/versions/node/v22.23.1/bin:$PATH"
omniroute doctor
tmux ls
ss -ltnp | grep -E '20128|20129'
```

Expected operational state is one gateway child process, tmux session `leadgen-omni`,
API port 20128, WS port 20129, version 3.8.46, and a 2048 MB configured memory limit.
`doctor` warns that 20128 is in use when the gateway is healthy; it is not a failure.
Use the repository launchers, which export `OMNIROUTE_MEMORY_MB=2048`; a controlled
Doctor probe verified that setting on 2026-07-14.

## Dashboard verification

Open `http://127.0.0.1:20128` in a fresh tab. Confirm dashboard navigation, provider
list, and each required provider detail page. If an old tab loops/reconnects while a
fresh tab works, document it as browser-session churn; do not delete configuration.

On 2026-07-13 a fresh tab showed no console warnings/errors while loading the dashboard
and Groq, Gemini, and Mistral detail pages.

For reconnect diagnosis, close stale OmniRoute dashboard tabs and run:

```bash
OMNI_HEALTHGUARD_WINDOW_SECONDS=20 bash scripts/omniroute-healthguard.sh
```

The healthy result is one process, zero active LiveWS clients when no dashboard is open,
and no high reconnect churn inside the requested time window.

## Credentials

The admin alone enters passwords, API keys, OAuth codes, and recovery codes in the
provider detail page. Never paste a credential into chat, terminal output, Git, docs,
or screenshots. After entry, run a single non-sensitive connection re-test and record
only its status/model count/latency.

## Disabled mode

Leave `OMNIROUTE_ENABLED` unset or `0`. This is the normal state and requires no
restart. LeadGen will continue with its direct provider chain.
