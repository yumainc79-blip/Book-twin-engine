const CACHE_NAME = "book-twin-drive-uploader-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./drive.js",
  "./zip.js",
  "./config.js",
  "./manifest.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (url.hostname.includes("googleapis.com") || url.hostname.includes("gstatic.com")) return;
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
});
