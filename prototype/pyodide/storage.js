"use strict";

const draftStore = (() => {
  const DB_NAME = "bwpdiy-online-local";
  const STORE_NAME = "drafts";
  const LEGACY_DRAFT_KEY = "current";
  const LAYOUT_KEY = "global-layout";
  const INDEX_KEY = "library-index";
  const WORK_PREFIX = "work:";
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
        request.onblocked = () => reject(new Error("浏览器卡库被其他标签页阻塞"));
      });
    }
    return databasePromise;
  }

  function requestResult(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function transactionDone(transaction) {
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  }

  async function put(key, value) {
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(value, key);
    await transactionDone(transaction);
  }

  async function get(key) {
    const database = await openDatabase();
    const request = database.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(key);
    return (await requestResult(request)) || null;
  }

  function workKey(id) {
    const value = String(id || "");
    if (!/^[A-Za-z0-9-]{1,80}$/.test(value)) throw new Error("作品内部 ID 非法");
    return WORK_PREFIX + value;
  }

  function normalizeIndex(value) {
    if (!value || value.schema !== 1 || !Array.isArray(value.works)) return {schema: 1, current_id: "", works: []};
    const works = value.works.filter(item => item && typeof item.id === "string").map(item => ({
      id: item.id,
      title: String(item.title || "未命名作品"),
      project: String(item.project || "默认项目"),
      kind: item.kind === "mechanism" ? "mechanism" : "card",
      saved_at: String(item.saved_at || ""),
    }));
    const current_id = works.some(item => item.id === value.current_id) ? value.current_id : (works[0] && works[0].id || "");
    return {schema: 1, current_id, works};
  }

  async function listWorks() { return normalizeIndex(await get(INDEX_KEY)); }

  async function saveWork(id, draft, meta) {
    const key = workKey(id);
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const index = normalizeIndex(await requestResult(store.get(INDEX_KEY)));
    const entry = {id, title: String(meta.title), project: String(meta.project),
      kind: meta.kind === "mechanism" ? "mechanism" : "card", saved_at: String(draft.saved_at || "")};
    index.works = [...index.works.filter(item => item.id !== id), entry]
      .sort((a, b) => a.project.localeCompare(b.project, "zh-CN") || a.title.localeCompare(b.title, "zh-CN") || a.id.localeCompare(b.id));
    index.current_id = id;
    store.put({...draft, id}, key);
    store.put(index, INDEX_KEY);
    await transactionDone(transaction);
    return index;
  }

  async function setCurrentWork(id) {
    workKey(id);
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const index = normalizeIndex(await requestResult(store.get(INDEX_KEY)));
    if (!index.works.some(item => item.id === id)) throw new Error("要切换的作品不存在");
    index.current_id = id;
    store.put(index, INDEX_KEY);
    await transactionDone(transaction);
  }

  async function deleteWork(id) {
    const key = workKey(id);
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const index = normalizeIndex(await requestResult(store.get(INDEX_KEY)));
    index.works = index.works.filter(item => item.id !== id);
    if (index.current_id === id) index.current_id = index.works[0] && index.works[0].id || "";
    store.delete(key);
    store.put(index, INDEX_KEY);
    await transactionDone(transaction);
    return index;
  }

  async function importWorks(entries, currentId) {
    if (!Array.isArray(entries) || !entries.length) throw new Error("没有可导入的作品");
    for (const entry of entries) workKey(entry.id);
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const index = normalizeIndex(await requestResult(store.get(INDEX_KEY)));
    const byId = new Map(index.works.map(item => [item.id, item]));
    for (const entry of entries) {
      store.put({...entry.draft, id: entry.id}, workKey(entry.id));
      byId.set(entry.id, {id: entry.id, ...entry.meta});
    }
    index.works = [...byId.values()];
    index.current_id = currentId;
    store.put(index, INDEX_KEY);
    await transactionDone(transaction);
    return index;
  }

  async function allWorks() {
    const index = await listWorks();
    const works = [];
    for (const item of index.works) {
      const work = await get(workKey(item.id));
      if (work) works.push(work);
    }
    return {index, works};
  }

  async function clearWorks() {
    const database = await openDatabase();
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const keys = await requestResult(store.getAllKeys());
    for (const key of keys) {
      if (key === LEGACY_DRAFT_KEY || key === INDEX_KEY || String(key).startsWith(WORK_PREFIX)) store.delete(key);
    }
    await transactionDone(transaction);
  }

  return {
    loadLegacy: () => get(LEGACY_DRAFT_KEY),
    clearLegacy: () => put(LEGACY_DRAFT_KEY, null),
    listWorks,
    saveWork,
    loadWork: id => get(workKey(id)),
    setCurrentWork,
    deleteWork,
    importWorks,
    allWorks,
    clearWorks,
    saveLayout: value => put(LAYOUT_KEY, value),
    loadLayout: () => get(LAYOUT_KEY),
    clearLayout: () => put(LAYOUT_KEY, null),
  };
})();

if (typeof module !== "undefined" && module.exports) module.exports = draftStore;
