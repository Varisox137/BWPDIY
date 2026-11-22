"use strict";

const LAYOUT_TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战", "对局式神", "机制"];
const LAYOUT_FRAME_TYPES = new Set(["式神", "战斗", "法术", "形态", "幻境", "协战"]);
const LAYOUT_NAMES = {
  level: "等级", burst: "爆能", status: "特殊状态", duo_frame: "双式神框",
  name: "卡名", rarity: "稀有度", desc: "描述", art_window: "卡图内窗",
  power: "力量", health: "生命", shield: "护甲", durability: "耐久", footer: "脚注",
  faction: "派系", combat_power: "战力", energy: "能量", countdown: "倒计时",
  defeated: "气绝倒计时", pos: "位置", offset: "偏移", center: "中心点",
  center_offset: "居中点偏移", num_offset: "数字偏移", font_size: "字号",
  icon_size: "图标尺寸", width: "宽度", height: "高度", enabled: "启用",
  size: "尺寸", gap: "间距", margin: "卡名间距", style: "样式",
  base_size: "底座尺寸", star_size: "星标尺寸", num_size: "数字尺寸",
  frames: "各框体", invocation: "灵咒框", skill: "关键字框", seal: "加护蚀印框",
  text_x: "文本偏移 x", text_dy: "文本偏移 y", badge_size: "角标尺寸",
  badge_pos: "角标位置", name_size: "名称字号", text_size: "正文字号",
  icon_scale: "小图标相对文字大小",
};
let defaultLayouts = null;
let globalLayouts = null;
let restoredLayouts = null;
let layoutType = "式神";
let layoutVariant = "norm";
let layoutSelection = null;
let layoutSaveTimer = null;
let layoutPreviewTimer = null;
let layoutPreviewImage = null;
let layoutCropOrigin = [0, 0];
let layoutRequestSeq = 0;
let layoutRenderBusy = false;
let layoutRenderQueued = false;

