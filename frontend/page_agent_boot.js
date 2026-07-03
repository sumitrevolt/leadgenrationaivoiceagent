/* Page-Agent admin copilot boot loader (alibaba/page-agent) — flag-gated, key-safe.
 *
 * Kaise chalta: admin page pe <script src="/api/page-agent/boot.js" defer> include.
 * 1) localStorage.accessToken (admin JWT) na ho -> silent no-op.
 * 2) GET /api/page-agent/config (admin-authed) -> enabled:false ya 4xx -> no-op.
 * 3) Enabled -> pinned CDN script inject (SRI jab default URL) -> new PageAgent()
 *    with baseURL = OUR proxy (/api/page-agent/v1) + apiKey = admin JWT.
 *    LLM provider key kabhi browser tak NAHI aati (server-side inject).
 * Sab kuch try/catch — copilot fail ho to admin page normal chalti rahe.
 */
(function () {
  'use strict';
  if (window.__pageAgentBooted) return;
  window.__pageAgentBooted = true;

  var tok = '';
  try { tok = localStorage.getItem('accessToken') || ''; } catch (e) { /* no-op */ }
  if (!tok) return;

  fetch('/api/page-agent/config', { headers: { Authorization: 'Bearer ' + tok } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (cfg) {
      if (!cfg || !cfg.enabled || !cfg.script_url) return;
      var s = document.createElement('script');
      s.src = cfg.script_url;
      s.crossOrigin = 'anonymous';
      if (cfg.integrity) s.integrity = cfg.integrity;
      s.onload = function () {
        try {
          if (!window.PageAgent) return;
          window.__pageAgent = new window.PageAgent({
            model: cfg.model || 'mistral-small-latest',
            baseURL: location.origin + '/api/page-agent/v1',
            apiKey: tok, // = admin JWT; proxy require_admin se verify karta
            language: 'en-US'
          });
          addLauncher(); // library ka panel default HIDDEN hai — apna entry-point
        } catch (e) {
          console.warn('[page-agent] init failed:', e);
        }
      };
      s.onerror = function () { console.warn('[page-agent] script load failed'); };
      document.head.appendChild(s);
    })
    .catch(function () { /* graceful no-op */ });

  // Floating launcher (🤖) + chhota command bar — library panel sirf execute ke
  // dauran progress dikhata, launcher khud nahi deta. Sab inline-style, no deps.
  function addLauncher() {
    if (document.getElementById('pa-launcher')) return;
    var btn = document.createElement('button');
    btn.id = 'pa-launcher';
    btn.textContent = '🤖';
    btn.title = 'AI Copilot — page ko Hinglish/English me command do';
    btn.style.cssText = 'position:fixed;bottom:18px;right:18px;z-index:2147482000;' +
      'width:46px;height:46px;border-radius:50%;border:none;cursor:pointer;' +
      'font-size:22px;background:#6d5dfc;color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.35)';
    var bar = document.createElement('div');
    bar.id = 'pa-bar';
    bar.style.cssText = 'position:fixed;bottom:72px;right:18px;z-index:2147482000;display:none;' +
      'background:#1c1c28;border:1px solid #3a3a4d;border-radius:10px;padding:8px;' +
      'box-shadow:0 6px 20px rgba(0,0,0,.45);width:min(340px,86vw)';
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = 'e.g. "approvals tab kholo" / "form bhar do"';
    inp.style.cssText = 'width:100%;box-sizing:border-box;padding:8px 10px;border-radius:7px;' +
      'border:1px solid #3a3a4d;background:#12121a;color:#eee;font-size:13px;outline:none';
    bar.appendChild(inp);
    function run() {
      var q = (inp.value || '').trim();
      if (!q || !window.__pageAgent) return;
      bar.style.display = 'none';
      inp.value = '';
      try { if (window.__pageAgent.panel) window.__pageAgent.panel.show(); } catch (e) { /* no-op */ }
      Promise.resolve(window.__pageAgent.execute(q)).catch(function (e) {
        console.warn('[page-agent] task failed:', e);
      });
    }
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') run(); });
    btn.addEventListener('click', function () {
      var open = bar.style.display !== 'none';
      bar.style.display = open ? 'none' : 'block';
      if (!open) inp.focus();
    });
    document.body.appendChild(bar);
    document.body.appendChild(btn);
  }
})();
