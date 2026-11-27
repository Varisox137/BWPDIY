"use strict";

const worker = new Worker("worker.js");
const logElement = document.getElementById("log");
let preview = document.getElementById("c-preview");
const resultMetas = [...document.querySelectorAll(".result-meta")];
const downloadButtons = [...document.querySelectorAll(".download-button")];
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
let saveQueue = Promise.resolve();
let restoringDraft = false;
let currentRenderKind = "card";
let activeMainTab = "cards";
let battleKind = "entity";
let renderActive = false;
let queuedRender = null;
let normalPreviewTimer = null;
let fontCoverage = null;
const lowPowerInput = document.getElementById("low-power");
let lowPowerPreference = null;
try { lowPowerPreference = localStorage.getItem("bwpdiy-low-power"); } catch (error) {}
lowPowerInput.checked = lowPowerPreference === null ?
  (matchMedia("(pointer: coarse)").matches || (navigator.deviceMemory && navigator.deviceMemory <= 4)) :
  lowPowerPreference === "1";
const helpModal = document.getElementById("help-modal");
function showHelp() { if (!helpModal.open) helpModal.showModal(); }
document.getElementById("c-btn-help").addEventListener("click", showHelp);
document.getElementById("help-close").addEventListener("click", () => helpModal.close());
const pending = new Map();
const recentLogs = [];
let exportStage = "尚未导出";

function log(message, isError = false) {
  const text = String(message);
  recentLogs.push(`${new Date().toISOString()} ${isError ? "ERROR" : "INFO"} ${text}`);
  if (recentLogs.length > 100) recentLogs.shift();
  const line = document.createElement("span");
  line.textContent = `${new Date().toLocaleTimeString()}  ${text}\n`;
  if (isError) line.className = "error";
  logElement.appendChild(line);
  logElement.scrollTop = logElement.scrollHeight;
}

function kindSupported(kind) {
  const type = document.querySelector('[data-card="type"]').value;
  const evolve = document.querySelector('[data-card="evolve"]').checked;
  if (kind === "entity") return ["式神", "形态"].includes(type) || (type === "法术" && evolve);
  if (kind === "portrait") return type === "式神";
  return true;
}

function setRendering(rendering) {
  const ready = document.body.dataset.ready === "true";
  for (const button of renderButtons) {
    button.disabled = rendering || !ready || !kindSupported(button.dataset.kind);
  }
  document.body.dataset.rendering = String(rendering);
  updateBattleStyles();
}

function callWorker(type, payload = null, artwork = null) {
  const id = ++requestSequence;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject, target: payload && payload.target, seq: payload && payload.layout_seq,
      work: type === "render" ? currentWorkId : ""});
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

function showPreviewStatus(message, isError = false) {
  if (renderCount === 0) resultMetas.forEach(element => { element.textContent = message; });
  for (const id of ["c-error", "b-error"]) {
    document.getElementById(id).textContent = isError ? message : "";
  }
}

function updateFontWarning() {
  const element = document.getElementById("font-warning");
  if (!fontCoverage) { element.textContent = ""; return; }
  const mechanism = !document.getElementById("mechanism-editor").hidden;
  const nameText = mechanism ? document.querySelector('[data-mech="name"]').value :
    ["name", "shikigami", "shikigami1", "shikigami2", "special_type"]
      .map(key => document.querySelector(`[data-card="${key}"]`).value).join("");
  const description = mechanism ? document.querySelector('[data-mech="text"]').value :
    document.querySelector('[data-card="description"]').value;
  const missing = [...new Set([
    ...BWPDiyUI.missingCharacters(nameText, fontCoverage.name),
    ...BWPDiyUI.missingCharacters(description, fontCoverage.desc),
  ])].slice(0, 12);
  element.textContent = missing.length ?
    `在线精简字体不含「${missing.join("")}」，这些字符可能显示为空框；桌面完整字体不受影响。` : "";
}

