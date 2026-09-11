> Verbatim: the 5-min daily standup script and dashboard/alerting integrations. See SKILL.md for the 6-step check.

## Daily Standup Script (5 min)

```bash
#!/bin/bash
# Add to your morning standup ritual

echo "🤖 Automation Health Check ($(date))"
python scripts/automation_health_audit.py --daily-check --format=json | \
  jq '{verdict: .verdict, checks: {alive: .checks.alive, budget: .checks.budget, anomalies: .checks.anomalies}}'

# If red, show details
VERDICT=$(python scripts/automation_health_audit.py --daily-check --format=json | jq -r '.verdict')
if [ "$VERDICT" != "green" ]; then
  echo ""
  echo "⚠️  Issues detected! Full report:"
  python scripts/automation_health_audit.py --daily-check
  echo ""
  echo "💡 Escalation: See docs/.claude/skills/audit-automation/SKILL.md"
fi
```

---

## Integration with Dashboards

- **Grafana**: Query `automation_health` metrics from Prometheus (if enabled)
- **Slack alert**: Watchdog job (`ops_watchdog.py`) sends red checks to Slack
- **Email**: Daily digest includes automation health score
- **API**: `GET /api/growth/infra/automation-health` for custom integrations
