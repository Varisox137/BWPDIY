"use strict";

const RESOURCE_CACHE = "bwpdiy-online-resources-v8";
const PYODIDE_CACHE = "bwpdiy-pyodide-v0.28.3";
const CURRENT_CACHES = [RESOURCE_CACHE, PYODIDE_CACHE];
const STATIC_PATHS = new Set(["/", "/index.html", "/style.css", "/storage.js",
  "/layout.js", "/app.js", "/worker.js", "/bridge.py", "/sw.js", "/runtime.json",
  "/tutorial.js", "/tutorial.css"]);

self.addEventListener("install", event => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys
      .filter(key => key.startsWith("bwpdiy-") && !CURRENT_CACHES.includes(key))
      .map(key => caches.delete(key)))),
    self.clients.claim(),
  ]));
});

async function cacheFirst(request, cacheName, cacheKey = request) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(cacheKey, response.clone());
  return response;
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin === self.location.origin &&
      (STATIC_PATHS.has(url.pathname) || /^\/runtime-chunks\/\d+$/.test(url.pathname))) {
    event.respondWith(cacheFirst(request, RESOURCE_CACHE, url.pathname));
  } else if (url.origin === "https://cdn.jsdelivr.net" &&
             url.pathname.startsWith("/pyodide/v0.28.3/")) {
    event.respondWith(cacheFirst(request, PYODIDE_CACHE));
  }
});