function showNormalResult(message) {
  updateFontWarning();
  currentPng = new Blob([message.png], {type: "image/png"});
  if (currentBlobUrl) URL.revokeObjectURL(currentBlobUrl);
  currentBlobUrl = URL.createObjectURL(currentPng);
  preview.src = currentBlobUrl;
  const info = message.info;
  const text = `${info.kind}：${info.width}×${info.height}，渲染 ${info.render_ms} ms，总耗时 ${info.total_ms} ms，PNG ${(info.png_bytes / 1024).toFixed(1)} KiB`;
  resultMetas.forEach(element => { element.textContent = text; });
  showPreviewStatus(text);
  currentRenderKind = info.kind;
  renderCount += 1;
  document.body.dataset.renderCount = String(renderCount);
  downloadButtons.forEach(button => { button.disabled = false; });
  log(text);
}

worker.onmessage = event => {
  const message = event.data;
  if (message.type === "status") { log(message.message); showPreviewStatus(message.message); return; }
  if (message.type === "progress") { showPreviewStatus(message.message); return; }
  const request = pending.get(message.id);
  const isLayout = request && request.target && request.target.startsWith("layout-");
  if (message.type === "ready") {
    fontCoverage = Object.fromEntries(Object.entries(message.info.environment.font_coverage || {})
      .map(([kind, characters]) => [kind, new Set(characters)]));
    updateFontWarning();
    document.body.dataset.ready = "true";
    setRendering(false);
    log(`初始化 ${message.info.startup_ms} ms；资源包 ${(message.info.runtime_bytes / 1048576).toFixed(1)} MiB`);
    showPreviewStatus("正在生成首次预览…");
    updateStorageStatus();
    initializeLayouts(message.info.layouts).then(() => {
      if (!renderActive && renderCount === 0 && activeMainTab !== "layout") {
        render(activeMainTab === "battle" ? battleKind : currentRenderKind, true);
      }
    }).catch(error => showPreviewStatus(`布局初始化失败：${error.message}`, true));
  }
  const staleWork = request && request.work && request.work !== currentWorkId;
  if (message.type === "result") {
    if (isLayout) handleLayoutRender(message, request.target, request.seq);
    else if (!staleWork) showNormalResult(message);
  }
  if (message.type === "error") {
    if (isLayout) handleLayoutError(message, request.seq);
    else if (!staleWork) {
      log(`失败：${message.message}`, true);
      if (message.detail) log(message.detail, true);
      document.body.dataset.error = message.message;
      showPreviewStatus(`渲染初始化或合成失败：${message.message}`, true);
    }
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
  showPreviewStatus(`渲染组件加载失败：${event.message}`, true);
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
    card: readGroup("[data-card]"), artwork: readGroup("[data-art]"),
    portrait: readGroup("[data-portrait]"), entity: readGroup("[data-state]"),
    mechanism: readGroup("[data-mech]"), width: document.getElementById("width").value,
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
  syncCardFrameButtons();
}

function currentDraft() {
  return {
    schema: 1, saved_at: new Date().toISOString(), state: readUiState(),
    artwork: artworkBytes ? {name: artworkName, path: artworkPath, bytes: artworkBytes} : null,
    layouts: globalLayouts ? deepCopy(globalLayouts) : null,
  };
}

async function saveDraftNow() {
  if (restoringDraft || tutorialMode) return;
  clearTimeout(draftTimer);
  draftTimer = null;
  const draft = currentDraft();
  const operation = saveQueue.then(() => persistCurrentWork(draft));
  saveQueue = operation.catch(() => {});
  try {
    await operation;
    if (libraryAvailable) {
      draftStatus.textContent = `作品已保存到当前浏览器：${new Date().toLocaleTimeString()}`;
      document.body.dataset.draftSaved = "true";
    }
    updateStorageStatus();
  } catch (error) {
    draftStatus.textContent = `作品保存失败：${error.message}`;
    log(draftStatus.textContent, true);
  }
}

function scheduleDraftSave() {
  if (restoringDraft || tutorialMode) return;
  draftStatus.textContent = "有尚未写入浏览器的作品更改…";
  clearTimeout(draftTimer);
  draftTimer = setTimeout(saveDraftNow, 300);
}

async function restoreDraft(draft) {
  if (!draft || draft.schema !== 1 || !draft.state) return false;
  restoringDraft = true;
  try {
    applyUiState(draft.state);
    if (draft.layouts) {
      restoredLayouts = deepCopy(draft.layouts);
      if (defaultLayouts) {
        globalLayouts = deepCopy(restoredLayouts);
        buildLayoutTypes();
        selectLayoutType(layoutType);
        await saveLayoutNow();
      }
    }
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
  draftStatus.textContent = draft.saved_at ? `已恢复浏览器作品：${new Date(draft.saved_at).toLocaleString()}` : "已恢复浏览器作品";
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
  document.getElementById("c-frame-variants").hidden = mechanism;
  updateFontWarning();
}

function showMainTab(tab) {
  activeMainTab = tab;
  updateMobileWorkspace(tab);
  document.querySelectorAll(".navtab").forEach(button => button.classList.toggle("active", button.dataset.tab === tab));
  document.querySelectorAll(".tabpage").forEach(page => page.classList.toggle("active", page.id === `tab-${tab}`));
  if (tab === "layout") {
    scheduleLayoutPreview(0);
    return;
  }
  preview = document.getElementById(tab === "battle" ? "b-preview" : "c-preview");
  if (currentPng) preview.src = currentBlobUrl;
  if (tab === "battle") {
    if (!kindSupported(battleKind)) battleKind = kindSupported("entity") ? "entity" : "card";
    updateBattleStyles();
    render(battleKind);
  }
}

function updateBattleStyles() {
  document.querySelectorAll(".battle-style").forEach(button => {
    button.classList.toggle("active", button.dataset.kind === battleKind);
    button.disabled = !kindSupported(button.dataset.kind);
  });
}

document.querySelectorAll(".navtab").forEach(button => {
  button.addEventListener("click", () => showMainTab(button.dataset.tab));
});
document.querySelectorAll(".battle-style").forEach(button => {
  button.addEventListener("click", () => {
    battleKind = button.dataset.kind;
    updateBattleStyles();
    render(battleKind);
  });
});

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

function resetCardForm(type = "式神") {
  for (const element of document.querySelectorAll("[data-card]")) {
    if (element.type === "checkbox") element.checked = element.defaultChecked;
    else if (element.tagName === "SELECT") element.value = element.options[0]?.value || "";
    else element.value = element.defaultValue;
  }
  document.querySelector('[data-card="type"]').value = type;
}

function applyCardSample(type) {
  resetCardForm(type);
  setGroup("[data-card]", CARD_SAMPLES[type]);
}
function numberValue(value) { return Number(value || 0); }
function optionalCounter(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  return text === "infinity" ? text : Number(text);
}

function cardPayload(values) {
  const type = values.type;
  const card = {type, name: values.name, id: values.id, version_date: values.version_date,
    level_color: values.level_color, frame_variant: values.frame_variant,
    special_type: values.special_type, description: values.description,
    text_layout: values.text_layout, inline_faction_style: numberValue(values.inline_faction_style)};
  const level = numberValue(values.level);
  if (level) card.level = level;
  if (type === "式神") {
    Object.assign(card, {faction: values.faction, faction_style: numberValue(values.faction_style),
      power: numberValue(values.power), health: numberValue(values.health)});
  } else card.rarity = values.rarity || null;
  if (["战斗", "法术", "形态", "幻境"].includes(type)) card.shikigami = values.shikigami;
  if (type === "战斗") Object.assign(card, {"power+": numberValue(values["power+"]), "shield+": numberValue(values["shield+"])});
  if (type === "法术") {
    card.evolve = values.evolve === true;
    if (card.evolve) Object.assign(card, {"power+": numberValue(values["power+"]), "health+": numberValue(values["health+"])});
  }
  if (type === "形态") Object.assign(card, {power: numberValue(values.power), health: numberValue(values.health)});
  if (type === "幻境") card.durability = numberValue(values.durability);
  if (type === "协战") Object.assign(card, {shikigami1: values.shikigami1,
    shikigami2: values.shikigami2, duo_frame: values.duo_frame === true});
  return card;
}

function renderPayload(kind, interactive = false) {
  const state = readUiState();
  let width = state.width ? Number(state.width) : null;
  if (interactive && lowPowerInput.checked && kind === "card" && width === null) width = 200;
  if (kind === "mechanism") {
    const mechanism = {...state.mechanism, chars_per_line: numberValue(state.mechanism.chars_per_line),
      inline_faction_style: numberValue(state.mechanism.inline_faction_style)};
    if (!mechanism.badge) delete mechanism.badge;
    return {kind, mechanism, layouts: globalLayouts};
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
  return {kind, card: cardPayload(state.card), state: entity,
    artwork: Object.fromEntries(Object.entries(state.artwork).map(([key, value]) => [key, Number(value || (key === "scale" ? 1 : 0))])),
    portrait, artwork_path: artworkPath, width, layouts: globalLayouts};
}

async function render(kind, manual = false, interactive = false) {
  if (!kindSupported(kind)) return;
  if (manual) clearTimeout(normalPreviewTimer);
  currentRenderKind = kind;
  if (renderActive) { queuedRender = {kind, interactive}; return; }
  renderActive = true;
  setRendering(true);
  downloadButtons.forEach(button => { button.disabled = true; });
  let next = {kind, interactive};
  try {
    while (next) {
      queuedRender = null;
      currentRenderKind = next.kind;
      document.body.dataset.error = "";
      try { await callWorker("render", renderPayload(next.kind, next.interactive), artworkBytes); }
      catch (error) { console.error(error); }
      next = queuedRender;
    }
  } finally {
    renderActive = false;
    setRendering(false);
    downloadButtons.forEach(button => { button.disabled = !currentPng; });
  }
}

function scheduleNormalPreview(kind = currentRenderKind, delay = 250, interactive = false) {
  if (activeMainTab === "layout" || document.hidden || !kindSupported(kind)) return;
  clearTimeout(normalPreviewTimer);
  normalPreviewTimer = setTimeout(() => render(kind, false, interactive), delay);
}

for (const button of renderButtons) button.addEventListener("click", () => render(button.dataset.kind, true));
document.getElementById("c-btn-refresh").addEventListener("click", () => render(currentRenderKind, true));
document.getElementById("b-btn-refresh").addEventListener("click", () => render(battleKind, true));
document.getElementById("tab-card").addEventListener("click", () => selectEditorKind("card"));
document.getElementById("tab-mechanism").addEventListener("click", () => selectEditorKind("mechanism"));

document.querySelector('[data-card="type"]').addEventListener("change", event => {
  resetCardForm(event.target.value);
  if (!kindSupported(currentRenderKind)) currentRenderKind = "card";
  updateTypeFields();
  scheduleNormalPreview(currentRenderKind);
});
document.querySelector('[data-mech="frame"]').addEventListener("change", updateTypeFields);
document.querySelector('[data-card="evolve"]').addEventListener("change", updateTypeFields);

const SYNTAX_INSERTS = [
  ["关键字", "[[关键字]]"], ["换行", "\n"], ["力量", "#ll"], ["生命", "#sm"],
  ["护甲", "#hj"], ["破甲", "#pj"], ["能量", "#nl"], ["耐久", "#nj"],
  ["战力", "#zl"], ["乏力", "#fl"], ["红莲", "#hl"], ["苍叶", "#cy"],
  ["青岚", "#ql"], ["紫岩", "#zy"],
];

function initializeSyntaxTools() {
  for (const textarea of document.querySelectorAll('[data-card="description"], [data-mech="text"]')) {
    const details = document.createElement("details");
    details.className = "syntax-helper";
    const summary = document.createElement("summary");
    summary.textContent = "快捷输入：高亮 / 小图标 / 换行";
    const tools = document.createElement("div");
    tools.className = "syntax-tools";
    for (const [label, insertion] of SYNTAX_INSERTS) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.title = `插入 ${insertion === "\n" ? "换行" : insertion}`;
      button.addEventListener("pointerdown", event => event.preventDefault());
      button.addEventListener("click", () => {
        const result = BWPDiyUI.insertText(
          textarea.value, textarea.selectionStart, textarea.selectionEnd, insertion);
        textarea.focus();
        textarea.value = result.value;
        textarea.setSelectionRange(result.cursor, result.cursor);
        textarea.dispatchEvent(new Event("input", {bubbles: true}));
        textarea.dispatchEvent(new Event("change", {bubbles: true}));
      });
      tools.appendChild(button);
    }
    details.append(summary, tools);
    textarea.closest("label").insertAdjacentElement("afterend", details);
  }
}

function scheduleControlPreview(element, delay = null) {
  updateFontWarning();
  const wait = delay ?? (element.matches("[data-art], [data-portrait]") ? 100 :
    element.matches("[data-state]") ? 150 : 250);
  if (element.matches("[data-art]")) scheduleNormalPreview(currentRenderKind, wait);
  else if (element.matches("[data-portrait]")) {
    if (currentRenderKind === "portrait") scheduleNormalPreview("portrait", wait);
  } else if (element.matches("[data-state]")) {
    if (activeMainTab === "battle") scheduleNormalPreview(battleKind, wait);
  } else scheduleNormalPreview(element.matches("[data-mech]") ? "mechanism" : currentRenderKind, wait);
}

initializeSyntaxTools();
const composingControls = new WeakSet();
for (const element of document.querySelectorAll("[data-card], [data-art], [data-portrait], [data-state], [data-mech], #width")) {
  element.addEventListener("compositionstart", () => {
    composingControls.add(element);
    clearTimeout(normalPreviewTimer);
    clearTimeout(draftTimer);
  });
  element.addEventListener("compositionend", () => {
    composingControls.delete(element);
    scheduleDraftSave();
    scheduleControlPreview(element, 0);
  });
  element.addEventListener("input", event => {
    if (event.isComposing || composingControls.has(element)) return;
    scheduleDraftSave();
    if (element.matches('textarea, input:not([type="number"]):not([type="checkbox"]):not([type="file"])')) {
      scheduleControlPreview(element);
    }
  });
  element.addEventListener("change", event => {
    if (event.isComposing || composingControls.has(element)) return;
    scheduleDraftSave();
    scheduleControlPreview(element);
  });
}

function syncCardFrameButtons() {
  const variant = document.querySelector('[data-card="frame_variant"]').value;
  document.querySelectorAll("#c-frame-variants .fv").forEach(button => button.classList.toggle("active", button.dataset.fv === variant));
}
document.querySelectorAll("#c-frame-variants .fv").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelector('[data-card="frame_variant"]').value = button.dataset.fv;
    syncCardFrameButtons();
    scheduleDraftSave();
    scheduleNormalPreview(currentRenderKind, 0);
  });
});
document.querySelector('[data-card="frame_variant"]').addEventListener("change", syncCardFrameButtons);

