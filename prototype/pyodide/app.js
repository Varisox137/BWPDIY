"use strict";

const worker = new Worker("worker.js");
const logElement = document.getElementById("log");
const preview = document.getElementById("preview");
const resultMeta = document.getElementById("result-meta");
const downloadButton = document.getElementById("download");
const renderButtons = [...document.querySelectorAll(".render-button")];
const runAllButton = document.getElementById("run-all");
let requestSequence = 0;
let artworkBytes = null;
let artworkPath = "";
let currentBlobUrl = "";
let currentPng = null;
let renderCount = 0;
const pending = new Map();

function log(message, isError = false) {
  const line = document.createElement("span");
  line.textContent = `${new Date().toLocaleTimeString()}  ${message}\n`;
  if (isError) line.className = "error";
  logElement.appendChild(line);
  logElement.scrollTop = logElement.scrollHeight;
}

function setRendering(rendering) {
  for (const button of [...renderButtons, runAllButton]) button.disabled = rendering;
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
    const png = new Uint8Array(message.png);
    currentPng = new Blob([png], {type: "image/png"});
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

function basePayload(kind) {
  const widthValue = document.getElementById("width").value;
  return {
    kind,
    type: document.getElementById("card-type").value,
    name: document.getElementById("card-name").value,
    description: document.getElementById("description").value,
    width: widthValue ? Number(widthValue) : null,
    artwork_path: artworkPath,
  };
}

function renderPayload(kind) {
  if (kind === "mechanism") {
    return {
      kind,
      mechanism: {
        name: "灵咒",
        frame: "invocation",
        text: "[[唯一]]。\n己方回合开始时，获得1#ll和[[贯通]]。\n攻击后移除。",
        chars_per_line: 12,
      },
    };
  }
  const payload = basePayload(kind);
  if (kind === "entity" || kind === "portrait") payload.type = "式神";
  return payload;
}

async function render(kind) {
  setRendering(true);
  document.body.dataset.error = "";
  try {
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

runAllButton.addEventListener("click", async () => {
  setRendering(true);
  try {
    for (const kind of ["card", "entity", "portrait", "mechanism"]) {
      await callWorker("render", renderPayload(kind), artworkBytes);
    }
  } catch (error) {
    console.error(error);
  } finally {
    setRendering(false);
  }
});

document.getElementById("card-type").addEventListener("change", event => {
  const samples = {
    "式神": ["山风", "倒计时3：发起一次攻击，本次战斗获得不屈。"],
    "战斗": ["义道", "贯通，连击。对有破甲的式神造成双倍伤害。"],
    "法术": ["觉醒·山风", "觉醒：倒计时3：发起一次攻击，本次战斗免疫战斗伤害。你的牌对山风以外的未气绝己方式神造成的减少倒计时效果对山风造成等量效果。（山风气绝时有效）"],
    "形态": ["竹取物语", "每个回合结束时，随机召唤一个辉夜姬的幻境。若辉夜姬的幻境耐久>=20，每当辉夜姬受到伤害时，改为扣除辉夜姬幻境等量的耐久（最多降低5耐久）。"],
    "幻境": ["燕子安贝", "自己回合结束时，使所有己方角色各恢复1点生命，使所有其他己方幻境各获得1耐久。若此牌耐久>=10，敌方回合结束时，再触发上述效果一次。"],
    "协战": ["鸮羽共鸣", "选择使用一项：山风-庇羽；薰-鸮鸣"],
  };
  const [name, description] = samples[event.target.value];
  document.getElementById("card-name").value = name;
  document.getElementById("description").value = description;
});

document.getElementById("artwork").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) {
    artworkBytes = null;
    artworkPath = "";
    return;
  }
  const extension = file.name.split(".").pop().toLowerCase();
  if (!["png", "jpg", "jpeg", "webp"].includes(extension)) {
    log("仅支持 png/jpg/jpeg/webp 卡图", true);
    event.target.value = "";
    return;
  }
  artworkBytes = await file.arrayBuffer();
  artworkPath = `artwork.${extension}`;
  log(`已在浏览器读取 ${file.name}（${file.size} 字节），未上传服务器`);
});

downloadButton.addEventListener("click", () => {
  if (!currentPng) return;
  const anchor = document.createElement("a");
  const name = document.getElementById("card-name").value.trim() || "BWPDIY";
  anchor.href = currentBlobUrl;
  anchor.download = `${name.replace(/[<>:"/\\|?*]/g, "_")}.png`;
  anchor.click();
});

setRendering(true);
logElement.textContent = "";
callWorker("init").catch(error => log(error.message, true));
