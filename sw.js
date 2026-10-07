/*
 * gigsnshows service worker: it lets the installed app open when the phone has no signal.
 * It always asks the network first, so you never see an old page while online; the saved copy is
 * only the fallback. It touches nothing except this site's own page, calendar code, icons and
 * listings (Firebase, Google Analytics and ticket sites are left alone).
 */
const CACHE = "gigsnshows-v1";
const SHELL = ["/", "/calendar.js", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png", "/data/events.json"];
const KEEP = new Set(SHELL);

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => Promise.all(SHELL.map(url => cache.add(new Request(url, { cache: "reload" })).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(request, key) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && key) cache.put(key, response.clone());
    return response;
  } catch (err) {
    const saved = (key && await cache.match(key)) || await cache.match(request);
    if (saved) return saved;
    throw err;
  }
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === "navigate") {
    // The app is one page that reads its state from the address, so one saved copy serves every address.
    const isApp = url.pathname === "/" || url.pathname === "/index.html";
    event.respondWith(networkFirst(request, isApp ? "/" : null).catch(async () => (await caches.match("/")) || Response.error()));
  } else if (KEEP.has(url.pathname)) {
    event.respondWith(networkFirst(request, url.pathname));
  }
});
