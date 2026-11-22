"use strict";

const worker = new Worker("worker.js");
const logElement = document.getElementById("log");
const preview = document.getElementById("preview");
const resultMeta = document.getElementById("result-meta");
const downloadButton = document.getElementById("download");
const renderButtons = [...document.querySelectorAll(".render-button")];
const draftStatus = document.getElementById("draft-status");
const cacheStatus = document.getElementById("cache-status");
let requestSequence = 0;
let artworkBytes = null;
let artworkPath = "";
let artworkName = "";
let currentBlobUrl = "";
let currentPng = null;
let renderCount = 0;
let draftTimer = null;
let restoringDraft = false;
const pending = new Map();

function log(message, isError = false) {
  const line = document.createElement("span");
  line.textContent = `${new Date().toLocaleTimeString()}  ${message}\n`;
  if (isError) line.className = "error";
  logElement.appendChild(line);
  logElement.scrollTop = logElement.scrollHeight;
}

function setRendering(rendering) {
  const ready = document.body.dataset.ready === "true";
  const type = document.querySelector('[data-card="type"]').value;
  const evolve = document.querySelector('[data-card="evolve"]').checked;
  for (const button of renderButtons) {
    const kind = button.dataset.kind;
    const supported = kind === "entity" ? ["式神", "形态"].includes(type) || (type === "法术" && evolve) :
      kind === "portrait" ? type === "式神" : true;
    button.disabled = rendering || !ready || !supported;
  }
  document.body.dataset.rendering = String(rendering);
}

function callWorker(type, payload = null, artwork = null) {
  const id = ++requestSequence;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject});
    const message = {type, id, payload};
    if (artwork) {
      const copy = artwork.slice(0);
      message.artwork = copy;
      worker.postMessage(message, [copy]);
    } else {
      worker.postMessage(message);
    }
  });
}

worker.onmessage = event => {
  const message = event.data;
  if (message.type === "status") {
    log(message.message);
    return;
  }
  const request = pending.get(message.id);
  if (message.type === "ready") {
    document.body.dataset.ready = "true";
    setRendering(false);
    log(`初始化 ${message.info.startup_ms} ms；资源包 ${(message.info.runtime_bytes / 1048576).toFixed(1)} MiB`);
  }
  if (message.type === "result") {
    currentPng = new Blob([message.png], {type: "image/png"});
    if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
    currentBlobUrl = URL.createObjectURL(currentPng);
    preview.src = currentBlobUrl;
    const info = message.info;
    resultMeta.textContent = `${info.kind}：${info.width}×${info.height}，渲染 ${info.render_ms} ms，总耗时 ${info.total_ms} ms，PNG ${(info.png_bytes / 1024).toFixed(1)} KiB`;
    document.body.dataset.lastRender = info.kind;
    renderCount += 1;
    document.body.dataset.renderCount = String(renderCount);
    downloadButton.disabled = false;
    log(resultMeta.textContent);
  }
  if (message.type === "error") {
    log(`失败：${message.message}`, true);
    if (message.detail) log(message.detail, true);
    document.body.dataset.error = message.message;
  }
  if (request) {
    pending.delete(message.id);
    if (message.type === "error") request.reject(new Error(message.message));
    else request.resolve(message);
  }
};

worker.onerror = event => {
  log(`Worker 加载失败：${event.message}`, true);
  document.body.dataset.error = event.message;
  setRendering(true);
};

function readGroup(selector) {
  const result = {};
  for (const element of document.querySelectorAll(selector)) {
    const container = element.closest("[data-types]");
    if (container && container.hidden) continue;
    const key = element.dataset.card || element.dataset.art || element.dataset.portrait ||
      element.dataset.state || element.dataset.mech;
    result[key] = element.type === "checkbox" ? element.checked : element.value;
  }
  return result;
}

function setGroup(selector, values) {
  if (!values || typeof values !== "object") return;
  for (const element of document.querySelectorAll(selector)) {
    const key = element.dataset.card || element.dataset.art || element.dataset.portrait ||
      element.dataset.state || element.dataset.mech;
    if (!(key in values)) continue;
    if (element.type === "checkbox") element.checked = values[key] === true;
    else element.value = String(values[key] ?? "");
  }
}

function readUiState() {
  return {
    tab: document.getElementById("mechanism-editor").hidden ? "card" : "mechanism",
    card: readGroup("[data-card]"),
    artwork: readGroup("[data-art]"),
    portrait: readGroup("[data-portrait]"),
    entity: readGroup("[data-state]"),
    mechanism: readGroup("[data-mech]"),
    width: document.getElementById("width").value,
  };
}

