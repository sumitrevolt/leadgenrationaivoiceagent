"""
main_helpers — presentation data/helpers extracted from app.main.

Programmatic SEO blog (inbound lead magnet) shared CSS, fonts and chrome
helpers. These are pure, order-independent module-level constants/functions
consumed only by the /blog and /blog/{slug} route handlers in app.main.
Moved here verbatim to keep app.main focused on app wiring/startup.
"""

_BLOG_CSS = """
:root{--indigo:#4f46e5;--violet:#7c3aed;--ink:#0f1024;--muted:#64647e;
--bg:#fff;--bg-soft:#f6f6fb;--line:#e8e8f2;--radius:16px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
color:var(--ink);background:var(--bg);line-height:1.7;-webkit-font-smoothing:antialiased}
a{color:var(--indigo);text-decoration:none}
.wrap{max-width:760px;margin:0 auto;padding:0 20px}
header.nav{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.9);
backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.nav-inner{display:flex;align-items:center;justify-content:space-between;height:64px;
max-width:760px;margin:0 auto;padding:0 20px}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:1.15rem;
font-family:'Plus Jakarta Sans',system-ui,sans-serif;color:var(--ink)}
.brand .logo{width:32px;height:32px;border-radius:9px;
background:linear-gradient(135deg,var(--indigo),var(--violet));display:grid;
place-items:center;color:#fff;font-weight:800}
.btn{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:.92rem;
padding:11px 18px;border-radius:11px;cursor:pointer;border:1.5px solid transparent}
.btn-primary{background:linear-gradient(135deg,var(--indigo),var(--violet));color:#fff;
box-shadow:0 16px 40px -18px rgba(79,70,229,.5)}
.btn-ghost{background:#fff;color:var(--ink);border-color:var(--line)}
h1,h2,h3{font-family:'Plus Jakarta Sans',system-ui,sans-serif;letter-spacing:-.02em;
line-height:1.2;color:var(--ink)}
.lead{padding:40px 0 16px}
.lead h1{font-size:clamp(1.6rem,4.5vw,2.4rem);font-weight:800;margin-bottom:10px}
.lead p.sub{color:var(--muted);font-size:1.05rem}
article h2{font-size:1.3rem;font-weight:700;margin:30px 0 10px}
article p{margin:0 0 14px;color:#23243f}
.meta{color:var(--muted);font-size:.86rem;margin-bottom:6px}
.cardlist{display:grid;gap:16px;padding:24px 0 60px}
.card{display:block;background:#fff;border:1px solid var(--line);border-radius:var(--radius);
padding:20px 22px;transition:transform .2s,box-shadow .2s,border-color .2s}
.card:hover{transform:translateY(-3px);box-shadow:0 16px 40px -22px rgba(15,16,36,.3);
border-color:#818cf8}
.card h3{font-size:1.12rem;margin-bottom:6px;color:var(--ink)}
.card p{color:var(--muted);font-size:.94rem;margin:0}
.card .tag{display:inline-block;font-size:.72rem;font-weight:600;color:var(--indigo);
background:#eef0ff;padding:3px 10px;border-radius:999px;margin-bottom:10px}
.cta-box{margin:34px 0 56px;padding:26px;border-radius:18px;
background:linear-gradient(135deg,#eef0ff,#f6f0ff);border:1px solid var(--line)}
.cta-box h3{font-size:1.2rem;margin-bottom:8px}
.cta-box p{color:var(--muted);margin-bottom:16px}
.cta-row{display:flex;gap:12px;flex-wrap:wrap}
footer{border-top:1px solid var(--line);padding:26px 0;color:var(--muted);font-size:.86rem}
.empty{padding:60px 0;text-align:center;color:var(--muted)}
"""

_BLOG_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&'
    'family=Inter:wght@400;500;600&display=swap" rel="stylesheet">'
)


def _blog_header() -> str:
    return (
        '<header class="nav"><div class="nav-inner">'
        '<a href="/" class="brand"><span class="logo">L</span>LeadGen AI</a>'
        '<a href="/audit" class="btn btn-primary">FREE Google Audit</a>'
        "</div></header>"
    )


def _blog_footer() -> str:
    return (
        '<footer><div class="wrap">© LeadGen AI — AI Marketing for Indian businesses · '
        '<a href="/">Home</a> · <a href="/blog">Blog</a> · '
        '<a href="/audit">Free Audit</a> · '
        '<a href="https://wa.me/918459012607">WhatsApp</a></div></footer>'
    )


def _cta_box() -> str:
    return (
        '<div class="cta-box"><h3>Apni marketing badhani hai?</h3>'
        "<p>2 minute me free Google audit lijiye — hum batayenge kahan kami hai aur "
        'kaise theek karein. Bilkul free.</p><div class="cta-row">'
        '<a href="/audit" class="btn btn-primary">🚀 FREE Audit nikalo</a>'
        '<a href="https://wa.me/918459012607" class="btn btn-ghost">💬 WhatsApp pe baat karo</a>'
        "</div></div>"
    )
