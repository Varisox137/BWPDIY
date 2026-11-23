"use strict";

const PYODIDE_VERSION = "0.28.3";
const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const MAX_ARTWORK_BYTES = 64 * 1024 * 1024;
const ARTWORK_PATH = /^artwork\.(?:png|jpe?g|webp)$/;
let pyodide = null;
let renderPython = null;
let readyPromise = null;

function postStatus(message) {
  self.postMessage({type: "status", message});
}

async function fetchRequired(url, attempts = 3) {
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response;
    } catch (error) {
      lastError = error;
      if (attempt < attempts) {
        postStatus(`${url} 下载失败，正在重试 ${attempt + 1}/${attempts}…`);
        await new Promise(resolve => setTimeout(resolve, 750 * attempt));
      }
    }
  }
  throw lastError;
}

async function initialize() {
  const started = performance.now();
  postStatus(`加载 Pyodide ${PYODIDE_VERSION}…`);
  importScripts(`${PYODIDE_BASE}pyodide.js`);
  pyodide = await loadPyodide({
    indexURL: PYODIDE_BASE,
    stdout: message => postStatus(`Python: ${message}`),
    stderr: message => postStatus(`Python 错误: ${message}`),
  });

  postStatus("加载浏览器版 Pillow…");
  await pyodide.loadPackage("Pillow");

  postStatus("下载并展开 BWPDIY 渲染核心与真实美术资源…");
  const response = await fetchRequired("runtime.zip");
  const runtimeBytes = new Uint8Array(await response.arrayBuffer());
  pyodide.FS.mkdirTree("/work");
  pyodide.FS.writeFile("/tmp/bwpdiy-runtime.zip", runtimeBytes);
  pyodide.runPython(`
import sys
import zipfile
with zipfile.ZipFile('/tmp/bwpdiy-runtime.zip') as archive:
    archive.extractall('/work')
sys.path.insert(0, '/work')
`);
  pyodide.FS.unlink("/tmp/bwpdiy-runtime.zip");

  const bridgeResponse = await fetchRequired("bridge.py");
  await pyodide.runPythonAsync(await bridgeResponse.text());
  renderPython = pyodide.globals.get("browser_render");
  const environment = JSON.parse(pyodide.globals.get("environment_info")());
  postStatus(`就绪：Python ${environment.python} / Pillow ${environment.pillow} / BWPDIY ${environment.bwpdiy}`);
  postStatus(`真实字体：${environment.fonts.join("、")}`);
  return {
    environment,
    layouts: JSON.parse(pyodide.globals.get("browser_layouts")()),
    runtime_bytes: runtimeBytes.length,
    startup_ms: Math.round(performance.now() - started),
  };
}

function ensureReady() {
  if (!readyPromise) readyPromise = initialize();
  return readyPromise;
}

function asBytes(result) {
  if (result instanceof Uint8Array) return result;
  if (result && typeof result.toJs === "function") return result.toJs();
  throw new Error("Python 渲染结果不是 PNG 字节");
}

self.onmessage = async event => {
  const message = event.data;
  try {
    if (message.type === "init") {
      const info = await ensureReady();
      self.postMessage({type: "ready", id: message.id, info});
      return;
    }
    if (message.type !== "render") return;
    if (message.artwork) {
      if (!ARTWORK_PATH.test(message.payload && message.payload.artwork_path)) {
        throw new Error("卡图路径非法");
      }
      if (!message.artwork.byteLength || message.artwork.byteLength > MAX_ARTWORK_BYTES) {
        throw new Error("卡图文件过大或为空");
      }
    }
    await ensureReady();
    if (message.artwork) {
      pyodide.FS.writeFile(`/work/user/${message.payload.artwork_path}`,
                           new Uint8Array(message.artwork));
    }
    const started = performance.now();
    let result;
    try {
      result = renderPython(JSON.stringify(message.payload));
      const png = new Uint8Array(asBytes(result));
      const info = JSON.parse(pyodide.globals.get("last_render_info"));
      info.total_ms = Math.round(performance.now() - started);
      self.postMessage({type: "result", id: message.id, info, png: png.buffer},
                       [png.buffer]);
    } finally {
      if (result && typeof result.destroy === "function") result.destroy();
    }
  } catch (error) {
    const pythonError = pyodide ? pyodide.globals.get("last_render_error") : "";
    self.postMessage({
      type: "error",
      id: message.id,
      message: String(error && error.message ? error.message : error),
      detail: pythonError || "",
    });
  }
};