function applyUiState(state) {
  if (!state || typeof state !== "object") return;
  setGroup("[data-card]", state.card);
  setGroup("[data-art]", state.artwork);
  setGroup("[data-portrait]", state.portrait);
  setGroup("[data-state]", state.entity);
  setGroup("[data-mech]", state.mechanism);
  document.getElementById("width").value = state.width || "";
  showTab(state.tab === "mechanism" ? "mechanism" : "card");
  updateTypeFields();
}

function currentDraft() {
  return {
    schema: 1,
    saved_at: new Date().toISOString(),
    state: readUiState(),
    artwork: artworkBytes ? {
      name: artworkName,
      path: artworkPath,
      bytes: artworkBytes,
    } : null,
  };
}

async function saveDraftNow() {
  if (restoringDraft) return;
  clearTimeout(draftTimer);
  draftTimer = null;
  try {
    await draftStore.save(currentDraft());
    draftStatus.textContent = `草稿已保存到当前浏览器：${new Date().toLocaleTimeString()}`;
    document.body.dataset.draftSaved = "true";
  } catch (error) {
    draftStatus.textContent = `草稿保存失败：${error.message}`;
    log(draftStatus.textContent, true);
  }
}

function scheduleDraftSave() {
  if (restoringDraft) return;
  draftStatus.textContent = "有尚未写入浏览器的草稿更改…";
  clearTimeout(draftTimer);
  draftTimer = setTimeout(saveDraftNow, 300);
}

async function restoreDraft(draft) {
  if (!draft || draft.schema !== 1 || !draft.state) return false;
  restoringDraft = true;
  try {
    applyUiState(draft.state);
    if (draft.artwork && draft.artwork.bytes instanceof ArrayBuffer) {
      artworkBytes = draft.artwork.bytes;
      artworkPath = String(draft.artwork.path || "artwork.png");
      artworkName = String(draft.artwork.name || artworkPath);
    } else {
      artworkBytes = null;
      artworkPath = "";
      artworkName = "";
    }
    updateArtworkLabel();
  } finally {
    restoringDraft = false;
  }
  draftStatus.textContent = draft.saved_at ?
    `已恢复浏览器草稿：${new Date(draft.saved_at).toLocaleString()}` : "已恢复浏览器草稿";
  document.body.dataset.draftRestored = "true";
  return true;
}

function updateArtworkLabel() {
  document.getElementById("artwork-name").textContent = artworkBytes ?
    `${artworkName}（${artworkBytes.byteLength} 字节，仅保存在浏览器）` : "默认使用内置样图";
}

function showTab(tab) {
  const mechanism = tab === "mechanism";
  document.getElementById("card-editor").hidden = mechanism;
  document.getElementById("mechanism-editor").hidden = !mechanism;
  document.getElementById("tab-card").classList.toggle("active", !mechanism);
  document.getElementById("tab-mechanism").classList.toggle("active", mechanism);
}

function updateTypeFields() {
  const type = document.querySelector('[data-card="type"]').value;
  for (const container of document.querySelectorAll("[data-types]")) {
    container.hidden = !container.dataset.types.split(",").includes(type);
  }
  const mechanismFrame = document.querySelector('[data-mech="frame"]').value;
  document.querySelector('[data-mech="badge"]').closest("label").hidden = mechanismFrame !== "seal";
  setRendering(document.body.dataset.rendering === "true");
}

const CARD_SAMPLES = {
  "式神": {name: "山风", description: "倒计时3：发起一次攻击，本次战斗获得不屈。", power: 3, health: 4},
  "战斗": {name: "义道", description: "贯通，连击。对有破甲的式神造成双倍伤害。", shikigami: "铃鹿御前", "power+": -1, "shield+": 2},
  "法术": {name: "觉醒·山风", description: "觉醒：倒计时3：发起一次攻击，本次战斗免疫战斗伤害。你的牌对山风以外的未气绝己方式神造成的减少倒计时效果对山风造成等量效果。（山风气绝时有效）", shikigami: "山风", evolve: true, "power+": 1, "health+": 1},
  "形态": {name: "竹取物语", description: "每个回合结束时，随机召唤一个辉夜姬的幻境。若辉夜姬的幻境耐久>=20，每当辉夜姬受到伤害时，改为扣除辉夜姬幻境等量的耐久（最多降低5耐久）。", shikigami: "辉夜姬", power: 5, health: 5},
  "幻境": {name: "燕子安贝", description: "自己回合结束时，使所有己方角色各恢复1点生命，使所有其他己方幻境各获得1耐久。若此牌耐久>=10，敌方回合结束时，再触发上述效果一次。", shikigami: "辉夜姬", durability: 5},
  "协战": {name: "鸮羽共鸣", description: "选择使用一项：山风-庇羽；薰-鸮鸣", shikigami1: "山风", shikigami2: "薰"},
};

