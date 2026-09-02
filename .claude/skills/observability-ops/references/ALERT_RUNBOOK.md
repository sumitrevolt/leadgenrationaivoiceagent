# Alert runbook — add, verify, roll back

On-demand reference for `observability-ops`. Load this when actually changing a rule,
a route, or a scrape target; the SKILL.md body only carries the summary.

## 1. Add or change a rule

1. Write the rule in `monitoring/alert_rules.yml` — PromQL `expr`, a `for:` window,
   `labels: {severity: critical}`, and `annotations` a human can act on.
2. Reload Prometheus. Config is bind-mounted, and a plain restart does **not** reliably
   re-read it:

   ```
   docker compose -f deploy/compose/docker-compose.observability.yml up -d --force-recreate prometheus
   # or, inside the container: kill -HUP 1
   ```

3. Route it in `monitoring/alertmanager.yml` (`severity="critical"` → `email-admin`,
   1h repeat interval), then validate before recreating:

   ```
   docker exec leadgen_alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
   ```

Every new critical rule needs `for:` plus a repeat interval, or the first flap becomes an
alert storm and operators start ignoring the channel.

## 2. Verify (all of these, not a subset)

| Check | Expected |
|---|---|
| `amtool check-config` | valid |
| target container | `status=running`, `restarts=0` |
| app `/metrics` | 200 |
| Grafana :3000 | up |
| flower :5555 | reachable **through an SSH tunnel only** |
| celery-exporter :9808/metrics | 200 |
| test alert | actually fires **and** the email arrives |

"Alert add ho gaya" without a firing proof is not evidence.

## 3. Roll back

- Bad rule or route → revert `monitoring/alert_rules.yml` / `monitoring/alertmanager.yml`
  and `up -d --force-recreate <svc>`.
- Crash-loop → go back to a minimal config. Tempo taught this one: unsupported
  `ingester` / `compactor` fields in `monitoring/tempo.yaml` were rejected by the image
  schema and produced 329 restarts. Keep server + distributor + storage only.

## 4. Two traps that cost real time

- A **missing** bind-mount file makes Docker create a *directory* in its place and the
  mount silently misbehaves. Create the file first, then `up`.
- The app-level `ops_watchdog` emails too, and it is **not** Alertmanager. If the app is
  down, `ops_watchdog` is down with it — Alertmanager and Uptime Kuma are what still page.
  Keep both layers.

## 5. Secret-safe

The SMTP password never lands in committed config: Alertmanager reads
`smtp_auth_password_file: /etc/alertmanager/smtp_pass`, and `monitoring/alertmanager_smtp_pass`
is gitignored and written on the VPS from `.env` `SMTP_PASSWORD` via a compose extra mount.
`FLOWER_USER` / `FLOWER_PASSWORD` and the Grafana credentials live in `.env` the same way.
Run the repo secret-scan gate (`check_secrets.py`, under the repo's own script directory)
on the diff before shipping.
