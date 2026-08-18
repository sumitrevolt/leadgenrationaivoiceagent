"""Admin dashboard auth-only UI and overflow contracts."""

from pathlib import Path

HTML = Path("frontend/admin_dashboard.html")


def test_admin_dashboard_has_single_logout_button():
    html = HTML.read_text(encoding="utf-8")
    assert html.count("Logout</button>") == 1
    assert 'id="sbLogoutBtn"' in html
    assert 'id="adminLogoutBtn"' not in html


def test_privileged_actions_hidden_until_admin_auth_boot():
    html = HTML.read_text(encoding="utf-8")
    assert "body:not(.admin-authenticated) .admin-auth-only" in html
    assert 'class="admin-auth-only" href="/app/inbox"' in html
    # The manualCallCard is a card div with admin-auth-only, linked from
    # the Start Here card with a plain "btn" class link.
    assert 'card admin-auth-only" id="manualCallCard"' in html
    assert 'href="#manualCallCard"' in html
    assert 'class="btn admin-auth-only" onclick="openOnboard()"' in html
    boot = html[
        html.index("async function adminAuthBoot()") : html.index("async function adminLogout()")
    ]
    assert 'document.body.classList.remove("admin-authenticated")' in boot
    assert 'document.body.classList.add("admin-authenticated")' in boot


def test_admin_dashboard_clamps_horizontal_overflow():
    html = HTML.read_text(encoding="utf-8")
    assert "html,body{max-width:100%;overflow-x:hidden}" in html
    assert ".top-right{margin-left:auto;display:flex" in html
    assert "flex:1 1 auto" in html


def test_admin_dashboard_timeout_does_not_race_normal_p95():
    html = HTML.read_text(encoding="utf-8")
    fn = html[
        html.index("async function loadDashboard()") : html.index(
            "/* 🏠 Aaj ka business", html.index("async function loadDashboard()")
        )
    ]
    assert "setTimeout(()=>ctrl.abort(), 15000)" in fn
    assert "clearTimeout(t)" in fn
    assert "Data load nahi hui" in fn
