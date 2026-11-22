/* KineType render engine — ported verbatim from web/kinetype.html (the single-file
   version), decoupled from the DOM: options come in as a plain object, output goes
   to a canvas you own.  Everything below matches the original logic 1:1 so a
   re-render is frame-for-frame identical.

   Usage:
     const eng = new Engine(canvas)
     eng.prepare(opts)        // opts: {text, ratio, res, preset, cadence, speed,
     eng.drawFrame(1.2)       //   fontScale, depth, accent, bg1, bg2, defFont,
     eng.play() / eng.stop()  //   defWeight, aliasMap, rotDir}
     eng.record()             // MediaRecorder → downloads kinetype.mp4/webm       */

import { PRESETS } from "./presets.js";
import { resolveFont } from "./fonts.js";

/* 录制格式探测：优先 MP4（H.264），浏览器不支持则回退 WebM（VP9 → VP8 → 默认）。
   Chrome/Edge 新版多数支持 video/mp4;codecs=avc1，Firefox 通常只支持 WebM。
   返回 {mimeType, ext, label}，mimeType 为空表示交给浏览器默认编码。 */
export function detectRecordFormat() {
  const candidates = [
    ['video/mp4;codecs="avc1.42E01E"', "mp4", "MP4"],
    ['video/mp4;codecs="avc1"', "mp4", "MP4"],
    ["video/mp4", "mp4", "MP4"],
    ['video/webm;codecs="vp9"', "webm", "WebM"],
    ['video/webm;codecs="vp8"', "webm", "WebM"],
    ["video/webm", "webm", "WebM"],
  ];
  try {
    for (const [mimeType, ext, label] of candidates) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(mimeType)) {
        return { mimeType, ext, label };
      }
    }
  } catch (_) { /* 探测失败 → 交给浏览器默认 */ }
  return { mimeType: "", ext: "webm", label: "WebM" };
}

/* ================= tiny utils ================= */
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
const lerp = (a, b, t) => a + (b - a) * t;
function rng(key) {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619);
  return () => { h = Math.imul(h ^ h >>> 15, 2246822507); h = Math.imul(h ^ h >>> 13, 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}
const outCubic = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
const outBack = (t, s = 2.1) => { t = clamp(t, 0, 1); const c = s + 1; return 1 + c * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2); };
const cushion = (t, e = 0.45) => t <= 0 ? 0 : 1 - Math.exp(-3.5 * t / e);
const isCJK = ch => { const c = ch.codePointAt(0); return (c >= 0x2e80 && c <= 0x9fff) || (c >= 0xf900 && c <= 0xfaff) || (c >= 0xff00 && c <= 0xff60); };

/* ================= style directives ================= */
/* {key:value key2:value2} opens a style block; {/} closes the whole block,
   {/color} closes ONE property only.  A block also ends at the line break.
   Styles nest — like <b><i> in HTML, like decorators in Python. */
const COLOR_OK = /^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)$/;
const PROPS = ["size", "font", "color", "weight", "bold", "shadow", "stroke", "strokew", "spacing", "hl"];
function applyDirective(s, k, v) {
  v = (v || "").trim();
  switch (k) {
    case "size": if (v) s.size = +v || 1; break;                        /* {size:1.5} 1.5倍 */
    case "font": if (v) s.font = v; break;                              /* {font:kai} 对照表别名 */
    case "color": if (v && COLOR_OK.test(v)) s.color = v; break;        /* {color:#FFD84D} */
    case "weight": s.weight = v === "bold" ? 900 : v === "normal" ? 400 : (+v || 400); break;
    case "bold": s.bold = true; break;                                  /* {bold} */
    case "shadow": s.shadow = (v === "off" || v === "none") ? 0 : (v ? +v : 1); break;  /* {shadow:off} */
    case "stroke": s.stroke = (v === "off" || v === "none") ? "off" : (v || "on"); break; /* {stroke:#00E5FF} */
    case "strokew": if (v) s.strokew = +v; break;                       /* {strokew:0.12} em */
    case "spacing": if (v) s.spacing = +v; break;                       /* {spacing:0.1} 字距 em */
    case "hl": s.hl = true; break;
  }
}
/* close ONE property: {/color} drops the override so the outer value shows again.
   The style object is replaced (not mutated) so the run-merging in tokenize sees a
   new identity and starts a fresh text run – otherwise "B{/color}C" would merge. */
function closeProp(stack, name) {
  const p = name.toLowerCase();
  if (!PROPS.includes(p)) return;
  const cur = stack[stack.length - 1];
  if (cur[p] !== undefined) {
    const s = Object.assign(Object.create(null), cur);
    delete s[p];
    stack[stack.length - 1] = s;
  }
}

