/**
 * Font subsystem: installed-font probing, Local Font Access authorization,
 * font-file import (FontFace + IndexedDB persistence), and alias resolution.
 *
 * Design notes:
 * - Canvas width probing works everywhere and needs no permission. It covers a
 *   curated list of 200+ Windows families; anything outside that list requires
 *   the Local Font Access API.
 * - The Local Font Access API (Chromium) requires transient user activation, so
 *   it must be invoked from a click handler. We never call it on page load;
 *   the UI entry point lives in Settings > Font.
 */

/* ------------------------------------------------------------------ */
/* Installed font probing (canvas fallback)                           */
/* ------------------------------------------------------------------ */

/** Curated list of font families commonly shipped with Windows. */
export const FONT_CANDIDATES = [
  "Agency FB", "Algerian", "Arial", "Arial Rounded MT Bold", "Bahnschrift", "Baskerville Old Face",
  "Bauhaus 93", "Bell MT", "Berlin Sans FB", "Berlin Sans FB Demi", "Bernard MT Condensed", "Blackadder ITC",
  "Bodoni MT", "Book Antiqua", "Bookman Old Style", "Bradley Hand ITC", "Britannic Bold", "Broadway",
  "Brush Script MT", "Calibri", "Californian FB", "Calisto MT", "Cambria", "Candara",
  "Cascadia Code", "Cascadia Mono", "Castellar", "Centaur", "Century", "Century Gothic",
  "Century Schoolbook", "Chiller", "Colonna MT", "Comic Sans MS", "Consolas", "Constantia",
  "Cooper Black", "Copperplate Gothic Bold", "Copperplate Gothic Light", "Corbel", "Courier New", "Curlz MT",
  "DengXian", "Dubai", "Ebrima", "Edwardian Script ITC", "Elephant", "Engravers MT",
  "Eras Bold ITC", "Eras Demi ITC", "Eras Light ITC", "Eras Medium ITC", "FangSong", "Felix Titling",
  "Footlight MT Light", "Forte", "Franklin Gothic Book", "Franklin Gothic Demi", "Franklin Gothic Demi Cond", "Franklin Gothic Heavy",
  "Franklin Gothic Medium", "Franklin Gothic Medium Cond", "Freestyle Script", "French Script MT", "FZShuTi", "FZYaoTi",
  "Gabriola", "Gadugi", "Garamond", "Georgia", "Gigi", "Gill Sans MT",
  "Gill Sans MT Condensed", "Gill Sans MT Ext Condensed Bold", "Gill Sans Ultra Bold", "Gill Sans Ultra Bold Condensed", "Gloucester MT Extra Condensed", "Goudy Old Style",
  "Goudy Stout", "Haettenschweiler", "Harlow Solid Italic", "Harrington", "High Tower Text", "Hiragino Sans GB",
  "HuaWenXingKai", "HYZhongHei", "Impact", "Imprint MT Shadow", "Informal Roman", "Ink Free",
  "Javanese Text", "Jokerman", "Juice ITC", "KaiTi", "Kristen ITC", "Kunstler Script",
  "Leelawadee UI", "Lingoes Unicode", "LiSu", "Lucida Bright", "Lucida Calligraphy", "Lucida Console",
  "Lucida Fax", "Lucida Handwriting", "Lucida Sans", "Lucida Sans Typewriter", "Lucida Sans Unicode", "Magneto",
  "Maiandra GD", "Malgun Gothic", "Marlett", "Matura MT Script Capitals", "Microsoft Himalaya", "Microsoft JhengHei",
  "Microsoft New Tai Lue", "Microsoft PhagsPa", "Microsoft Sans Serif", "Microsoft Tai Le", "Microsoft YaHei", "Microsoft YaHei UI",
  "Microsoft Yi Baiti", "MingLiU-ExtB", "Mistral", "Modern No. 20", "Mongolian Baiti", "Monotype Corsiva",
  "MS Gothic", "MS Outlook", "MS Reference Sans Serif", "MS Reference Specialty", "MT Extra", "MV Boli",
  "Myanmar Text", "Niagara Engraved", "Niagara Solid", "Nirmala UI", "Noto Sans SC", "Noto Serif SC",
  "OCR A Extended", "Old English Text MT", "Onyx", "Palace Script MT", "Palatino Linotype", "Papyrus",
  "Parchment", "Perpetua", "Perpetua Titling MT", "PingFang SC", "Playbill", "Poor Richard",
  "Pristina", "Rage Italic", "Ravie", "Rockwell", "Rockwell Condensed", "Rockwell Extra Bold",
  "Sans Serif Collection", "Script MT Bold", "Segoe MDL2 Assets", "Segoe Print", "Segoe Script", "Segoe UI",
  "Segoe UI Emoji", "Segoe UI Historic", "Segoe UI Variable", "Showcard Gothic", "SimHei", "SimSun",
  "SimSun-ExtB", "SimSun-ExtG", "Sitka", "Snap ITC", "Source Han Sans SC", "Source Han Serif SC",
  "STCaiyun", "Stencil", "STFangsong", "STHupo", "STKaiti", "STLiti",
  "STSong", "STXihei", "STXIHEI", "STXingkai", "STXinwei", "STZhongsong",
  "Sylfaen", "Tahoma", "Tempus Sans ITC", "Times New Roman", "Trebuchet MS", "Tw Cen MT",
  "Tw Cen MT Condensed", "Tw Cen MT Condensed Extra Bold", "Verdana", "Viner Hand ITC", "Vivaldi", "Vladimir Script",
  "Webdings", "Wide Latin", "Wingdings", "Wingdings 2", "Wingdings 3", "YouYuan",
  "Yu Gothic",
];