document.getElementById("artwork").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  const extension = file.name.split(".").pop().toLowerCase();
  if (!["png", "jpg", "jpeg", "webp"].includes(extension)) {
    log("仅支持 png/jpg/jpeg/webp 卡图", true); event.target.value = ""; return;
  }
  if (file.size > 64 * 1024 * 1024) {
    log("原型卡图文件不能超过 64 MiB", true); event.target.value = ""; return;
  }
  artworkBytes = await file.arrayBuffer();
  artworkPath = `artwork.${extension}`;
  artworkName = file.name;
  updateArtworkLabel();
  log(`已在浏览器读取 ${file.name}，未上传服务器`);
  scheduleDraftSave();
  scheduleNormalPreview(currentRenderKind, 0);
});

for (const button of document.querySelectorAll(".preview-toggle")) {
  button.addEventListener("click", () => {
    const panel = document.getElementById(button.dataset.preview);
    const collapsed = panel.classList.toggle("preview-collapsed");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.textContent = collapsed ? "展开预览" : "收起预览";
  });
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

const exportModal = document.getElementById("export-modal");
const exportImage = document.getElementById("export-image");
const exportBackgroundButton = document.getElementById("export-bg-toggle");
const exportStatus = document.getElementById("export-status");

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand && document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("当前浏览器不允许自动复制");
}