/* ================= script parsing ================= */
/* one line -> tokens: {t, st} text | {br:true} | {rot:true, deg} */
export function tokenize(line) {
  const out = [];
  const base = {};
  const stack = [base];
  const cur = () => stack[stack.length - 1];
  const pushText = t => {
    if (!t) return;
    const last = out[out.length - 1];
    if (last && !last.br && last.st === cur()) last.t += t;   /* merge same-style runs */
    else out.push({ t, st: cur() });
  };
  let i = 0;
  while (i < line.length) {
    const ch = line[i];
    if (ch === "\\") { const nx = line[i + 1]; if ("{}[]*|\\".includes(nx)) { pushText(nx); i += 2; continue; } pushText(ch); i++; continue; }
    if (ch === "|") { pushText(""); out.push({ br: true }); i++; continue; }
    if (ch === "[") {
      const e = line.indexOf("]", i + 1);
      if (e > 0) { const s = cur(); out.push({ t: line.slice(i + 1, e), st: Object.assign(Object.create(null), s, { hl: true }) }); i = e + 1; continue; }
    }
    if (line.startsWith("**", i)) {
      const e = line.indexOf("**", i + 2);
      if (e > 0) { const s = cur(); out.push({ t: line.slice(i + 2, e), st: Object.assign(Object.create(null), s, { bold: true }) }); i = e + 2; continue; }
    }
    if (ch === "{") {
      const e = line.indexOf("}", i + 1);
      if (e > 0) {
        const body = line.slice(i + 1, e).trim();
        const rm = /^(转|rot)[:：]?(-?\d+)?$/.exec(body);
        const cm = /^\/([A-Za-z]+)$/.exec(body);          /* {/color} – close one property */
        if (body === "/") { if (stack.length > 1) stack.pop(); }
        else if (cm) { closeProp(stack, cm[1]); }
        else if (rm) { pushText(""); out.push({ rot: true, deg: rm[2] !== undefined ? +rm[2] : null }); }
        else {
          const s = Object.assign(Object.create(null), cur());
          for (const tok of body.split(/\s+/)) {
            const m = /^([A-Za-z]+)[:：](.*)$/.exec(tok);
            if (m) applyDirective(s, m[1].toLowerCase(), m[2]);
            else if (/^[A-Za-z]+$/.test(tok)) applyDirective(s, tok.toLowerCase(), "");
          }
          stack.push(s);
        }
        i = e + 1; continue;
      }
    }
    pushText(ch); i++;
  }
  return out;
}

/* tokens -> keys (word/phrase units), styles carried through */
function toKeys(tokens) {
  const keys = [];
  for (const tk of tokens) {
    if (tk.br) { keys.push({ br: true }); continue; }
    if (tk.rot) { keys.push({ rot: true, deg: tk.deg }); continue; }
    const text = tk.t, st = tk.st;
    let buf = "", latin = null;
    const emit = t => { if (t) keys.push({ text: t, st }); };
    for (const ch of text) {
      if (ch === " ") {
        if (buf) { emit(buf); buf = ""; latin = null; }
        else if (keys.length && keys[keys.length - 1].text) keys[keys.length - 1].text += " ";
        continue;
      }
      const cj = isCJK(ch);
      if (latin === null) latin = !cj;
      if (cj === latin) buf += ch; else { emit(buf); buf = ch; latin = cj; }
      if (cj && "，。！？；：、…—～".includes(ch)) { emit(buf); buf = ""; latin = null; }
    }
    emit(buf);
  }
  /* weld punctuation-only keys onto the previous key */
  const out = [];
  for (const k of keys) {
    const core = (k.text || "").replace(/\s/g, "");
    if (out.length && core && [...core].every(ch => "，。！？；：、…—～!?%》」』】)）。".includes(ch))) {
      out[out.length - 1].text += k.text;
      continue;
    }
    out.push(k);
  }
  return out.filter(k => k.br || k.rot || (k.text && k.text.trim()));
}

/* whole text -> beats */
export function parseScript(text, seg, cps) {
  const beats = []; let para = [], paraRot = false, paraDeg = null;
  const unitsOf = ks => ks.reduce((n, k) => n + (k.text ? k.text.replace(/\s/g, "").length : 0), 0);
  const flush = () => { if (!para.length) { paraRot = false; paraDeg = null; return; }
    beats.push({ keys: para, rotReq: paraRot, rotDeg: paraDeg });
    para = []; paraRot = false; paraDeg = null;
  };
  for (const raw of text.replace(/\r/g, "").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) { flush(); continue; }
    for (const k of toKeys(tokenize(line))) {
      if (k.br) { flush(); continue; }
      if (k.rot) { paraRot = true; if (k.deg != null) paraDeg = k.deg; continue; }
      para.push(k);
      const units = unitsOf(para);
      const tail = (k.text || "").trim().slice(-1);
      if ("。！？!?；;…".includes(tail)) flush();
      else if (units >= seg * 1.75) flush();
      else if (units >= seg && "，,、：:—～".includes(tail)) flush();
    }
  }
  flush();
  /* merge tiny fragments (never across a finished sentence) */
  const merged = [];
  for (const b of beats) {
    const u = unitsOf(b.keys);
    if (!merged.length) { merged.push(b); continue; }
    const prev = merged[merged.length - 1];
    const prevU = unitsOf(prev.keys);
    const tiny = u < 2 || u < seg * 0.75;
    const prevEnded = "。！？!?…".includes(prev.keys[prev.keys.length - 1].text.trim().slice(-1));
    const prevSmall = prevU < seg * 0.6;
    if ((tiny || (u < seg * 1.05 && prevSmall)) && !prevEnded && !b.rotReq && !prev.rotReq
      && prev.keys.length + b.keys.length <= 8) {
      prev.keys.push(...b.keys);
    } else merged.push(b);
  }
  return merged.map((b, i) => ({
    keys: b.keys, index: i, rotReq: b.rotReq, rotDeg: b.rotDeg,
    hl: b.keys.some(k => k.st && k.st.hl),
    plain: b.keys.map(k => k.text || "").join(""),
    dur: clamp(unitsOf(b.keys) / cps, 0.32, 2.2),
  }));
}

