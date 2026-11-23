"use strict";

const RESOURCE_CACHE = "bwpdiy-online-resources-v3";
const PYODIDE_CACHE = "bwpdiy-pyodide-v0.28.3";
const CURRENT_CACHES = [RESOURCE_CACHE, PYODIDE_CACHE];

self.addEventListener("install", event => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys
      .filter(key => key.startsWith("bwpdiy-") && !CURRENT_CACHES.includes(key))
      .map(key => caches.delete(key)))),
    self.clients.claim(),
  ]));
});

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(request, RESOURCE_CACHE));
  } else if (url.origin === "https://cdn.jsdelivr.net" &&
             url.pathname.startsWith("/pyodide/v0.28.3/")) {
    event.respondWith(cacheFirst(request, PYODIDE_CACHE));
  }
});
