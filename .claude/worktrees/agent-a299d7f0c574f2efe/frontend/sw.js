// LeadsGenAI PWA service worker — dashboards network-only; shell cache optional.
const CACHE = "lgai-v2";

function isAppPage(url) {
  try {
    const p = new URL(url).pathname;
    return p.startsWith("/app/") || p === "/sw.js";
  } catch (_) {
    return false;
  }
}

self.addEventListener("install", (e) => {
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => clients.claim())
  );
});
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || !e.request.url.startsWith(self.location.origin)) return;
  if (e.request.url.includes("/api/")) return;
  if (isAppPage(e.request.url)) {
    e.respondWith(fetch(e.request, { cache: "no-store" }));
    return;
  }
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        const copy = r.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});

// Web Push (webpush.py) — push notification listener
self.addEventListener("push", function (e) {
  var d = {};
  try {
    d = e.data ? e.data.json() : {};
  } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(d.title || "LeadsGenAI", {
      body: d.body || "",
      icon: "/pwa-icon-192.png",
      badge: "/pwa-icon-192.png",
      data: { url: d.url || "/" },
    })
  );
});
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  e.waitUntil(
    clients.openWindow((e.notification.data && e.notification.data.url) || "/")
  );
});