function diagnosticsReport() {
  return [
    "BWPDIY 在线本地版诊断（不含卡名、描述和卡图数据）",
    `时间：${new Date().toISOString()}`,
    `页面：${location.href}`,
    `浏览器：${navigator.userAgent}`,
    `在线：${navigator.onLine}；初始化：${document.body.dataset.ready}；渲染次数：${renderCount}`,
    `导出阶段：${exportStage}；当前 PNG：${currentPng ? currentPng.size : 0} 字节`,
    `存储：${document.getElementById("storage-status").textContent}`,
    "近期运行记录：",
    ...recentLogs.slice(-60),
  ].join("\n");
}

async function copyDiagnostics(statusElement) {
  try {
    await copyText(diagnosticsReport());
    log("诊断信息已复制");
    if (statusElement) statusElement.textContent = "诊断信息已复制，可粘贴后反馈";
  } catch (error) {
    log(`复制诊断信息失败：${error.message}`, true);
    if (statusElement) statusElement.textContent = `${error.message}；请截图运行记录`;
  }
}
document.getElementById("copy-diagnostics").addEventListener("click", () => copyDiagnostics(null));
document.getElementById("export-diagnostics").addEventListener("click", () => copyDiagnostics(exportStatus));

let exportOriginal = null;
let exportBlob = null;
let exportUrl = "";
let exportFilename = "BWPDIY.png";
let exportWhite = false;
let exportOperation = 0;

