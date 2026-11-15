// Caches the app shell so the page itself opens with no network.
// All data comes from the local backend, which reads only the packaged region.
const CACHE = "marspath-shell-v3";
const SHELL = ["./", "index.html", "style.css", "app.js", "globe.js", "vendor/leaflet.js", "vendor/leaflet.css",
  "vendor/three.module.min.js", "vendor/mars_globe_4k.jpg",
  "vendor/images/marker-icon.png", "vendor/images/marker-shadow.png", "vendor/images/layers.png"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return; // API: always ask the local backend
  e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r; })
    // ignoreVary: the server sends "Vary: Origin", and ES-module requests (globe.js, three.js) carry an
    // Origin header, so without it the offline lookup misses and the 3D globe cannot load.
    .catch(() => caches.match(e.request, { ignoreVary: true })));
});
