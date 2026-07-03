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

  // 🤖 HQ Copilot drawer — MAIN entry point (2026-07-03 user-ask): sawal poocho
  // to Boss grounded jawab deta (POST /api/platform/office/ask), kaam do to
  // sahi agent ko auto-dispatch (draft-safe Kaam-Do path). "/page <cmd>" =
  // is page pe DOM-action (page-agent execute). Sab inline-style, no deps.
  function addLauncher() {
    if (document.getElementById('pa-launcher')) return;
    var btn = document.createElement('button');
    btn.id = 'pa-launcher';
    btn.textContent = '🤖';
    btn.title = 'HQ Copilot — Boss se poocho ya kaam do';
    btn.style.cssText = 'position:fixed;bottom:18px;right:18px;z-index:2147482000;' +
      'width:46px;height:46px;border-radius:50%;border:none;cursor:pointer;' +
      'font-size:22px;background:#6d5dfc;color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.35)';

    var bar = document.createElement('div');
    bar.id = 'pa-bar';
    bar.style.cssText = 'position:fixed;bottom:72px;right:18px;z-index:2147482000;display:none;' +
      'background:#1c1c28;border:1px solid #3a3a4d;border-radius:12px;padding:10px;' +
      'box-shadow:0 6px 22px rgba(0,0,0,.5);width:min(380px,90vw);font-family:system-ui,sans-serif';
    bar.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
      '<b style="color:#eee;font-size:13px">🏢 HQ Copilot</b>' +
      '<span style="color:#8b8b9e;font-size:11px">poocho · kaam do · /page = is page pe action</span></div>' +
      '<div id="pa-msgs" style="max-height:300px;overflow-y:auto;display:flex;flex-direction:column;' +
      'gap:6px;margin-bottom:8px"></div>' +
      '<div style="display:flex;gap:6px;margin-bottom:8px">' +
      '<button class="pa-chip" data-q="Aaj ka status kya hai? Kya important pending hai?">📊 Status</button>' +
      '<button class="pa-chip" data-q="__briefing__">📻 Briefing</button></div>' +
      '<input id="pa-inp" type="text" placeholder=\'e.g. "kitne hot leads hain?" / "blog likho" / /page approvals kholo\' ' +
      'style="width:100%;box-sizing:border-box;padding:9px 10px;border-radius:8px;border:1px solid #3a3a4d;' +
      'background:#12121a;color:#eee;font-size:13px;outline:none">';
    var chipCss = 'padding:4px 9px;border-radius:14px;border:1px solid #3a3a4d;background:#26263a;' +
      'color:#cfcfe4;font-size:11px;cursor:pointer';

    function msgs() { return document.getElementById('pa-msgs'); }
    function addMsg(text, who) {
      var d = document.createElement('div');
      d.textContent = text;
      d.style.cssText = 'padding:7px 10px;border-radius:9px;font-size:12.5px;line-height:1.45;' +
        'white-space:pre-wrap;word-break:break-word;max-width:92%;' +
        (who === 'me' ? 'align-self:flex-end;background:#6d5dfc;color:#fff'
                      : 'align-self:flex-start;background:#26263a;color:#e6e6f2');
      msgs().appendChild(d);
      msgs().scrollTop = msgs().scrollHeight;
      return d;
    }
    function hdrs() { return { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok }; }

    function ask(q) {
      addMsg(q, 'me');
      var wait = addMsg('sochne do…', 'boss');
      if (q === '__briefing__' || /^briefing$/i.test(q)) {
        fetch('/api/platform/office/briefing', { headers: hdrs() })
          .then(function (r) { return r.json(); })
          .then(function (d) { wait.textContent = (d && d.text) ? d.text : 'Briefing abhi nahi bani.'; })
          .catch(function () { wait.textContent = 'Briefing load fail.'; });
        return;
      }
      if (q.indexOf('/page ') === 0) {
        var cmd = q.slice(6).trim();
        wait.textContent = '🖱️ Page task shuru — progress panel me dekho.';
        try { if (window.__pageAgent && window.__pageAgent.panel) window.__pageAgent.panel.show(); } catch (e) { /* no-op */ }
        if (window.__pageAgent && cmd) {
          Promise.resolve(window.__pageAgent.execute(cmd)).catch(function (e) {
            addMsg('❌ Page task fail: ' + (e && e.message || e), 'boss');
          });
        }
        return;
      }
      fetch('/api/platform/office/ask', { method: 'POST', headers: hdrs(), body: JSON.stringify({ q: q }) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          wait.textContent = (d && d.text) ? d.text : ('❌ ' + ((d && d.error) || 'jawab nahi mila'));
        })
        .catch(function (e) { wait.textContent = '❌ Network fail: ' + e; });
    }

    bar.addEventListener('click', function (e) {
      var t = e.target;
      if (t && t.classList && t.classList.contains('pa-chip')) {
        var q = t.getAttribute('data-q') || '';
        ask(q === '__briefing__' ? '__briefing__' : q);
      }
    });
    document.body.appendChild(bar);
    var chips = bar.querySelectorAll('.pa-chip');
    for (var i = 0; i < chips.length; i++) chips[i].style.cssText = chipCss;
    var inp = document.getElementById('pa-inp');
    inp.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var q = (inp.value || '').trim();
      if (!q) return;
      inp.value = '';
      ask(q);
    });
    btn.addEventListener('click', function () {
      var open = bar.style.display !== 'none';
      bar.style.display = open ? 'none' : 'block';
      if (!open) {
        if (!msgs().childNodes.length) {
          addMsg('Namaste! Main Boss hoon 🧑‍💼 — kuch bhi poocho (status, leads, pending kaam) ya seedha kaam do ("blog likho", "prospects dhundo"). Is page pe UI-action ke liye "/page <command>" likho.', 'boss');
        }
        inp.focus();
      }
    });
    document.body.appendChild(btn);
  }
})();