/** Chinese display names for families that have a localized name. */
export const FONT_ZH = {
  "Microsoft YaHei": "微软雅黑", "SimHei": "黑体", "SimSun": "宋体", "KaiTi": "楷体",
  "FangSong": "仿宋", "YouYuan": "幼圆", "LiSu": "隶书", "DengXian": "等线", "STXIHEI": "华文细黑",
  "STSong": "华文宋体", "STKaiti": "华文楷体", "STFangsong": "华文仿宋", "STZhongsong": "华文中宋",
  "FZShuTi": "方正舒体", "HuaWenXingKai": "华文行楷", "Noto Sans SC": "思源黑体",
  "Source Han Sans SC": "思源黑体", "PingFang SC": "苹方", "Heiti SC": "黑体-简", "Hiragino Sans GB": "冬青黑体",
};

export const fontLabel = f => FONT_ZH[f] || f;

/**
 * Probes FONT_CANDIDATES against a bogus family using canvas text metrics.
 * A measurable width difference means the family is installed (no fallback).
 * @param {(fonts: string[]) => void} onDone
 */
export function detectSystemFonts(onDone) {
  const ctx = document.createElement("canvas").getContext("2d");
  const probe = "永汉字永WY记字体测试ABC123数字笔画粗细Ii1lO0";
  const measure = family => { ctx.font = `48px "${family}"`; return ctx.measureText(probe).width; };
  const baseline = measure("__wf_no_such_font__");
  const found = FONT_CANDIDATES.filter(f =>
    Math.abs(measure(f) - baseline) > 0.5 || f === "Microsoft YaHei"
  ).sort((a, b) => fontLabel(a).localeCompare(fontLabel(b), "zh-CN"));
  onDone(found.slice());
}

/* ------------------------------------------------------------------ */
/* Local Font Access API (Chromium, permission-gated)                 */
/* ------------------------------------------------------------------ */

const LOCAL_FONTS_KEY = "kinetype-localfonts-v1"

/**
 * Returns the Local Font Access entry point, or null when unavailable.
 * Chromium exposes it on `navigator.queryLocalFonts`, while newer Edge builds
 * (verified on 156) expose it on `window.queryLocalFonts` — check both.
 */
