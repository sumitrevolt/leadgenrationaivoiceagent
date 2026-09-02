/* LeadGen AI — "🏢 Aapka Office" virtual-office widget (shared by all 3 customer
   dashboards: combo /app/customer, marketing /app/customer/marketing, voice
   /app/customer/voice). Self-mounts into <div id="aapkaOffice"></div>, fetches
   /api/customer/office, and renders three things a non-technical customer needs
   at a glance:
     1. 📋 Aapke kaam  — manual to-dos with WHY + automation-IMPACT + a CTA that
        scrolls to the relevant existing card (no new pages).
     2. 🤖 AI team ne kya kiya — recent activity (what we did for you).
   Product-aware payload comes from the backend; this file is presentation only.
   Degrades silently: no token / disabled / error => renders nothing (the page's
   own cards still work). All dynamic text is HTML-escaped (inquiry names/cities
   are user-controlled). */
(function () {
  "use strict";
  var MOUNT_ID = "aapkaOffice";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function injectStyles() {
    if (document.getElementById("lgo-style")) return;
    var css =
      ".lgo-wrap{background:var(--card,#fff);border:1px solid var(--line,#e5e7eb);" +
      "border-radius:14px;box-shadow:var(--shadow,0 6px 20px rgba(20,16,40,.06));" +
      "padding:16px 18px;margin:0 0 18px}" +
      ".lgo-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}" +
      ".lgo-title{font-size:16px;font-weight:800;color:var(--ink,#1e1b2e)}" +
      ".lgo-headline{font-size:13px;font-weight:700;color:var(--muted,#6b7280)}" +
      ".lgo-stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}" +
      ".lgo-stat{flex:1 1 110px;min-width:100px;background:#f8f8fc;border:1px solid var(--line,#e5e7eb);" +
      "border-radius:11px;padding:9px 12px;text-align:center}" +
      ".lgo-stat b{display:block;font-size:19px;font-weight:800;color:var(--ink,#1e1b2e)}" +
      ".lgo-stat span{font-size:10.5px;font-weight:700;color:var(--muted,#6b7280);text-transform:uppercase;letter-spacing:.3px}" +
      ".lgo-cols{display:grid;grid-template-columns:1.25fr 1fr;gap:18px;margin-top:10px}" +
      ".lgo-subh{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;" +
      "color:var(--muted,#6b7280);margin:2px 0 9px}" +
      ".lgo-task{display:flex;align-items:flex-start;gap:11px;background:#fff;" +
      "border:1px solid var(--line,#e5e7eb);border-left:4px solid var(--no,#9ca3af);" +
      "border-radius:11px;padding:11px 12px;margin-bottom:9px}" +
      ".lgo-task.sev-high{border-left-color:var(--bad,#dc2626);background:#fff7f7}" +
      ".lgo-task.sev-medium{border-left-color:var(--busy,#d97706);background:#fffbf2}" +
      ".lgo-task.sev-low{border-left-color:var(--no,#9ca3af)}" +
      ".lgo-ic{font-size:21px;line-height:1;flex:0 0 auto;margin-top:1px}" +
      ".lgo-tbody{flex:1;min-width:0}" +
      ".lgo-tt{font-weight:800;font-size:13.5px;color:var(--ink,#1e1b2e)}" +
      ".lgo-tw{font-size:12px;color:var(--muted,#6b7280);margin-top:2px}" +
      ".lgo-imp{font-size:12px;font-weight:700;color:#15803d;margin-top:5px}" +  /* darker green = WCAG-AA on light cards */
      ".lgo-cta{flex:0 0 auto;align-self:center;background:var(--brand,#6d28d9);color:#fff;" +
      "border:none;border-radius:9px;padding:9px 12px;font-size:12px;font-weight:700;" +
      "cursor:pointer;min-height:38px;white-space:nowrap}" +
      ".lgo-cta:hover{filter:brightness(1.07)}" +
      ".lgo-empty{font-size:13px;color:var(--muted,#6b7280);background:#f8f8fc;" +
      "border:1px dashed var(--line,#e5e7eb);border-radius:11px;padding:14px}" +
      ".lgo-act{display:flex;gap:10px;padding:8px 2px;border-bottom:1px solid var(--line,#eef0f4)}" +
      ".lgo-act:last-child{border-bottom:none}" +
      ".lgo-when{flex:0 0 84px;font-size:11px;color:#6b7280;font-weight:600;padding-top:1px}" +  /* AA contrast on white */
      ".lgo-did{flex:1;font-size:12.5px;color:var(--ink,#1e1b2e);min-width:0}" +
      ".lgo-flash{animation:lgoFlash 1.6s ease}" +
      "@keyframes lgoFlash{0%,100%{box-shadow:0 0 0 0 rgba(109,40,217,0)}" +
      "30%{box-shadow:0 0 0 4px rgba(109,40,217,.35)}}" +
      "@media(max-width:760px){.lgo-cols{grid-template-columns:1fr;gap:14px}" +
      ".lgo-cta{padding:9px 10px}}" +
      "@media(max-width:440px){.lgo-task{flex-wrap:wrap}" +
      ".lgo-tbody{flex:1 1 100%}.lgo-cta{width:100%;margin-top:8px}}";
    var st = document.createElement("style");
    st.id = "lgo-style";
    st.textContent = css;
    document.head.appendChild(st);
  }

  function scrollToTarget(id) {
    if (!id) return;
    var el = document.getElementById(id);
    if (!el) return;
    try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) { el.scrollIntoView(); }
    el.classList.add("lgo-flash");
    setTimeout(function () { el.classList.remove("lgo-flash"); }, 1700);
  }

  function taskHtml(t) {
    var sev = t.severity === "high" ? "sev-high" : t.severity === "medium" ? "sev-medium" : "sev-low";
    return (
      '<div class="lgo-task ' + sev + '">' +
      '<div class="lgo-ic">' + esc(t.icon || "•") + "</div>" +
      '<div class="lgo-tbody">' +
      '<div class="lgo-tt">' + esc(t.title) + "</div>" +
      '<div class="lgo-tw">' + esc(t.why) + "</div>" +
      '<div class="lgo-imp">⚡ ' + esc(t.impact) + "</div>" +
      "</div>" +
      (t.cta_target || t.cta_url
        ? '<button class="lgo-cta" data-target="' + esc(t.cta_target || "") +
          '" data-url="' + esc(t.cta_url || "") + '">' + esc(t.cta_label || "Dekho") + " →</button>"
        : "") +
      "</div>"
    );
  }

  function actHtml(a) {
    return (
      '<div class="lgo-act"><div class="lgo-when">' + esc(a.when || "") + "</div>" +
      '<div class="lgo-did"><b>' + esc(a.who || "") + "</b> — " + esc(a.did || "") + "</div></div>"
    );
  }

  function stat(n, label) {
    return '<div class="lgo-stat"><b>' + esc(n) + '</b><span>' + esc(label) + "</span></div>";
  }

  function statsHtml(summary, product) {
    if (!summary) return "";
    var isVoice = product === "voice" || product === "combo";
    var items = [
      stat(summary.posts_ready || 0, "Posts taiyaar"),
      stat(summary.approvals_pending || 0, "Approval pending"),
      stat(summary.new_leads || 0, "Naye leads"),
      stat(summary.hot_leads || 0, "🔥 Hot leads"),
    ];
    // voice/combo only — calls/bookings are meaningless (always 0) for a pure
    // marketing plan, so hiding them avoids a confusing "0 calls" on a plan
    // that never makes calls.
    if (isVoice) {
      items.push(stat(summary.calls_completed || 0, "Calls complete"));
      items.push(stat(summary.bookings || 0, "Bookings"));
    }
    return '<div class="lgo-stats" aria-label="Aaj tak ka kaam">' + items.join("") + "</div>";
  }

  function render(mount, data) {
    if (!data || data.enabled === false) { mount.innerHTML = ""; return; }
    injectStyles();
    var tasks = Array.isArray(data.your_tasks) ? data.your_tasks : [];
    var acts = Array.isArray(data.activity) ? data.activity : [];

    var tasksHtml = tasks.length
      ? tasks.map(taskHtml).join("")
      : '<div class="lgo-empty">✅ Abhi aapko kuch nahi karna — aapki AI team sab sambhaal rahi hai 🎉</div>';
    var actsHtml = acts.length
      ? acts.map(actHtml).join("")
      : '<div class="lgo-empty">Abhi tak koi activity nahi. Setup pura karo — phir yahan har kaam dikhega.</div>';

    mount.innerHTML =
      '<section class="lgo-wrap" aria-label="Aapka Office">' +
      '<div class="lgo-head"><div class="lgo-title">🏢 Aapka Office</div>' +
      '<div class="lgo-headline">' + esc(data.headline || "") + "</div></div>" +
      statsHtml(data.summary, data.product) +
      '<div class="lgo-cols">' +
      '<div class="lgo-col"><div class="lgo-subh">📋 Aapke kaam' +
      (tasks.length ? " (" + tasks.length + ")" : "") + "</div>" + tasksHtml + "</div>" +
      '<div class="lgo-col"><div class="lgo-subh">🤖 AI team ne kya kiya</div>' + actsHtml + "</div>" +
      "</div></section>";

    var btns = mount.querySelectorAll(".lgo-cta");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () {
        var url = this.getAttribute("data-url");
        if (url) { window.location.href = url; return; }
        scrollToTarget(this.getAttribute("data-target"));
      });
    }
  }

  function load() {
    var mount = document.getElementById(MOUNT_ID);
    if (!mount) return;
    var token = "";
    try { token = localStorage.getItem("lgai_token") || ""; } catch (e) {}
    if (!token) { mount.innerHTML = ""; return; } // not logged in — page auth handles it
    fetch("/api/customer/office", { headers: { Authorization: "Bearer " + token } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) render(mount, j); else mount.innerHTML = ""; })
      .catch(function () { mount.innerHTML = ""; });
  }

  // Expose a manual refresh hook (e.g. after a customer approves a post).
  window.LeadGenOffice = { refresh: load };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
