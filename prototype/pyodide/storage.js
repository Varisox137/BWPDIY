"use strict";

const draftStore = (() => {
  const DB_NAME = "bwpdiy-online-local";
  const STORE_NAME = "drafts";
  const DRAFT_KEY = "current";
  const LAYOUT_KEY = "global-layout";
  let databasePromise = null;

  function openDatabase() {
    if (!databasePromise) {
      databasePromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => {
          if (!request.result.objectStoreNames.contains(STORE_NAME)) {
            request.result.createObjectStore(STORE_NAME);
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error("浏览器草稿数据库被其他标签页阻塞"));
      });
    }
    return databasePromise;
  }

  async function put(key, value) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(value, key);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async function get(key) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const request = database.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async function remove(key) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(key);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  }

  return {
    save: value => put(DRAFT_KEY, value),
    load: () => get(DRAFT_KEY),
    clear: () => remove(DRAFT_KEY),
    saveLayout: value => put(LAYOUT_KEY, value),
    loadLayout: () => get(LAYOUT_KEY),
    clearLayout: () => remove(LAYOUT_KEY),
  };
})();
