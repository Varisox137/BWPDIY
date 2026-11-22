"use strict";

const RESOURCE_CACHE = "bwpdiy-online-resources-v1";
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

async function networkFirst(request) {
  const cache = await caches.open(RESOURCE_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(PYODIDE_CACHE);
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
    event.respondWith(networkFirst(request));
  } else if (url.origin === "https://cdn.jsdelivr.net" &&
             url.pathname.startsWith("/pyodide/v0.28.3/")) {
    event.respondWith(cacheFirst(request));
  }
});
