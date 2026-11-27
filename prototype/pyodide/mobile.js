"use strict";

const BWPDiyMobile = (() => {
  let gestureLocked = false;
  try { gestureLocked = localStorage.getItem("bwpdiy-gesture-lock") === "1"; } catch (error) {}

  function setPreviewCollapsed(panel, collapsed) {
    panel.classList.toggle("preview-collapsed", collapsed);
    const button = document.querySelector(`.preview-toggle[data-preview="${panel.id}"]`);
    if (button) {
      button.setAttribute("aria-expanded", String(!collapsed));
      button.textContent = collapsed ? "展开预览" : "收起预览";
    }
  }

  function exitFullscreen() {
    for (const panel of document.querySelectorAll(".preview-fullscreen")) {
      panel.classList.remove("preview-fullscreen");
    }
    document.body.classList.remove("preview-modal-open");
    document.querySelectorAll(".preview-fullscreen-button").forEach(button => {
      button.setAttribute("aria-pressed", "false");
      button.textContent = "全屏预览";
    });
  }

  function initializeFullscreen() {
    document.querySelectorAll(".preview-fullscreen-button").forEach(button => {
      button.addEventListener("click", () => {
        const panel = document.getElementById(button.dataset.preview);
        const opening = !panel.classList.contains("preview-fullscreen");
        exitFullscreen();
        if (opening) {
          setPreviewCollapsed(panel, false);
          panel.classList.add("preview-fullscreen");
          document.body.classList.add("preview-modal-open");
          button.setAttribute("aria-pressed", "true");
          button.textContent = "退出全屏";
        }
      });
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") exitFullscreen();
    });
    document.querySelectorAll(".navtab").forEach(button => button.addEventListener("click", exitFullscreen));
  }

  function initializeGestureLock() {
    const button = document.getElementById("gesture-lock");
    const update = () => {
      button.setAttribute("aria-pressed", String(gestureLocked));
      button.textContent = gestureLocked ? "解锁卡图手势" : "锁定卡图手势";
      document.body.dataset.gestureLocked = String(gestureLocked);
    };
    button.addEventListener("click", () => {
      gestureLocked = !gestureLocked;
      try { localStorage.setItem("bwpdiy-gesture-lock", gestureLocked ? "1" : "0"); } catch (error) {}
      update();
    });
    update();
  }

  function initializePrecisionControls() {
    const fineInput = document.getElementById("fine-adjustment");
    const controls = [...document.querySelectorAll("[data-art], [data-portrait]")];
    const updateSteps = () => {
      for (const input of controls) {
        const key = input.dataset.art || input.dataset.portrait;
        input.step = String(BWPDiyUI.precisionStep(key, fineInput.checked));
      }
    };
    fineInput.addEventListener("change", updateSteps);
    updateSteps();
    for (const input of controls) {
      const key = input.dataset.art || input.dataset.portrait;
      const group = document.createElement("span");
      group.className = "precision-stepper";
      for (const [direction, label] of [[-1, "−"], [1, "+"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "precision-button";
        button.textContent = label;
        button.setAttribute("aria-label", `${label === "+" ? "增加" : "减少"}${input.closest("label").childNodes[0].textContent.trim()}`);
        let delayTimer = null;
        let repeatTimer = null;
        const stop = () => {
          clearTimeout(delayTimer);
          clearInterval(repeatTimer);
          delayTimer = null;
          repeatTimer = null;
        };
        const adjust = () => {
          input.value = String(BWPDiyUI.stepNumeric(input.value, key, direction, fineInput.checked));
          input.dispatchEvent(new Event("input", {bubbles: true}));
          input.dispatchEvent(new Event("change", {bubbles: true}));
        };
        button.addEventListener("pointerdown", event => {
          if (event.button !== 0) return;
          event.preventDefault();
          stop();
          adjust();
          delayTimer = setTimeout(() => { repeatTimer = setInterval(adjust, 80); }, 350);
        });
        button.addEventListener("click", event => { if (event.detail === 0) adjust(); });
        button.addEventListener("pointerup", stop);
        button.addEventListener("pointercancel", stop);
        button.addEventListener("pointerleave", stop);
        window.addEventListener("pointerup", stop);
        group.appendChild(button);
      }
      input.insertAdjacentElement("afterend", group);
      input.closest("label").classList.add("precision-label");
    }
  }

  function initializeKeyboardAvoidance() {
    if (!window.visualViewport) return;
    const viewport = window.visualViewport;
    let baseline = viewport.height;
    let keyboardOpen = false;
    let autoCollapsed = null;
    let focused = null;
    document.addEventListener("focusin", event => {
      if (!event.target.matches("input:not([type=checkbox]), textarea, select")) return;
      focused = event.target;
      baseline = Math.max(viewport.height, baseline);
    });
    document.addEventListener("focusout", () => { focused = null; });
    viewport.addEventListener("resize", () => {
      if (!matchMedia("(max-width: 760px)").matches) return;
      const active = document.activeElement;
      if (active && active.matches("input:not([type=checkbox]), textarea, select")) focused = active;
      const open = focused && baseline - viewport.height > 120;
      if (open && !keyboardOpen) {
        keyboardOpen = true;
        exitFullscreen();
        const panel = document.querySelector(".tabpage.active #c-mid, .tabpage.active #b-mid");
        if (panel && !panel.classList.contains("preview-collapsed")) {
          autoCollapsed = panel;
          setPreviewCollapsed(panel, true);
        }
        setTimeout(() => focused && focused.scrollIntoView({block: "center", behavior: "smooth"}), 80);
      } else if (!open && keyboardOpen && viewport.height >= baseline - 40) {
        keyboardOpen = false;
        if (autoCollapsed) setPreviewCollapsed(autoCollapsed, false);
        autoCollapsed = null;
        focused = null;
      }
      if (!focused) baseline = Math.max(baseline, viewport.height);
    });
  }

  function initialize() {
    initializeFullscreen();
    initializeGestureLock();
    initializePrecisionControls();
    initializeKeyboardAvoidance();
  }

  return Object.freeze({initialize, exitFullscreen, gesturesLocked: () => gestureLocked});
})();
