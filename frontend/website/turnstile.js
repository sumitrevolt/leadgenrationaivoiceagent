/* Cloudflare Turnstile auto-loader (F.1).
 *
 * Inert-by-default helper for public lead-magnet pages. On load:
 *   1. GET /api/public/turnstile/config  ->  {enabled, site_key}
 *   2. If !enabled  ->  window.turnstileToken = async () => ""  (passthrough)
 *   3. If enabled   ->  inject Cloudflare API script + render the widget into
 *      the element matching [data-turnstile-host] (the form prepends one if
 *      missing). Expose `await window.turnstileToken()` to resolve a fresh
 *      token (waits up to ~30s if the user hasn't solved yet).
 *
 * Forms use it like:
 *   const tok = await window.turnstileToken();
 *   fetch('/api/...', { headers: { 'X-Turnstile-Token': tok, ... }, ... })
 *
 * Server side: app/security/turnstile.py — INERT when secret unset,
 * fail-CLOSED on missing/invalid when armed, fail-OPEN on infra error.
 */
(function () {
  var widgetId = null;
  var pendingResolvers = [];
  var ready = false;
  // Set permanently true when the server reports Turnstile disabled (or the
  // config fetch fails). Distinct from `ready`: `ready` also flips true the
  // instant an ENABLED widget finishes rendering (before it's solved), so
  // reusing it alone as the passthrough check made every turnstileToken()
  // call AFTER boot() resolve hang for the full 30s wait-for-widget timeout
  // in the disabled case (no widget ever renders, so nothing ever calls
  // flushPending() again after boot()'s one-time flush).
  var disabled = false;

  function flushPending(token) {
    while (pendingResolvers.length) {
      try { pendingResolvers.shift()(token || ""); } catch (_e) {}
    }
  }

  window.turnstileToken = function () {
    return new Promise(function (resolve) {
      if (disabled || !ready) return resolve(""); // INERT — server-side will pass through too
      try {
        var t = window.turnstile && widgetId != null
          ? window.turnstile.getResponse(widgetId) : "";
        if (t) return resolve(t);
      } catch (_e) {}
      // Not solved yet — wait up to 30s for the user/managed widget to settle
      var to = setTimeout(function () { flushPending(""); }, 30000);
      pendingResolvers.push(function (tok) { clearTimeout(to); resolve(tok); });
    });
  };

  function ensureHost() {
    var el = document.querySelector("[data-turnstile-host]");
    if (el) return el;
    // Form did not pre-render a host — drop one before the first <form> or <button>.
    el = document.createElement("div");
    el.setAttribute("data-turnstile-host", "");
    el.style.margin = "10px 0";
    var anchor = document.querySelector("form") || document.querySelector("button");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(el, anchor);
    else document.body.appendChild(el);
    return el;
  }

  function render(siteKey) {
    var host = ensureHost();
    try {
      widgetId = window.turnstile.render(host, {
        sitekey: siteKey,
        size: "flexible",
        callback: function (tok) { ready = true; flushPending(tok); },
        "error-callback": function () { flushPending(""); },
        "expired-callback": function () {
          try { window.turnstile.reset(widgetId); } catch (_e) {}
        },
      });
      ready = true;
    } catch (e) {
      // Render failure — fail-OPEN on the client too (server is the real gate).
      ready = true;
      flushPending("");
    }
  }

  function loadScript(siteKey) {
    // Expose the callback first so the API script can fire it on load.
    window.__leadgenTurnstileReady = function () { render(siteKey); };
    var s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=__leadgenTurnstileReady&render=explicit";
    s.async = true; s.defer = true;
    s.onerror = function () { ready = true; flushPending(""); };
    document.head.appendChild(s);
  }

  function boot() {
    fetch("/api/public/turnstile/config", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : { enabled: false }; })
      .then(function (cfg) {
        if (!cfg || !cfg.enabled || !cfg.site_key) {
          disabled = true; ready = true; flushPending(""); return;
        }
        loadScript(cfg.site_key);
      })
      .catch(function () { disabled = true; ready = true; flushPending(""); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