function currentExportFilename() {
  const mechanismVisible = !document.getElementById("mechanism-editor").hidden;
  const name = mechanismVisible ? document.querySelector('[data-mech="name"]').value :
    document.querySelector('[data-card="name"]').value;
  return BWPDiyUI.pngFilename(name);
}

function replaceExportImage(blob) {
  if (exportUrl) URL.revokeObjectURL(exportUrl);
  exportBlob = blob;
  exportUrl = URL.createObjectURL(blob);
  exportImage.src = exportUrl;
}

function openExportDialog() {
  if (exportModal.open) return;
  exportStage = "打开长按保存窗口";
  exportOperation += 1;
  exportOriginal = currentPng;
  exportFilename = currentExportFilename();
  exportWhite = false;
  exportBackgroundButton.disabled = false;
  exportBackgroundButton.textContent = "切换为白底";
  exportStatus.textContent = "默认保留透明背景";
  replaceExportImage(exportOriginal);
  exportModal.showModal();
  log(`导出：${exportStage}，PNG ${exportOriginal.size} 字节`);
}

async function whiteBackgroundPng(blob) {
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0);
    if (canvas.toBlob) {
      return await new Promise((resolve, reject) => {
        canvas.toBlob(result => result ? resolve(result) : reject(new Error("浏览器未能生成白底 PNG")), "image/png");
      });
    }
    const encoded = canvas.toDataURL("image/png").split(",")[1];
    const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
    return new Blob([bytes], {type: "image/png"});
  } finally {
    URL.revokeObjectURL(url);
  }
}