/* ================= layout: beat -> sprite ================= */
/* Every key carries its own style; the sprite is the beat's line box in the
   block's LOCAL frame (the block as a whole may be rotated later).
   `maxLine` is the longest a line may get — chosen so the line still fits after
   the block rotates 90°, where it runs along the screen's short side. */
function layoutBeat(beat, fsBase, acc, defFont, defWeight, aliasMap, maxLine, P) {
  const probe = document.createElement("canvas").getContext("2d");
  const maxW = maxLine;
  const fontOf = (k, px) => {
    const st = k.st || {};
    const fam = resolveFont(st.font, aliasMap, defFont);
    const w = st.bold ? 700 : (st.weight || defWeight || 400);
    return `${w} ${px}px "${fam}","${defFont}","Microsoft YaHei",sans-serif`;
  };
  const measureKey = (g, k, px) => {
    g.font = fontOf(k, px);
    const sp = (k.st && k.st.spacing) || 0;
    if (!sp) return g.measureText(k.text).width;
    let w = 0; for (const ch of k.text) w += g.measureText(ch).width + px * sp;
    return w - px * sp;
  };
  const wrap = s => {
    const rows = []; let cur = [], w = 0, gap = 0;
    for (const k of beat.keys) {
      if (!k.text) continue;
      const px = s * ((k.st && k.st.size) || 1);
      const kw = measureKey(probe, k, px);
      if (cur.length && w + gap + kw > maxW) { rows.push({ keys: cur, w }); cur = [k]; w = kw; }
      else { w += cur.length ? gap + kw : kw; cur.push(k); }
      gap = px * 0.26;                       /* same gap the raster pass advances by */
    }
    if (cur.length) rows.push({ keys: cur, w });
    return rows;
  };
  let fit = 1, rows = wrap(fsBase);
  const widest = r => Math.max(...r.map(x => x.w), 0);
  while ((widest(rows) > maxW || rows.length > 3) && fit > 0.45) { fit *= 0.9; rows = wrap(fsBase * fit); }
  if (beat.keys.length <= 2 && rows.length === 1 && rows[0].w < maxW * 0.55) {
    const big = Math.min(1.5, (maxW * 0.78) / rows[0].w);
    const rr = wrap(fsBase * big);
    if (widest(rr) <= maxW) { fit = big; rows = rr; }
  }
  /* per-row metrics: height follows the biggest glyph in the row */
  const kpx0 = k => fsBase * fit * ((k.st && k.st.size) || 1);
  const rowPx = rows.map(r => Math.max(...r.keys.map(kpx0), fsBase * fit * 0.5));
  const lineHeights = rowPx.map(px => (px * 0.98 + px * 0.30) * 1.12);
  const pad = Math.ceil(Math.max(...rowPx) * 0.30);
  const c = document.createElement("canvas");
  c.width = Math.ceil(widest(rows)) + pad * 2;
  c.height = Math.ceil(lineHeights.reduce((a, b) => a + b, 0) + pad * 2);
  const g = c.getContext("2d");
  g.textBaseline = "alphabetic"; g.lineJoin = "round";
  const pick = rng("pal" + beat.index);
  const palFill = P.pal.length > 1 ? P.pal[Math.floor(pick() * P.pal.length)] : P.pal[0];
  let y = pad;
  let lastBase = 0;
  for (let ri = 0; ri < rows.length; ri++) {
    const row = rows[ri], px = rowPx[ri];
    const asc = px * 0.98, desc = px * 0.30;
    const base = y + asc; lastBase = base;
    const r = rng("dx" + beat.index + "r" + ri);
    let x = (c.width - row.w) / 2 + (r() - 0.5) * px * 0.08;
    for (const k of row.keys) {
      const st = k.st || {};
      const kSize = fsBase * fit * ((st.size) || 1);
      const col = st.color || palFill;
      const kw = measureKey(g, k, kSize);
      if (st.hl) {
        const bp = kSize * 0.20;
        g.fillStyle = acc;
        g.beginPath(); g.roundRect(x - bp, base - asc - bp * 0.35, kw + bp * 2, asc + desc + bp * 0.8, kSize * 0.14); g.fill();
        drawGlyphs(g, k, x, base, kSize, "#101014", false);
      } else {
        drawGlyphs(g, k, x, base, kSize, col, true);
      }
      x += kw + kSize * 0.26;
    }
    y += lineHeights[ri];
  }
  function drawGlyphs(g, k, x, base, kSize, col, useFx) {
    const st = k.st || {};
    g.font = fontOf(k, kSize);
    const sp = st.spacing || 0;
    const shadowOff = !useFx || st.shadow === 0;
    const sh = st.shadow == null ? 1 : st.shadow;
    /* shadow pass */
    if (!shadowOff) {
      g.shadowColor = "rgba(0,0,0,0.55)"; g.shadowBlur = kSize * 0.12 * sh; g.shadowOffsetY = kSize * 0.06 * sh;
    }
    /* stroke pass */
    /* outline is OFF by default — turn it on with {stroke} or {stroke:#00E5FF} */
    const strokeOn = useFx && !!st.stroke && st.stroke !== "off";
    const strokeCol = (st.stroke && st.stroke !== "on") ? st.stroke : "#0b0b10";
    const strokeW = st.strokew != null ? st.strokew : 0.085;
    const putText = (txt, px, py) => {
      if (!sp) { g.fillText(txt, px, py); return; }
      let cx = px;
      for (const ch of txt) { g.fillText(ch, cx, py); cx += g.measureText(ch).width + kSize * sp; }
    };
    if (strokeOn) {
      g.lineJoin = "round";
      g.strokeStyle = strokeCol; g.lineWidth = Math.max(1, kSize * strokeW);
      if (!sp) { g.strokeText(k.text, x, base); }
      else { let cx = x; for (const ch of k.text) { g.strokeText(ch, cx, base); cx += g.measureText(ch).width + kSize * sp; } }
    }
    if (P.glow && useFx && !shadowOff) { g.save(); g.shadowColor = col; g.shadowBlur = P.glow; g.globalAlpha = 0.9; }
    g.fillStyle = col;
    putText(k.text, x, base);
    if (P.glow && useFx && !shadowOff) g.restore();
    g.shadowColor = "transparent"; g.shadowBlur = 0; g.shadowOffsetY = 0;
  }
  return { img: c, w: c.width, h: c.height, ay: (lastBase) / c.height, fs: fsBase * fit, pad };
}

