"use strict";

const BWPDiyUI = (() => {
  function insertText(value, start, end, insertion) {
    const original = String(value ?? "");
    const text = String(insertion ?? "");
    let from = Number.isFinite(Number(start)) ? Math.trunc(Number(start)) : original.length;
    let to = Number.isFinite(Number(end)) ? Math.trunc(Number(end)) : from;
    from = Math.max(0, Math.min(original.length, from));
    to = Math.max(0, Math.min(original.length, to));
    if (to < from) [from, to] = [to, from];
    return {
      value: original.slice(0, from) + text + original.slice(to),
      cursor: from + text.length,
    };
  }

  function pngFilename(name) {
    const base = String(name ?? "").trim().replace(/[<>:"/\\|?*]/g, "_") || "BWPDIY";
    return `${base}.png`;
  }

  function isEmbeddedBrowser(userAgent) {
    return /(MicroMessenger|MQQBrowser|QQBrowser|QQ\/|Weibo|AlipayClient|UCBrowser|Quark|baiduboxapp)/i
      .test(String(userAgent || ""));
  }

  function missingCharacters(value, coverage) {
    if (!coverage) return [];
    const supported = typeof coverage === "string" ? new Set(coverage) : coverage;
    const missing = [];
    for (const character of String(value ?? "")) {
      if (!/\s/.test(character) && !supported.has(character) && !missing.includes(character)) {
        missing.push(character);
        if (missing.length === 12) break;
      }
    }
    return missing;
  }

  function precisionStep(key, fine) {
    if (key === "scale") return fine ? 0.01 : 0.05;
    if (key === "rotate") return fine ? 0.1 : 1;
    return fine ? 1 : 5;
  }

  function stepNumeric(value, key, direction, fine) {
    const current = Number.isFinite(Number(value)) ? Number(value) : (key === "scale" ? 1 : 0);
    const step = precisionStep(key, fine) * (Number(direction) < 0 ? -1 : 1);
    const digits = key === "scale" ? 3 : key === "rotate" ? 1 : 0;
    const result = Number((current + step).toFixed(digits));
    return key === "scale" ? Math.max(0.01, result) : result;
  }

  return Object.freeze({insertText, pngFilename, isEmbeddedBrowser, missingCharacters,
    precisionStep, stepNumeric});
})();

if (typeof module !== "undefined" && module.exports) module.exports = BWPDiyUI;