function deepCopy(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

function deepMerge(base, override) {
  if (!override || typeof override !== "object" || Array.isArray(override)) return deepCopy(override);
  const result = base && typeof base === "object" && !Array.isArray(base) ? deepCopy(base) : {};
  for (const [key, value] of Object.entries(override)) {
    result[key] = value && typeof value === "object" && !Array.isArray(value) ?
      deepMerge(result[key], value) : deepCopy(value);
  }
  return result;
}

function layoutDisp(key) {
  return LAYOUT_NAMES[key] || key;
}

async function initializeLayouts(defaults) {
  defaultLayouts = deepCopy(defaults);
  let saved = null;
  try {
    saved = await draftStore.loadLayout();
  } catch (error) {
    log(`浏览器布局读取失败：${error.message}`, true);
  }
  globalLayouts = saved && saved.schema === 1 ? saved.layouts :
    restoredLayouts || deepCopy(defaultLayouts);
  buildLayoutTypes();
  selectLayoutType(layoutType);
  document.body.dataset.layoutReady = "true";
}

function materializeCardLayout(layouts, type, variant) {
  const base = layouts[type];
  if (variant === "norm") return base;
  base.frame_variants = base.frame_variants || {};
  if (!base.frame_variants[variant]) {
    const {frame_variants: _ignored, ...norm} = base;
    base.frame_variants[variant] = deepCopy(norm);
  }
  return base.frame_variants[variant];
}

function currentLayout() {
  if (layoutType === "对局式神" || layoutType === "机制") return globalLayouts[layoutType];
  return materializeCardLayout(globalLayouts, layoutType, layoutVariant);
}

function defaultCurrentTypeLayouts() {
  if (layoutType === "对局式神" || layoutType === "机制") return deepCopy(defaultLayouts[layoutType]);
  const result = deepCopy(defaultLayouts[layoutType]);
  materializeCardLayout({[layoutType]: result}, layoutType, layoutVariant);
  return result;
}

function buildLayoutTypes() {
  const container = document.getElementById("l-types");
  container.textContent = "";
  for (const type of LAYOUT_TYPES) {
    const button = document.createElement("button");
    button.className = "tab";
    button.textContent = type;
    button.dataset.type = type;
    button.addEventListener("click", () => selectLayoutType(type));
    container.appendChild(button);
  }
}

function selectLayoutType(type) {
  layoutType = type;
  layoutSelection = null;
  layoutPreviewImage = null;
  document.querySelectorAll("#l-types .tab").forEach(button => {
    button.classList.toggle("active", button.dataset.type === type);
  });
  const mechanism = type === "机制";
  document.getElementById("l-preview").hidden = mechanism;
  document.getElementById("l-mech").classList.toggle("active", mechanism);
  document.getElementById("l-frame-variants").hidden = mechanism;
  document.querySelectorAll("#l-frame-variants .fv").forEach(button => {
    button.classList.toggle("active", button.dataset.fv === layoutVariant);
  });
  buildLayoutElements();
  buildLayoutProps();
  scheduleLayoutPreview(0);
}

document.querySelectorAll("#l-frame-variants .fv").forEach(button => {
  button.addEventListener("click", () => {
    layoutVariant = button.dataset.fv;
    selectLayoutType(layoutType);
  });
});

function layoutItems() {
  if (layoutType === "机制") {
    return [{name: "通用设置", path: []},
      {name: "灵咒框", path: ["frames", "invocation"]},
      {name: "关键字框", path: ["frames", "skill"]},
      {name: "加护蚀印框", path: ["frames", "seal"]}];
  }
  const layout = currentLayout();
  const items = [];
  for (const [name, value] of Object.entries(layout.elements || {})) {
    items.push({name: layoutDisp(name), path: ["elements", name], kind: value.kind});
  }
  if (layoutType === "对局式神") {
    if (layout.art_window) items.push({name: "卡图内窗", path: ["art_window"]});
  } else {
    for (const name of Object.keys(layout.text_regions || {})) {
      items.push({name: layoutDisp(name), path: ["text_regions", name]});
    }
  }
  return items;
}

function getPath(root, path) {
  return path.reduce((value, key) => value[key], root);
}

function buildLayoutElements() {
  const container = document.getElementById("l-elems");
  container.textContent = "";
  for (const item of layoutItems()) {
    const element = document.createElement("div");
    element.className = "item";
    element.textContent = item.name;
    element.dataset.path = JSON.stringify(item.path);
    element.addEventListener("click", () => {
      layoutSelection = item;
      document.querySelectorAll("#l-elems .item").forEach(entry => entry.classList.toggle("active", entry === element));
      buildLayoutProps();
      drawLayoutCanvas();
    });
    container.appendChild(element);
  }
}

function buildLayoutProps() {
  const container = document.getElementById("l-props");
  container.textContent = "";
  if (!layoutSelection) {
    container.textContent = "点击元素/文本区以编辑";
    return;
  }
  const title = document.createElement("h3");
  title.textContent = layoutSelection.name;
  container.appendChild(title);
  const value = getPath(currentLayout(), layoutSelection.path);
  buildLayoutFields(container, value, value, layoutType === "机制" && layoutSelection.path.length === 0);
}

function boundedLayoutNumber(input) {
  const value = Number(input.value);
  if (!Number.isFinite(value)) return null;
  return Math.max(-8192, Math.min(8192, value));
}

function buildLayoutFields(container, root, value, skipFrames = false) {
  for (const [key, entry] of Object.entries(value)) {
    if (skipFrames && key === "frames") continue;
    if (entry === null || entry === undefined) continue;
    if (typeof entry === "number") {
      const label = document.createElement("label");
      label.textContent = `${layoutDisp(key)} `;
      const input = document.createElement("input");
      input.type = "number";
      input.step = Number.isInteger(entry) ? "1" : "0.01";
      input.value = String(entry);
      input.addEventListener("change", () => {
        const next = boundedLayoutNumber(input);
        if (next === null) { input.value = String(entry); return; }
        value[key] = next;
        layoutChanged();
      });
      label.appendChild(input);
      container.appendChild(label);
    } else if (typeof entry === "boolean") {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = entry;
      input.addEventListener("change", () => { value[key] = input.checked; layoutChanged(); });
      label.appendChild(input);
      label.appendChild(document.createTextNode(` ${layoutDisp(key)}`));
      container.appendChild(label);
    } else if (typeof entry === "string") {
      const label = document.createElement("label");
      label.textContent = `${layoutDisp(key)}：${entry}`;
      container.appendChild(label);
    } else if (Array.isArray(entry) && entry.every(item => typeof item === "number")) {
      const label = document.createElement("label");
      label.textContent = layoutDisp(key);
      const row = document.createElement("div");
      entry.forEach((number, index) => {
        const input = document.createElement("input");
        input.type = "number";
        input.value = String(number);
        input.title = index === 0 ? "x" : "y";
        input.addEventListener("change", () => {
          const next = boundedLayoutNumber(input);
          if (next === null) { input.value = String(number); return; }
          entry[index] = next;
          layoutChanged();
        });
        row.appendChild(input);
      });
      label.appendChild(row);
      container.appendChild(label);
    } else if (typeof entry === "object" && !Array.isArray(entry)) {
      const fieldset = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = layoutDisp(key);
      fieldset.appendChild(legend);
      buildLayoutFields(fieldset, root, entry);
      container.appendChild(fieldset);
    }
  }
}

function layoutChanged() {
  document.getElementById("l-status").textContent = "● 浏览器保存中";
  clearTimeout(layoutSaveTimer);
  layoutSaveTimer = setTimeout(saveLayoutNow, 300);
  drawLayoutCanvas();
  scheduleLayoutPreview();
}

async function saveLayoutNow() {
  clearTimeout(layoutSaveTimer);
  try {
    await draftStore.saveLayout({schema: 1, layouts: globalLayouts});
    document.getElementById("l-status").textContent = "已保存到当前浏览器";
    updateStorageStatus();
  } catch (error) {
    document.getElementById("l-status").textContent = `保存失败：${error.message}`;
  }
}

document.getElementById("l-btn-restore").addEventListener("click", async () => {
  if (!defaultLayouts || !confirm(`将「${layoutType}」全部框品布局还原为内置默认值，是否继续？`)) return;
  globalLayouts[layoutType] = defaultCurrentTypeLayouts();
  await draftStore.clearLayout();
  await saveLayoutNow();
  selectLayoutType(layoutType);
});

function scheduleLayoutPreview(delay = 300) {
  if (!document.getElementById("tab-layout").classList.contains("active")) return;
  clearTimeout(layoutPreviewTimer);
  layoutPreviewTimer = setTimeout(refreshLayoutPreview, delay);
}

function layoutSampleCard(type) {
  const card = {type, name: "布局样卡", level: 2, frame_variant: layoutVariant};
  if (type !== "式神") card.rarity = "SSR";
  return card;
}

async function refreshLayoutPreview() {
  if (!globalLayouts || !document.getElementById("tab-layout").classList.contains("active")) return;
  if (layoutRenderBusy) { layoutRenderQueued = true; return; }
  layoutRenderBusy = true;
  do {
    layoutRenderQueued = false;
    const seq = ++layoutRequestSeq;
    try {
      if (layoutType === "机制") {
        await Promise.all(["invocation", "skill", "seal"].map(frame => callWorker("render", {
          kind: "mechanism",
          mechanism: {name: "示例机制", frame,
            text: "[[唯一]]。\n己方回合开始时，获得1#ll和[[贯通]]。\n攻击后移除。",
            chars_per_line: 12},
          layouts: globalLayouts,
          target: `layout-mech-${frame}`,
          layout_seq: seq,
        })));
      } else if (layoutType === "对局式神") {
        await callWorker("render", {
          kind: "entity", card: layoutSampleCard("式神"),
          state: {level: 2, level_color: "yellow", frame_variant: layoutVariant,
            power: 2, health: 5, combat_power: 1, shield: -1, energy: 2,
            countdown: null, defeated_countdown: null, art_scale: 1},
          artwork: {offset_x: 0, offset_y: 0, scale: 1, rotate: 0},
          portrait: {frame: true}, artwork_path: "", width: null,
          layouts: globalLayouts, target: "layout-card", layout_seq: seq,
        });
      } else {
        await callWorker("render", {
          kind: "card", card: layoutSampleCard(layoutType),
          state: {}, artwork: {offset_x: 0, offset_y: 0, scale: 1, rotate: 0},
          portrait: {frame: true}, artwork_path: "", width: null,
          layouts: globalLayouts, target: "layout-card", layout_seq: seq,
        });
      }
    } catch (error) {
      if (seq === layoutRequestSeq) document.getElementById("l-status").textContent = `预览失败：${error.message}`;
    }
  } while (layoutRenderQueued);
  layoutRenderBusy = false;
}

document.getElementById("l-btn-preview").addEventListener("click", () => refreshLayoutPreview());

async function bitmapFromMessage(message) {
  return createImageBitmap(new Blob([message.png], {type: "image/png"}));
}

async function handleLayoutRender(message, target, seq) {
  if (seq !== layoutRequestSeq) return;
  if (target.startsWith("layout-mech-")) {
    const bitmap = await bitmapFromMessage(message);
    if (seq !== layoutRequestSeq) { bitmap.close(); return; }
    const canvas = document.getElementById(`l-mech-${message.info.kind === "mechanism" ? target.slice("layout-mech-".length) : ""}`);
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    context.drawImage(bitmap, 0, 0);
    const info = message.info;
    if ([info.text_x, info.text_top, info.text_width, info.text_height].every(Number.isFinite)) {
      context.strokeStyle = "#4f4";
      context.strokeRect(info.text_x + 0.5, info.text_top + 0.5, info.text_width, info.text_height);
    }
    bitmap.close();
    document.getElementById("l-status").textContent = "已使用浏览器本地布局";
    return;
  }
  const nextImage = await bitmapFromMessage(message);
  if (seq !== layoutRequestSeq) { nextImage.close(); return; }
  if (layoutPreviewImage) layoutPreviewImage.close();
  layoutPreviewImage = nextImage;
  layoutCropOrigin = message.info.crop_origin || [0, 0];
  const canvas = document.getElementById("l-preview");
  canvas.width = layoutPreviewImage.width;
  canvas.height = layoutPreviewImage.height;
  const scale = layoutType === "对局式神" ? 3 : 1;
  canvas.style.width = `${canvas.width * scale}px`;
  canvas.style.height = `${canvas.height * scale}px`;
  drawLayoutCanvas();
  document.getElementById("l-status").textContent = "已使用浏览器本地布局";
}

function handleLayoutError(message, seq) {
  if (seq === layoutRequestSeq) document.getElementById("l-status").textContent = `预览失败：${message.message}`;
}

function drawLayoutHandle(context, point, color, size = 5) {
  context.fillStyle = color;
  context.beginPath();
  context.arc(point[0], point[1], size, 0, Math.PI * 2);
  context.fill();
}

function drawLayoutCanvas() {
  const canvas = document.getElementById("l-preview");
  if (!layoutPreviewImage || !canvas.width || layoutType === "机制") return;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(layoutPreviewImage, 0, 0);
  context.save();
  context.translate(-layoutCropOrigin[0], -layoutCropOrigin[1]);
  const layout = currentLayout();
  for (const [name, element] of Object.entries(layout.elements || {})) {
    if (!Array.isArray(element.pos)) continue;
    const active = layoutSelection && JSON.stringify(layoutSelection.path) === JSON.stringify(["elements", name]);
    drawLayoutHandle(context, element.pos, active ? "#ff4" : "#4f4", 4);
    if (Array.isArray(element.num_offset)) {
      drawLayoutHandle(context, [element.pos[0] + element.num_offset[0], element.pos[1] + element.num_offset[1]], "#f8f", 4);
    }
  }
  const regions = layoutType === "对局式神" ? {art_window: layout.art_window} : layout.text_regions || {};
  for (const [name, region] of Object.entries(regions)) {
    if (!region || !Array.isArray(region.center)) continue;
    const active = layoutSelection && JSON.stringify(layoutSelection.path).includes(`"${name}"`);
    context.strokeStyle = active ? "#ff4" : "#4f4";
    context.strokeRect(region.center[0] - region.width / 2, region.center[1] - region.height / 2,
                       region.width, region.height);
    drawLayoutHandle(context, region.center, active ? "#ff4" : "#4f4", 5);
    if (Array.isArray(region.center_offset)) {
      drawLayoutHandle(context, [region.center[0] + region.center_offset[0], region.center[1] + region.center_offset[1]], "#f80", 4);
    }
  }
  context.restore();
}
