"use strict";

const BWPDiyLibrary = (() => {
  const MAX_ARTWORK_BYTES = 64 * 1024 * 1024;
  const MAX_WORKS = 1000;
  const ARTWORK_PATH = /^artwork\.(?:png|jpe?g|webp)$/;

  function copy(value) {
    return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value));
  }

  function workTitle(draft) {
    const state = draft && draft.state || {};
    const mechanism = state.tab === "mechanism";
    const values = mechanism ? state.mechanism || {} : state.card || {};
    const name = String(values.name || "").trim();
    return name || (mechanism ? "未命名机制" : "未命名卡牌");
  }

  function projectName(value) {
    return String(value || "").trim().slice(0, 40) || "默认项目";
  }

  function blankDraft(template, tab) {
    const state = copy(template);
    state.tab = tab === "mechanism" ? "mechanism" : "card";
    return {schema: 1, saved_at: new Date().toISOString(), state, artwork: null, layouts: null};
  }

  function newWorkId() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
    return `work-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  }

  function bytesToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let index = 0; index < bytes.length; index += 32768) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 32768));
    }
    return btoa(binary);
  }

  function base64ToBytes(value) {
    if (typeof value !== "string" || value.length > Math.ceil(MAX_ARTWORK_BYTES / 3) * 4 + 4) {
      throw new Error("卡图编码大小异常");
    }
    const binary = atob(value);
    if (!binary.length || binary.length > MAX_ARTWORK_BYTES) throw new Error("卡图文件过大或为空");
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes.buffer;
  }

  function normalizeArtwork(artwork, decode) {
    if (artwork === null || artwork === undefined) return null;
    if (!artwork || typeof artwork !== "object" || Array.isArray(artwork)) throw new Error("卡图记录无效");
    const path = String(artwork.path || "");
    if (!ARTWORK_PATH.test(path)) throw new Error("卡图路径非法");
    let bytes = artwork.bytes;
    if (decode && typeof bytes === "string") bytes = base64ToBytes(bytes);
    if (!(bytes instanceof ArrayBuffer) || !bytes.byteLength || bytes.byteLength > MAX_ARTWORK_BYTES) {
      throw new Error("卡图字节无效");
    }
    return {name: String(artwork.name || path).slice(0, 260), path, bytes};
  }

  function normalizeWork(work, decode) {
    if (!work || typeof work !== "object" || Array.isArray(work) || work.schema !== 1 ||
        !work.state || typeof work.state !== "object" || Array.isArray(work.state)) {
      throw new Error("作品记录无效");
    }
    if (!["card", "mechanism"].includes(work.state.tab)) throw new Error("作品类型无效");
    return {
      schema: 1,
      id: String(work.id || ""),
      project: projectName(work.project),
      saved_at: String(work.saved_at || ""),
      state: copy(work.state),
      artwork: normalizeArtwork(work.artwork, decode),
      layouts: null,
    };
  }

  function encodeBackup(source) {
    const result = copy(source);
    const works = result.schema === 2 ? result.works : [result];
    for (const work of works) {
      const normalized = normalizeWork(work, false);
      if (normalized.artwork) normalized.artwork.bytes = bytesToBase64(normalized.artwork.bytes);
      if (result.schema === 2) Object.assign(work, normalized);
      else Object.assign(result, normalized);
    }
    return result;
  }

  function decodeBackup(source) {
    if (!source || typeof source !== "object" || Array.isArray(source)) throw new Error("备份不是有效对象");
    if (source.schema === 1) {
      return {schema: 1, works: [normalizeWork(source, true)], layouts: null, applyLayouts: false};
    }
    if (source.schema !== 2 || !Array.isArray(source.works) || !source.works.length || source.works.length > MAX_WORKS) {
      throw new Error("不是受支持的 BWPDIY 卡库备份");
    }
    if (source.layouts !== null && source.layouts !== undefined &&
        (typeof source.layouts !== "object" || Array.isArray(source.layouts) || source.layouts.schema !== 1)) {
      throw new Error("卡库布局记录无效");
    }
    return {
      schema: 2,
      current_id: String(source.current_id || ""),
      works: source.works.map(work => normalizeWork(work, true)),
      layouts: source.layouts ? copy(source.layouts) : null,
      applyLayouts: true,
    };
  }

  return Object.freeze({workTitle, projectName, blankDraft, newWorkId, encodeBackup, decodeBackup});
})();

if (typeof module !== "undefined" && module.exports) module.exports = BWPDiyLibrary;

let currentWorkId = "";
let currentProject = "默认项目";
let libraryIndex = {schema: 1, current_id: "", works: []};
let libraryAvailable = true;
let libraryBusy = false;
let blankUiState = null;
let libraryInitialized = false;

function workMeta(draft) {
  return {title: BWPDiyLibrary.workTitle(draft), project: BWPDiyLibrary.projectName(draft.project),
    kind: draft.state.tab === "mechanism" ? "mechanism" : "card", saved_at: draft.saved_at || ""};
}

function refreshWorkList() {
  const container = document.getElementById("work-list");
  container.textContent = "";
  let project = "";
  for (const item of libraryIndex.works) {
    if (item.project !== project) {
      project = item.project;
      const heading = document.createElement("div");
      heading.className = "work-project";
      heading.textContent = project;
      container.appendChild(heading);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "work-item";
    button.classList.toggle("active", item.id === currentWorkId);
    button.dataset.workId = item.id;
    const title = document.createElement("span");
    title.textContent = item.title;
    const kind = document.createElement("small");
    kind.textContent = item.kind === "mechanism" ? "机制" : "卡牌";
    button.append(title, kind);
    button.addEventListener("click", () => switchWork(item.id));
    container.appendChild(button);
  }
  document.getElementById("delete-work").disabled = libraryBusy || !libraryAvailable || !libraryIndex.works.length;
  document.body.dataset.workCount = String(libraryIndex.works.length);
}

function updateLibraryBusy(busy) {
  libraryBusy = busy;
  document.body.dataset.libraryBusy = String(busy);
  for (const id of ["new-card-work", "new-mechanism-work", "delete-work", "project-name", "import-draft", "export-library"]) {
    document.getElementById(id).disabled = busy || !libraryAvailable && id !== "export-library";
  }
  document.querySelectorAll(".work-item").forEach(button => { button.disabled = busy; });
}

async function persistCurrentWork(draft) {
  if (!libraryAvailable) {
    draftStatus.textContent = "浏览器卡库不可用；当前仅在内存编辑，请立即导出作品备份";
    return;
  }
  if (!currentWorkId) currentWorkId = BWPDiyLibrary.newWorkId();
  draft.id = currentWorkId;
  draft.project = currentProject;
  draft.layouts = null;
  libraryIndex = await draftStore.saveWork(currentWorkId, draft, workMeta(draft));
  refreshWorkList();
}

function clearWorkPreview() {
  currentPng = null;
  if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
  currentBlobUrl = "";
  for (const image of [document.getElementById("c-preview"), document.getElementById("b-preview")]) image.removeAttribute("src");
  downloadButtons.forEach(button => { button.disabled = true; });
  showPreviewStatus("正在生成当前作品预览…");
}

function showMobileWorkspace(target) {
  if (!["library", "editor", "mechanism", "more"].includes(target)) target = "editor";
  document.body.dataset.mobileView = target;
  updateMobileWorkspace(activeMainTab);
  document.querySelectorAll("#mobile-workspace-nav button").forEach(button => {
    button.classList.toggle("active", button.dataset.mobileTarget === target);
  });
  if (target === "more") document.querySelector(".data-settings").open = true;
  if (matchMedia("(max-width: 760px)").matches) window.scrollTo({top: 0, behavior: "smooth"});
}

async function selectEditorKind(kind) {
  if (tutorialMode || libraryBusy) return;
  const target = kind === "mechanism" ? "mechanism" : "card";
  if (readUiState().tab === target) {
    showMobileWorkspace(target === "mechanism" ? "mechanism" : "editor");
    return;
  }
  const candidate = libraryIndex.works.find(item => item.kind === target);
  if (candidate) await switchWork(candidate.id);
  else await createWork(target);
}

function updateMobileWorkspace(tab) {
  document.getElementById("mobile-workspace-nav").hidden = tab !== "cards";
}

async function activateWork(id, draft, mobileTarget = null) {
  currentWorkId = id;
  currentProject = BWPDiyLibrary.projectName(draft.project);
  document.getElementById("project-name").value = currentProject;
  await restoreDraft(draft);
  clearWorkPreview();
  refreshWorkList();
  const mechanism = draft.state.tab === "mechanism";
  currentRenderKind = mechanism ? "mechanism" : "card";
  showMobileWorkspace(mobileTarget || (mechanism ? "mechanism" : "editor"));
  scheduleNormalPreview(currentRenderKind, 0);
}

async function switchWork(id) {
  if (tutorialMode || libraryBusy || id === currentWorkId) return;
  updateLibraryBusy(true);
  try {
    await saveDraftNow();
    const draft = await draftStore.loadWork(id);
    if (!draft) throw new Error("作品不存在或已被删除");
    await draftStore.setCurrentWork(id);
    libraryIndex = await draftStore.listWorks();
    await activateWork(id, draft);
    log(`已切换作品：${BWPDiyLibrary.workTitle(draft)}`);
  } catch (error) {
    draftStatus.textContent = `切换作品失败：${error.message}`;
    log(draftStatus.textContent, true);
  } finally { updateLibraryBusy(false); }
}

async function createWork(kind) {
  if (tutorialMode || libraryBusy || !libraryAvailable) return;
  updateLibraryBusy(true);
  try {
    await saveDraftNow();
    const id = BWPDiyLibrary.newWorkId();
    const draft = BWPDiyLibrary.blankDraft(blankUiState, kind);
    draft.project = currentProject;
    await persistCurrentWorkForNew(id, draft);
    await activateWork(id, draft, kind === "mechanism" ? "mechanism" : "editor");
    log(kind === "mechanism" ? "已新建机制" : "已新建卡牌");
  } catch (error) {
    draftStatus.textContent = `新建作品失败：${error.message}`;
    log(draftStatus.textContent, true);
  } finally { updateLibraryBusy(false); }
}

async function persistCurrentWorkForNew(id, draft) {
  draft.id = id;
  libraryIndex = await draftStore.saveWork(id, draft, workMeta(draft));
}

async function deleteCurrentWork() {
  if (tutorialMode || libraryBusy || !libraryAvailable || !currentWorkId) return;
  if (!confirm("仅删除当前浏览器中的这一作品及其卡图，是否继续？")) return;
  updateLibraryBusy(true);
  try {
    await saveDraftNow();
    libraryIndex = await draftStore.deleteWork(currentWorkId);
    if (libraryIndex.current_id) {
      const draft = await draftStore.loadWork(libraryIndex.current_id);
      await activateWork(libraryIndex.current_id, draft);
    } else {
      const id = BWPDiyLibrary.newWorkId();
      const draft = BWPDiyLibrary.blankDraft(blankUiState, "card");
      draft.project = currentProject;
      await persistCurrentWorkForNew(id, draft);
      await activateWork(id, draft, "editor");
    }
    log("已删除作品");
  } catch (error) {
    draftStatus.textContent = `删除作品失败：${error.message}`;
    log(draftStatus.textContent, true);
  } finally { updateLibraryBusy(false); }
}

function exportCurrentWork() {
  const draft = currentDraft();
  draft.id = currentWorkId;
  draft.project = currentProject;
  const encoded = BWPDiyLibrary.encodeBackup(draft);
  downloadBlob(new Blob([JSON.stringify(encoded, null, 2)], {type: "application/json"}),
               `bwpdiy-work-${new Date().toISOString().slice(0, 10)}.json`);
}

async function exportFullLibrary() {
  if (libraryBusy) return;
  updateLibraryBusy(true);
  try {
    await saveDraftNow();
    const {works} = await draftStore.allWorks();
    const encoded = BWPDiyLibrary.encodeBackup({schema: 2, current_id: currentWorkId,
      works, layouts: {schema: 1, layouts: globalLayouts}});
    downloadBlob(new Blob([JSON.stringify(encoded)], {type: "application/json"}),
                 `bwpdiy-library-${new Date().toISOString().slice(0, 10)}.json`);
    log(`已导出完整卡库：${works.length} 部作品`);
  } catch (error) {
    draftStatus.textContent = `导出卡库失败：${error.message}`;
    log(draftStatus.textContent, true);
  } finally { updateLibraryBusy(false); }
}

async function importBackupFile(file) {
  if (tutorialMode || libraryBusy || !libraryAvailable) return;
  updateLibraryBusy(true);
  try {
    if (file.size > 200 * 1024 * 1024) throw new Error("备份文件超过 200 MiB");
    const decoded = BWPDiyLibrary.decodeBackup(JSON.parse(await file.text()));
    if (decoded.applyLayouts && decoded.layouts &&
        !confirm("完整卡库将合并导入，备份中的全局布局会覆盖当前浏览器布局。是否继续？")) return;
    await saveDraftNow();
    const entries = [];
    for (const source of decoded.works) {
      const id = BWPDiyLibrary.newWorkId();
      const draft = {...source, id, layouts: null};
      entries.push({id, draft, meta: workMeta(draft)});
    }
    const selected = entries[0].id;
    libraryIndex = await draftStore.importWorks(entries, selected);
    if (decoded.applyLayouts && decoded.layouts) {
      restoredLayouts = decoded.layouts.layouts;
      if (defaultLayouts) {
        globalLayouts = restoredLayouts;
        buildLayoutTypes();
        selectLayoutType(layoutType);
        await saveLayoutNow();
      }
    }
    await activateWork(selected, entries[0].draft);
    draftStatus.textContent = `已导入 ${entries.length} 部作品；原有作品未删除`;
    log(draftStatus.textContent);
  } catch (error) {
    draftStatus.textContent = `导入失败：${error.message}`;
    log(draftStatus.textContent, true);
  } finally { updateLibraryBusy(false); }
}

async function clearLocalLibrary() {
  if (tutorialMode || libraryBusy || !libraryAvailable) return;
  if (!confirm("仅清空当前浏览器中的全部作品和卡图；全局布局与资源缓存不受影响。建议先导出完整卡库。是否继续？")) return;
  updateLibraryBusy(true);
  try {
    await saveDraftNow();
    await draftStore.clearWorks();
    location.reload();
  } catch (error) {
    draftStatus.textContent = `清空卡库失败：${error.message}`;
    log(draftStatus.textContent, true);
    updateLibraryBusy(false);
  }
}

async function initializeLibrary() {
  blankUiState = readUiState();
  if (!libraryInitialized) {
    libraryInitialized = true;
    document.getElementById("new-card-work").addEventListener("click", () => createWork("card"));
    document.getElementById("new-mechanism-work").addEventListener("click", () => createWork("mechanism"));
    document.getElementById("delete-work").addEventListener("click", deleteCurrentWork);
    document.getElementById("project-name").addEventListener("input", event => {
      currentProject = event.target.value.slice(0, 40);
      scheduleDraftSave();
    });
    document.getElementById("project-name").addEventListener("change", event => {
      currentProject = BWPDiyLibrary.projectName(event.target.value);
      event.target.value = currentProject;
      scheduleDraftSave();
    });
    document.querySelectorAll("#mobile-workspace-nav button").forEach(button => {
      button.addEventListener("click", () => {
        const target = button.dataset.mobileTarget;
        if (target === "editor" || target === "mechanism") selectEditorKind(target === "mechanism" ? "mechanism" : "card");
        else showMobileWorkspace(target);
      });
    });
    showMobileWorkspace("editor");
  }
  try {
    libraryIndex = await draftStore.listWorks();
    libraryAvailable = true;
    if (!libraryIndex.works.length) {
      let draft = null;
      try {
        const legacy = await draftStore.loadLegacy();
        if (legacy) draft = BWPDiyLibrary.decodeBackup(legacy).works[0];
      } catch (error) { log(`旧草稿无法迁移，将保留空作品：${error.message}`, true); }
      const id = BWPDiyLibrary.newWorkId();
      draft ||= BWPDiyLibrary.blankDraft(blankUiState, "card");
      draft.project = BWPDiyLibrary.projectName(draft.project);
      await persistCurrentWorkForNew(id, draft);
      await draftStore.clearLegacy();
      libraryIndex = await draftStore.listWorks();
    }
    const id = libraryIndex.current_id || libraryIndex.works[0].id;
    const draft = await draftStore.loadWork(id);
    if (!draft) throw new Error("当前作品记录缺失");
    await activateWork(id, draft);
    draftStatus.textContent = `本地卡库已加载：${libraryIndex.works.length} 部作品；更改会自动保存`;
    document.body.dataset.draftRestored = "true";
  } catch (error) {
    libraryAvailable = false;
    currentWorkId = BWPDiyLibrary.newWorkId();
    const draft = BWPDiyLibrary.blankDraft(blankUiState, "card");
    await activateWork(currentWorkId, draft);
    libraryIndex = {schema: 1, current_id: currentWorkId, works: [{id: currentWorkId, ...workMeta(draft)}]};
    refreshWorkList();
    updateLibraryBusy(false);
    draftStatus.textContent = `浏览器卡库不可用：${error.message}；当前可编辑并导出，但刷新会丢失`;
    log(draftStatus.textContent, true);
  }
}