exportBackgroundButton.addEventListener("click", async () => {
  if (!exportOriginal) return;
  const operation = ++exportOperation;
  const white = !exportWhite;
  exportBackgroundButton.disabled = true;
  try {
    const blob = white ? await whiteBackgroundPng(exportOriginal) : exportOriginal;
    if (operation !== exportOperation) return;
    exportWhite = white;
    replaceExportImage(blob);
    exportBackgroundButton.textContent = white ? "恢复透明底" : "切换为白底";
    exportStatus.textContent = white ? "已生成白底 PNG；原图未修改" : "已恢复透明 PNG";
  } catch (error) {
    exportStatus.textContent = `背景切换失败：${error.message}`;
  } finally {
    exportBackgroundButton.disabled = false;
  }
});
function attemptPngDownload(blob, filename) {
  exportStage = "调用浏览器下载";
  try {
    downloadBlob(blob, filename);
    log(`已调用浏览器下载：${currentRenderKind}，PNG ${blob.size} 字节`);
  } catch (error) {
    exportStage = "浏览器下载调用失败";
    log(`${exportStage}：${error.message}`, true);
    exportStatus.textContent = "直接下载失败，请长按图片保存或复制诊断信息";
    openExportDialog();
  }
}
document.getElementById("export-download").addEventListener("click", () => {
  if (exportBlob) attemptPngDownload(exportBlob, exportFilename);
});
document.getElementById("export-copy-link").addEventListener("click", async () => {
  try {
    await copyText(location.href);
    exportStatus.textContent = "页面链接已复制，可粘贴到系统浏览器打开";
  } catch (error) {
    exportStatus.textContent = `${error.message}；请手动复制地址栏链接`;
  }
});
document.getElementById("export-close").addEventListener("click", () => exportModal.close());
exportModal.addEventListener("close", () => {
  if (exportModal.open) return;
  exportOperation += 1;
  exportOriginal = null;
  exportBlob = null;
  if (exportUrl) URL.revokeObjectURL(exportUrl);
  exportUrl = "";
  exportImage.removeAttribute("src");
});

