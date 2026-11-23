"use strict";

let tutorialBackup = null;
let tutorialStep = 0;
let tutorialFinished = false;
let tutorialInitialized = false;
let tutorialFrame = 0;

const tutorialWelcome = document.getElementById("tutorial-welcome");
const tutorialCoach = document.getElementById("tutorial-coach");
const tutorialHighlight = document.getElementById("tutorial-highlight");
const tutorialBack = document.getElementById("tutorial-back");
const tutorialNext = document.getElementById("tutorial-next");
const tutorialExit = document.getElementById("tutorial-exit");
const TUTORIAL_STEPS = [
  {
    selector: "#c-card-name", title: "先写卡牌内容",
    text: "已填入山风样卡。修改卡名和描述，右侧内容会自动合成到中央预览中。",
  },
  {
    selector: "#c-upload-art", title: "认识卡图",
    text: "教程使用内置样图，不会上传文件。正式制作时，点击这里可选择本地 PNG/JPEG/WebP 卡图。",
  },
  {
    selector: "#c-preview", title: "让构图更合适",
    text: "在中央卡图上左键拖拽移动、滚轮缩放，按住右键并滚轮旋转；也可用右侧数值框精确调整。",
  },
  {
    selector: "#c-card-description", title: "标记关键字",
    text: "描述中的 [[不屈]] 会在预览里异色高亮。你也可以修改双方括号中的关键字，或输入 #ll 插入力量小图标。",
  },
  {
    selector: "#c-export-card", title: "导出你的成品",
    text: "点击金色「导出卡图」，确认文件名并成功下载 PNG 后，教程才会完成。",
  },
];

function markTutorialSeen() {
  try { localStorage.setItem("bwpdiy-desktop-tutorial-v1", "done"); } catch (error) {}
}

function tutorialAlreadySeen() {
  try { return localStorage.getItem("bwpdiy-desktop-tutorial-v1") === "done"; }
  catch (error) { return false; }
}

function tutorialWelcomeOpen() { return tutorialWelcome.style.display === "block"; }

function setTutorialChrome(on) {
  for (const id of ["c-left", "update-banner"]) {
    const element = document.getElementById(id);
    if (element) element.inert = on;
  }
  document.querySelectorAll(".navtab, #app-shutdown, #ext-options").forEach(element => {
    element.inert = on;
  });
}

function updateTutorialHighlight() {
  tutorialFrame = 0;
  if (!tutorialMode || tutorialFinished) return;
  const step = TUTORIAL_STEPS[tutorialStep];
  const target = document.querySelector(step.selector);
  if (!target || target.hidden || !target.getClientRects().length) {
    tutorialHighlight.hidden = true;
    return;
  }
  const rect = target.getBoundingClientRect();
  const padding = 5;
  tutorialHighlight.hidden = false;
  tutorialHighlight.style.left = `${Math.max(0, rect.left - padding)}px`;
  tutorialHighlight.style.top = `${Math.max(0, rect.top - padding)}px`;
  tutorialHighlight.style.width = `${Math.min(innerWidth, rect.width + padding * 2)}px`;
  tutorialHighlight.style.height = `${Math.min(innerHeight, rect.height + padding * 2)}px`;
}

function scheduleTutorialHighlight() {
  if (!tutorialFrame) tutorialFrame = requestAnimationFrame(updateTutorialHighlight);
}

function renderTutorialStep() {
  const step = TUTORIAL_STEPS[tutorialStep];
  document.getElementById("tutorial-progress").textContent = `第一张卡 · ${tutorialStep + 1}/${TUTORIAL_STEPS.length}`;
  document.getElementById("tutorial-title").textContent = step.title;
  document.getElementById("tutorial-text").textContent = step.text;
  tutorialBack.hidden = tutorialStep === 0;
  tutorialNext.hidden = tutorialStep === TUTORIAL_STEPS.length - 1;
  tutorialNext.textContent = "下一步";
  tutorialExit.textContent = "退出教程";
  const target = document.querySelector(step.selector);
  if (target) target.scrollIntoView({block: "center", behavior: "smooth"});
  setTimeout(scheduleTutorialHighlight, 180);
  scheduleTutorialHighlight();
}

async function tutorialPreviewBody() {
  await ensureLayouts();
  return {
    type: formData.type,
    card: formData,
    layout: layoutForRender(globalTypeLayout(formData.type, formData.frame_variant ?? "norm")),
  };
}

