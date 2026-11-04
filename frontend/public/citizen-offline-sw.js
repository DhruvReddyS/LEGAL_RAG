/*
 * C-04 offline. This worker handles exactly one page: /rights and the static
 * assets it loaded. Everything else passes straight through to the network, so
 * it cannot serve a stale copy of the app, or of anything private, to anyone.
 */
const CACHE = "corpusil-rights-v1";

function isRightsPage(url) {
  return url.pathname === "/rights" || url.pathname === "/rights/" || url.pathname === "/rights.html";
}

function isStaticAsset(url) {
  return url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/brand/");
}

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith("corpusil-rights-") && key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", event => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (isRightsPage(url)) {
    // Network first: the page updates whenever there is a connection.
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then(cache => cache.put("/rights", copy));
          }
          return response;
        })
        .catch(() => caches.match("/rights").then(cached => cached || Response.error())),
    );
    return;
  }

  if (isStaticAsset(url)) {
    // Asset names carry a content hash, so a cached copy is never stale.
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      })),
    );
  }
});