for (const button of downloadButtons) button.addEventListener("click", () => {
  if (!currentPng) return;
  if (BWPDiyUI.isEmbeddedBrowser(navigator.userAgent)) openExportDialog();
  else attemptPngDownload(currentPng, currentExportFilename());
});

document.getElementById("export-draft").addEventListener("click", exportCurrentWork);
document.getElementById("export-library").addEventListener("click", exportFullLibrary);
document.getElementById("import-draft").addEventListener("click", () => document.getElementById("draft-file").click());
document.getElementById("draft-file").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (file) await importBackupFile(file);
  event.target.value = "";
});

document.getElementById("clear-draft").addEventListener("click", clearLocalLibrary);
document.getElementById("clear-cache").addEventListener("click", async () => {
  if (!confirm("仅清除浏览器中的程序和素材缓存；作品、卡图与布局不受影响。下次联网打开时会重新下载。是否继续？")) return;
  const keys = await caches.keys();
  await Promise.all(keys.filter(key => key.startsWith("bwpdiy-")).map(key => caches.delete(key)));
  cacheStatus.textContent = "资源缓存已清除；作品与布局未改动";
  log(cacheStatus.textContent);
});

function bindArtMouse(image) {
  const pointers = new Map();
  let drag = null;
  let gesture = null;
  let rightButtonDown = false;
  const channel = () => currentRenderKind === "portrait" ? "portrait" : "art";
  const get = key => Number(document.querySelector(`[data-${channel()}="${key}"]`).value || (key === "scale" ? 1 : 0));
  const set = (key, value) => {
    document.querySelector(`[data-${channel()}="${key}"]`).value = String(value);
    scheduleDraftSave();
  };
  const metrics = () => {
    const points = [...pointers.values()].slice(0, 2);
    const dx = points[1].x - points[0].x;
    const dy = points[1].y - points[0].y;
    return {distance: Math.max(1, Math.hypot(dx, dy)), angle: Math.atan2(dy, dx) * 180 / Math.PI,
      x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2};
  };
  const displayRatio = () => {
    const rect = image.getBoundingClientRect();
    return rect.width > 0 && image.naturalWidth > 0 ? image.naturalWidth / rect.width : 1;
  };
  image.addEventListener("pointerdown", event => {
    if (BWPDiyMobile.gesturesLocked()) return;
    if (event.button === 2) { rightButtonDown = true; return; }
    if (event.button !== 0 || !currentPng || currentRenderKind === "mechanism") return;
    event.preventDefault();
    image.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    if (pointers.size === 1) {
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY, ox: get("offset_x"), oy: get("offset_y")};
    } else if (pointers.size === 2) {
      const start = metrics();
      drag = null;
      gesture = {distance: start.distance, angle: start.angle, x: start.x, y: start.y,
        scale: get("scale"), rotate: get("rotate"), ox: get("offset_x"), oy: get("offset_y")};
    }
  });
  window.addEventListener("pointerup", event => {
    if (event.button === 2) rightButtonDown = false;
  });
  image.addEventListener("pointermove", event => {
    if (BWPDiyMobile.gesturesLocked() || !pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    if (gesture && pointers.size >= 2) {
      const current = metrics();
      const angleDelta = current.angle - gesture.angle;
      set("scale", Math.round(Math.max(0.01, gesture.scale * current.distance / gesture.distance) * 1000) / 1000);
      set("rotate", Math.round(gesture.rotate + angleDelta));
      set("offset_x", Math.round(gesture.ox + (current.x - gesture.x) * displayRatio()));
      set("offset_y", Math.round(gesture.oy + (current.y - gesture.y) * displayRatio()));
    } else if (drag && drag.id === event.pointerId) {
      set("offset_x", Math.round(drag.ox + (event.clientX - drag.x) * displayRatio()));
      set("offset_y", Math.round(drag.oy + (event.clientY - drag.y) * displayRatio()));
    }
    scheduleNormalPreview(currentRenderKind, 80, true);
  });
  const finish = event => {
    if (!pointers.has(event.pointerId)) return;
    pointers.delete(event.pointerId);
    gesture = null;
    drag = null;
    if (pointers.size === 1) {
      const [id, point] = [...pointers.entries()][0];
      drag = {id, x: point.x, y: point.y, ox: get("offset_x"), oy: get("offset_y")};
    }
    scheduleNormalPreview(currentRenderKind, 0, false);
  };
  image.addEventListener("pointerup", finish);
  image.addEventListener("pointercancel", finish);
  image.addEventListener("wheel", event => {
    if (BWPDiyMobile.gesturesLocked() || !currentPng || currentRenderKind === "mechanism") return;
    event.preventDefault();
    if ((event.buttons & 2) || rightButtonDown) set("rotate", Math.round(get("rotate")) + (event.deltaY < 0 ? 3 : -3));
    else set("scale", Math.round(Math.max(0.01, get("scale") * (event.deltaY < 0 ? 1.05 : 1 / 1.05)) * 1000) / 1000);
    scheduleNormalPreview(currentRenderKind, 60, false);
  }, {passive: false});
  image.addEventListener("contextmenu", event => event.preventDefault());
}
BWPDiyMobile.initialize();
bindArtMouse(document.getElementById("c-preview"));
bindArtMouse(document.getElementById("b-preview"));