/* ================= line rotation ================= */
/* The GLYPHS never rotate – every line always reads upright.  A rotation event
   only swings the POSITIONS of the lines that were already on screen (the ones
   above the marked line) around the centre; the marked line and everything after
   it keeps stacking straight up.  Lines above are pushed out sideways as the
   stack grows, and vanish once they leave the frame. */
const ROT_DUR = 0.55;
function planRotations(beats, layout, W, H, fs, rotdir) {
  const events = []; let seg = 0, stackH = 0;
  for (let i = 0; i < beats.length; i++) {
    const slot = layout[i].h * 1.045 + fs * 0.06;
    let need = false, want = null;
    if (beats[i].rotReq) { need = true; want = beats[i].rotDeg; }
    else if (rotdir !== "none" && stackH + slot > H * 0.82 && layout[i].w <= H * 0.9) {
      /* Rotating turns the line along H; skip rows that are too wide to fit
         there (they stay horizontal rather than overflow the frame). */
      need = true;
    }
    if (need) {
      /* explicit degree wins; otherwise alternate the swing so the pile fans out
         instead of spinning into an upside-down arrangement */
      const base = rotdir === "ccw" ? -1 : rotdir === "rand" ? (rng("rd" + i)() < 0.5 ? -1 : 1) : 1;
      const delta = want != null ? want : (events.length % 2 === 0 ? 90 : -90) * base;
      events.push({ t: beats[i].start, beatIndex: i, delta, seg: seg + 1 });
      seg++; stackH = 0;
    }
    beats[i].seg = seg;
    stackH += slot;
  }
  return events;
}
/* how far a given line has been swung away from upright, in degrees (animated) */
function beatAngle(t, b, events) {
  let a = 0;
  for (const e of events) {
    if (b.index >= e.beatIndex) continue;     /* this line is at/below the mark → upright */
    if (t < e.t) continue;
    a += e.delta * outBack((t - e.t) / ROT_DUR, 1.25);
  }
  return a;
}
/* which rotation caught this line – the pile turns as ONE rigid group around the
   start point of the line that was showing when {转} fired (the pivot line) */
function eraInfo(b, events) {
  for (const e of events) {
    if (e.beatIndex > b.index) return { mark: e.beatIndex, anchor: e.beatIndex };
  }
  return null;
}
function segmentAgeFade(t, b, events) {
  /* b is from segment s; once the second rotation after it fires, b is gone –
     a hard cut, no fade-out flash */
  const cut = events[b.seg + 1];
  if (!cut) return 1;
  return t < cut.t ? 1 : 0;
}

/* ================= engine ================= */
export const RATIOS = {
  "9:16": [9, 16], "16:9": [16, 9], "3:4": [3, 4], "4:3": [4, 3],
  "4:5": [4, 5], "1:1": [1, 1], "21:9": [21, 9],
};
export function frameSize(ratio, shortSide) {
  const [rw, rh] = RATIOS[ratio] || RATIOS["9:16"];
  const S = Math.max(360, +shortSide || 1080);
  let W, H;
  if (rw <= rh) { W = S; H = Math.round(S * rh / rw); }
  else { H = S; W = Math.round(S * rw / rh); }
  W -= W % 2; H -= H % 2;
  return [Math.max(2, W), Math.max(2, H)];
}
const refArea = 1080 * 1920;

