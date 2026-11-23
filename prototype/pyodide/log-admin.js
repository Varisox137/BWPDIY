"use strict";

const tokenInput = document.getElementById("token");
const connectButton = document.getElementById("connect");
const logList = document.getElementById("logs");
const downloadButton = document.getElementById("download");
const status = document.getElementById("status");
const previewElement = document.getElementById("preview");
const previewNote = document.getElementById("preview-note");
let selectedLog = "";
let previewGeneration = 0;

function validName(name) {
  return typeof name === "string" && /^bwpdiy-[A-Za-z0-9-]+\.log$/.test(name);
}

async function api(path) {
  const response = await fetch(path, {
    headers: {Authorization: `Bearer ${tokenInput.value.trim()}`},
    cache: "no-store",
  });
  if (response.status === 401) throw new Error("提取码无效或已轮换");
  if (!response.ok) throw new Error(`服务器返回 HTTP ${response.status}`);
  return response;
}

function formatSize(bytes) {
  return Number.isFinite(bytes) && bytes >= 0 ? `${(bytes / 1024).toFixed(1)} KiB` : "未知大小";
}

async function preview(name) {
  if (!validName(name)) return;
  const generation = ++previewGeneration;
  selectedLog = name;
  downloadButton.disabled = false;
  previewElement.textContent = "正在读取预览…";
  previewNote.textContent = "";
  try {
    const response = await api(`/api/log-admin/logs/${encodeURIComponent(name)}/preview`);
    const payload = await response.json();
    if (generation !== previewGeneration) return;
    if (typeof payload.text !== "string" || typeof payload.truncated !== "boolean") {
      throw new Error("预览响应格式无效");
    }
    previewElement.textContent = payload.text || "（空日志）";
    previewNote.textContent = payload.truncated ? "（仅显示开头 512 KiB）" : "";
    status.textContent = `已选择 ${name}`;
  } catch (error) {
    if (generation !== previewGeneration) return;
    previewElement.textContent = "预览失败";
    status.textContent = error.message;
  }
}

async function refresh() {
  if (!tokenInput.value.trim()) {
    status.textContent = "请输入提取码";
    return;
  }
  connectButton.disabled = true;
  status.textContent = "正在读取日志列表…";
  try {
    const response = await api("/api/log-admin/logs");
    const payload = await response.json();
    if (!Array.isArray(payload.logs)) throw new Error("日志列表响应格式无效");
    const logs = payload.logs.filter(item => item && validName(item.name));
    logList.textContent = "";
    for (const item of logs) {
      const option = document.createElement("option");
      option.value = item.name;
      option.textContent = `${item.current ? "● " : ""}${item.name}（${formatSize(item.size)}）`;
      logList.appendChild(option);
    }
    logList.disabled = logs.length === 0;
    downloadButton.disabled = logs.length === 0;
    const next = logs.find(item => item.name === selectedLog) ||
      logs.find(item => item.current) || logs[0];
    if (next) {
      logList.value = next.name;
      await preview(next.name);
    } else {
      selectedLog = "";
      previewElement.textContent = "没有可查看的日志";
      previewNote.textContent = "";
      status.textContent = "日志列表为空";
    }
  } catch (error) {
    status.textContent = `连接失败：${error.message}`;
    logList.disabled = true;
    downloadButton.disabled = true;
  } finally {
    connectButton.disabled = false;
  }
}

connectButton.addEventListener("click", refresh);
tokenInput.addEventListener("keydown", event => { if (event.key === "Enter") refresh(); });
logList.addEventListener("change", () => preview(logList.value));
downloadButton.addEventListener("click", async () => {
  if (!validName(selectedLog)) return;
  downloadButton.disabled = true;
  status.textContent = `正在下载 ${selectedLog}…`;
  try {
    const response = await api(`/api/log-admin/logs/${encodeURIComponent(selectedLog)}/download`);
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = selectedLog;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = `已下载 ${selectedLog}`;
  } catch (error) {
    status.textContent = `下载失败：${error.message}`;
  } finally {
    downloadButton.disabled = false;
  }
});