async function startTutorial() {
  if (tutorialMode || (typeof activeAsk !== "undefined" && activeAsk) ||
      (typeof storageBusy === "function" && storageBusy())) return;
  tutorialBackup = {
    cardData: deepCopy(cardData), formData: deepCopy(formData), cDirty, contentRev,
    undoStack: deepCopy(undoStack), prevFormSnap: deepCopy(prevFormSnap), lastEditAt,
    curMech, mechData: deepCopy(mechData), mechForm: deepCopy(mechForm), mDirty,
  };
  tutorialMode = true;
  tutorialFinished = false;
  tutorialStep = 0;
  setTutorialChrome(true);
  tutorialWelcome.style.display = "none";
  document.getElementById("help-modal").style.display = "none";
  document.getElementById("changelog-modal").style.display = "none";
  selectSeq++;
  clearTimeout(cPreviewTimer);
  clearTimeout(cPortraitTimer);
  cPreviewTimer = cPortraitTimer = null;
  for (const channel of ["art", "portrait"]) {
    if (mousePreviewFrames[channel]) cancelAnimationFrame(mousePreviewFrames[channel]);
    mousePreviewFrames[channel] = 0;
  }
  cPreviewSeq++;
  cPreviewAppliedSeq = cPreviewSeq;
  curMech = null;
  mechData = null;
  mechForm = null;
  mDirty = false;
  try {
    const response = await fetch("/api/samples");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const sampleData = await response.json();
    const sample = deepCopy(sampleData["式神"]);
    sample.artwork = {images: [{path: "sample_art.png"}]};
    cardData = deepCopy(sample);
    formData = sample;
    cDirty = false;
    resetUndo();
    buildForm();
    cPreviewPortrait(true);
    await cPreviewForm(false);
  } catch (error) {
    await restoreTutorialBackup();
    cStatusEl.textContent = `教程样卡读取失败：${error}`;
    return;
  }
  cStatusEl.textContent = "教程沙盒：修改仅保留在内存，不会写盘";
  tutorialCoach.hidden = false;
  renderTutorialStep();
}

async function restoreTutorialBackup() {
  const backup = tutorialBackup;
  if (!backup) return;
  tutorialMode = false;
  tutorialFinished = false;
  tutorialCoach.hidden = true;
  tutorialHighlight.hidden = true;
  tutorialWelcome.style.display = "none";
  setTutorialChrome(false);
  selectSeq++;
  clearTimeout(cPreviewTimer);
  clearTimeout(cPortraitTimer);
  cPreviewTimer = cPortraitTimer = null;
  for (const channel of ["art", "portrait"]) {
    if (mousePreviewFrames[channel]) cancelAnimationFrame(mousePreviewFrames[channel]);
    mousePreviewFrames[channel] = 0;
  }
  cPreviewSeq++;
  cPreviewAppliedSeq = cPreviewSeq;
  cPortraitSeq++;
  cPortraitAppliedSeq = cPortraitSeq;
  cardData = deepCopy(backup.cardData);
  formData = deepCopy(backup.formData);
  cDirty = backup.cDirty;
  contentRev = backup.contentRev;
  undoStack = deepCopy(backup.undoStack);
  prevFormSnap = deepCopy(backup.prevFormSnap);
  lastEditAt = backup.lastEditAt;
  curMech = backup.curMech;
  mechData = deepCopy(backup.mechData);
  mechForm = deepCopy(backup.mechForm);
  mDirty = backup.mDirty;
  tutorialBackup = null;
  cStatusEl.textContent = "";
  if (curMech) {
    buildMechForm();
    await mechPreview(!!mDirty);
  } else {
    buildForm();
    if (formData) {
      if (cDirty) await cPreviewForm(false);
      else await cPreviewProject();
    } else {
      cPreviewImg.removeAttribute("src");
      cPreviewPortrait(true);
    }
  }
}

function finishTutorial() {
  markTutorialSeen();
  tutorialFinished = true;
  document.getElementById("tutorial-progress").textContent = "第一张卡 · 已完成";
  document.getElementById("tutorial-title").textContent = "已经得到一张 PNG 卡图";
  document.getElementById("tutorial-text").textContent = "教程内容没有写入你的卡牌库。点击「完成并返回」恢复进入教程前的内容；以后可在「使用说明」中重新打开教程。";
  tutorialHighlight.hidden = true;
  tutorialBack.hidden = true;
  tutorialNext.hidden = false;
  tutorialNext.textContent = "完成并返回";
  tutorialExit.textContent = "退出教程";
}

function tutorialExportSucceeded() {
  if (!tutorialMode || tutorialFinished || tutorialStep !== TUTORIAL_STEPS.length - 1) return;
  finishTutorial();
}

function initializeTutorial() {
  if (tutorialInitialized) return;
  tutorialInitialized = true;
  document.getElementById("tutorial-start").addEventListener("click", startTutorial);
  document.getElementById("tutorial-skip").addEventListener("click", () => {
    tutorialWelcome.style.display = "none";
    markTutorialSeen();
  });
  document.getElementById("help-start-tutorial").addEventListener("click", startTutorial);
  tutorialBack.addEventListener("click", () => {
    if (tutorialStep > 0) {
      tutorialStep -= 1;
      renderTutorialStep();
    }
  });
  tutorialNext.addEventListener("click", () => {
    if (tutorialFinished) {
      restoreTutorialBackup();
      return;
    }
    if (tutorialStep === 2 && !String(formData.description || "").includes("[[")) {
      const description = document.getElementById("c-card-description");
      const marked = String(formData.description || "").replace("不屈", "[[不屈]]");
      if (marked !== formData.description) {
        formData.description = marked;
        description.value = marked;
        afterEdit();
      }
    }
    if (tutorialStep < TUTORIAL_STEPS.length - 1) {
      tutorialStep += 1;
      renderTutorialStep();
    }
  });
  tutorialExit.addEventListener("click", restoreTutorialBackup);
  window.addEventListener("resize", scheduleTutorialHighlight);
  window.addEventListener("scroll", scheduleTutorialHighlight, true);
  let hasBootHistory = false;
  try { hasBootHistory = !!localStorage.getItem("bwpdiy_boot_id"); } catch (error) {}
  if (!tutorialAlreadySeen() && !hasBootHistory) tutorialWelcome.style.display = "block";
}