function applyCardSample(type) {
  setGroup("[data-card]", CARD_SAMPLES[type]);
}

function numberValue(value) {
  return Number(value || 0);
}

function optionalCounter(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  if (text === "infinity") return text;
  return Number(text);
}

function cardPayload(values) {
  const type = values.type;
  const card = {
    type,
    name: values.name,
    id: values.id,
    version_date: values.version_date,
    level: numberValue(values.level),
    level_color: values.level_color,
    frame_variant: values.frame_variant,
    special_type: values.special_type,
    description: values.description,
    text_layout: values.text_layout,
    inline_faction_style: numberValue(values.inline_faction_style),
  };
  if (type === "式神") {
    Object.assign(card, {faction: values.faction,
      faction_style: numberValue(values.faction_style),
      power: numberValue(values.power), health: numberValue(values.health)});
  } else {
    card.rarity = values.rarity || null;
  }
  if (["战斗", "法术", "形态", "幻境"].includes(type)) card.shikigami = values.shikigami;
  if (type === "战斗") Object.assign(card, {"power+": numberValue(values["power+"]), "shield+": numberValue(values["shield+"])});
  if (type === "法术") {
    card.evolve = values.evolve === true;
    if (card.evolve) Object.assign(card, {"power+": numberValue(values["power+"]), "health+": numberValue(values["health+"])});
  }
  if (type === "形态") Object.assign(card, {power: numberValue(values.power), health: numberValue(values.health)});
  if (type === "幻境") card.durability = numberValue(values.durability);
  if (type === "协战") Object.assign(card, {
    shikigami1: values.shikigami1, shikigami2: values.shikigami2,
    duo_frame: values.duo_frame === true,
  });
  return card;
}

function renderPayload(kind) {
  const state = readUiState();
  const width = state.width ? Number(state.width) : null;
  if (kind === "mechanism") {
    const mechanism = {...state.mechanism,
      chars_per_line: numberValue(state.mechanism.chars_per_line),
      inline_faction_style: numberValue(state.mechanism.inline_faction_style)};
    if (!mechanism.badge) delete mechanism.badge;
    return {kind, mechanism};
  }
  const entity = {};
  for (const [key, value] of Object.entries(state.entity)) {
    if (["level", "power", "health", "combat_power", "shield"].includes(key)) entity[key] = numberValue(value);
    else if (["energy", "countdown", "defeated_countdown"].includes(key)) entity[key] = optionalCounter(value);
    else if (key === "art_scale") entity[key] = Number(value || 1);
    else if (key.endsWith("_color")) entity[key] = value || null;
    else entity[key] = value;
  }
  const portrait = {...state.portrait};
  for (const key of ["offset_x", "offset_y", "scale", "rotate"]) portrait[key] = Number(portrait[key] || (key === "scale" ? 1 : 0));
  return {
    kind,
    card: cardPayload(state.card),
    state: entity,
    artwork: Object.fromEntries(Object.entries(state.artwork).map(([key, value]) => [key, Number(value || (key === "scale" ? 1 : 0))])),
    portrait,
    artwork_path: artworkPath,
    width,
  };
}

async function render(kind) {
  setRendering(true);
  document.body.dataset.error = "";
  try {
    await saveDraftNow();
    await callWorker("render", renderPayload(kind), artworkBytes);
  } catch (error) {
    console.error(error);
  } finally {
    setRendering(false);
  }
}

for (const button of renderButtons) {
  button.addEventListener("click", () => render(button.dataset.kind));
}

document.getElementById("tab-card").addEventListener("click", () => { showTab("card"); scheduleDraftSave(); });
document.getElementById("tab-mechanism").addEventListener("click", () => { showTab("mechanism"); scheduleDraftSave(); });

document.querySelector('[data-card="type"]').addEventListener("change", event => {
  applyCardSample(event.target.value);
  updateTypeFields();
});
document.querySelector('[data-mech="frame"]').addEventListener("change", updateTypeFields);
document.querySelector('[data-card="evolve"]').addEventListener("change", updateTypeFields);

for (const element of document.querySelectorAll("[data-card], [data-art], [data-portrait], [data-state], [data-mech], #width")) {
  element.addEventListener("input", scheduleDraftSave);
  element.addEventListener("change", scheduleDraftSave);
}

