/* EV Charge India - service worker.
   Caches the app shell + data so it opens offline; map tiles need network. */
const CACHE = "evcharge-v1";
const SHELL = [
  "./", "index.html", "styles.css", "app.js", "data.js",
  "manifest.webmanifest", "icon-192.png", "icon-512.png"
];

self.addEventListener("install", e => {
  // Add files one at a time: a single missing asset would abort addAll() and
  // make the browser discard the whole registration.
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  // never cache the API or map tiles
  if (url.pathname.startsWith("/api/") || /tile\.openstreetmap\.org/.test(url.host)) return;
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
      if (e.request.method === "GET" && res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match("index.html")))
  );
});
