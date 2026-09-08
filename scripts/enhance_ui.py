import re

with open("frontend/admin_dashboard.html", encoding="utf-8") as f:
    html = f.read()

new_nav = """    <nav class="nav" role="menubar" aria-label="Main menu">
      <div class="sec nav-group" role="presentation">1. Today</div>
      <a href="#sec-today-biz" role="menuitem" aria-label="Aaj ka business"><span class="ic" aria-hidden="true">🏠</span> Overview & Performance</a>
      <a href="#sec-revenue" role="menuitem" aria-label="Revenue analytics"><span class="ic" aria-hidden="true">📈</span> Revenue Analytics</a>

      <div class="sec nav-group" role="presentation">2. Sales</div>
      <a class="admin-auth-only" href="/app/inbox" id="navHotQueue" role="menuitem" aria-label="Hot Queue 15-minute outreach sprint" style="background:#4f46e5;color:#fff;font-weight:700;"><span class="ic" aria-hidden="true">🔥</span> Hot Queue</a>
      <a href="#sec-prospects" role="menuitem" aria-label="Prospects and leads"><span class="ic" aria-hidden="true">⊞</span> Pipeline & Leads</a>
      <a href="#sec-campaigns" role="menuitem" aria-label="Campaigns"><span class="ic" aria-hidden="true">◎</span> Campaigns <span class="badge" id="nav-camp">—</span></a>
      <a href="/app/outreach" role="menuitem" aria-label="WhatsApp / Email Outreach pipeline"><span class="ic" aria-hidden="true">📧</span> WhatsApp / Email Outreach</a>

      <div class="sec nav-group" role="presentation">3. Customers</div>
      <a href="#sec-clients" role="menuitem" aria-label="All clients"><span class="ic" aria-hidden="true">★</span> Sabhi Clients <span class="badge" id="nav-clients" aria-label="client count">—</span></a>
      <a class="admin-auth-only" href="#onboardCard" onclick="openOnboard();return false;" role="menuitem" aria-label="Add new customer" style="background:#10b981;color:#fff;font-weight:700;"><span class="ic" aria-hidden="true">➕</span> Add & Onboard Customer</a>
      <a href="/app/clients" role="menuitem" aria-label="Client support"><span class="ic" aria-hidden="true">🕵️</span> Health & Support</a>

      <div class="sec nav-group" role="presentation">4. Content & Delivery</div>
      <a href="/app/delivery-command-center" role="menuitem" aria-label="Delivery Cockpit"><span class="ic" aria-hidden="true">📦</span> Full Delivery Cockpit</a>
      <a href="/app/studio" role="menuitem" aria-label="AI creative studio"><span class="ic" aria-hidden="true">🎨</span> Creative & AI Studio</a>
      <a href="#sec-recordings" role="menuitem" aria-label="Call Recordings"><span class="ic" aria-hidden="true">🎙</span> Completed Call Recordings</a>

      <div class="sec nav-group" role="presentation">5. Automations</div>
      <a href="/app/automation" role="menuitem" aria-label="Mission Control automation"><span class="ic" aria-hidden="true">🎛</span> Automation Control Plane <span class="badge" id="nav-auto-appr" style="background:#f59e0b;display:none">0</span></a>
      <a href="/app/automation#approvals" role="menuitem" aria-label="Approvals and workflows"><span class="ic" aria-hidden="true">✅</span> Rule Approvals</a>
      <a href="#sec-webcalls" role="menuitem" aria-label="Web test calls"><span class="ic" aria-hidden="true">💬</span> Voice Diagnostics / Sandbox</a>

      <div class="sec nav-group" role="presentation">6. Agents</div>
      <a href="#sec-agents" role="menuitem" aria-label="AI Agents"><span class="ic" aria-hidden="true">👥</span> AI Workforce Roster <span class="badge" id="nav-ag">—</span></a>
      <a href="#openclawAdminCard" onclick="scrollToSec('openclawAdminCard');return false;" role="menuitem" aria-label="OpenClaw Owner Copilot"><span class="ic" aria-hidden="true">🧠</span> OpenClaw Copilot <span class="badge" id="nav-openclaw-flag" style="background:#64748b;display:none">OFF</span></a>

      <div class="sec nav-group" role="presentation">7. System</div>
      <a href="/app/control-center" id="navControlCenter" role="menuitem" aria-label="Control Center system observability"><span class="ic" aria-hidden="true">🖥</span> Control Center <span id="navCcGate" class="badge" style="display:none;background:#64748b">flag OFF</span></a>
      <a href="/app/explorer?view=master" role="menuitem" aria-label="Master Blueprint"><span class="ic" aria-hidden="true">🏛</span> Architecture Explorer</a>
      <a href="#sec-health" role="menuitem" aria-label="System Health"><span class="ic" aria-hidden="true">◐</span> Telemetry & Health</a>

      <div class="sec nav-group" role="presentation">8. Owner Controls</div>
      <a href="/app/team-access" role="menuitem" aria-label="Team RBAC and settings"><span class="ic" aria-hidden="true">🔐</span> Global Settings</a>
      <a href="#sec-godmode" onclick="expandAdvTech()" role="menuitem" aria-label="God Mode production control" style="background:rgba(239,68,68,.18);color:#fca5a5;font-weight:700"><span class="ic" aria-hidden="true">⚡</span> Advanced / God Mode</a>
      <a href="/app/admin-login" id="navAdminLogin" role="menuitem" aria-label="Admin login"><span class="ic" aria-hidden="true">🔑</span> Admin Login</a>
    </nav>"""

new_html = re.sub(
    r'<nav class="nav" role="menubar" aria-label="Main menu">.*?</nav>',
    new_nav,
    html,
    flags=re.DOTALL,
)

with open("frontend/admin_dashboard.html", "w", encoding="utf-8") as f:
    f.write(new_html)
