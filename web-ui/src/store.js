/**
 * Application store.
 *
 * Single source of truth for user settings and runtime state. Responsibilities:
 * - Persist a whitelisted subset of settings to localStorage (debounced).
 * - Resolve theme mode (auto/light/dark) and apply the html class contract
 *   used by WinUIonWeb (theme-light / theme-dark).
 * - Track the Windows accent color: CSS derives the ramp via color-mix;
 *   JS only computes the contrasting foreground color and watches for changes.
 */
import { reactive, watch } from 'vue'
import { PRESETS } from './engine/presets.js'
import { aliasMapFromRows } from './engine/fonts.js'
import { detectRecordFormat } from './engine/kinetype.js'

const SAMPLE = `喂，您好，这里是 {color:#dfc243 bold}保险公司{/}。

{转} 用 别的工具，{font:kai}我老手艺人了{/}

[倒鸭子]？您说的是……什么鸭子？

就是那个，[倒]了的鸭子啊。

{size:1.6 spacing:0.12 color:#c04851}倒鸭子{/} 特效时

去查了不少教程

发现最方便的方案

{转} 竟然是 {stroke:#2bae85}AE 手搓{/}

这也太难了吧

{shadow:off}先生，您能描述一下现场情况吗？{/}

我的车，把一只鸭子给撞了，它[倒]在路边。

{color:#2bae85}好的，请问鸭子现在怎么样？{/}

它[倒]着，但是它[没死]。

那您想让我们赔什么呢？

我们保[车]。

那我的车也坏了啊！

{转:-90} 那这鸭子算什么？

算[第三者]吧……大概。`;

/* ------------------------------------------------------------------ */
/* Theme bootstrap                                                    */
/* ------------------------------------------------------------------ */

const savedThemeMode = localStorage.getItem('winui-theme-mode')
const urlTheme = new URLSearchParams(location.search).get('theme')
const initialThemeMode = ['auto', 'light', 'dark'].includes(urlTheme) ? urlTheme
  : ['auto', 'light', 'dark'].includes(savedThemeMode) ? savedThemeMode : 'auto'
const savedAccent = localStorage.getItem('winui-accent-system')
const urlAccent = new URLSearchParams(location.search).get('accent')

/* ------------------------------------------------------------------ */
/* Persistence                                                        */
/* ------------------------------------------------------------------ */

const STORAGE_KEY = 'kinetype-settings-v1'

/* Default export name: today's date (YYYY-MM-DD), so files sort by day.
   Computed at startup; a long-running tab keeps the day it was opened. */
function todayStamp() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const DEFAULTS = {
  text: SAMPLE,
  ratio: '16:9',
  res: '1080',
  preset: 'guofeng',
  cadence: 6,
  speed: 13,
  fontScale: 100,
  depth: 25,
  defFont: 'Microsoft YaHei',
  defWeight: 700,
  rotDir: 'cw',
  bg1: PRESETS.guofeng.sug[0],
  bg2: PRESETS.guofeng.sug[1],
  accent: PRESETS.guofeng.sug[2],
  aliases: [
    { font: 'KaiTi', alias: 'kai' },
    { font: 'SimHei', alias: 'hei' },
  ],
  customFonts: [],   /* Families added from font files (see engine/fonts.js). */
  progress: 0,       /* Playback position 0..1, restored on next launch. */
  exportName: todayStamp(),  /* Base file name used when exporting the video. */
  /* Manual UI accent (#rrggbb) used when the system color is not followed.
     Distinct from `accent`, which is the video palette's accent. */
  uiAccent: '',
  /* Swatches shown under 最近使用的颜色, newest first. */
  recentAccents: [],
}

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' ? obj : {}
  } catch (_) { return {} }
}

/* Only whitelisted keys with matching types are restored; anything else is
   discarded so stale or hand-edited payloads cannot break the UI. */
const saved = loadSaved()
const restored = {}
for (const key of Object.keys(DEFAULTS)) {
  if (!(key in saved)) continue
  const def = DEFAULTS[key]
  const val = saved[key]
  if (Array.isArray(def)) {
    const valid = Array.isArray(val) && val.every(item => def.length === 0
      ? typeof item === 'string'
      : (def[0] && typeof def[0] === 'object' ? (item && typeof item === 'object') : typeof item === typeof def[0]))
    if (valid) restored[key] = val
  } else if (typeof val === typeof def) {
    restored[key] = val
  }
}