document.getElementById("artwork").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  const extension = file.name.split(".").pop().toLowerCase();
  if (!["png", "jpg", "jpeg", "webp"].includes(extension)) {
    log("仅支持 png/jpg/jpeg/webp 卡图", true);
    event.target.value = "";
    return;
  }
  if (file.size > 64 * 1024 * 1024) {
    log("原型卡图文件不能超过 64 MiB", true);
    event.target.value = "";
    return;
  }
  artworkBytes = await file.arrayBuffer();
  artworkPath = `artwork.${extension}`;
  artworkName = file.name;
  updateArtworkLabel();
  log(`已在浏览器读取 ${file.name}，未上传服务器`);
  scheduleDraftSave();
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

downloadButton.addEventListener("click", () => {
  if (!currentPng) return;
  const mechanismVisible = !document.getElementById("mechanism-editor").hidden;
  const name = mechanismVisible ? document.querySelector('[data-mech="name"]').value : document.querySelector('[data-card="name"]').value;
  downloadBlob(currentPng, `${(name.trim() || "BWPDIY").replace(/[<>:"/\\|?*]/g, "_")}.png`);
});

function bufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let index = 0; index < bytes.length; index += 32768) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 32768));
  }
  return btoa(binary);
}

function base64ToBuffer(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

document.getElementById("export-draft").addEventListener("click", async () => {
  const draft = currentDraft();
  if (draft.artwork) {
    draft.artwork = {...draft.artwork, bytes: bufferToBase64(draft.artwork.bytes)};
  }
  const blob = new Blob([JSON.stringify(draft, null, 2)], {type: "application/json"});
  downloadBlob(blob, `bwpdiy-draft-${new Date().toISOString().slice(0, 10)}.json`);
});

document.getElementById("import-draft").addEventListener("click", () => document.getElementById("draft-file").click());
document.getElementById("draft-file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 100 * 1024 * 1024) throw new Error("草稿备份超过 100 MiB");
    const draft = JSON.parse(await file.text());
    if (draft.schema !== 1 || !draft.state) throw new Error("不是受支持的 BWPDIY 草稿备份");
    if (draft.artwork && typeof draft.artwork.bytes === "string") {
      draft.artwork.bytes = base64ToBuffer(draft.artwork.bytes);
    }
    await restoreDraft(draft);
    await saveDraftNow();
    log("草稿备份已导入当前浏览器");
  } catch (error) {
    log(`导入失败：${error.message}`, true);
  } finally {
    event.target.value = "";
  }
});

document.getElementById("clear-draft").addEventListener("click", async () => {
  if (!confirm("仅删除当前浏览器中的草稿和卡图，并恢复初始表单；资源缓存不受影响。是否继续？")) return;
  clearTimeout(draftTimer);
  await draftStore.clear();
  location.reload();
});

document.getElementById("clear-cache").addEventListener("click", async () => {
  if (!confirm("仅清除浏览器中的程序和素材缓存；草稿与卡图不受影响。下次联网打开时会重新下载。是否继续？")) return;
  const keys = await caches.keys();
  await Promise.all(keys.filter(key => key.startsWith("bwpdiy-")).map(key => caches.delete(key)));
  cacheStatus.textContent = "资源缓存已清除；草稿未改动";
  log(cacheStatus.textContent);
});

async function setupResourceCache() {
  if (!("serviceWorker" in navigator) || !("caches" in window)) {
    cacheStatus.textContent = "当前浏览器不支持资源缓存";
    return;
  }
  try {
    await navigator.serviceWorker.register("sw.js");
    await navigator.serviceWorker.ready;
    cacheStatus.textContent = "资源缓存已启用（仅当前浏览器）";
    document.body.dataset.cacheReady = "true";
  } catch (error) {
    cacheStatus.textContent = `资源缓存启用失败：${error.message}`;
    log(cacheStatus.textContent, true);
  }
}

async function start() {
  setRendering(true);
  logElement.textContent = "";
  const cacheTask = setupResourceCache();
  try {
    const draft = await draftStore.load();
    if (!await restoreDraft(draft)) {
      updateTypeFields();
      draftStatus.textContent = "暂无草稿；编辑后自动保存到当前浏览器";
    }
  } catch (error) {
    draftStatus.textContent = `草稿读取失败：${error.message}`;
    log(draftStatus.textContent, true);
  }
  await cacheTask;
  callWorker("init").catch(error => log(error.message, true));
}

start();
