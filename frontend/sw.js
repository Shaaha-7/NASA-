// Caches the app shell so the page itself opens with no network.
// All data comes from the local backend, which reads only the packaged region.
const CACHE = "marspath-shell-v1";
const SHELL = ["./", "index.html", "style.css", "app.js", "vendor/leaflet.js", "vendor/leaflet.css",
  "vendor/images/marker-icon.png", "vendor/images/marker-shadow.png", "vendor/images/layers.png"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return; // API: always ask the local backend
  e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request)));
});