const clampNum = (v, lo, hi, fallback) =>
  (typeof v === 'number' && isFinite(v)) ? Math.min(hi, Math.max(lo, v)) : fallback
if ('speed' in restored) restored.speed = clampNum(restored.speed, 6, 26, DEFAULTS.speed)
if ('fontScale' in restored) restored.fontScale = clampNum(restored.fontScale, 40, 200, DEFAULTS.fontScale)
if ('depth' in restored) restored.depth = clampNum(restored.depth, -50, 60, DEFAULTS.depth)
if ('progress' in restored) restored.progress = clampNum(restored.progress, 0, 1, 0)

/* One-time migration: earlier builds defaulted to 9:16 portrait. Upgrade only
   once, so a deliberate later choice of 9:16 is preserved. */
const RATIO_MIGRATED_KEY = 'kinetype-ratio-169-migrated'
if (!localStorage.getItem(RATIO_MIGRATED_KEY)) {
  if (!('ratio' in restored) || restored.ratio === '9:16') restored.ratio = '16:9'
  try { localStorage.setItem(RATIO_MIGRATED_KEY, '1'); } catch (_) { /* ignore */ }
}

/* One-time migration: drop the hard-coded blue from the sample caption so it
   renders in the default text color. Only touches the known sample line. */
const SAMPLE_TEXT_MIGRATED_KEY = 'kinetype-sample-text-v2'
if (!localStorage.getItem(SAMPLE_TEXT_MIGRATED_KEY)) {
  if (typeof restored.text === 'string' && restored.text.includes('{color:#1661ab}别的工具{/}')) {
    restored.text = restored.text.replace('{color:#1661ab}别的工具{/}', '别的工具')
  }
  try { localStorage.setItem(SAMPLE_TEXT_MIGRATED_KEY, '1'); } catch (_) { /* ignore */ }
}

/* One-time migration: the old default was the literal 'kinetype'. Replace it
   with today's date so the new default actually shows up for existing users. */
const EXPORT_NAME_MIGRATED_KEY = 'kinetype-export-name-v2'
if (!localStorage.getItem(EXPORT_NAME_MIGRATED_KEY)) {
  if (!restored.exportName || restored.exportName === 'kinetype') {
    restored.exportName = todayStamp()
  }
  try { localStorage.setItem(EXPORT_NAME_MIGRATED_KEY, '1'); } catch (_) { /* ignore */ }
}

export const state = reactive({
  themeMode: initialThemeMode,          /* 'auto' | 'light' | 'dark' */
  theme: 'light',                       /* resolved theme actually applied */
  useSystemAccent: urlAccent === '0' ? false : (urlAccent === '1' ? true : savedAccent !== '0'),
  ...DEFAULTS,
  ...restored,
  systemFonts: [],
  /* Runtime-only state (never persisted). */
  exportFormat: detectRecordFormat(),
  /* Where the current accent came from: '' (pending) | 'registry' | 'browser' | 'fixed' | 'none'. */
  accentSource: '',
  accentValue: '',
  /* Best encoder this device can run (see engine/capabilities.js). */
  renderTier: 'unknown',
  renderLabel: '',
  playing: false,
  recording: false,
  status: '',
})

/* Debounced persistence of whitelisted keys. */
let saveTimer = 0
function persistNow() {
  const data = {}
  for (const key of Object.keys(DEFAULTS)) data[key] = state[key]
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch (_) { /* quota / private mode */ }
}
watch(
  () => Object.keys(DEFAULTS).map(k => state[k]),
  () => { clearTimeout(saveTimer); saveTimer = setTimeout(persistNow, 250) },
  { deep: true },
)

export function aliasMap() {
  return aliasMapFromRows(state.aliases)
}

/* ------------------------------------------------------------------ */
/* Font list                                                          */
/* ------------------------------------------------------------------ */

/* Adds an imported family to the candidate lists. Manual free-text input is
   not allowed: entries must come from font files (engine/fonts.js) or from
   the authorized local font scan exposed in Settings. */
function pushFont(family, msg) {
  const exists = state.customFonts.some(f => f.toLowerCase() === family.toLowerCase())
    || state.systemFonts.some(f => f.toLowerCase() === family.toLowerCase())
  if (exists) return { ok: false, msg: '该字体已在列表中' }
  state.customFonts.push(family)
  state.systemFonts.push(family)
  state.systemFonts.sort((a, b) => a.localeCompare(b, 'zh-CN'))
  return { ok: true, msg }
}

