// LeadGen AI — Service Worker (offline shell caching)
const CACHE_NAME = 'leadgen-ai-v1';
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icons/icon.svg'
];

// Install: pre-cache the static shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: cache-first for static shell, network fallback (and cache new GETs)
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          // Only cache same-origin successful responses
          if (
            response &&
            response.status === 200 &&
            response.type === 'basic'
          ) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => {
          // Offline fallback: serve the cached landing page for navigations
          if (request.mode === 'navigate') {
            return caches.match('/index.html');
          }
        });
    })
  );
});