function getQueryLocalFonts() {
  if (typeof navigator !== "undefined" && typeof navigator.queryLocalFonts === "function") {
    return navigator.queryLocalFonts.bind(navigator)
  }
  if (typeof window !== "undefined" && typeof window.queryLocalFonts === "function") {
    return window.queryLocalFonts.bind(window)
  }
  return null
}

/** True when the browser exposes the Local Font Access API. */
export function hasLocalFontAccess() {
  return getQueryLocalFonts() !== null
}

/** Families captured by a previous authorized scan (persisted across sessions). */
export function loadSavedLocalFonts() {
  try {
    const stored = JSON.parse(localStorage.getItem(LOCAL_FONTS_KEY) || "[]");
    return Array.isArray(stored) ? stored.filter(x => typeof x === "string" && x) : [];
  } catch (_) { return []; }
}

/**
 * Requests the full local font list. Must be called from a click handler:
 * Chromium requires transient user activation before showing the permission prompt.
 * On success the family names are persisted so the next session does not need
 * to re-authorize.
 * @returns {Promise<{ok: boolean, names?: string[], msg: string}>}
 */
export async function requestLocalFonts() {
  const queryLocalFonts = getQueryLocalFonts()
  if (!queryLocalFonts) {
    return { ok: false, msg: "当前环境未开放本地字体访问（需 Chrome/Edge，且通过 localhost 或 HTTPS 打开）" }
  }
  try {
    const list = await queryLocalFonts();
    const names = [...new Set(list.map(x => String(x.family || "").trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "zh-CN"));
    try { localStorage.setItem(LOCAL_FONTS_KEY, JSON.stringify(names)); } catch (_) { /* quota/private mode */ }
    return { ok: true, names, msg: `已识别 ${names.length} 种字体` };
  } catch (err) {
    if (err && err.name === "AbortError") return { ok: false, msg: "已取消授权" };
    return { ok: false, msg: "授权未通过或读取失败：" + ((err && err.message) || err) };
  }
}

/* ------------------------------------------------------------------ */
/* Font-file import (FontFace + IndexedDB)                            */
/* ------------------------------------------------------------------ */

const DB_NAME = "kinetype-fonts";
const STORE_NAME = "files";
/** Families imported during this session (used to gate manual additions). */
const importedFamilies = new Set();

function openFontDB() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("IndexedDB unavailable")); return; }
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Reads the font family name (name table, nameID = 1) from a TTF/OTF/TTC buffer.
 * Supports TrueType (0x00010000), OpenType (OTTO), Apple (true) and TTC headers.
 * @param {ArrayBuffer} buffer
 * @returns {string | null}
 */
export function readFontFamily(buffer) {
  const view = new DataView(buffer);
  if (buffer.byteLength < 12) return null;

  /* TTC (font collection, e.g. msyh.ttc): use the first child font's sfnt offset. */
  let base = 0;
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic === "ttcf") {
    base = view.getUint32(12, false);
    if (base <= 0 || base + 12 > buffer.byteLength) return null;
  }

  const numTables = view.getUint16(base + 4, false);
  let nameOffset = 0;
  for (let i = 0; i < numTables; i++) {
    const entry = base + 12 + i * 16;
    if (entry + 16 > buffer.byteLength) break;
    const tag = String.fromCharCode(view.getUint8(entry), view.getUint8(entry + 1),
      view.getUint8(entry + 2), view.getUint8(entry + 3));
    if (tag === "name") { nameOffset = view.getUint32(entry + 8, false); break; }
  }
  if (!nameOffset) return null;

  const format = view.getUint16(nameOffset, false);
  if (format > 1) return null;
  const count = view.getUint16(nameOffset + 2, false);
  const stringOffset = nameOffset + view.getUint16(nameOffset + 4, false);

  /* Prefer Windows Unicode (platform 3, en-US), then other Windows, then Mac. */
  const picks = [];
  for (let i = 0; i < count; i++) {
    const record = nameOffset + 6 + i * 12;
    if (record + 12 > buffer.byteLength) break;
    const platform = view.getUint16(record, false);
    const encoding = view.getUint16(record + 2, false);
    const language = view.getUint16(record + 4, false);
    const nameID = view.getUint16(record + 6, false);
    const length = view.getUint16(record + 8, false);
    const offset = view.getUint16(record + 10, false);
    if (nameID !== 1) continue;
    const start = stringOffset + offset;
    if (start + length > buffer.byteLength) continue;

    let name = "";
    if (platform === 3 || (platform === 0 && encoding !== 0)) {
      for (let k = 0; k + 1 < length; k += 2) name += String.fromCharCode(view.getUint16(start + k, false));
    } else {
      for (let k = 0; k < length; k++) name += String.fromCharCode(view.getUint8(start + k));
    }
    name = name.replace(/\0/g, "").trim();
    if (!name) continue;
    const score = platform === 3 && language === 0x409 ? 3 : platform === 3 ? 2 : platform === 1 ? 1 : 0;
    picks.push({ score, name });
  }
  if (!picks.length) return null;
  picks.sort((a, b) => b.score - a.score);
  return picks[0].name;
}