/** Registers a family that was imported from a font file this session. */
export function addImportedFont(family, importedCheck) {
  const name = String(family || '').trim()
  if (!name) return { ok: false, msg: '字体文件没有有效家族名' }
  if (typeof importedCheck === 'function' && !importedCheck(name)) {
    return { ok: false, msg: '请先导入字体文件' }
  }
  return pushFont(name, `已添加「${name}」`)
}

/* ------------------------------------------------------------------ */
/* Presets and reset                                                  */
/* ------------------------------------------------------------------ */

/** Applies the suggested [bg1, bg2, accent] palette of a preset. */
export function applyPreset(name) {
  state.preset = name
  const preset = PRESETS[name]
  if (preset && preset.sug) {
    state.bg1 = preset.sug[0]
    state.bg2 = preset.sug[1]
    state.accent = preset.sug[2]
  }
}

/**
 * Records a manual UI accent and moves it to the front of the recent swatches.
 * Kept here so every entry point (picker, palette, tests) updates both at once.
 */
export function setUiAccent(hex) {
  const value = String(hex || '').trim().toUpperCase()
  if (!/^#[0-9A-F]{6}$/.test(value)) return
  state.uiAccent = value
  state.recentAccents = [value, ...state.recentAccents.filter(c => c !== value)].slice(0, 5)
}

/** Restores every setting to its default and clears persisted state. */
export function resetSettings() {
  try {
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem('kinetype-ratio-169-migrated')
    localStorage.setItem('kinetype-ratio-169-migrated', '1')  /* keep the migration from re-applying */
    localStorage.setItem('winui-theme-mode', 'auto')
    localStorage.setItem('winui-accent-system', '1')
  } catch (_) { /* ignore */ }
  for (const key of Object.keys(DEFAULTS)) {
    state[key] = typeof DEFAULTS[key] === 'object' && DEFAULTS[key] !== null
      ? JSON.parse(JSON.stringify(DEFAULTS[key]))
      : DEFAULTS[key]
  }
  state.progress = 0
  state.themeMode = 'auto'
  state.useSystemAccent = true
}

/* ------------------------------------------------------------------ */
/* Theme mode                                                         */
/* ------------------------------------------------------------------ */

/** Applies the html class contract used by WinUIonWeb (theme-light / theme-dark). */
export function applyThemeClass(theme) {
  document.documentElement.classList.remove('theme-light', 'theme-dark')
  document.documentElement.classList.add(theme === 'dark' ? 'theme-dark' : 'theme-light')
}

function resolveTheme() {
  if (state.themeMode !== 'auto') return state.themeMode
  const mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null
  return mq && mq.matches ? 'dark' : 'light'
}

function applyTheme() {
  state.theme = resolveTheme()
  applyThemeClass(state.theme)
}

const themeMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null
if (themeMedia) {
  const onSchemeChange = () => { if (state.themeMode === 'auto') applyTheme() }
  themeMedia.addEventListener ? themeMedia.addEventListener('change', onSchemeChange)
    : themeMedia.addListener && themeMedia.addListener(onSchemeChange)
}

/* ------------------------------------------------------------------ */
/* System accent color                                                */
/* ------------------------------------------------------------------ */

/* Measured fact: CSS `AccentColor` is a hard-coded Chromium blue (#0075ff) and
   does not follow the Windows personalization color. So the real accent comes
   from the bridge Vite serves on ACCENT_ENDPOINT; without it (static hosting,
   file://) we degrade to `AccentColor`, and settings can opt out entirely. */
const ACCENT_ENDPOINT = '__wf/system-colors'
const ACCENT_POLL_MS = 3000

/* Every property publishAccent() may write; clearing must cover all of them. */
const ACCENT_VARS = [
  '--winui-system-accent-color',
  '--winui-system-accent-color-dark',
  '--SystemAccentColorLight1',
  '--SystemAccentColorLight2',
  '--SystemAccentColorLight3',
  '--SystemAccentColorDark1',
  '--SystemAccentColorDark2',
  '--SystemAccentColorDark3',
  '--winui-system-accent-text-light',
  '--winui-system-accent-text-dark',
  '--winui-system-accent-text-secondary-light',
  '--winui-system-accent-text-secondary-dark',
]

let accentTimer = null
let accentListening = false
let accentBusy = false
let accentSignature = ''

/**
 * Reads the browser's own accent as an rgb() string, or null. Note this is the
 * engine default (#0075ff in Chromium), *not* the Windows personalization
 * colour — it is only the fallback when the local bridge is unreachable.
 */
export function resolveSystemAccent() {
  try {
    if (!window.CSS || !window.CSS.supports || !window.CSS.supports('color', 'AccentColor')) return null
    const probe = document.createElement('span')
    probe.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;color:AccentColor'
    ;(document.body || document.documentElement).appendChild(probe)
    const color = getComputedStyle(probe).color.trim()
    probe.remove()
    return /^rgba?\(/.test(color) ? color : null
  } catch {
    return null
  }
}

function parseRgb(color) {
  const m = /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/.exec(color || '')
  return m ? [+m[1], +m[2], +m[3]] : null
}

function relativeLuminance(rgb) {
  const [r, g, b] = rgb.map(v => {
    const c = v / 255
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** Picks black or white for best contrast on the given background. */
function contrastingText(rgb) {
  const L = relativeLuminance(rgb)
  const contrastWithWhite = 1.05 / (L + 0.05)
  const contrastWithBlack = (L + 0.05) / 0.05
  return contrastWithWhite >= contrastWithBlack ? '#FFFFFF' : '#000000'
}

function mixRgb(rgb, target, amount) {
  return rgb.map((c, i) => Math.round(c * (1 - amount) + target[i] * amount))
}

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim())
  if (!m) return null
  const v = parseInt(m[1], 16)
  return [(v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff]
}

function rgbToHex(rgb) {
  return ('#' + rgb.map(c => c.toString(16).padStart(2, '0')).join('')).toUpperCase()
}

/**
 * The ramp steps Windows ships next to the base accent (three lighter, three
 * darker). Mirrored verbatim so buttons, focus rings and text-on-accent match
 * the OS instead of being approximated with color-mix.
 */
const ACCENT_STEPS = ['light1', 'light2', 'light3', 'dark1', 'dark2', 'dark3']

/**
 * Publishes a palette on :root. Inline properties deliberately win over
 * theme.css so the stylesheet keeps working as the fallback path.
 */
export function publishAccent(palette) {
  const base = String(palette.base || palette.accent || '').toUpperCase()
  const rgb = hexToRgb(base)
  if (!rgb) return
  /* Dark surfaces need the lightened step; fall back to a white mix. */
  const dark = String(palette.light2 || rgbToHex(mixRgb(rgb, [255, 255, 255], 0.28))).toUpperCase()
  const darkRgb = hexToRgb(dark)

  const signature = [base, dark, palette.light1, palette.dark1].join('|')
  if (signature === accentSignature) return
  accentSignature = signature

  const root = document.documentElement
  root.style.setProperty('--winui-system-accent-color', base)
  root.style.setProperty('--winui-system-accent-color-dark', dark)
  for (const step of ACCENT_STEPS) {
    if (palette[step]) root.style.setProperty(`--SystemAccentColor${step[0].toUpperCase()}${step.slice(1)}`, palette[step])
  }
  /* Foreground on accent cannot be derived in CSS, so pick black or white here.
     Light theme follows WinUI: the accent fill is a dark blue and the text is
     white even when a strict luminance test would marginally favour black.
     Very light custom accents still flip to black to stay readable. */
  const onAccent = relativeLuminance(rgb) > 0.35 ? '#000000' : '#FFFFFF'
  root.style.setProperty('--winui-system-accent-text-light', onAccent)
  root.style.setProperty('--winui-system-accent-text-dark', contrastingText(darkRgb))
  root.style.setProperty('--winui-system-accent-text-secondary-light',
    onAccent === '#FFFFFF' ? 'rgba(255,255,255,0.70)' : 'rgba(0,0,0,0.70)')
  root.style.setProperty('--winui-system-accent-text-secondary-dark',
    contrastingText(darkRgb) === '#FFFFFF' ? 'rgba(255,255,255,0.70)' : 'rgba(0,0,0,0.70)')
}

/**
 * Polling only makes sense while the bridge answers: the registry can change
 * under us, whereas the browser's own accent never does. Keeping the timer off
 * otherwise also spares static deployments a 404 every few seconds.
 */
function setAccentPolling(on) {
  if (on && accentTimer === null) accentTimer = setInterval(onAccentWake, ACCENT_POLL_MS)
  else if (!on && accentTimer !== null) { clearInterval(accentTimer); accentTimer = null }
}

/**
 * Re-reads the system accent. Prefers the local bridge, then the browser's
 * own accent; publishes nothing when following the system is switched off.
 */
async function refreshSystemAccent() {
  if (!state.useSystemAccent || accentBusy) return
  accentBusy = true
  let palette = null
  try {
    const res = await fetch(new URL(ACCENT_ENDPOINT, document.baseURI), { cache: 'no-store' })
    if (res.ok) palette = await res.json()
  } catch (_) { /* static hosting or file:// — no bridge, degrade below */ }
  accentBusy = false
  if (!state.useSystemAccent) return

  if (palette && palette.accent) {
    state.accentSource = palette.source || 'registry'
    state.accentValue = String(palette.base || palette.accent).toUpperCase()
    publishAccent(palette)
    setAccentPolling(true)
    return
  }
  setAccentPolling(false)
  const rgb = parseRgb(resolveSystemAccent())
  if (!rgb) { state.accentSource = 'none'; return }
  state.accentSource = 'browser'
  state.accentValue = rgbToHex(rgb)
  publishAccent({ accent: state.accentValue })
}

/** Wakes the accent refresh; skipping hidden documents avoids useless fetches. */
function onAccentWake() {
  if (document.visibilityState !== 'hidden') refreshSystemAccent()
}

function startSystemAccentWatch() {
  /* Registered once for the page lifetime: refreshSystemAccent() already
     returns early while following the system is off. Wake events also serve as
     the retry path if the bridge appears only later (e.g. server just started). */
  if (!accentListening) {
    accentListening = true
    document.addEventListener('visibilitychange', onAccentWake)
    window.addEventListener('focus', onAccentWake)
    window.addEventListener('pageshow', onAccentWake)
  }
  refreshSystemAccent()
}

function stopSystemAccentWatch() {
  setAccentPolling(false)
}

/** Drops every inline accent property so theme.css defaults apply again. */
function clearAccentVars() {
  const root = document.documentElement
  for (const name of ACCENT_VARS) root.style.removeProperty(name)
  accentSignature = ''
}

function applyAccentMode(enabled) {
  if (enabled) {
    startSystemAccentWatch()
    return
  }
  stopSystemAccentWatch()
  clearAccentVars()
  /* Manual override wins over the traditional blue, so the UI stays usable on
     systems where neither the bridge nor `AccentColor` can be trusted. */
  const custom = /^#[0-9a-f]{6}$/i.test(state.uiAccent || '') ? state.uiAccent.toUpperCase() : ''
  if (custom) {
    publishAccent({ accent: custom })
    state.accentSource = 'custom'
    state.accentValue = custom
    return
  }
  /* Fixed traditional blue fallback (景泰蓝 / 睛蓝). */
  const root = document.documentElement
  root.style.setProperty('--winui-system-accent-color', '#2775b6')
  root.style.setProperty('--winui-system-accent-color-dark', '#5698c3')
  state.accentSource = 'fixed'
  state.accentValue = '#2775B6'
}

watch(() => state.themeMode, (mode) => {
  localStorage.setItem('winui-theme-mode', mode)
  applyTheme()
})
watch(() => state.useSystemAccent, (enabled) => {
  localStorage.setItem('winui-accent-system', enabled ? '1' : '0')
  applyAccentMode(enabled)
})
/* Only matters while the system color is not followed; re-runs are cheap and
   publishAccent() short-circuits when nothing changed. */
watch(() => state.uiAccent, () => {
  if (!state.useSystemAccent) applyAccentMode(false)
})

applyTheme()
applyAccentMode(state.useSystemAccent)

/* ------------------------------------------------------------------ */
/* Engine options                                                     */
/* ------------------------------------------------------------------ */

/** Snapshot of the settings consumed by the rendering engine. */
export function engineOptions() {
  return {
    text: state.text,
    ratio: state.ratio,
    res: state.res,
    preset: state.preset,
    cadence: state.cadence,
    speed: state.speed,
    fontScale: state.fontScale,
    depth: state.depth,
    accent: state.accent,
    bg1: state.bg1,
    bg2: state.bg2,
    defFont: state.defFont,
    defWeight: state.defWeight,
    aliasMap: aliasMap(),
    rotDir: state.rotDir,
  }
}
