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
        } catch (e) {
          console.warn('[page-agent] init failed:', e);
        }
      };
      s.onerror = function () { console.warn('[page-agent] script load failed'); };
      document.head.appendChild(s);
    })
    .catch(function () { /* graceful no-op */ });
})();
