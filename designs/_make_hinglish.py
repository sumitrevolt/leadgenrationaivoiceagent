"""Generate Hinglish copy variant of the dark premium dashboard HTML.

Maps the English labels in designs/leadgen-dark-dashboard.html to the
Hinglish copy that the live app actually uses in frontend/customer_dashboard.html.
Pure copy swap, design tokens untouched.
"""
from pathlib import Path

src_path = Path('designs/leadgen-dark-dashboard.html')
out_path = Path('designs/leadgen-dark-dashboard-hinglish.html')

src = src_path.read_text(encoding='utf-8')

# (find, replace) pairs. Order matters: longer/more specific first.
# Tuples only — strings in a list would unpack wrong.
replacements = [
    # Page head
    ('<h1>Good morning, Jiya 👋</h1>', '<h1>Suprabhat, Jiya 👋</h1>'),
    ("here's what moved today.", "aaj kya hua, yahan dikh raha hai."),

    # Search
    ('placeholder="Search leads, calls, campaigns…"',
     'placeholder="Leads, calls, campaigns dhoondo…"'),

    # KPI labels
    ('>New Leads<', '>Naye Leads<'),
    ('>Calls Connected<', '>Calls Judh Gaye<'),
    ('>Avg Talk Time<', '>Avg Baat Time<'),
    ('>per connected lead<', '>har connected lead par<'),

    # Buttons
    ('>Export<', '>Export karo<'),
    ('>New Campaign<', '>Naya Campaign<'),
    ('>24h<', '>24 ghante<'),
    ('>7 days<', '>7 din<'),
    ('>30 days<', '>30 din<'),

    # Call Activity card
    ('Outbound AI calls vs. connected — last 7 days',
     'Outbound AI calls vs. connected — pichhle 7 din'),
    ('>Placed<', '>Lage<'),
    ('>Connected<', '>Judh Gaye<'),

    # Lead Temperature
    ('AI-scored across 148 active leads',
     'AI ne 148 active leads ka score kiya'),
    ('>Hot<', '>Garam<'),
    ('>Warm<', '>Gunguna<'),
    ('>Cold<', '>Thanda<'),

    # Recent Leads
    ('<h3>Recent Leads</h3>', '<h3>Haaal ke Leads</h3>'),
    ('Highest-intent first — SLA clock running',
     'Sabse high-intent pehle — SLA clock chal rahi hai'),
    ('>View all<', '>Sab dekho<'),

    # Table headers
    ('<th>Next action</th>', '<th>Agla action</th>'),

    # Lead rows - actions / status
    ('>Call back 4:00 PM<', '>4:00 PM ko call back<'),
    ('>Callback set<', '>Callback set hai<'),
    ('>Send quotation<', '>Quotation bhejo<'),
    ('>Awaiting reply<', '>Reply ka wait<'),
    ('>Share portfolio<', '>Portfolio share karo<'),
    ('>Nurturing<', '>Nurture ho rahi<'),
    ('>Book demo call<', '>Demo call book karo<'),
    ('>Follow-up Tue<', '>Tue ko follow-up<'),
    ('>Re-engage in 7d<', '>7 din me re-engage<'),
    ('>Dormant<', '>Soya hua<'),

    # Plan card
    ('<h3>Your Plan</h3>', '<h3>Aapka Plan</h3>'),
    ('AI Automated Marketing — renews 1 Sep 2026',
     'AI Automated Marketing — 1 Sep 2026 ko renew hoga'),
    ('158 min left', '158 min bache'),
    ('>Top-up minutes<', '>Minutes top-up<'),
    ('>Upgrade<', '>Upgrade<'),

    # AI Team
    ('4 agents · 3 active', '4 agents · 3 active'),
    ('>Outbound · Hindi + English<', '>Outbound · Hindi + English<'),
    ('>On call<', '>Call par<'),
    ('312 calls · 61% connect', '312 calls · 61% connect'),
    ('>Prospecting · Google Maps<', '>Prospecting · Google Maps<'),
    ('>Working<', '>Kaam kar raha<'),
    ('1,204 scanned today', '1,204 aaj scan hue'),
    ('>Social + WhatsApp copy<', '>Social + WhatsApp copy<'),
    ('18 assets queued', '18 assets queue me'),
    ('>Compliance + DLT checks<', '>Compliance + DLT checks<'),
    ('>Idle<', '>Soya hua<'),
    ('Last run 40 min ago', 'Last run 40 min pehle'),

    # Live Activity
    ('>Streaming<', '>Streaming<'),
    ('answered — 3m 12s, intent high, callback set 4 PM.',
     'ne uthaya — 3m 12s, intent high, callback 4 PM set.'),
    ('published 4 Instagram posts for this week.',
     'ne is hafte ke 4 Instagram posts publish kiye.'),
    ('12 new leads imported from Google Maps — Andheri West cluster.',
     '12 naye leads Google Maps se aaye — Andheri West cluster.'),
    ('Monsoon Bridal Offer campaign crossed 4,200 impressions.',
     'Monsoon Bridal Offer campaign ne 4,200 impressions cross kiye.'),
    ('opened quotation — nudged on WhatsApp.',
     'ne quotation kholi — WhatsApp par nudge bheja.'),
    ('2 min ago', '2 min pehle'),
    ('18 min ago', '18 min pehle'),
    ('1 hr ago', '1 ghante pehle'),
    ('3 hr ago', '3 ghante pehle'),
    ('5 hr ago', '5 ghante pehle'),

    # Wins
    ('<h3>This Week\'s Wins</h3>', '<h3>Is Hafte ki Jeet</h3>'),
    ('Auto-summarised by AI', 'AI ne khud summarize kiya'),
    ('27 bookings closed', '27 bookings band hui'),
    ('Bridal season push + 2 extra evening call slots drove the lift.',
     'Bridal season push + 2 extra shaam call slots ne lift diya.'),
    ('Connect rate up to 61%', 'Connect rate 61% tak gaya'),
    ('Evening 6–8 PM window outperformed mornings by 19pp.',
     'Shaam 6–8 PM window ne subah se 19pp behtar perform kiya.'),
    ('Watch: 8 hot leads aging', 'Dhyaan: 8 garam leads purani ho rahi'),
    ('Past 24h SLA. Voice Agent can clear them in ~30 minutes.',
     'Pichhle 24h SLA. Voice Agent unhe ~30 min me clear kar sakta hai.'),
    ('>Let AI clear the backlog<', '>AI se backlog clear karwao<'),

    # Voice minutes mini-card
    ('342 of 500 minutes used this cycle.', 'Is cycle me 500 me se 342 minutes used.'),
    ('>Resets 1 Sep<', '>1 Sep ko reset<'),

    # Topbar live pill
    ('Voice Agent live · 2 on call', 'Voice Agent live · 2 call par'),
]

count = 0
missing = []
for old, new in replacements:
    if old in src:
        # Use first-occurrence replace to avoid global side effects
        src = src.replace(old, new, 1)
        count += 1
    else:
        missing.append(old)

# Update page title and the lang attribute so it reads as Hinglish
src = src.replace(
    '<title>LeadGen AI — Customer Dashboard (Dark Premium)</title>',
    '<title>LeadGen AI — Customer Dashboard (Hinglish, Dark Premium)</title>',
)
src = src.replace(
    'LadiGen AI',
    'LeadGen AI',  # safety noop
)
src = src.replace(
    '<html lang="en">',
    '<html lang="hi">',
)

out_path.write_text(src, encoding='utf-8')

print(f"replaced {count} of {len(replacements)} patterns")
if missing:
    print(f"missing {len(missing)} (likely already replaced or absent):")
    for m in missing:
        print(f"  - {m!r}")
print(f"output: {out_path}")
print(f"size:    {len(src):,} bytes")
