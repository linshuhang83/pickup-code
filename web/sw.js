// network-first：本机服务每次打开都拿最新静态文件，服务不可用时回退缓存（离线兜底）
const CACHE = "qjk-v2";
const ASSETS = ["/", "/index.html", "/style.css", "/app.js", "/manifest.json", "/icon-192.png", "/icon-180.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return resp;
      })
      .catch(() => caches.match(e.request).then((hit) => hit || Response.error()))
  );
});
