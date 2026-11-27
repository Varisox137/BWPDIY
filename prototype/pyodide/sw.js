"use strict";

const RESOURCE_CACHE = "bwpdiy-online-resources-v21";
const RUNTIME_CACHE = "bwpdiy-online-runtime-v3";
const PYODIDE_CACHE = "bwpdiy-pyodide-v0.28.3";
const CURRENT_CACHES = [RESOURCE_CACHE, RUNTIME_CACHE, PYODIDE_CACHE];
const STATIC_PATHS = new Set(["/", "/index.html", "/style.css", "/storage.js", "/library.js",
  "/layout.js", "/app.js", "/ui-utils.js", "/mobile.js", "/worker.js", "/bridge.py", "/sw.js",
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

async function cacheFirst(event, cacheName, cacheKey = event.request) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;
  const response = await fetch(event.request, {cache: "reload"});
  if (response.ok) event.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    if (url.origin === "https://cdn.jsdelivr.net" &&
        url.pathname.startsWith("/pyodide/v0.28.3/")) {
      event.respondWith(cacheFirst(event, PYODIDE_CACHE));
    }
    return;
  }
  if (STATIC_PATHS.has(url.pathname)) {
    event.respondWith(cacheFirst(event, RESOURCE_CACHE, url.pathname));
  } else if (url.pathname === "/runtime.json" || /^\/runtime-chunks\/\d+$/.test(url.pathname)) {
    event.respondWith(cacheFirst(event, RUNTIME_CACHE, url.pathname));
  }
});
