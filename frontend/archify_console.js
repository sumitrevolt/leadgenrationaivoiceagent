/* ============================================================================
   ARCHIFY CONSOLE — shared runtime
   ----------------------------------------------------------------------------
   One runtime drives BOTH product consoles (voice + marketing). Pages only
   declare their navigation and their system-map topology; every renderer is
   shared so the two products cannot drift apart visually or behaviourally.

   Design obligations inherited from Archify DESIGN.md:
     - Truth before spectacle: every rendered state comes from a real API value.
       Unknown is rendered as "unknown", never as a hopeful green.
     - Progressive disclosure: one section visible at a time; detail opens in
       exactly one focused surface (the drawer).
     - Motion is bounded: 140-200ms, and prefers-reduced-motion is respected by
       the stylesheet. No spinner implies work that is not happening.
   ============================================================================ */
(function () {
  'use strict';

  var TOKEN_KEYS = ['lgai_token', 'accessToken', 'adminToken'];

  function token() {
    for (var i = 0; i < TOKEN_KEYS.length; i++) {
      try {
        var v = localStorage.getItem(TOKEN_KEYS[i]);
        if (v) return v;
      } catch (e) { /* storage blocked */ }
    }
    return '';
  }

  function authHeaders(extra) {
    var h = Object.assign({}, extra || {});
    var t = token();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  }

  /* --- session loss: every console surface is auth-backed ------------------
     A 401 means the session is dead. Leaving a half-rendered shell holding a
     stale error toast is a dead end, so send the operator to the canonical
     login. `/app/login` honours no return-path parameter (verified 2026-09-04),
     so no `next=` is passed — passing one would be dead code. The one-shot flag
     stops several concurrent in-flight calls from racing each other.        */
  function redirectToLogin() {
    try {
      if (window.__ax_login_redirect) return;
      window.__ax_login_redirect = true;
      window.location.href = '/app/login';
    } catch (e) { /* navigation blocked */ }
  }

  /* --- api: returns parsed JSON; throws Error with a human message --------- */
  async function api(path, opts) {
    opts = opts || {};
    var res;
    try {
      res = await fetch(path, {
        method: opts.method || 'GET',
        headers: authHeaders(opts.json ? { 'Content-Type': 'application/json' } : {}),
        body: opts.json ? JSON.stringify(opts.body || {}) : undefined,
        cache: 'no-store',
      });
    } catch (e) {
      throw new Error('Network unreachable');
    }
    var data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      var msg = (data && (data.detail || data.message)) || ('Request failed (' + res.status + ')');
      if (res.status === 401) {
        msg = 'Session expired — redirecting to sign in…';
        redirectToLogin();
      }
      throw new Error(msg);
    }
    return data || {};
  }

  /* --- escaping: all tenant-supplied text is escaped before injection ----- */
  function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function n(v) { return Number(v || 0); }

  function fmtInt(v) { return n(v).toLocaleString('en-IN'); }

  function fmtDate(v) {
    if (!v) return '—';
    try {
      var d = new Date(v);
      if (isNaN(d.getTime())) return String(v);
      return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch (e) { return String(v); }
  }

  /* --- toast -------------------------------------------------------------- */
  var toastHost = null;
  function toast(msg, tone) {
    if (!toastHost) {
      toastHost = document.createElement('div');
      toastHost.className = 'ax-toasts';
      toastHost.setAttribute('role', 'status');
      toastHost.setAttribute('aria-live', 'polite');
      document.body.appendChild(toastHost);
    }
    var el = document.createElement('div');
    el.className = 'ax-toast';
    el.setAttribute('data-tone', tone || 'info');
    el.textContent = msg;
    toastHost.appendChild(el);
    setTimeout(function () {
      el.style.transition = 'opacity 200ms ease';
      el.style.opacity = '0';
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    }, 4200);
  }

  /* --- drawer: THE single focused detail surface -------------------------- */
  var scrim = null, drawer = null;
  function ensureDrawer() {
    if (drawer) return;
    scrim = document.createElement('div');
    scrim.className = 'ax-scrim';
    scrim.addEventListener('click', closeDrawer);
    drawer = document.createElement('aside');
    drawer.className = 'ax-drawer';
    drawer.setAttribute('role', 'dialog');
    drawer.setAttribute('aria-modal', 'true');
    drawer.innerHTML =
      '<div class="ax-drawer__hd">' +
        '<div class="ax-grow"><div class="ax-title" data-drawer-title></div></div>' +
        '<button class="ax-btn ax-btn--ghost ax-btn--sm" data-drawer-close aria-label="Close">Close</button>' +
      '</div>' +
      '<div class="ax-drawer__bd" data-drawer-body></div>' +
      '<div class="ax-drawer__ft" data-drawer-foot></div>';
    document.body.appendChild(scrim);
    document.body.appendChild(drawer);
    drawer.querySelector('[data-drawer-close]').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeDrawer();
    });
  }

  function openDrawer(title, bodyHTML, footHTML) {
    ensureDrawer();
    drawer.querySelector('[data-drawer-title]').textContent = title;
    drawer.querySelector('[data-drawer-body]').innerHTML = bodyHTML || '';
    var ft = drawer.querySelector('[data-drawer-foot]');
    ft.innerHTML = footHTML || '';
    ft.style.display = footHTML ? '' : 'none';
    scrim.setAttribute('data-open', 'true');
    drawer.setAttribute('data-open', 'true');
  }

  function closeDrawer() {
    if (!drawer) return;
    scrim.setAttribute('data-open', 'false');
    drawer.setAttribute('data-open', 'false');
  }

  /* --- status vocabulary: one place maps API status -> chip tone ---------- */
  var STATUS_TONE = {
    healthy: 'green', ok: 'green', done: 'green', connected: 'green', live: 'green',
    never_configured: 'slate', unknown: 'slate', idle: 'slate', todo: 'slate',
    expiring_soon: 'amber', pending: 'amber', expiring: 'amber',
    revoked: 'rose', expired: 'rose', unauthorized: 'rose', error: 'rose', blocked: 'rose',
    transient_failure: 'orange', unreachable: 'orange',
  };
  function toneOf(s) { return STATUS_TONE[String(s || '').toLowerCase()] || 'slate'; }

  function chip(text, tone) {
    return '<span class="ax-chip ax-chip--' + esc(tone || 'slate') + '">' +
           '<span class="ax-chip__dot"></span>' + esc(text) + '</span>';
  }

  /* ======================================================================== */
  /* SYSTEM MAP — deterministic SVG, semantic palette only                    */
  /* ======================================================================== */
  var NODE_W = 160, NODE_H = 58;

  function renderMap(el, spec) {
    if (!el) return;
    var nodes = spec.nodes || [];
    var edges = spec.edges || [];
    var byId = {};
    nodes.forEach(function (nd) { byId[nd.id] = nd; });

    function edgePath(a, b) {
      // Right-centre of A -> left-centre of B, with a soft orthogonal bend.
      var ax = a.x + NODE_W, ay = a.y + NODE_H / 2;
      var bx = b.x, by = b.y + NODE_H / 2;
      if (Math.abs(ay - by) < 2) return 'M' + ax + ' ' + ay + ' H' + bx;
      var mid = (ax + bx) / 2;
      return 'M' + ax + ' ' + ay + ' H' + mid + ' V' + by + ' H' + bx;
    }

    var svg = '<svg class="ax-map__svg" viewBox="0 0 900 268" role="img" ' +
              'aria-label="Live configuration topology">';

    edges.forEach(function (e) {
      var a = byId[e.from], b = byId[e.to];
      if (!a || !b) return;
      svg += '<path class="ax-edge" data-state="' + esc(e.state || 'dim') + '" d="' +
             edgePath(a, b) + '" />';
    });

    nodes.forEach(function (nd) {
      var x = nd.x, y = nd.y;
      svg += '<g class="ax-node" tabindex="0" role="button" data-target="' + esc(nd.target || '') + '" ' +
             'aria-label="' + esc(nd.label + ' — ' + (nd.sub || '')) + '">';
      svg += '<rect class="ax-node-box" data-state="' + esc(nd.state || 'idle') + '" x="' + x +
             '" y="' + y + '" width="' + NODE_W + '" height="' + NODE_H +
             '" rx="8" ry="8" />';
      svg += '<text class="ax-node-t" x="' + (x + 14) + '" y="' + (y + 25) + '">' + esc(nd.label) + '</text>';
      svg += '<text class="ax-node-s" x="' + (x + 14) + '" y="' + (y + 42) + '">' + esc(nd.sub || '') + '</text>';
      svg += '</g>';
    });

    svg += '</svg>';

    var legend = '<div class="ax-map__legend">' +
      ['<span class="ax-row ax-row--tight"><span class="ax-chip ax-chip--green"><span class="ax-chip__dot"></span>Verified</span></span>',
       '<span class="ax-row ax-row--tight"><span class="ax-chip ax-chip--cyan"><span class="ax-chip__dot"></span>Active</span></span>',
       '<span class="ax-row ax-row--tight"><span class="ax-chip ax-chip--amber"><span class="ax-chip__dot"></span>Needs action</span></span>',
       '<span class="ax-row ax-row--tight"><span class="ax-chip ax-chip--rose"><span class="ax-chip__dot"></span>Blocked</span></span>',
       '<span class="ax-row ax-row--tight"><span class="ax-chip ax-chip--slate"><span class="ax-chip__dot"></span>Not configured</span></span>'
      ].join('') +
      '<span class="ax-grow"></span><span class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">CLICK A NODE TO OPEN ITS SECTION</span></div>';

    el.innerHTML = svg + legend;

    el.querySelectorAll('.ax-node').forEach(function (g) {
      var go = function () {
        var t = g.getAttribute('data-target');
        if (t) show(t);
      };
      g.addEventListener('click', go);
      g.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); go(); }
      });
    });
  }

  /* ======================================================================== */
  /* RENDERERS                                                                */
  /* ======================================================================== */

  function renderMetrics(el, metrics) {
    if (!el) return;
    el.innerHTML = (metrics || []).map(function (m) {
      return '<div class="ax-metric">' +
        '<span class="ax-label ax-metric__k">' + esc(m.k) + '</span>' +
        '<span class="ax-metric__v" data-tone="' + esc(m.tone || '') + '">' + esc(m.v) + '</span>' +
        (m.sub ? '<span class="ax-dim" style="font-size:.625rem">' + esc(m.sub) + '</span>' : '') +
        '</div>';
    }).join('');
  }

  function renderReadiness(el, data) {
    if (!el) return;
    var r = data.readiness || {};
    var steps = r.steps || [];

    var gates = '';
    if ((r.gates || []).length) {
      gates = '<div class="ax-panel" style="border-color:var(--cloud)">' +
        '<div class="ax-panel__bd ax-panel__bd--tight">' +
        (r.gates || []).map(function (g) {
          return '<div class="ax-row ax-row--tight" style="align-items:flex-start">' +
            '<span class="ax-chip ax-chip--' + (g.severity === 'error' ? 'rose' : 'amber') + '">' +
            esc(String(g.severity || 'warn').toUpperCase()) + '</span>' +
            '<span class="ax-grow ax-body">' + esc(g.message) + '</span></div>';
        }).join('<div style="height:.5rem"></div>') +
        '</div></div>';
    }

    el.innerHTML = gates +
      '<div class="ax-row ax-row--between" style="margin-bottom:.75rem">' +
        '<span class="ax-label">Provisioning — ' + esc(r.done || 0) + ' of ' + esc(r.total || 0) + ' complete</span>' +
        '<label class="ax-row ax-row--tight" style="cursor:pointer">' +
          '<input type="checkbox" id="ax-hide-done" ' +
            'style="accent-color:var(--frontend);width:13px;height:13px">' +
          '<span class="ax-label" style="text-transform:none;letter-spacing:.04em">Hide completed</span>' +
        '</label>' +
      '</div>' +
      '<div class="ax-readiness"><div class="ax-readiness__fill" style="width:' +
        esc(r.percent || 0) + '%"></div></div>' +
      '<div class="ax-steps" style="margin-top:1rem">' +
      steps.map(function (s, i) {
        return '<div class="ax-step" data-state="' + esc(s.state) + '" data-done="' +
          (s.done ? '1' : '0') + '">' +
          '<div class="ax-step__idx">' + esc(s.done ? '✓' : String(i + 1)) + '</div>' +
          '<div class="ax-step__body">' +
            '<div class="ax-step__t">' + esc(s.title) + '</div>' +
            '<div class="ax-step__d">' + esc(s.detail) + '</div>' +
          '</div>' +
          '<div class="ax-step__act">' +
            '<button class="ax-btn ax-btn--sm" data-goto="' + esc(s.target) + '">' +
              esc(s.done ? 'Review' : 'Set up') + '</button>' +
          '</div>' +
        '</div>';
      }).join('') +
      '</div>';

    var cb = document.getElementById('ax-hide-done');
    if (cb) {
      cb.addEventListener('change', function () {
        el.querySelectorAll('.ax-step').forEach(function (st) {
          st.style.display = (cb.checked && st.getAttribute('data-done') === '1') ? 'none' : '';
        });
      });
    }
    el.querySelectorAll('[data-goto]').forEach(function (b) {
      b.addEventListener('click', function () { show(b.getAttribute('data-goto')); });
    });
  }

  /* --- business form ------------------------------------------------------ */
  var LANGUAGES = [
    ['hinglish', 'Hinglish (recommended)'], ['hi-IN', 'Hindi'], ['en-IN', 'English'],
    ['mr-IN', 'Marathi'], ['gu-IN', 'Gujarati'], ['ta-IN', 'Tamil'], ['bn-IN', 'Bengali'],
  ];
  var TIMEZONES = ['Asia/Kolkata', 'Asia/Delhi', 'Asia/Mumbai', 'Asia/Calcutta'];
  var DAYS = [['mon', 'Mon'], ['tue', 'Tue'], ['wed', 'Wed'], ['thu', 'Thu'],
              ['fri', 'Fri'], ['sat', 'Sat'], ['sun', 'Sun']];

  function renderBusiness(el, data) {
    if (!el) return;
    var b = data.business || {};
    var hours = b.business_hours || {};
    var days = hours.days || ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

    el.innerHTML =
      '<div class="ax-panel">' +
        '<div class="ax-panel__hd"><div class="ax-panel__title">' +
          '<div class="ax-title">Business identity</div>' +
          '<div class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">HOW THE AGENT INTRODUCES YOU</div>' +
        '</div></div>' +
        '<div class="ax-panel__bd">' +
          '<div class="ax-field-row">' +
            field('business_name', 'Business name', b.business_name, 'Used in the greeting') +
            field('niche', 'Industry / niche', b.niche, 'Selects default scripts') +
          '</div>' +
          '<div class="ax-field-row">' +
            field('phone', 'Business phone', b.phone, '') +
            field('email', 'Business email', b.email, 'Where lead summaries are sent') +
          '</div>' +
          '<div class="ax-field-row">' +
            field('city', 'City', b.city, '') +
            field('website', 'Website', b.website, 'Can be imported into knowledge') +
          '</div>' +
        '</div>' +
      '</div>' +

      '<div class="ax-panel">' +
        '<div class="ax-panel__hd"><div class="ax-panel__title">' +
          '<div class="ax-title">Agent behaviour</div>' +
          '<div class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">LANGUAGE, HOURS AND VOICE</div>' +
        '</div></div>' +
        '<div class="ax-panel__bd">' +
          '<div class="ax-field-row">' +
            '<div class="ax-field"><label class="ax-label ax-field__label" for="f-language">Language</label>' +
              '<select class="ax-select" id="f-language" data-f="language">' +
                LANGUAGES.map(function (l) {
                  return '<option value="' + esc(l[0]) + '"' +
                    (String(b.language || 'hinglish') === l[0] ? ' selected' : '') + '>' +
                    esc(l[1]) + '</option>';
                }).join('') +
              '</select></div>' +
            '<div class="ax-field"><label class="ax-label ax-field__label" for="f-timezone">Timezone</label>' +
              '<select class="ax-select" id="f-timezone" data-f="timezone">' +
                TIMEZONES.map(function (t) {
                  return '<option value="' + esc(t) + '"' +
                    (String(b.timezone || 'Asia/Kolkata') === t ? ' selected' : '') + '>' +
                    esc(t) + '</option>';
                }).join('') +
              '</select></div>' +
          '</div>' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label" for="f-greeting">Opening line</label>' +
            '<input class="ax-input" id="f-greeting" data-f="greeting" maxlength="500" ' +
              'value="' + esc(b.greeting || '') + '" ' +
              'placeholder="Namaste, {{business_name}} mein aapka swagat hai.">' +
            '<div class="ax-field__hint">Use {{business_name}} to insert your business name.</div>' +
          '</div>' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label" for="f-voice">Brand voice</label>' +
            '<textarea class="ax-textarea" id="f-voice" data-f="brand_voice" maxlength="2000" ' +
              'placeholder="Warm and professional. Short sentences. Never over-promise.">' +
              esc(b.brand_voice || '') + '</textarea>' +
            '<div class="ax-field__hint">Steers tone across calls and generated content.</div>' +
          '</div>' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label">Calling days</label>' +
            '<div class="ax-row ax-row--tight" id="f-days">' +
              DAYS.map(function (d) {
                return '<label class="ax-chip" style="cursor:pointer;text-transform:none;letter-spacing:.04em;height:28px">' +
                  '<input type="checkbox" value="' + esc(d[0]) + '"' +
                  (days.indexOf(d[0]) >= 0 ? ' checked' : '') +
                  ' style="accent-color:var(--frontend);width:12px;height:12px"> ' +
                  esc(d[1]) + '</label>';
              }).join('') +
            '</div>' +
          '</div>' +
          '<div class="ax-field-row">' +
            '<div class="ax-field"><label class="ax-label ax-field__label" for="f-open">Window start</label>' +
              '<input class="ax-input" id="f-open" type="time" value="' +
                esc(hours.start || '10:00') + '"></div>' +
            '<div class="ax-field"><label class="ax-label ax-field__label" for="f-close">Window end</label>' +
              '<input class="ax-input" id="f-close" type="time" value="' +
                esc(hours.end || '19:00') + '"></div>' +
          '</div>' +
          '<div class="ax-field__hint">Outside this window, calls are queued for the next business day.</div>' +
        '</div>' +
        '<div class="ax-panel__ft">' +
          '<span class="ax-grow ax-dim" id="f-status" style="font-size:.625rem;letter-spacing:.12em">UNSAVED CHANGES APPEAR HERE</span>' +
          '<button class="ax-btn ax-btn--primary" id="f-save">Save configuration</button>' +
        '</div>' +
      '</div>';
  }

  function field(name, label, value, hint) {
    return '<div class="ax-field">' +
      '<label class="ax-label ax-field__label" for="f-' + esc(name) + '">' + esc(label) + '</label>' +
      '<input class="ax-input" id="f-' + esc(name) + '" data-f="' + esc(name) + '" value="' +
        esc(value || '') + '">' +
      (hint ? '<div class="ax-field__hint">' + esc(hint) + '</div>' : '') +
      '</div>';
  }

  /* --- knowledge ---------------------------------------------------------- */
  function renderKnowledge(el, data, product) {
    if (!el) return;
    var kb = data.knowledge || {};
    var sources = kb.sources || [];

    var rows = sources.length
      ? '<div class="ax-table-wrap"><table class="ax-table"><thead><tr>' +
          '<th>Source</th><th>Kind</th><th class="ax-table__num">Chunks</th><th>Added</th><th></th>' +
        '</tr></thead><tbody>' +
        sources.map(function (s) {
          return '<tr>' +
            '<td class="ax-table__clip" title="' + esc(s.source) + '">' + esc(s.source) + '</td>' +
            '<td>' + chip(String(s.kind || 'text').toUpperCase(), 'violet') + '</td>' +
            '<td class="ax-table__num">' + fmtInt(s.chunks) + '</td>' +
            '<td class="ax-nowrap ax-muted">' + esc(fmtDate(s.added_at)) + '</td>' +
            '<td><button class="ax-btn ax-btn--ghost ax-btn--sm" data-kb-del="' + esc(s.source) + '">Remove</button></td>' +
          '</tr>';
        }).join('') +
        '</tbody></table></div>'
      : '<div class="ax-empty">' +
          '<div class="ax-empty__t">No knowledge yet</div>' +
          '<p class="ax-empty__d">Until you add knowledge, the agent answers with a safe hand-off ' +
          'instead of guessing. Add your FAQs or import your website.</p>' +
          '<button class="ax-btn ax-btn--primary" data-kb-focus="text">Add your first source</button>' +
        '</div>';

    el.innerHTML =
      '<div class="ax-panel">' +
        '<div class="ax-panel__hd">' +
          '<div class="ax-panel__title">' +
            '<div class="ax-title">Knowledge sources</div>' +
            '<div class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">NAMESPACE ' +
              esc(kb.namespace || '') + ' · BACKEND ' + esc(String(kb.backend || '').toUpperCase()) + '</div>' +
          '</div>' +
          '<span class="ax-grow"></span>' +
          chip(fmtInt(kb.chunks) + ' CHUNKS', kb.chunks > 0 ? 'violet' : 'slate') +
        '</div>' +
        '<div class="ax-panel__bd">' + rows + '</div>' +
      '</div>' +

      '<div class="ax-panel">' +
        '<div class="ax-panel__hd"><div class="ax-panel__title">' +
          '<div class="ax-title">Add knowledge</div>' +
          '<div class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">PERSISTED TO YOUR PRIVATE NAMESPACE</div>' +
        '</div></div>' +
        '<div class="ax-panel__bd">' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label" for="kb-source">Source label</label>' +
            '<input class="ax-input" id="kb-source" placeholder="e.g. Pricing FAQ" maxlength="120">' +
          '</div>' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label" for="kb-text">Paste content</label>' +
            '<textarea class="ax-textarea" id="kb-text" maxlength="50000" ' +
              'placeholder="Paste pricing, services, timings, policies — anything the agent must answer accurately."></textarea>' +
            '<div class="ax-field__hint">Minimum 10 characters. Longer text is split into retrievable chunks automatically.</div>' +
          '</div>' +
          '<div class="ax-row">' +
            '<button class="ax-btn ax-btn--primary" id="kb-add-text">Ingest text</button>' +
            '<label class="ax-switch"><input type="checkbox" id="kb-replace">' +
              '<span class="ax-switch__track"></span>' +
              '<span class="ax-switch__text">Replace existing content for this source</span></label>' +
          '</div>' +
          '<hr class="ax-sep">' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label" for="kb-url">Or import a web page</label>' +
            '<div class="ax-row">' +
              '<input class="ax-input ax-grow" id="kb-url" placeholder="https://yourbusiness.com/services" maxlength="500">' +
              '<button class="ax-btn" id="kb-add-url">Import page</button>' +
            '</div>' +
            '<div class="ax-field__hint">Fetches the page, strips layout, and stores the readable text.</div>' +
          '</div>' +
        '</div>' +
      '</div>' +

      '<div class="ax-panel">' +
        '<div class="ax-panel__hd"><div class="ax-panel__title">' +
          '<div class="ax-title">Grounding probe</div>' +
          '<div class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">TEST BEFORE YOU GO LIVE — NO CREDENTIALS REQUIRED</div>' +
        '</div></div>' +
        '<div class="ax-panel__bd">' +
          '<div class="ax-field">' +
            '<label class="ax-label ax-field__label" for="kb-probe">Ask what a customer would ask</label>' +
            '<div class="ax-row">' +
              '<input class="ax-input ax-grow" id="kb-probe" placeholder="Aapki service ka charge kya hai?" maxlength="500">' +
              '<button class="ax-btn ax-btn--primary" id="kb-probe-run">Run probe</button>' +
            '</div>' +
          '</div>' +
          '<div id="kb-probe-out"></div>' +
        '</div>' +
      '</div>';
  }

  function renderProbeResult(out, res) {
    var ev = (res.evidence || []);
    out.innerHTML =
      '<div class="ax-row ax-row--tight" style="margin-bottom:.75rem">' +
        chip(res.grounded ? 'GROUNDED' : 'NO MATCH', res.grounded ? 'green' : 'amber') +
        '<span class="ax-dim" style="font-size:.625rem;letter-spacing:.12em">' +
          esc(ev.length) + ' SOURCE CHUNK' + (ev.length === 1 ? '' : 'S') + '</span>' +
      '</div>' +
      '<div class="ax-mono-block">' + esc(res.answer) + '</div>' +
      (ev.length
        ? '<div style="margin-top:1rem"><div class="ax-label" style="margin-bottom:.5rem">Evidence</div>' +
          ev.map(function (e) {
            return '<div class="ax-panel" style="margin-bottom:.5rem">' +
              '<div class="ax-panel__bd ax-panel__bd--tight">' +
                '<div class="ax-row ax-row--between" style="margin-bottom:.25rem">' +
                  '<span class="ax-chip ax-chip--violet">' + esc(e.source || 'source') + '</span>' +
                  '<span class="ax-num ax-dim" style="font-size:.625rem">SCORE ' + esc(e.score) + '</span>' +
                '</div>' +
                '<div class="ax-body ax-muted">' + esc(e.text) + '</div>' +
              '</div></div>';
          }).join('') + '</div>'
        : '');
  }

  /* --- connections (three-state vault cards) ------------------------------ */
  function renderConnections(el, data) {
    if (!el) return;
    var c = data.connections || {};
    var plats = c.platforms || [];

    var cards = plats.map(function (p) {
      var connected = p.status && p.status !== 'never_configured';
      var tone = toneOf(connected ? p.status : 'never_configured');
      var label = connected ? (p.label || 'Connected') : 'Not connected';
      return '<div class="ax-panel" style="margin-bottom:.75rem">' +
        '<div class="ax-panel__bd ax-panel__bd--tight">' +
          '<div class="ax-row ax-row--between">' +
            '<div class="ax-grow">' +
              '<div class="ax-title">' + esc(platformName(p.platform)) + '</div>' +
              '<div class="ax-dim" style="font-size:.625rem;letter-spacing:.12em;margin-top:.125rem">' +
                esc(String(p.platform).toUpperCase()) + '</div>' +
            '</div>' +
            chip(label, tone) +
          '</div>' +
          (connected && p.action_required
            ? '<div class="ax-row ax-row--tight" style="margin-top:.75rem">' +
                '<span class="ax-chip ax-chip--amber"><span class="ax-chip__dot"></span>ACTION REQUIRED</span>' +
                '<span class="ax-body ax-muted">' + esc(p.recommended_action || '') + '</span></div>'
            : '') +
          (!connected && p.external_blocker
            ? '<div class="ax-body ax-muted" style="margin-top:.75rem">' +
                esc(p.external_blocker) + '</div>'
            : '') +
          '<div class="ax-row ax-row--tight" style="margin-top:.75rem">' +
            (connected
              ? '<button class="ax-btn ax-btn--danger ax-btn--sm" data-revoke="' + esc(p.platform) + '">Disconnect</button>'
              : '<button class="ax-btn ax-btn--primary ax-btn--sm" data-connect="' + esc(p.platform) + '"' +
                (p.oauth_ready ? '' : ' disabled') + '>' +
                esc(p.oauth_ready ? 'Connect' : 'Not available') + '</button>') +
            '<button class="ax-btn ax-btn--ghost ax-btn--sm" data-scopes="' + esc(p.platform) + '">Scopes</button>' +
          '</div>' +
        '</div></div>';
    }).join('');

    el.innerHTML =
      '<div class="ax-metrics">' +
        '<div class="ax-metric"><span class="ax-label ax-metric__k">Connected</span>' +
          '<span class="ax-metric__v" data-tone="' + (c.connected > 0 ? 'green' : '') + '">' +
            fmtInt(c.connected) + '</span></div>' +
        '<div class="ax-metric"><span class="ax-label ax-metric__k">Available</span>' +
          '<span class="ax-metric__v">' + fmtInt(c.total) + '</span></div>' +
        '<div class="ax-metric"><span class="ax-label ax-metric__k">Storage</span>' +
          '<span class="ax-metric__v" style="font-size:.875rem">ENCRYPTED</span>' +
          '<span class="ax-dim" style="font-size:.625rem">Fernet at rest</span></div>' +
      '</div>' +
      (cards || '<div class="ax-empty"><div class="ax-empty__t">No channels available</div>' +
        '<p class="ax-empty__d">Channel availability depends on platform approval. ' +
        'Contact support to enable more.</p></div>');
  }

  function platformName(k) {
    return ({
      facebook: 'Facebook', instagram: 'Instagram', linkedin: 'LinkedIn',
      gbp: 'Google Business Profile', x: 'X (Twitter)', youtube: 'YouTube',
    })[String(k)] || String(k);
  }

  /* ======================================================================== */
  /* NAVIGATION                                                               */
  /* ======================================================================== */
  var current = '';
  function show(id) {
    document.querySelectorAll('.ax-view').forEach(function (v) {
      v.setAttribute('data-active', v.getAttribute('data-view') === id ? 'true' : 'false');
    });
    document.querySelectorAll('.ax-nav').forEach(function (n) {
      if (n.getAttribute('data-view') === id) n.setAttribute('aria-current', 'page');
      else n.removeAttribute('aria-current');
    });
    current = id;
    if (history.replaceState) history.replaceState(null, '', '#' + id);
    var main = document.querySelector('.ax-main');
    if (main) main.scrollTop = 0;
  }

  /* ======================================================================== */
  /* BOOT                                                                     */
  /* ======================================================================== */
  async function boot(opts) {
    var data;
    try {
      data = await api('/api/consoles/bootstrap?product=' + encodeURIComponent(opts.product));
    } catch (e) {
      document.querySelector('.ax-main').innerHTML =
        '<div class="ax-canvas"><div class="ax-empty"><div class="ax-empty__t">Could not load console</div>' +
        '<p class="ax-empty__d">' + esc(e.message) + '</p></div></div>';
      return;
    }

    AC.data = data;
    AC.product = opts.product;

    renderMetrics(document.getElementById('ax-metrics'), opts.metrics ? opts.metrics(data) : []);
    renderMap(document.getElementById('ax-map'), opts.mapSpec(data));
    renderReadiness(document.getElementById('ax-readiness'), data);
    renderBusiness(document.getElementById('ax-business'), data);
    renderKnowledge(document.getElementById('ax-knowledge'), data, opts.product);
    renderConnections(document.getElementById('ax-connections'), data);
    if (opts.extra) opts.extra(data);

    // nav
    document.querySelectorAll('.ax-nav').forEach(function (n) {
      n.addEventListener('click', function () { show(n.getAttribute('data-view')); });
    });

    var hash = (location.hash || '').replace('#', '');
    var first = (opts.nav && opts.nav[0] && opts.nav[0].id) || 'readiness';
    show(hash || first);

    wireBusiness();
    wireKnowledge();
    wireConnections();
    if (opts.wire) opts.wire(data);
  }

  function collectBusiness() {
    var out = {};
    document.querySelectorAll('#ax-business [data-f]').forEach(function (i) {
      out[i.getAttribute('data-f')] = i.value;
    });
    var days = [];
    document.querySelectorAll('#f-days input:checked').forEach(function (c) { days.push(c.value); });
    out.business_hours = {
      days: days,
      start: (document.getElementById('f-open') || {}).value || '10:00',
      end: (document.getElementById('f-close') || {}).value || '19:00',
    };
    return out;
  }

  function wireBusiness() {
    var btn = document.getElementById('f-save');
    if (!btn) return;
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      var st = document.getElementById('f-status');
      st.textContent = 'SAVING…';
      try {
        await api('/api/consoles/business-config', { method: 'PUT', json: true, body: collectBusiness() });
        st.textContent = 'SAVED';
        toast('Business configuration saved.', 'ok');
        var d = await api('/api/consoles/bootstrap?product=' + encodeURIComponent(AC.product));
        AC.data = d;
        renderReadiness(document.getElementById('ax-readiness'), d);
        renderMap(document.getElementById('ax-map'), (AC.opts.mapSpec)(d));
      } catch (e) {
        st.textContent = 'SAVE FAILED';
        toast(e.message, 'error');
      } finally {
        btn.disabled = false;
      }
    });
  }

  async function refresh() {
    var d = await api('/api/consoles/bootstrap?product=' + encodeURIComponent(AC.product));
    AC.data = d;
    renderMetrics(document.getElementById('ax-metrics'), AC.opts.metrics ? AC.opts.metrics(d) : []);
    renderMap(document.getElementById('ax-map'), AC.opts.mapSpec(d));
    renderReadiness(document.getElementById('ax-readiness'), d);
    renderKnowledge(document.getElementById('ax-knowledge'), d, AC.product);
    renderConnections(document.getElementById('ax-connections'), d);
    if (AC.opts.extra) AC.opts.extra(d);
  }

  function wireKnowledge() {
    var addText = document.getElementById('kb-add-text');
    if (addText) addText.addEventListener('click', async function () {
      var src = (document.getElementById('kb-source') || {}).value || '';
      var txt = (document.getElementById('kb-text') || {}).value || '';
      if (!src.trim()) return toast('Give this source a label first.', 'warn');
      if (txt.trim().length < 10) return toast('Paste at least 10 characters.', 'warn');
      addText.disabled = true;
      try {
        var r = await api('/api/consoles/knowledge/text', {
          method: 'POST', json: true,
          body: { text: txt, source: src.trim(),
                  replace: !!((document.getElementById('kb-replace') || {}).checked) },
        });
        toast(fmtInt(r.chunks_added) + ' chunks added.', 'ok');
        document.getElementById('kb-text').value = '';
        await refresh();
      } catch (e) { toast(e.message, 'error'); }
      finally { addText.disabled = false; }
    });

    var addUrl = document.getElementById('kb-add-url');
    if (addUrl) addUrl.addEventListener('click', async function () {
      var u = ((document.getElementById('kb-url') || {}).value || '').trim();
      if (!u) return toast('Enter a URL.', 'warn');
      addUrl.disabled = true;
      try {
        var r = await api('/api/consoles/knowledge/url', { method: 'POST', json: true, body: { url: u } });
        toast(fmtInt(r.chunks_added) + ' chunks imported.', 'ok');
        document.getElementById('kb-url').value = '';
        await refresh();
      } catch (e) { toast(e.message, 'error'); }
      finally { addUrl.disabled = false; }
    });

    var run = document.getElementById('kb-probe-run');
    if (run) run.addEventListener('click', async function () {
      var q = ((document.getElementById('kb-probe') || {}).value || '').trim();
      if (q.length < 2) return toast('Type a question first.', 'warn');
      var out = document.getElementById('kb-probe-out');
      out.innerHTML = '<div class="ax-skel" style="width:60%"></div>';
      try {
        var r = await api('/api/consoles/knowledge/probe', { method: 'POST', json: true, body: { query: q } });
        renderProbeResult(out, r);
      } catch (e) { out.innerHTML = '<div class="ax-body" style="color:var(--security)">' + esc(e.message) + '</div>'; }
    });

    document.querySelectorAll('[data-kb-del]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var s = b.getAttribute('data-kb-del');
        if (!confirm('Remove this source? "' + s + '" will no longer ground any answer.')) return;
        try {
          await api('/api/consoles/knowledge/source?source=' + encodeURIComponent(s), { method: 'DELETE' });
          toast('Source removed.', 'ok');
          await refresh();
        } catch (e) { toast(e.message, 'error'); }
      });
    });

    var focusBtn = document.querySelector('[data-kb-focus]');
    if (focusBtn) focusBtn.addEventListener('click', function () {
      var t = document.getElementById('kb-text');
      if (t) t.focus();
    });
  }

  function wireConnections() {
    document.querySelectorAll('[data-connect]').forEach(function (b) {
      b.addEventListener('click', function () {
        var p = b.getAttribute('data-connect');
        window.location.href = '/api/social/oauth/' + encodeURIComponent(p) +
          '/start?return_to=' + encodeURIComponent(location.pathname + '#connections');
      });
    });
    document.querySelectorAll('[data-revoke]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var p = b.getAttribute('data-revoke');
        if (!confirm('Disconnect ' + platformName(p) + '? Stored credentials will be deleted.')) return;
        try {
          await api('/api/consoles/connections/' + encodeURIComponent(p), { method: 'DELETE' });
          toast(platformName(p) + ' disconnected.', 'ok');
          await refresh();
        } catch (e) { toast(e.message, 'error'); }
      });
    });
    document.querySelectorAll('[data-scopes]').forEach(function (b) {
      b.addEventListener('click', function () {
        var p = b.getAttribute('data-scopes');
        var rec = ((AC.data.connections || {}).platforms || []).filter(function (x) {
          return x.platform === p;
        })[0] || {};
        var scopes = rec.scopes_required || [];
        openDrawer(platformName(p) + ' — requested access',
          '<div class="ax-body ax-muted" style="margin-bottom:1rem">' +
            'We request the narrowest scopes needed to publish and read basic ' +
            'account metadata. Tokens are encrypted at rest and can be revoked at any time.' +
          '</div>' +
          (scopes.length
            ? '<ul class="ax-col" style="gap:.5rem">' + scopes.map(function (s) {
                return '<li class="ax-row ax-row--tight"><span class="ax-chip ax-chip--cyan" ' +
                  'style="text-transform:none;letter-spacing:.02em">' + esc(s) + '</span></li>';
              }).join('') + '</ul>'
            : '<div class="ax-dim">No OAuth scopes — this channel uses a token or is not yet available.</div>'),
          '<button class="ax-btn" data-drawer-close>Close</button>');
      });
    });
  }

  var AC = {
    token: token, api: api, esc: esc, toast: toast, chip: chip,
    openDrawer: openDrawer, closeDrawer: closeDrawer,
    renderMap: renderMap, renderMetrics: renderMetrics, renderReadiness: renderReadiness,
    renderBusiness: renderBusiness, renderKnowledge: renderKnowledge,
    renderConnections: renderConnections, renderProbeResult: renderProbeResult,
    platformName: platformName, toneOf: toneOf, fmtInt: fmtInt, fmtDate: fmtDate,
    show: show, refresh: refresh, data: {}, product: 'voice', opts: {},
    init: function (opts) { AC.opts = opts; return boot(opts); },
  };

  window.AC = AC;
})();