export class Engine {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext("2d");
    this.prog = null;
    this.t0 = 0;
    this.raf = 0;
    this.recorder = null;
    this.chunks = [];
    this.isPlaying = false;
    this.lastDrawT = 0;
    this.onPlayState = () => {};
    this.onStatus = () => {};
    this.onProgress = () => {};
    this.onRecorded = () => {};
  }

  /* opts: {text, ratio, res, preset, cadence, speed, fontScale, depth,
            accent, bg1, bg2, defFont, defWeight, aliasMap, rotDir} */
  prepare(o) {
    const dims = frameSize(o.ratio, o.res);
    const W = this.cv.width = dims[0], H = this.cv.height = dims[1];
    const P = PRESETS[o.preset] || PRESETS["meme-punch"];
    this.preset = P;
    const seg = +o.cadence || 6;
    const cps = +o.speed || 13;
    const beats = parseScript(o.text, seg, cps);
    if (!beats.length) return null;
    const acc = o.accent;
    const zoom = +o.fontScale / 100 || 1;
    const fs = 44 * Math.sqrt((W * H) / refArea) * zoom;
    const defFont = o.defFont || "Microsoft YaHei";
    const defWeight = +(o.defWeight || 400) || 400;
    /* Per-aspect max line width. Landscape frames let a line run nearly edge
       to edge; portrait frames are bounded by their own (short) side. Keep each
       ratio explicit instead of one shared factor — the old
       min(W, H) * 0.86 capped 16:9 at ~48% of the width and forced early wraps. */
    const MAX_LINE_RATIO = {
      "16:9": 0.94, "21:9": 0.96, "4:3": 0.94,
      "9:16": 0.92, "3:4": 0.92, "4:5": 0.92, "1:1": 0.92,
    };
    const maxLineWide = W * (MAX_LINE_RATIO[o.ratio] || 0.92);
    /* A beat with an explicit {转} runs its lines along H after turning, so
       only those need the short-side cap. */
    const maxLineRotated = H * 0.9;
    const layout = beats.map(b => layoutBeat(b, fs, acc, defFont, defWeight, o.aliasMap,
      b.rotReq ? Math.min(maxLineWide, maxLineRotated) : maxLineWide, P));

    /* timeline first – rotation events are keyed to beat start times */
    let t = 0.25; for (const b of beats) { b.start = t; t += b.dur + 0.06; }
    const events = planRotations(beats, layout, W, H, fs, o.rotDir);
    /* depth scale: how strongly lines shrink (or grow) as they travel upward */
    const depth = +o.depth || 0;

    /* background */
    const bg = document.createElement("canvas"); bg.width = W; bg.height = H;
    const g = bg.getContext("2d");
    const c1 = o.bg1, c2 = o.bg2;
    if (P.bg === "flat") { g.fillStyle = c1; g.fillRect(0, 0, W, H); }
    else {
      const gr = P.bg === "radial"
        ? g.createRadialGradient(W / 2, H * 0.42, 0, W / 2, H * 0.42, W * 0.8)
        : g.createLinearGradient(0, 0, W * 0.35, H);
      gr.addColorStop(0, c1); gr.addColorStop(1, c2);
      g.fillStyle = gr; g.fillRect(0, 0, W, H);
    }
    if (P.dots) { g.fillStyle = P.dots; g.globalAlpha = 0.35;
      for (let y = 24, row = 0; y < H; y += 48, row++) for (let x = (row % 2 ? 24 : 48); x < W; x += 48) { g.beginPath(); g.arc(x, y, 2.2, 0, 7); g.fill(); }
      g.globalAlpha = 1; }
    if (P.noise) { const n = document.createElement("canvas"); n.width = n.height = 160;
      const nc = n.getContext("2d"), im = nc.createImageData(160, 160);
      for (let i = 0; i < im.data.length; i += 4) { const v = Math.random() * 255 | 0; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255; }
      nc.putImageData(im, 0, 0);
      g.globalAlpha = P.noise; g.globalCompositeOperation = "overlay";
      g.fillStyle = g.createPattern(n, "repeat"); g.fillRect(0, 0, W, H);
      g.globalCompositeOperation = "source-over"; g.globalAlpha = 1; }
    this.lastDrawT = 0;
    this.prog = { beats, layout, bg, P, W, H, total: t + 0.6, acc, events, defFont, defWeight, depth };
    return this.prog;
  }

  /* Beats that can still be on screen at time t.  A line is NOT removed on a timer:
     it stays until it has been pushed out of the frame.  Only the last MAX_TRACK
     beats can be visible, so that is the window we walk. */
  liveWindow(t) {
    const beats = this.prog.beats;
    let last = beats.length - 1;
    while (last >= 0 && beats[last].start > t) last--;
    return last < 0 ? [] : beats.slice(Math.max(0, last - MAX_TRACK + 1), last + 1);
  }

  drawFrame(t) {
    const prog = this.prog;
    if (!prog) return false;
    const { beats, layout, bg, P, W, H, total, events } = prog;
    const ctx = this.ctx;
    ctx.drawImage(bg, 0, 0);
    /* on-beat background flash */
    if (P.flash.length) {
      const fb = beats.find(b => b.hl && t >= b.start && t - b.start < 0.3);
      if (fb) { const age = t - fb.start;
        ctx.fillStyle = P.flash[fb.index % P.flash.length];
        ctx.globalAlpha = 0.16 * (1 - clamp(age / 0.3, 0, 1)); ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
    }
    /* shake */
    let sx = 0, sy = 0;
    if (P.shake) {
      for (const b of beats) { const age = t - b.start;
        if (age >= 0 && age < 0.3) { const d = Math.exp(-age / 0.12); sx = Math.sin(age * 47) * P.shake * 26 * d; sy = Math.cos(age * 39) * P.shake * 20 * d; } }
    }
    const live = this.liveWindow(t);
    const newest = live.length ? live[live.length - 1].index : -1;
    this.lastDrawT = t;

    ctx.save();
    ctx.translate(W / 2 + sx, H * 0.5 + sy);   /* screen centre (the rotation anchor) */
    const SCROLL = 0.32, SCROLL_E = 0.45, ENTER = 0.28;
    /* stack offset of a beat: how far the newer lines have pushed it up */
    const stackY = (idx, Lf) => {
      let y = 0;
      for (const o of live) if (o.index > idx)
        y -= (layout[o.index].h * 1.045 + Lf.fs * 0.06) * cushion((t - o.start) / SCROLL, SCROLL_E);
      return y;
    };
    const yOf = {};
    for (const b of live) yOf[b.index] = stackY(b.index, layout[b.index]);
    for (const b of live) {
      const L = layout[b.index], age = t - b.start;
      const y = yOf[b.index];
      let op = 1, sc = 1, dy = 0, swing = 0;
      const style = P.enter === "rand" ? ["pop", "rise", "drop", "zoom"][Math.floor(rng("e" + b.index)() * 4)] : P.enter;
      if (age < ENTER) {
        const u = age / ENTER;
        if (style === "pop") { sc = lerp(0.6, 1, outBack(u)); op = clamp(u * 1.5, 0, 1); }
        else if (style === "rise") { dy = lerp(L.fs * 1.4, 0, outBack(u, 1.4)); op = u; }
        else if (style === "drop") { dy = lerp(-L.fs * 1.5, 0, outCubic(u)); op = clamp(u * 1.3, 0, 1); }
        else if (style === "zoom") { sc = lerp(1.55, 1, outBack(u, 1.1)); op = clamp(u * 1.8, 0, 1); }
        else if (style === "type") { op = 1; sc = lerp(1.06, 1, outCubic(u)); }
        else if (style === "swing") { swing = lerp(-8, 0, outBack(u, 1.5)); dy = lerp(-L.fs * 0.4, 0, outCubic(u)); op = u * 1.3; }
      }
      /* the line lives until it leaves the frame – the old timed exit is gone */
      if (b.index === newest) {
        const f = 1 - cushion(age / SCROLL, SCROLL_E);
        dy += L.fs * 0.30 * f;
      }
      else if (age > 0.4) { dy -= L.fs * 0.05 * clamp((age - 0.4) / 2, 0, 1); }
      /* depth: the further a line has travelled from the centre line, the more the
         user-chosen scale kicks in (positive = shrinks going up, negative = grows) */
      const travel = clamp((-y - dy) / Math.max(1, Math.min(W, H) * 0.34), 0, 1);
      const dscale = 1 - (prog.depth || 0) / 100 * travel;
      sc *= Math.max(0.2, dscale);
      /* ---- rotation era ------------------------------------------------
         The pile above {转} turns as ONE rigid group.  Pivot, as asked:
           · turning right → the TOP-RIGHT corner of the LAST glyph
           · turning left  → the TOP-LEFT  corner of the FIRST glyph
         of the line that was on screen when {转} fired.  A small gap keeps the
         turned pile clear of that line. */
      const a = beatAngle(t, b, events);
      const ca = Math.cos(a * Math.PI / 180), sa = Math.sin(a * Math.PI / 180);
      const era = eraInfo(b, events);
      let px = 0, py = y + dy;               /* each line's anchor is its own centre */
      if (era) {
        const Lf = layout[era.anchor] || L;
        const yPivot = stackY(era.anchor, Lf);
        const pad = Lf.pad || 0;
        const topY = yPivot - Lf.h / 2 + pad;               /* top edge of that line's glyphs */
        const Px = a > 0 ? Lf.w / 2 - pad                   /* right→ right edge of last glyph */
          : -Lf.w / 2 + pad;                                 /* left → left edge of first glyph */
        const dx0 = -Px, dy0 = (y + dy) - topY;
        px = Px + dx0 * ca - dy0 * sa;
        py = topY + dx0 * sa + dy0 * ca;
        /* breathing room between the turned pile and the live line */
        py -= Lf.fs * 0.55 * Math.min(1, Math.abs(a) / 90);
      }
      /* sprite occupies [px-w/2, px+w/2] × [py-h/2, py+h/2] (rotated when a≠0) */
      const scx0 = W / 2 + px, scy0 = H / 2 + py;
      const hw2 = (Math.abs(L.w / 2 * ca) + Math.abs(L.h / 2 * sa)) * sc;
      const hh2 = (Math.abs(L.w / 2 * sa) + Math.abs(L.h / 2 * ca)) * sc;
      const out = Math.max(0, Math.max(-(scx0 + hw2), scx0 - hw2 - W), Math.max(-(scy0 + hh2), scy0 - hh2 - H));
      if (out > 0) continue;                /* completely out of frame – drop it at once */
      op *= segmentAgeFade(t, b, events);
      if (op <= 0.01) continue;
      let deg = swing;
      if (!b.rotReq && P.rot) deg += (rng("t" + b.index)() - 0.5) * P.rot * 0.8;   /* tiny organic tilt */
      ctx.save();
      ctx.globalAlpha = clamp(op, 0, 1);
      ctx.translate(px, py);
      if (a) ctx.rotate(a * Math.PI / 180);        /* only the pile above the mark swings */
      if (deg) ctx.rotate(deg * Math.PI / 180);
      if (sc !== 1) ctx.scale(sc, sc);
      ctx.drawImage(L.img, -L.w / 2, -L.h / 2);   /* the sprite's centre sits on the anchor */
      ctx.restore();
    }
    ctx.restore();
    /* 进度只汇报给外部 Slider，不再画进画面（用户要求视频内不要进度条） */
    this.onProgress(clamp(t / total, 0, 1));
    return t < total;
  }

  loop = (now) => {
    if (!this.prog) return;
    if (this.drawFrame((now - this.t0) / 1000)) this.raf = requestAnimationFrame(this.loop);
    else { this.setPlaying(false); cancelAnimationFrame(this.raf); this.onStatus(`播放完毕 · ${this.prog.total.toFixed(1)}s`); }
  };

  setOptions(o) { this.opts = o; return this; }

  start() {
    const n = this.prog.events.length;
    this.onStatus(`播放中 · 总时长 ${this.prog.total.toFixed(1)}s · ${n} 次整块旋转`);
    this.t0 = performance.now(); this.setPlaying(true);
    this.raf = requestAnimationFrame(this.loop);
  }
  play() {
    this.stop(false);
    this.prog = this.prepare(this.opts);
    if (!this.prog) { this.onStatus("请先输入文案"); return; }
    this.start();
  }
  /* 拖动外部 Slider 定位：ratio∈[0,1]。把 t0 反推到目标时间点，
     播放中继续从此处走，暂停时只重绘该帧。 */
  seek(ratio) {
    if (!this.prog) return false;
    const r = Math.max(0, Math.min(1, Number(ratio) || 0));
    const t = r * this.prog.total;
    this.t0 = performance.now() - t * 1000;
    this.drawFrame(t);
    this.onProgress(r);
    return true;
  }
  stop(notify = true) {
    cancelAnimationFrame(this.raf); this.setPlaying(false);
    this._recordCancel = true;              /* 让离线 WebCodecs 编码循环尽快退出 */
    if (notify) this.onStatus("已停止");
    if (this.recorder && this.recorder.state === "recording") { this.recorder.stop(); this.recorder = null; }
  }
  setPlaying(v) {
    this.isPlaying = v;
    this.onPlayState(v);
  }

  /* Normalize the user-supplied export name into a safe, extension-free base.
     Strips path separators and reserved characters, falls back to "kinetype". */
  _exportBase(name) {
    let s = String(name == null ? "" : name).trim()
    s = s.replace(/[\\/:*?"<>|]/g, "").replace(/\.(mp4|webm|mov)$/i, "").trim()
    return s || "kinetype"
  }

  /* 统一的下载：把 <a> 挂进 DOM 再 click，部分浏览器（Firefox）不接受游离节点；
     延时 revoke，避免有些浏览器还没开始读 Blob 就被释放 → "导出了却没文件"。 */
  _download(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 60000);
  }

  /* 探测 H.264 硬件编码配置。Edge/Chrome on Windows 的 H.264 编码器只认 High
     profile（avc1.640033）；Baseline 会 isConfigSupported=false。依次尝试。 */
  async _pickEncoderConfig(W, H, bitrate, fps) {
    const tries = [
      ["avc1.640033", "prefer-hardware"],
      ["avc1.640033", "no-preference"],
      ["avc1.4d4028", "prefer-hardware"],   /* Main profile */
      ["avc1.42001E", "no-preference"],     /* Baseline，兼容性兜底 */
    ];
    for (const [codec, hardwareAcceleration] of tries) {
      const cfg = { codec, width: W, height: H, bitrate, framerate: fps,
        latencyMode: "quality", hardwareAcceleration };
      try {
        const sup = await VideoEncoder.isConfigSupported(cfg);
        if (sup.supported) return sup.config || cfg;
      } catch (_) { /* 试下一个 */ }
    }
    return null;
  }

  /* 主路径：WebCodecs 离线逐帧编码。渲染与真实时间解耦——每帧用固定的 t
     渲染并打上精确时间戳，所以渲染再慢也不会掉帧/时序错乱；编码走 GPU。 */
  async _recordWebCodecs() {
    if (typeof VideoEncoder === "undefined" || typeof VideoFrame === "undefined") return false;
    const W = this.cv.width, H = this.cv.height;
    const fps = 30;
    const total = this.prog.total;
    const frameCount = Math.max(1, Math.round(total * fps));
    const area = W * H;
    const bitrate = Math.min(48_000_000, Math.max(4_000_000, Math.round(area / (1080 * 1920) * 8_000_000)));

    const cfg = await this._pickEncoderConfig(W, H, bitrate, fps);
    if (!cfg) return false;
    const hw = cfg.hardwareAcceleration === "prefer-hardware" ? " · 硬件加速" : "";

    let muxer, target, MuxCtor, TargetCtor;
    ({ Muxer: MuxCtor, ArrayBufferTarget: TargetCtor } = await import("mp4-muxer"));
    target = new TargetCtor();
    muxer = new MuxCtor({
      target,
      video: { codec: "avc", width: W, height: H, frameRate: fps },
      fastStart: "in-memory",
      firstTimestampBehavior: "offset",
    });

    let encErr = null;
    const encoder = new VideoEncoder({
      output: (chunk, meta) => { try { muxer.addVideoChunk(chunk, meta); } catch (e) { encErr = e; } },
      error: e => { encErr = e; },
    });
    encoder.configure(cfg);

    this.onStatus(`编码中 0% · ${W}×${H} · H.264${hw}`);
    for (let i = 0; i < frameCount; i++) {
      if (this._recordCancel) break;
      const t = Math.min(total, i / fps);
      this.drawFrame(t);
      const ts = Math.round(i * 1_000_000 / fps);
      const vf = new VideoFrame(this.cv, { timestamp: ts });
      encoder.encode(vf, { keyFrame: i % (fps * 2) === 0 });   /* 每 2s 一个关键帧 */
      vf.close();
      if (encErr) throw encErr;
      /* 背压：队列太长就等它消化，避免一次性塞满内存；同时让出主线程保持 UI 响应 */
      if (encoder.encodeQueueSize > 12) {
        await new Promise(res => {
          const kick = () => encoder.encodeQueueSize <= 6 ? res() : setTimeout(kick, 4);
          kick();
        });
      } else if (i % 3 === 0) {
        await new Promise(res => setTimeout(res, 0));
      }
      if (i % 15 === 0 || i === frameCount - 1)
        this.onStatus(`编码中 ${Math.round((i + 1) / frameCount * 100)}% · ${W}×${H} · H.264${hw}`);
    }
    if (this._recordCancel) { encoder.close(); return true; }   /* 用户取消：算作已处理 */
    await encoder.flush();
    if (encErr) throw encErr;
    encoder.close();
    muxer.finalize();
    const outName = `${this._exportBase(this.exportName)}.mp4`;
    this._download(new Blob([target.buffer], { type: "video/mp4" }), outName);
    const tag = area >= 2160 * 3840 ? " · 4K" : "";
    this.onStatus(`已导出 ${outName}（MP4 · H.264${hw}${tag}）✓`);
    return true;
  }

  /* 回退路径：浏览器无 WebCodecs（如 Firefox）时的 MediaRecorder 实时录制。
     修复点：下载走 _download()（挂 DOM + 延时 revoke），解决"导出没文件"。 */
  _recordMediaRecorder(fmt) {
    if (!window.MediaRecorder) { this.onStatus("此浏览器不支持录制"); return false; }
    const stream = this.cv.captureStream(30);
    const area = this.cv.width * this.cv.height;
    const videoBitsPerSecond = Math.min(48_000_000, Math.max(4_000_000, Math.round(area / (1080 * 1920) * 8_000_000)));
    const opts = { videoBitsPerSecond };
    if (fmt.mimeType) opts.mimeType = fmt.mimeType;
    try { this.recorder = new MediaRecorder(stream, opts); }
    catch (_) { this.recorder = new MediaRecorder(stream); fmt = { mimeType: "", ext: "webm", label: "WebM" }; }
    const rec = this.recorder;
    this.chunks = [];
    rec.ondataavailable = e => { if (e.data && e.data.size) this.chunks.push(e.data); };
    rec.onstop = () => {
      const type = rec.mimeType || fmt.mimeType || "video/webm";
      const name = `${this._exportBase(this.exportName)}.${fmt.ext}`;
      this._download(new Blob(this.chunks, { type }), name);
      this.onStatus(`已导出 ${name}（${fmt.label} · 兼容模式）✓`);
      this.onRecorded();
    };
    this.t0 = performance.now(); rec.start(); this.setPlaying(true);
    this.raf = requestAnimationFrame(this.loop);
    return true;
  }

  /* prefer = "compat" skips WebCodecs entirely; capabilities.js sets it on
     devices that cannot encode H.264 so we do not waste a failed attempt. */
  async record({ format, name, prefer = "auto" } = {}) {
    this.exportName = name;
    this.prog = this.prog || this.prepare(this.opts);
    if (!this.prog) return;
    this._recordCancel = false;
    const fmt = format || detectRecordFormat();
    this.recordFormat = fmt;
    if (prefer !== "compat") {
      try {
        const done = await this._recordWebCodecs();
        if (done) { this.onRecorded(); return; }
      } catch (e) {
        console.warn("WebCodecs 导出失败，回退 MediaRecorder：", e);
        this.onStatus("硬件编码失败，改用兼容模式…");
      }
    }
    /* 回退：MediaRecorder（取消时不再重复触发） */
    if (!this._recordCancel) this._recordMediaRecorder(fmt);
    else this.onRecorded();
  }
}
const MAX_TRACK = 40;