lowPowerInput.addEventListener("change", () => {
  try { localStorage.setItem("bwpdiy-low-power", lowPowerInput.checked ? "1" : "0"); } catch (error) {}
  log(lowPowerInput.checked ? "已启用低负载预览；导出仍使用完整质量" : "已关闭低负载预览");
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && activeMainTab === "layout") scheduleLayoutPreview(0);
});

function formatStorageSize(value) {
  if (!Number.isFinite(value) || value <= 0) return "0 MiB";
  return `${(value / 1048576).toFixed(value >= 10485760 ? 0 : 1)} MiB`;
}

async function updateStorageStatus() {
  const element = document.getElementById("storage-status");
  const button = document.getElementById("persist-storage");
  if (!navigator.storage || !navigator.storage.estimate) {
    element.textContent = "当前浏览器不提供存储容量查询；请定期导出作品备份";
    button.disabled = true;
    return;
  }
  try {
    const estimate = await navigator.storage.estimate();
    const persisted = navigator.storage.persisted ? await navigator.storage.persisted() : false;
    const usage = formatStorageSize(estimate.usage || 0);
    const quota = estimate.quota ? formatStorageSize(estimate.quota) : "未知";
    element.textContent = `本站浏览器存储 ${usage} / ${quota}；持久保护：${persisted ? "已开启" : "未开启"}`;
    document.body.dataset.storagePersisted = String(persisted);
    button.disabled = persisted || !navigator.storage.persist;
    if (persisted) button.textContent = "已获得持久存储保护";
  } catch (error) {
    element.textContent = `存储状态读取失败：${error.message}`;
  }
}

document.getElementById("persist-storage").addEventListener("click", async () => {
  if (!navigator.storage || !navigator.storage.persist) return;
  const button = document.getElementById("persist-storage");
  button.disabled = true;
  try {
    const granted = await navigator.storage.persist();
    log(granted ? "浏览器已允许持久存储保护" : "浏览器暂未授予持久存储保护；请保留导出的作品备份", !granted);
  } catch (error) {
    log(`持久存储请求失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    await updateStorageStatus();
  }
});

async function setupResourceCache() {
  if (!("serviceWorker" in navigator) || !("caches" in window)) {
    cacheStatus.textContent = "当前浏览器不支持资源缓存"; return;
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
  updateStorageStatus();
  await initializeLibrary();
  syncCardFrameButtons();
  initializeTutorial();
  await cacheTask;
  callWorker("init").catch(error => log(error.message, true));
}

start();
