/* EV Charge India - share page service worker.
   Caches only files that actually exist in this build, and adds them one at a
   time so a single missing asset cannot abort the install. */
const CACHE = "evcharge-share-v1";
const SHELL = [
  "./", "index.html", "manifest.webmanifest",
  "icon-192.png", "icon-512.png", "og-image.png"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // never cache map tiles - they are large and need a live network anyway
  if (/tile\.openstreetmap\.org/.test(url.host)) return;
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match("index.html")))
  );
});