/**
 * Imports a font file: parse family name, register a FontFace, persist the bytes.
 * @param {File} file
 * @returns {Promise<{ok: boolean, family?: string, msg: string}>}
 */
export async function importFontFile(file) {
  if (!file) return { ok: false, msg: "未选择文件" };
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (!["ttf", "otf", "ttc", "woff", "woff2"].includes(ext)) {
    return { ok: false, msg: "请选择 ttf / otf / ttc / woff / woff2 字体文件" };
  }
  let buffer;
  try { buffer = await file.arrayBuffer(); }
  catch { return { ok: false, msg: "读取字体文件失败" }; }

  const family = readFontFamily(buffer);
  if (!family) return { ok: false, msg: "无法从字体文件读出家族名（可能不是有效字体）" };

  try {
    const face = new FontFace(family, buffer);
    await face.load();
    document.fonts.add(face);
  } catch (e) {
    return { ok: false, msg: "字体加载失败：" + (e && e.message ? e.message : "未知错误") };
  }

  try {
    const db = await openFontDB();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(buffer, family);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch { /* Persistence is best-effort (private mode may fail). */ }

  importedFamilies.add(family);
  return { ok: true, family, msg: `已导入字体「${family}」` };
}

/**
 * Re-registers fonts persisted in IndexedDB. Called once on startup.
 * @returns {Promise<string[]>} family names restored
 */
export async function restoreImportedFonts() {
  let db;
  try { db = await openFontDB(); } catch { return []; }
  const names = [];
  try {
    const items = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const keysReq = store.getAllKeys();
      const valuesReq = store.getAll();
      tx.oncomplete = () => resolve({ keys: keysReq.result || [], values: valuesReq.result || [] });
      tx.onerror = () => reject(tx.error);
    });
    for (let i = 0; i < items.keys.length; i++) {
      const family = String(items.keys[i]);
      const buffer = items.values[i];
      if (!buffer) continue;
      try {
        const face = new FontFace(family, buffer);
        await face.load();
        document.fonts.add(face);
        importedFamilies.add(family);
        names.push(family);
      } catch { /* Skip corrupted entries. */ }
    }
  } catch { /* Ignore read failures. */ }
  db.close();
  return names;
}

/** True when the family was imported from a file in this session. */
export function isImportedFont(name) {
  return importedFamilies.has(String(name || ""));
}

/* ------------------------------------------------------------------ */
/* Alias resolution                                                   */
/* ------------------------------------------------------------------ */

/** @param {Array<{font: string, alias: string}>} rows */
export function aliasMapFromRows(rows) {
  const map = {};
  for (const row of rows || []) {
    const alias = String(row.alias || "").trim().toLowerCase();
    const font = String(row.font || "").trim();
    if (alias && font) map[alias] = font;
  }
  return map;
}

/** Resolves an alias to a concrete family, falling back to the raw name. */
export function resolveFont(name, aliasMap, fallback) {
  if (!name) return fallback;
  return aliasMap[String(name).toLowerCase()] || name;
}
