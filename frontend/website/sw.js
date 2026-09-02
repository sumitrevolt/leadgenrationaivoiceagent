// LeadGen AI — Service Worker
// Public marketing shell = cache-first. App + revenue pages = network-only (never stale).
const CACHE_NAME = "leadgen-ai-v6"; // v6: conversion pages always-fresh (2026-08-16)

const SHELL_ASSETS = ["/manifest.json", "/icons/icon.svg"];

function isAlwaysFreshPage(url) {
  try {
    const p = new URL(url).pathname;
    return (
      p.startsWith("/app/") ||
      p.startsWith("/design-system/") ||
      p === "/" ||
      p === "/index.html" ||
      p === "/audit" ||
      p === "/site-audit" ||
      p === "/demo" ||
      p === "/pricing" ||
      p === "/start" ||
      p === "/sw.js"
    );
  } catch (_) {
    return false;
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  if (request.url.includes("/api/")) return;

  // Dashboards + conversion funnel: always network — deploy/UI changes turant dikhein.
  if (isAlwaysFreshPage(request.url)) {
    event.respondWith(fetch(request, { cache: "no-store" }));
    return;
  }

  // Marketing shell: cache-first (offline landing).
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === "basic") {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => {
          if (request.mode === "navigate") {
            return caches.match("/index.html");
          }
        });
    })
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
