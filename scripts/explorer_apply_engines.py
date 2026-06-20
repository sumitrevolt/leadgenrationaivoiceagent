"""One-time additive patch — make /app/explorer cover all scheduled engine modules.

`explorer_sync.py` flags 28 engine modules whose name-string is absent from
frontend/explorer.html (60% coverage). The graph is HAND-CURATED so we do NOT
auto-regenerate; instead this patch is ADDITIVE + accurate:

  1. APPEND real module filenames to existing nodes that already represent them
     (e.g. speed_to_lead.py -> existing 'stl' node) — makes drift recognize them
     AND makes the node `files:` fields truthful.
  2. ADD nodes for genuinely-unrepresented retention/marketing engines
     (booking/service reminders, customer-CRM, newsletter, client report, trainer).

Idempotent: re-run safe (skips already-present). Targeted edits only — if a node
id isn't found it WARNS (never corrupts). Validate after: `python scripts/explorer_sync.py`.
Windows venv: .venv\\Scripts\\python.exe scripts/explorer_apply_engines.py
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
F = ROOT / "frontend" / "explorer.html"

# existing node id -> module filenames it actually covers (append to its files: field)
APPENDS: dict[str, list[str]] = {
    "revenue": ["client_health.py", "revenue_digest.py", "revenue_snapshots.py", "reporting.py", "winback.py"],
    "eval_gate": ["eval_metrics.py", "eval_suite.py"],
    "growth_opt": ["growth_engine.py"],
    "ops": ["infra_handler.py", "integration_health.py"],
    "sched_ops": ["dlq_retry.py"],
    "memory_vault": ["live_notes.py"],
    "sales": ["sales_pipeline.py", "proposal_tracking.py"],
    "blog": ["seo_blog.py"],
    "stl": ["speed_to_lead.py"],
    "telegram_pub": ["telegram_publish.py"],
    "meter_watch": ["usage_alerts.py"],
    "whatsapp_wa": ["wa_campaign_runner.py"],
    "review_monitor": ["brand_pulse.py"],
    "voice_brain": ["natural_dialog.py"],  # structural view
}

# genuinely-unrepresented engines -> new automation nodes (placed in free grid rows)
NEW_NODES = [
    "      {id:'auto_trainer', type:'ai', badge:'ML TRAIN', cx:'moderate', sched:'03:00 nightly', title:'Auto Trainer (Meera)', desc:'Nightly batch ML model train/improve from collected data · ML_NIGHTLY_TRAINING', files:'auto_trainer.py', flag:'ML_NIGHTLY_TRAINING', x:1240, y:1840, w:260, h:100},",
    "      {id:'booking_reminders', type:'marketing', badge:'REMIND', cx:'simple', sched:'daily', title:'Booking Reminders', desc:'Calendly/HighLevel-pattern booking + no-show reminders (no-show kam karo)', files:'booking_reminders.py', x:1520, y:1840, w:260, h:100},",
    "      {id:'service_reminders', type:'marketing', badge:'REPEAT', cx:'simple', sched:'daily', title:'Service Reminders', desc:'Repeat-service reminders (NiceJob parity) — recurring-revenue nudges', files:'service_reminders.py', x:40, y:1960, w:260, h:100},",
    "      {id:'customer_crm', type:'marketing', badge:'CRM', cx:'simple', sched:'daily', title:'Customer Mini-CRM + Wishes', desc:'End-customer mini-CRM + birthday/anniversary WISH engine (per-client retention)', files:'customer_crm.py', x:320, y:1960, w:270, h:100},",
    "      {id:'newsletter', type:'marketing', badge:'NEWSLETTER', cx:'simple', sched:'scheduled', title:'Auto Newsletter', desc:'Mailchimp-lite per-client newsletter to THEIR customers', files:'newsletter.py', x:620, y:1960, w:260, h:100},",
    "      {id:'client_report', type:'marketing', badge:'REPORT', cx:'simple', sched:'monthly/weekly', title:'Client Report + Team Story', desc:'White-label monthly client report + weekly AI-team story (retention #1)', files:'client_report.py · team_report.py', x:920, y:1960, w:280, h:100},",
]

NEW_EDGES = [
    "      {f:'worker', t:'auto_trainer', lbl:'nightly', style:'async'},",
    "      {f:'worker', t:'booking_reminders', lbl:'daily', style:'async'},",
    "      {f:'worker', t:'service_reminders', lbl:'daily', style:'async'},",
    "      {f:'worker', t:'customer_crm', lbl:'daily', style:'async'},",
    "      {f:'worker', t:'newsletter', lbl:'sched', style:'async'},",
    "      {f:'worker', t:'client_report', lbl:'monthly', style:'async'},",
]

# anchors (must be unique in the file)
NODE_ANCHOR = re.compile(r"(\{id:'niche_prospector',[^\n]*\},\n)")
EDGE_ANCHOR = "{f:'beat', t:'worker', lbl:'cron fire', style:'async'},\n"


def append_files(html: str, node_id: str, mods: list[str]) -> tuple[str, int]:
    pat = re.compile(r"(\{id:'" + re.escape(node_id) + r"',[^\n]*?files:')([^']*)(')")
    m = pat.search(html)
    if not m:
        print(f"  WARN: node not found -> {node_id}")
        return html, 0
    cur = m.group(2)
    add = [x for x in mods if x not in cur]
    if not add:
        return html, 0
    new = cur + " · " + " · ".join(add)
    html = html[: m.start(2)] + new + html[m.end(2):]
    print(f"  {node_id}: +{', '.join(add)}")
    return html, len(add)


def main() -> int:
    html = F.read_text(encoding="utf-8")
    before_nodes = len(re.findall(r"\{id:'", html))
    before_edges = len(re.findall(r"\{f:'", html))

    appended = 0
    for nid, mods in APPENDS.items():
        html, n = append_files(html, nid, mods)
        appended += n

    if "id:'auto_trainer'" not in html:
        m = NODE_ANCHOR.search(html)
        if m:
            html = html[: m.end()] + "".join(x + "\n" for x in NEW_NODES) + html[m.end():]
            print(f"  +{len(NEW_NODES)} new nodes")
        else:
            print("  WARN: node anchor (niche_prospector) not found — new nodes skipped")
    else:
        print("  new nodes already present (skip)")

    if "t:'auto_trainer'" not in html and EDGE_ANCHOR in html:
        html = html.replace(EDGE_ANCHOR, EDGE_ANCHOR + "".join(x + "\n" for x in NEW_EDGES), 1)
        print(f"  +{len(NEW_EDGES)} new edges")
    else:
        print("  new edges already present or anchor missing (skip)")

    F.write_text(html, encoding="utf-8")
    after_nodes = len(re.findall(r"\{id:'", html))
    after_edges = len(re.findall(r"\{f:'", html))
    print(f"\nfiles-appends: {appended} · nodes {before_nodes}->{after_nodes} · edges {before_edges}->{after_edges}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
