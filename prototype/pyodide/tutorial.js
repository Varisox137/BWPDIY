"use strict";

let tutorialMode = false;
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
    selector: '[data-card="name"]', title: "先写卡牌内容",
    text: "已填入一张真实范例卡。你可以修改卡名和描述；右侧内容会自动合成到中央预览中。",
  },
  {
    selector: "#artwork", title: "选择一张卡图",
    text: "点击这里选择本地 PNG/JPEG/WebP 图片。也可以直接使用内置样图继续；文件只在本机浏览器读取。",
  },
  {
    selector: "#c-preview", title: "让构图更合适",
    text: "在卡图上拖拽移动，滚轮缩放；手机单指移动、双指缩放/旋转。也可以在右侧输入精确数值。",
  },
  {
    selector: '[data-card="description"]', title: "标记关键字",
    text: "范例中的「不屈」已用双方括号标为 [[不屈]]，预览会显示异色。也可输入 #ll 插入力量小图标。",
  },
  {
    selector: "#c-actions .download-button", title: "导出你的成品",
    text: "预览满意后，点击「导出当前图片」下载真正的 PNG 文件。",
  },
];

function markTutorialSeen() {
  try { localStorage.setItem("bwpdiy-tutorial-v1", "done"); } catch (error) {}
}

function tutorialAlreadySeen() {
  try { return localStorage.getItem("bwpdiy-tutorial-v1") === "done"; }
  catch (error) { return false; }
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

async function startTutorial() {
  if (tutorialMode) return;
  tutorialBackup = currentDraft();
  tutorialMode = true;
  tutorialFinished = false;
  tutorialStep = 0;
  if (tutorialWelcome.open) tutorialWelcome.close();
  if (helpModal.open) helpModal.close();
  showMainTab("cards");
  showTab("card");
  setGroup("[data-card]", {type: "式神"});
  applyCardSample("式神");
  artworkBytes = null;
  artworkPath = "";
  artworkName = "";
  updateArtworkLabel();
  updateTypeFields();
  scheduleNormalPreview("card", 0);
  tutorialCoach.hidden = false;
  renderTutorialStep();
}

async function restoreTutorialBackup() {
  const backup = tutorialBackup;
  if (backup) await restoreDraft(backup);
  tutorialBackup = null;
  tutorialMode = false;
  tutorialFinished = false;
  tutorialCoach.hidden = true;
  tutorialHighlight.hidden = true;
}

function finishTutorial() {
  tutorialFinished = true;
  document.getElementById("tutorial-progress").textContent = "第一张卡 · 已完成";
  document.getElementById("tutorial-title").textContent = "已经得到一张 PNG 卡图";
  document.getElementById("tutorial-text").textContent = "可以保留这张作品作为当前草稿，或恢复进入教程前的内容。以后可在「使用说明」中重新打开教程。";
  tutorialHighlight.hidden = true;
  tutorialBack.hidden = true;
  tutorialNext.hidden = false;
  tutorialNext.textContent = "保留作品并完成";
  tutorialExit.textContent = "恢复原草稿";
  document.querySelector("#c-actions .download-button").scrollIntoView({block: "center", behavior: "smooth"});
}

function keepTutorialResult() {
  markTutorialSeen();
  tutorialFinished = false;
  tutorialMode = false;
  tutorialBackup = null;
  tutorialCoach.hidden = true;
  tutorialHighlight.hidden = true;
  saveDraftNow();
}

function initializeTutorial() {
  if (tutorialInitialized) return;
  tutorialInitialized = true;
  document.getElementById("tutorial-start").addEventListener("click", startTutorial);
  document.getElementById("tutorial-skip").addEventListener("click", () => {
    tutorialWelcome.close();
    markTutorialSeen();
  });
  document.getElementById("help-start-tutorial").addEventListener("click", startTutorial);
  tutorialBack.addEventListener("click", () => {
    if (tutorialStep > 0) { tutorialStep -= 1; renderTutorialStep(); }
  });
  tutorialNext.addEventListener("click", () => {
    if (tutorialFinished) { keepTutorialResult(); return; }
    if (tutorialStep === 2) {
      const description = document.querySelector('[data-card="description"]');
      if (!description.value.includes("[[")) {
        description.value = description.value.replace("不屈", "[[不屈]]");
        scheduleNormalPreview("card", 0);
      }
    }
    if (tutorialStep < TUTORIAL_STEPS.length - 1) {
      tutorialStep += 1;
      renderTutorialStep();
    }
  });
  tutorialExit.addEventListener("click", restoreTutorialBackup);
  document.querySelector("#c-actions .download-button").addEventListener("click", () => {
    if (tutorialMode && tutorialStep === TUTORIAL_STEPS.length - 1) finishTutorial();
  });
  window.addEventListener("resize", scheduleTutorialHighlight);
  window.addEventListener("scroll", scheduleTutorialHighlight, true);
  if (!tutorialAlreadySeen()) tutorialWelcome.showModal();
}
