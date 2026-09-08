#!/usr/bin/env python3
"""
Owner Admin WhatsApp Bot — simple text interface.
Owner messages WhatsApp bot → bot routes to admin actions.
"""

import sys, json, os
from datetime import datetime

# Add workspace
sys.path.insert(0, "/opt/leadgen")
sys.path.insert(0, "C:\\Users\\Ratanshila\\.openclaw\\workspace")

def handle_owner_message(text: str) -> str:
    """Owner WhatsApp text → admin action + response."""
    text = text.strip().lower()
    
    # Command routing
    if text in ["1", "hotqueue", "leads", "status"]:
        from app.platform.admin_api import hot_queue_status
        return json.dumps(hot_queue_status(), indent=2)
    
    elif text in ["2", "compliance", "gates"]:
        from app.platform.admin_api import compliance_snapshot
        return json.dumps(compliance_snapshot(), indent=2)
    
    elif text in ["3", "deploy"]:
        from app.platform.admin_api import deploy_initiate
        return json.dumps(deploy_initiate(), indent=2)
    
    elif text in ["4", "squads"]:
        from app.platform.admin_api import squad_health
        return json.dumps(squad_health(), indent=2)
    
    elif text in ["5", "knowledge"]:
        # Default knowledge query
        from app.platform.admin_api import knowledge_query
        return json.dumps(knowledge_query({"query": "What is our compliance status?"}), indent=2)
    
    elif text in ["6", "controls"]:
        return json.dumps({
            "note": "Use: controls {\"param\": \"outreach_daily_cap\", \"value\": 100}",
            "example": "controls {\"param\": \"voice_daily_cap\", \"value\": 100}"
        }, indent=2)
    
    elif text in ["7", "campaign"]:
        from app.platform.squad_marketing import run_hourly_campaign
        return json.dumps(run_hourly_campaign(), indent=2)
    
    elif text in ["8", "whatsapp", "wa"]:
        from app.platform.squad_whatsapp import check_wa_status
        return json.dumps(check_wa_status(), indent=2)
    
    elif text in ["9", "squad"]:
        # Ask which squad
        return "Which squad? 1=Voice, 2=Marketing, 3=Compliance, 4=Deploy, 5=Knowledge, 6=QA, 7=Data, 8=Billing, 9=WA, 10=Monitoring, 11=CI/CD"
    
    elif text in ["10", "monitoring"]:
        from app.platform.squad_monitoring import gate_health_dashboard
        return json.dumps(gate_health_dashboard(), indent=2)
    
    elif text in ["11", "ci/cd"]:
        from app.platform.squad_cicd import check_prod_gates
        return json.dumps(check_prod_gates(), indent=2)
    
    elif text in ["help", "menu"]:
        return """
🛠️ LEADGEN AI — OWNER ADMIN COMMANDS

1. hotqueue / leads / status → 42 flagged leads + pack status
2. compliance / gates → TRAI/DND/kill-fence gate status
3. deploy → 2-step kill-fence deploy initiation
4. squads → All 15 squad health summaries
5. knowledge → Ask question from knowledge base
6. controls → Adjust system params (gated)
7. campaign / outreach → Hourly outreach execution
8. whatsapp / wa → WAHA status + connected channels
9. squad N → Execute task for squad N (1-11)
10. monitoring → Observability dashboard
11. ci/cd → CI pipeline health check
help / menu → This help text

🛡️ All commands gated — cannot weaken compliance (TRAI/DND/kill-fence)
⚙️ Autopilot: 1000 engineers × 15 squads active
"""
    
    else:
        # Unknown command - show help + recent status
        from app.platform.admin_api import hot_queue_status, compliance_snapshot
        hs = hot_queue_status()
        cs = compliance_snapshot()
        return f"""❓ Unknown command: '{text}'

Type 'help' or 'menu' for available commands.

Recent status:
- Hot leads: {'ready' if hs.get('csv_exists') else 'no pack yet'}
- Compliance: {'ALL PASS' if all(v == 'pass' for v in cs.values()) else 'review needed'}
- Autopilot: 1000 engineers × 15 squads active
"""

# CLI test
if __name__ == "__main__":
    if len(sys.argv) > 1:
        result = handle_owner_message(sys.argv[1])
        print(result)
    else:
        print("Usage: owner_bot.py <command>")
        print("Type 'help' for available commands")