<script setup>
/**
 * Left settings pane.
 *
 * Contains the caption script editor, every layout/typography control and the
 * font alias table. Kept in a single file on purpose: these controls share the
 * same state object and are edited together, so one file avoids cross-file hops.
 *
 * SelBox is a thin ComboBox adapter defined inline below; WinUIonWeb's
 * ComboBox emits SelectionChanged with the label, while the app stores values.
 */
import { computed, h, nextTick, onBeforeUnmount, onMounted, ref, resolveComponent, watch } from 'vue'
import { state, applyPreset, addImportedFont } from '../store.js'
import { fontLabel, importFontFile, isImportedFont } from '../engine/fonts.js'
import { AppIcon, svgFor } from '../icons/index.js'

/* @type {import('vue').Component} ComboBox adapter: [{label, value}] <-> value. */
const SelBox = {
  name: 'SelBox',
  props: {
    items: { type: Array, required: true },
    modelValue: { default: undefined },
    header: { type: String, default: '' },
    placeholder: { type: String, default: '' },
    minWidth: { type: [String, Number], default: 0 },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const ComboBox = resolveComponent('ComboBox')
    const labels = computed(() => props.items.map(item => item.label))
    const selectedIndex = computed(() => props.items.findIndex(item => item.value === props.modelValue))
    const onSelectionChanged = (sender, args) => {
      const added = args && args.AddedItems && args.AddedItems[0]
      if (added === undefined) return
      const index = labels.value.indexOf(added)
      if (index >= 0) emit('update:modelValue', props.items[index].value)
    }
    return () => h(ComboBox, {
      ItemsSource: labels.value,
      SelectedIndex: selectedIndex.value,
      Header: props.header,
      PlaceholderText: props.placeholder,
      MinWidth: props.minWidth,
      class: 'wf-sel',
      onSelectionChanged,
    })
  },
}

/* ------------------------------------------------------------------ */
/* Option lists                                                       */
/* ------------------------------------------------------------------ */

const ratioItems = [
  { label: '16:9 横屏', value: '16:9' },
  { label: '9:16 竖屏', value: '9:16' },
  { label: '3:4 竖版', value: '3:4' },
  { label: '4:3 横版', value: '4:3' },
  { label: '4:5 宽屏', value: '4:5' },
  { label: '1:1 方形', value: '1:1' },
  { label: '21:9 电影', value: '21:9' },
]
const resItems = [
  { label: '省流 · 720p', value: '720' },
  { label: '标准 · 1080p', value: '1080' },
  { label: '高清 · 1440p', value: '1440' },
  { label: '4K 超清 · 2160p', value: '2160' },
]
const presetItems = [
  { label: '国风青绿 · 绢本', value: 'guofeng' },
  { label: '抖音爆款 · meme-punch', value: 'meme-punch' },
  { label: '音乐卡点 · beat-flash', value: 'beat-flash' },
  { label: '终端极客 · neon-terminal', value: 'neon-terminal' },
  { label: '日系小清新 · sakura-pop', value: 'sakura-pop' },
  { label: '新闻播报 · broadcast', value: 'broadcast' },
  { label: '复古印刷 · retro-print', value: 'retro-print' },
]
const cadenceItems = [
  { label: '很快 · 4 字/拍', value: 4 },
  { label: '快 · 6 字/拍', value: 6 },
  { label: '中 · 8 字/拍', value: 8 },
  { label: '慢 · 13 字/拍', value: 13 },
]
const rotItems = [
  { label: '向右倒 90°', value: 'cw' },
  { label: '向左倒 90°', value: 'ccw' },
  { label: '左右随机', value: 'rand' },
  { label: '不自动', value: 'none' },
]

/* Default font list pairs every family with Regular and Bold. */
const fontItems = computed(() => {
  const fonts = state.systemFonts.length ? state.systemFonts : ['Microsoft YaHei']
  const out = []
  for (const family of fonts) {
    out.push({ label: `${fontLabel(family)} · 常规`, value: family + ':400' })
    out.push({ label: `${fontLabel(family)} · Bold`, value: family + ':700' })
  }
  return out
})
const defFontValue = computed({
  get: () => `${state.defFont}:${state.defWeight}`,
  set: v => {
    const bits = String(v).split(':')
    state.defFont = bits[0] || 'Microsoft YaHei'
    state.defWeight = +(bits[1] || 400) || 400
  },
})

/* Traditional Chinese color swatches. */
const bgSwatches = [
  { hex: '#223e36', name: '苍绿' }, { hex: '#141e1b', name: '莽丛绿' },
  { hex: '#1f2623', name: '苷蓝绿' }, { hex: '#1a3b32', name: '深海绿' },
  { hex: '#15231b', name: '云杉绿' }, { hex: '#5c2223', name: '暗玉紫' },
  { hex: '#310f1b', name: '墨紫' }, { hex: '#4c1f24', name: '葡萄紫' },
  { hex: '#eef7f2', name: '月白' }, { hex: '#fffef8', name: '象牙白' },
  { hex: '#c6dfc8', name: '淡翠绿' }, { hex: '#f0e7d8', name: '米色' },
]
const accSwatches = [
  { hex: '#dfc243', name: '蒿黄' }, { hex: '#f0d695', name: '象牙黄' },
  { hex: '#c04851', name: '玉红' }, { hex: '#a7535a', name: '满江红' },
  { hex: '#2bae85', name: '铜绿' }, { hex: '#45b787', name: '蛙绿' },
  { hex: '#1661ab', name: '靛青' }, { hex: '#1772b4', name: '群青' },
  { hex: '#134857', name: '苍蓝' }, { hex: '#f28e16', name: '杏黄' },
  { hex: '#894e54', name: '烟红' }, { hex: '#b9dec9', name: '竹篁绿' },
]

const cheat =
`{color:#dfc243}  颜色        {size:1.5}   字号倍数
{font:kai}     字体(短名)   {weight:900}  粗细
{bold}         加粗        {shadow:off}  阴影关
{stroke}       描边开      {stroke:red}  描边色
{strokew:.12}  描边粗细     {spacing:.1}  字距
{转}           整块旋转     {转:-90}      指定方向
{/}            关整段样式   {/color}      只关颜色
[高亮]  **粗体**  |  强制换行  # 注释行  \\{ 转义`

/* ------------------------------------------------------------------ */
/* Script editor: syntax highlighting + quick-format toolbar          */
/* ------------------------------------------------------------------ */

/* Highlighting is done by layering a read-only <pre> under a transparent
   <textarea>: the textarea owns the editing/caret, the pre shows the colors.
   Both must share identical font metrics, padding and content width. */

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }
const escapeHtml = s => s.replace(/[&<>"]/g, c => HTML_ESCAPES[c])

/* Only well-formed color values reach the inline style (no injection). */
const COLOR_TAG = /^color\s*:\s*(#[0-9a-fA-F]{3,8})\s*$/

/** Renders inline markup for one run of escaped text. */
function renderInline(escaped, color) {
  const html = escaped
    .replace(/\[([^\[\]]*)\]/g,
      '<span class="hl-tag">[</span><span class="hl-mark">$1</span><span class="hl-tag">]</span>')
    .replace(/\*\*([^*]+)\*\*/g,
      '<span class="hl-tag">**</span><span class="hl-bold">$1</span><span class="hl-tag">**</span>')
  return color ? `<span style="color:${color}">${html}</span>` : html
}

/* Highlight classes by tag kind — colors defined in theme.css so both themes
   stay readable. */
function tagClass(tag) {
  const t = String(tag).trim().toLowerCase()
  if (t.startsWith('/')) return 'hl-tag hl-close'
  if (t.startsWith('color')) return 'hl-tag hl-color'
  if (t.startsWith('size')) return 'hl-tag hl-size'
  if (t.startsWith('font')) return 'hl-tag hl-font'
  if (t.startsWith('weight') || t === 'bold') return 'hl-tag hl-weight'
  if (t.startsWith('stroke')) return 'hl-tag hl-stroke'
  if (t.startsWith('spacing')) return 'hl-tag hl-spacing'
  if (t.startsWith('转')) return 'hl-tag hl-rotate'
  if (t.startsWith('shadow')) return 'hl-tag hl-shadow'
  return 'hl-tag'
}

/** Converts the caption script to highlighted HTML. Color state spans lines. */
function highlightScript(src) {
  const state = { color: null }
  const out = []
  for (const line of String(src || '').split('\n')) {
    if (/^\s*#/.test(line)) {
      out.push(`<span class="hl-comment">${escapeHtml(line)}</span>`)
      continue
    }
    let html = ''
    let last = 0
    const re = /\{([^{}]*)\}/g
    let match
    while ((match = re.exec(line))) {
      html += renderInline(escapeHtml(line.slice(last, match.index)), state.color)
      const tag = match[1]
      if (tag.startsWith('/')) {
        state.color = null
      } else {
        const colorMatch = COLOR_TAG.exec(tag)
        if (colorMatch) state.color = colorMatch[1]
      }
      html += `<span class="${tagClass(tag)}">{${escapeHtml(tag)}}</span>`
      last = match.index + match[0].length
    }
    html += renderInline(escapeHtml(line.slice(last)), state.color)
    out.push(html)
  }
  return out.join('\n')
}

const highlightedScript = computed(() => highlightScript(state.text))
const highlightedCheat = computed(() => highlightScript(cheat))

const scriptInput = ref(null)
const highlightLayer = ref(null)
const colorPanelOpen = ref(false)

/* Scroll model shared with the WinUI ScrollBar (native bar is hidden). */
const scrollValue = ref(0)
const scrollMax = ref(1)
const scrollViewport = ref(1)

const scriptMsg = ref('')
let scriptMsgTimer = 0
function flashScriptMsg(msg) {
  scriptMsg.value = msg
  clearTimeout(scriptMsgTimer)
  scriptMsgTimer = setTimeout(() => { if (scriptMsg.value === msg) scriptMsg.value = '' }, 2600)
}

/* Size the script box so the collapsed sidebar fills its pane exactly — no
   dead space, no scrollbar. Recomputed on resize; expanding other groups is
   allowed to scroll. Measured from the DOM instead of guessed in CSS because
   Expander header metrics come from WinUIonWeb's stylesheet. */
const EDITOR_MIN = 140
const EDITOR_PAD = 24            /* .wf-scroll padding: 14 top + 10 bottom */

function fitEditor() {
  const scroll = document.querySelector('.wf-scroll')
  const pane = document.querySelector('.wf-pane')
  const editor = document.querySelector('.wf-script-editor')
  if (!scroll || !pane || !editor) return
  const available = scroll.clientHeight - EDITOR_PAD
  const used = [...pane.children].reduce((n, c) => n + c.getBoundingClientRect().height, 0)
  const gaps = (pane.children.length - 1) * 4   /* .wf-pane gap */
  const current = editor.getBoundingClientRect().height
  /* Leave a few pixels of slack so sub-pixel rounding never trips a scrollbar. */
  const target = Math.max(EDITOR_MIN, Math.floor(available - used - gaps + current) - 8)
  editor.style.height = `${target}px`
  nextTick(syncEditorScroll)
}

/** Keeps the highlight layer aligned and mirrors the offset to the ScrollBar. */
function syncEditorScroll() {
  const ta = scriptInput.value
  const hl = highlightLayer.value
  if (!ta) return
  if (hl) { hl.scrollTop = ta.scrollTop; hl.scrollLeft = ta.scrollLeft }
  const max = Math.max(0, ta.scrollHeight - ta.clientHeight)
  scrollMax.value = Math.max(1, max)
  scrollViewport.value = Math.max(1, ta.clientHeight)
  scrollValue.value = Math.min(ta.scrollTop, scrollMax.value)
}

/** ScrollBar drag -> textarea scroll offset. */
function onScriptScrollBarChanged(sender, args) {
  const ta = scriptInput.value
  if (!ta) return
  const next = args && typeof args.NewValue === 'number' ? args.NewValue : scrollValue.value
  if (Math.abs(ta.scrollTop - next) < 0.5) return
  ta.scrollTop = next
  syncEditorScroll()
}

/* A selection that already contains markup would nest tags into garbage. */
const MARKUP_PATTERN = /[{}[\]]/

/* Undo stack. Native execCommand('undo') is unreliable once a menu button
   takes focus, so edits are snapshotted here and restored explicitly. */
const scriptHistory = []
let lastTypeAt = 0
const HISTORY_LIMIT = 100

/** Snapshot the editor before a change so the context-menu Undo can restore it. */
function pushHistory(text, selStart, selEnd) {
  scriptHistory.push({ text, selStart, selEnd })
  if (scriptHistory.length > HISTORY_LIMIT) scriptHistory.shift()
}

/** Coalesce a burst of typing into one undo step (600 ms gap starts a new one). */
function onScriptKeydown(e) {
  const k = e.key
  const typing = k.length === 1 || k === 'Backspace' || k === 'Delete' || k === 'Enter'
  if (!typing || e.ctrlKey || e.metaKey || e.altKey) return
  const now = Date.now()
  if (now - lastTypeAt > 600) {
    const ta = scriptInput.value
    if (ta) pushHistory(state.text, ta.selectionStart, ta.selectionEnd)
  }
  lastTypeAt = now
}

/**
 * Applies an edit to the script while preserving the viewport.
 * Assigning `state.text` replaces the textarea's value, which resets its
 * scroll position; the previous offset is restored after the DOM updates.
 * @param {(text: string, start: number, end: number, selected: string) =>
 *   ({text: string, selStart: number, selEnd: number} | null)} producer
 */
function applyScriptEdit(producer) {
  const ta = scriptInput.value
  if (!ta) return false
  const scrollTop = ta.scrollTop
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = state.text.slice(start, end)
  if (MARKUP_PATTERN.test(selected)) {
    flashScriptMsg('请只选择文字内容，不要包含 {} 或 [] 标记')
    return false
  }
  const result = producer(state.text, start, end, selected)
  if (!result) return false
  pushHistory(state.text, start, end)
  state.text = result.text
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(result.selStart, result.selEnd)
    ta.scrollTop = scrollTop
    syncEditorScroll()
  })
  return true
}

/** Wraps the selection (or a placeholder) with the given tags. */
function wrapScriptSelection(open, close = '{/}', placeholder = '文字') {
  applyScriptEdit((text, start, end, selected) => {
    const body = selected || placeholder
    return {
      text: text.slice(0, start) + open + body + close + text.slice(end),
      selStart: start + open.length,
      selEnd: start + open.length + body.length,
    }
  })
}

/* ------------------------------------------------------------------ */
/* Style tags: merge into the enclosing tag instead of nesting        */
/* ------------------------------------------------------------------ */

/** Tag names that can live inside one `{...}` set as attributes. */
const MERGEABLE_TAG = /^(color|size|font|weight|bold|stroke|strokew|spacing|shadow)\b/i

/**
 * Lists every style tag with its matching `{/}`, using the same flat grammar
 * as the renderer. Rotation is a beat directive rather than a style scope, so
 * it is skipped.
 * @returns {Array<{open: number, openEnd: number, body: string, closeStart: number|null}>}
 */
function listStyleTags(text) {
  const re = /\{(\/?)([^{}]*)\}/g
  const stack = []
  const tags = []
  let m
  while ((m = re.exec(text)) !== null) {
    if (m[1] === '/') {
      /* `{/}` ends a scope; `{/color}` only drops one attribute. */
      if (m[2].trim() === '') {
        const t = stack.pop()
        if (t) t.closeStart = m.index
      }
      continue
    }
    const body = m[2].trim()
    if (!body || /^(转|rot)[:：]?-?\d*$/.test(body)) continue
    const t = { open: m.index, openEnd: m.index + m[0].length, body, closeStart: null }
    stack.push(t)
    tags.push(t)
  }
  return tags
}

/**
 * Innermost style tag whose scope fully covers [start, end).
 * @returns {{open: number, openEnd: number, body: string, closeStart: number} | null}
 */
function findEnclosingTag(text, start, end) {
  let best = null
  for (const t of listStyleTags(text)) {
    if (t.closeStart == null) continue
    if (t.open >= start || t.closeStart < end) continue
    if (!MERGEABLE_TAG.test(t.body)) continue
    if (!best || t.open > best.open) best = t
  }
  return best
}

/**
 * True when the selection covers the tag's whole run. Highlight brackets are
 * decoration, so `{color:…}[文字]{/}` still counts as "all".
 */
function coversTagContent(text, tag, start, end) {
  const from = tag.openEnd + (text[tag.openEnd] === '[' ? 1 : 0)
  const to = tag.closeStart - (text[tag.closeStart - 1] === ']' ? 1 : 0)
  return start <= from && end >= to
}

/** True when a tag body already carries exactly this attribute/value. */
function tagHasAttr(body, name, value) {
  if (value == null) return new RegExp(`(^|\\s)${name}(\\s|$)`, 'i').test(body)
  const m = body.match(new RegExp(`(?:^|\\s)${name}\\s*:\\s*([^\\s}]+)`, 'i'))
  return !!m && m[1].toLowerCase() === String(value).toLowerCase()
}

/** Adds or replaces one attribute inside an existing tag body. */
function mergeTagAttrs(tagBody, name, value) {
  const lower = tagBody.toLowerCase()
  if (value != null) {
    const existing = new RegExp(`${name}\\s*:\\s*[^\\s}]+`, 'i')
    if (existing.test(tagBody)) return tagBody.replace(existing, `${name}:${value}`)
    /* `color` is meaningful once per tag; other valued attrs append too. */
    return `${tagBody} ${name}:${value}`
  }
  if (new RegExp(`(^|\\s)${name}(\\s|$)`, 'i').test(tagBody)) return tagBody
  return `${tagBody} ${name}`
}

/**
 * Applies one style attribute to the selection.
 * - Whole tag selected: merge into it, so tags stay terse.
 * - Part of a tag selected: nest a tag around just the selection, leaving the
 *   rest of the run on its original style.
 * - No tag: wrap the selection (or a placeholder).
 */
function applyStyleTag(name, value = null, placeholder = '文字') {
  applyScriptEdit((text, start, end, selected) => {
    const tag = findEnclosingTag(text, start, end)
    if (tag) {
      const coversAll = coversTagContent(text, tag, start, end)
      if (coversAll) {
        const merged = mergeTagAttrs(tag.body, name, value)
        if (merged === tag.body) return null          /* attribute already set */
        const delta = merged.length - tag.body.length
        return {
          text: text.slice(0, tag.open + 1) + merged + text.slice(tag.openEnd - 1),
          selStart: start + delta,
          selEnd: end + delta,
        }
      }
      /* Partial run: skip when the outer tag already provides this exact
         style, otherwise nest an override around the selection only. */
      if (tagHasAttr(tag.body, name, value)) return null
      const openTag = value == null ? `{${name}}` : `{${name}:${value}}`
      return {
        text: text.slice(0, start) + openTag + text.slice(start, end) + '{/}' + text.slice(end),
        selStart: start + openTag.length,
        selEnd: end + openTag.length,
      }
    }
    const open = value == null ? `{${name}}` : `{${name}:${value}}`
    const body = selected || placeholder
    const text2 = text.slice(0, start) + open + body + '{/}' + text.slice(end)
    /* With no selection, select the numeric value so it can be typed over. */
    if (!selected && value != null) {
      const valueStart = start + 1 + name.length + 1
      return { text: text2, selStart: valueStart, selEnd: valueStart + String(value).length }
    }
    return { text: text2, selStart: start + open.length, selEnd: start + open.length + body.length }
  })
}

/* Size nudge bounds. One decimal keeps tag length stable so repeated clicks
   shift the selection by the same offset every time. */
const SIZE_STEP = 0.1
const SIZE_MIN = 0.4
const SIZE_MAX = 3
const SIZE_BASE = 1

/**
 * Nudges the `size` attribute of the enclosing tag (or wraps the selection in
 * a fresh one). The selection is preserved on the text body so consecutive
 * clicks keep tuning the same value instead of nesting new tags.
 * @param {number} dir +1 enlarges, -1 shrinks
 */
function adjustFontSize(dir) {
  applyScriptEdit((text, start, end, selected) => {
    const tag = findEnclosingTag(text, start, end)
    if (tag) {
      const coversAll = coversTagContent(text, tag, start, end)
      const m = tag.body.match(/size\s*:\s*([0-9.]+)/i)
      const cur = m ? parseFloat(m[1]) : SIZE_BASE
      const next = Math.min(SIZE_MAX, Math.max(SIZE_MIN,
        Math.round((cur + dir * SIZE_STEP) * 10) / 10)).toFixed(1)

      if (coversAll) {
        /* 1.0 is the implicit default: drop the attribute instead of spelling
           it out, so tags stay terse ({font:kai} not {font:kai size:1.0}). */
        const neutral = next === '1.0'
        const merged = m
          ? (neutral ? tag.body.replace(/\s*size\s*:\s*[0-9.]+/i, '').trim()
                     : tag.body.replace(/size\s*:\s*[0-9.]+/i, `size:${next}`))
          : (neutral ? tag.body : `${tag.body} size:${next}`)
        /* Size was the only attribute: remove the whole tag pair, keep text. */
        if (!merged) {
          const openLen = tag.openEnd - tag.open
          return {
            text: text.slice(0, tag.open) + text.slice(tag.openEnd, tag.closeStart)
              + text.slice(tag.closeStart + 3),
            selStart: start - openLen,
            selEnd: end - openLen,
          }
        }
        const delta = merged.length - tag.body.length
        return {
          text: text.slice(0, tag.open + 1) + merged + text.slice(tag.openEnd - 1),
          selStart: start + delta,
          selEnd: end + delta,
        }
      }

      /* Partial run: nesting is the only way to override the outer size.
         "1" is the shortest form of the neutral value when it must be written. */
      const value = next === '1.0' ? '1' : next
      if (tagHasAttr(tag.body, 'size', value)) return null
      const openTag = `{size:${value}}`
      return {
        text: text.slice(0, start) + openTag + text.slice(start, end) + '{/}' + text.slice(end),
        selStart: start + openTag.length,
        selEnd: end + openTag.length,
      }
    }
    /* No enclosing tag: base is 1.0, so a single nudge never lands on neutral. */
    const next = (SIZE_BASE + dir * SIZE_STEP).toFixed(1)
    const open = `{size:${next}}`
    const body = selected || '文字'
    return {
      text: text.slice(0, start) + open + body + '{/}' + text.slice(end),
      selStart: start + open.length,
      selEnd: start + open.length + body.length,
    }
  })
}

/** Inserts text at the caret, replacing the selection. */
function insertScriptText(insert) {
  applyScriptEdit((text, start, end) => ({
    text: text.slice(0, start) + insert + text.slice(end),
    selStart: start + insert.length,
    selEnd: start + insert.length,
  }))
}

/** Prefixes the caret's line (used by the comment button). */
function prefixScriptLine(prefix) {
  applyScriptEdit((text, start) => {
    const lineStart = text.lastIndexOf('\n', start - 1) + 1
    return {
      text: text.slice(0, lineStart) + prefix + text.slice(lineStart),
      selStart: start + prefix.length,
      selEnd: start + prefix.length,
    }
  })
}

/* Quick-format buttons. Style tags merge into an enclosing `{…}` tag when one
   is present, so repeated clicks build `{color:#dfc243 bold stroke}` instead of
   nesting layers. */
const SCRIPT_TOOLS = [
  { id: 'bold', icon: 'tb-bold', label: 'B', title: '加粗  bold（合并到已有标记）', run: () => applyStyleTag('bold') },
  { id: 'color', icon: 'tb-color', label: '◐', title: '文字颜色（合并或替换 color）', color: true },
  { id: 'sizeUp', icon: 'tb-size-up', label: 'A⁺', title: '字号放大  size +0.1（可连续点）', run: () => adjustFontSize(1) },
  { id: 'sizeDown', icon: 'tb-size-down', label: 'A⁻', title: '字号缩小  size -0.1（可连续点）', run: () => adjustFontSize(-1) },
  { id: 'font', icon: 'tb-font', label: 'f', italic: true, title: '换字体  font:kai（合并到已有标记）', run: () => applyStyleTag('font', 'kai') },
  { id: 'mark', icon: 'tb-mark', label: '▮', title: '高亮  [文字]', run: () => wrapScriptSelection('[', ']') },
  { id: 'rotate', icon: 'tb-rotate', label: '↻', title: '整块旋转  {转}', run: () => wrapScriptSelection('{转}') },
  { id: 'stroke', icon: 'tb-stroke', label: '◎', title: '描边  stroke（合并到已有标记）', run: () => applyStyleTag('stroke') },
  { id: 'shadow', icon: 'tb-shadow', label: '◑', title: '关闭阴影  shadow:off', run: () => applyStyleTag('shadow', 'off') },
  { id: 'spacing', icon: 'tb-spacing', label: '↔', title: '字距  spacing（可改数字）', run: () => applyStyleTag('spacing', '0.1') },
  { id: 'comment', icon: 'tb-comment', label: '#', title: '注释行', run: () => prefixScriptLine('# ') },
  { id: 'break', icon: 'tb-break', label: '↵', title: '强制换行', run: () => insertScriptText('|') },
]

/* Traditional palette picks for quick text coloring. */
const TEXT_COLORS = ['#c04851', '#dfc243', '#2bae85', '#1661ab', '#894e54', '#eef7f2']

function applyTextColor(hex) {
  colorPanelOpen.value = false
  applyStyleTag('color', hex)
}

/* ------------------------------------------------------------------ */
/* Editor context menu                                                */
/* ------------------------------------------------------------------ */

/* Right-clicking inside a textarea can move the caret, so the selection is
   captured on button-down and restored before the menu opens. */
let ctxSavedSelection = { start: 0, end: 0 }

const ctxMenu = ref({ open: false, x: 0, y: 0 })
const CTX_MENU_WIDTH = 240
const CTX_MENU_HEIGHT = 500

/* Clipboard group mirrors the native Windows menu; the second group applies
   the same commands as the toolbar, to the current selection only. */
const CTX_MENU = [
  { id: 'cut', icon: 'cut', label: '剪切', hint: 'Ctrl+X', run: () => document.execCommand('cut') },
  { id: 'copy', icon: 'copy', label: '复制', hint: 'Ctrl+C', run: () => document.execCommand('copy') },
  { id: 'paste', icon: 'paste', label: '粘贴', hint: 'Ctrl+V', run: () => pasteFromClipboard() },
  { id: 'undo', icon: 'undo', label: '撤消', hint: 'Ctrl+Z', run: () => undoEdit() },
  { id: 'selectAll', icon: 'select-all', label: '全选', hint: 'Ctrl+A', run: () => scriptInput.value?.select() },
  { sep: true },
  { id: 'bold', icon: 'bold', label: '加粗', run: () => applyStyleTag('bold') },
  { id: 'stroke', icon: 'stroke', label: '描边', run: () => applyStyleTag('stroke') },
  { id: 'sizeUp', icon: 'size-up', label: '字号放大', run: () => adjustFontSize(1) },
  { id: 'sizeDown', icon: 'size-down', label: '字号缩小', run: () => adjustFontSize(-1) },
  { id: 'font', icon: 'font', label: '换字体 kai', run: () => applyStyleTag('font', 'kai') },
  { id: 'mark', icon: 'highlight', label: '高亮', run: () => wrapScriptSelection('[', ']') },
  { id: 'break', icon: 'break', label: '强制换行', run: () => insertScriptText('|') },
  { id: 'rotate', icon: 'rotate', label: '整块旋转', run: () => wrapScriptSelection('{转}') },
]

/** Restores the last editor snapshot taken before an edit or typing burst. */
function undoEdit() {
  const snap = scriptHistory.pop()
  if (!snap) { flashScriptMsg('没有可撤消的操作'); return }
  state.text = snap.text
  lastTypeAt = 0
  nextTick(() => {
    const ta = scriptInput.value
    if (ta) { ta.focus(); ta.setSelectionRange(snap.selStart, snap.selEnd) }
    syncEditorScroll()
  })
}

function onEditorMouseDown(e) {
  if (e.button !== 2) return
  const ta = scriptInput.value
  if (ta) ctxSavedSelection = { start: ta.selectionStart, end: ta.selectionEnd }
}

function onEditorContextMenu(e) {
  e.preventDefault()
  const ta = scriptInput.value
  if (ta) {
    ta.focus()
    /* Restore the pre-click selection so the action applies to what the user
       had highlighted, not to the caret position right-click produced. */
    if (ctxSavedSelection.start !== ctxSavedSelection.end) {
      ta.setSelectionRange(ctxSavedSelection.start, ctxSavedSelection.end)
    }
  }
  ctxMenu.value = {
    open: true,
    x: Math.max(8, Math.min(e.clientX, window.innerWidth - CTX_MENU_WIDTH - 8)),
    y: Math.max(8, Math.min(e.clientY, window.innerHeight - CTX_MENU_HEIGHT - 8)),
  }
}

function closeCtxMenu() {
  if (ctxMenu.value.open) ctxMenu.value.open = false
}

function runCtxItem(item) {
  closeCtxMenu()
  item.run()
}

/** Clipboard read needs a user gesture and permission; fall back with a hint. */
async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    if (text) insertScriptText(text)
  } catch (_) {
    flashScriptMsg('浏览器未允许读取剪贴板，请用 Ctrl+V 粘贴')
  }
}

function onDocPointerDown(e) {
  if (!ctxMenu.value.open) return
  if (e.target instanceof Element && e.target.closest('.wf-ctx-menu')) return
  closeCtxMenu()
}

function onDocKeyDown(e) {
  if (e.key === 'Escape') closeCtxMenu()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocPointerDown, true)
  document.addEventListener('keydown', onDocKeyDown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  document.removeEventListener('keydown', onDocKeyDown)
})

/* Keep the ScrollBar range in sync with the content height. */
onMounted(() => {
  nextTick(() => { fitEditor(); syncEditorScroll() })
  window.addEventListener('resize', fitEditor)
})
onBeforeUnmount(() => window.removeEventListener('resize', fitEditor))
watch(() => state.text, () => nextTick(syncEditorScroll))

/* ------------------------------------------------------------------ */
/* Font alias table                                                   */
/* ------------------------------------------------------------------ */

const aliasMsg = ref('')
const fontFileInput = ref(null)
let aliasMsgTimer = 0

function flashAlias(msg) {
  aliasMsg.value = msg
  clearTimeout(aliasMsgTimer)
  aliasMsgTimer = setTimeout(() => { if (aliasMsg.value === msg) aliasMsg.value = '' }, 3000)
}

/** Families available in a row's dropdown, excluding families used by other rows. */
function aliasFontItems(row) {
  const taken = new Set(state.aliases.filter(r => r !== row).map(r => r.font))
  let fonts = state.systemFonts.filter(f => !taken.has(f))
  if (!fonts.length) fonts = state.systemFonts.slice()
  return fonts.map(f => ({ label: fontLabel(f), value: f }))
}

function addAliasRow() {
  const taken = new Set(state.aliases.map(r => r.font))
  const next = state.systemFonts.find(f => !taken.has(f)) || state.systemFonts[0] || 'Microsoft YaHei'
  state.aliases.push({ font: next, alias: '' })
}

function removeAliasRow(index) {
  state.aliases.splice(index, 1)
}

/** Imports a font file and appends a ready-to-name alias row. */
async function onFontFilePicked(event) {
  const file = event.target.files && event.target.files[0]
  if (!file) return
  const result = await importFontFile(file)
  if (!result.ok) { flashAlias(result.msg); event.target.value = ''; return }
  const added = addImportedFont(result.family, isImportedFont)
  if (added.ok) state.aliases.push({ font: result.family, alias: '' })
  flashAlias(added.ok ? result.msg : added.msg)
  event.target.value = ''
}
</script>

<template>
  <div class="wf-pane">

    <!-- Script editor with syntax highlighting and quick-format toolbar -->
    <Expander Header="文案" :HeaderIcon="svgFor('text')" IsExpanded="True" HorizontalAlignment="Stretch" class="wf-exp">
      <div class="wf-exp-body">
        <div class="wf-script-tools">
          <Button v-for="tool in SCRIPT_TOOLS" :key="tool.id" class="wf-tool-btn"
            :title="tool.title"
            @Click="tool.color ? (colorPanelOpen = !colorPanelOpen) : tool.run()">
            <AppIcon v-if="tool.icon" :name="tool.icon" :size="16" class="wf-tool-icon" />
            <span v-else class="wf-tool-label" :class="{ 'wf-tool-italic': tool.italic }">{{ tool.label }}</span>
          </Button>
        </div>

        <div v-if="scriptMsg" class="wf-hint wf-script-msg">{{ scriptMsg }}</div>

        <div v-if="colorPanelOpen" class="wf-script-colors">
          <Button v-for="c in TEXT_COLORS" :key="c" class="wf-color-btn"
            :ToolTipService.ToolTip="c" @Click="applyTextColor(c)">
            <span class="wf-color-dot" :style="{ background: c }" />
          </Button>
        </div>

        <div class="wf-script-editor"
          @contextmenu="onEditorContextMenu"
          @mousedown="onEditorMouseDown">
          <pre ref="highlightLayer" class="wf-script-hl" aria-hidden="true" v-html="highlightedScript"></pre>
          <textarea
            ref="scriptInput"
            v-model="state.text"
            class="wf-script-ta"
            spellcheck="false"
            placeholder="每行一句 · 空行分组"
            @scroll="syncEditorScroll"
            @keydown="onScriptKeydown"
          />
          <ScrollBar
            Orientation="Vertical"
            class="wf-script-scrollbar"
            :Minimum="0"
            :Maximum="scrollMax"
            :Value="scrollValue"
            :ViewportSize="scrollViewport"
            @ValueChanged="onScriptScrollBarChanged"
          />
        </div>
      </div>
    </Expander>

    <!-- Syntax cheat sheet (highlighted with the same tokenizer) -->
    <Expander Header="语法速查" :HeaderIcon="svgFor('code')" HorizontalAlignment="Stretch" class="wf-exp">
      <pre class="wf-cheat" v-html="highlightedCheat"></pre>
    </Expander>

    <!-- Frame and style -->
    <Expander Header="画面" :HeaderIcon="svgFor('screen')" HorizontalAlignment="Stretch" class="wf-exp">
      <div class="wf-exp-body">
        <div class="wf-row">
          <SelBox :items="ratioItems" v-model="state.ratio" header="画幅" />
          <SelBox :items="resItems" v-model="state.res" header="清晰度" />
        </div>
        <div class="wf-row">
          <SelBox :items="presetItems" :model-value="state.preset" header="风格" @update:model-value="applyPreset" />
          <SelBox :items="cadenceItems" v-model="state.cadence" header="节奏" />
        </div>
      </div>
    </Expander>

    <!-- Pace and type size -->
    <Expander Header="节奏与字号" :HeaderIcon="svgFor('rhythm')" HorizontalAlignment="Stretch" class="wf-exp">
      <div class="wf-exp-body">
        <div>
          <div class="wf-color-label">语速
            <NumberBox v-model:Value="state.speed" :Minimum="6" :Maximum="26" :SmallChange="1"
              Width="90" HorizontalAlignment="Left" class="wf-numbox" />
            <span class="tname">字/秒</span>
          </div>
          <Slider v-model:Value="state.speed" :Minimum="6" :Maximum="26" :StepFrequency="1" />
        </div>
        <div>
          <div class="wf-color-label">文字大小
            <NumberBox v-model:Value="state.fontScale" :Minimum="40" :Maximum="200" :SmallChange="5"
              Width="90" HorizontalAlignment="Left" class="wf-numbox" />
            <span class="tname">%</span>
          </div>
          <Slider v-model:Value="state.fontScale" :Minimum="40" :Maximum="200" :StepFrequency="5" />
        </div>
        <div>
          <div class="wf-color-label">远近缩放
            <NumberBox v-model:Value="state.depth" :Minimum="-50" :Maximum="60" :SmallChange="5"
              Width="90" HorizontalAlignment="Left" class="wf-numbox" />
            <span class="tname">%</span>
          </div>
          <Slider v-model:Value="state.depth" :Minimum="-50" :Maximum="60" :StepFrequency="5" />
        </div>
      </div>
    </Expander>

    <!-- Fonts: default family, auto-rotate direction, alias table -->
    <Expander Header="字体" :HeaderIcon="svgFor('font')" HorizontalAlignment="Stretch" class="wf-exp">
      <div class="wf-exp-body">
        <div class="wf-row">
          <SelBox :items="fontItems" v-model="defFontValue" header="默认字体" />
          <SelBox :items="rotItems" v-model="state.rotDir" header="自动旋转方向" />
        </div>

        <div class="wf-alias-list">
          <div v-for="(row, i) in state.aliases" :key="i" class="wf-alias-row">
            <SelBox :items="aliasFontItems(row)" :model-value="row.font" min-width="0"
              @update:model-value="v => { row.font = v }" />
            <TextBox :Text="row.alias" PlaceholderText="短名" MaxLength="24" class="wf-alias-short"
              @update:Text="v => { row.alias = v }" />
            <Button class="wf-alias-del" ToolTipService.ToolTip="删除这一行" @Click="removeAliasRow(i)">
              <AppIcon glyph="&#xE711;" :size="16" />
            </Button>
          </div>

          <div class="wf-alias-tools">
            <Button class="wf-alias-addrow" ToolTipService.ToolTip="添加一行" @Click="addAliasRow">
              <AppIcon glyph="&#xE710;" :size="16" />
            </Button>
            <Button class="wf-alias-import" ToolTipService.ToolTip="导入字体文件（ttf/otf/ttc/woff/woff2）"
              @Click="fontFileInput && fontFileInput.click()">
              <AppIcon glyph="&#xE8E5;" :size="16" />
              <span>导入字体</span>
            </Button>
            <input ref="fontFileInput" type="file" accept=".ttf,.otf,.ttc,.woff,.woff2"
              class="wf-font-file-input" @change="onFontFilePicked" />
          </div>

          <div v-if="aliasMsg" class="wf-hint wf-addfont-msg">{{ aliasMsg }}</div>
        </div>
      </div>
    </Expander>

    <!-- Background and accent colors -->
    <Expander Header="背景与强调色" :HeaderIcon="svgFor('palette')" HorizontalAlignment="Stretch" class="wf-exp">
      <div class="wf-exp-body">
        <div class="wf-color-block">
          <div class="wf-color-label">背景色 1</div>
          <div class="wf-color-row">
            <input type="color" v-model="state.bg1" class="wf-native-color" />
            <TextBox v-model:Text="state.bg1" MaxLength="7" class="wf-hex" />
          </div>
          <div class="wf-swatch-grid">
            <button v-for="c in bgSwatches" :key="'b1'+c.hex" class="wf-swatch" :class="{ selected: state.bg1.toLowerCase() === c.hex }"
              :style="{ background: c.hex }" :title="c.name" @click="state.bg1 = c.hex" />
          </div>
        </div>
        <div class="wf-color-block">
          <div class="wf-color-label">背景色 2</div>
          <div class="wf-color-row">
            <input type="color" v-model="state.bg2" class="wf-native-color" />
            <TextBox v-model:Text="state.bg2" MaxLength="7" class="wf-hex" />
          </div>
          <div class="wf-swatch-grid">
            <button v-for="c in bgSwatches" :key="'b2'+c.hex" class="wf-swatch" :class="{ selected: state.bg2.toLowerCase() === c.hex }"
              :style="{ background: c.hex }" :title="c.name" @click="state.bg2 = c.hex" />
          </div>
        </div>
        <div class="wf-color-block">
          <div class="wf-color-label">强调色</div>
          <div class="wf-color-row">
            <input type="color" v-model="state.accent" class="wf-native-color" />
            <TextBox v-model:Text="state.accent" MaxLength="7" class="wf-hex" />
          </div>
          <div class="wf-swatch-grid">
            <button v-for="c in accSwatches" :key="'a'+c.hex" class="wf-swatch" :class="{ selected: state.accent.toLowerCase() === c.hex }"
              :style="{ background: c.hex }" :title="c.name" @click="state.accent = c.hex" />
          </div>
        </div>
      </div>
    </Expander>

    <!-- Editor context menu. Teleported to body: the sidebar's scroll
         container establishes a containing block, which would otherwise clip
         a fixed-position menu to the navigation pane. -->
    <Teleport to="body">
      <div v-if="ctxMenu.open" class="wf-ctx-menu"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        role="menu" @pointerdown.stop>
        <template v-for="(item, i) in CTX_MENU" :key="item.id || 'sep' + i">
          <div v-if="item.sep" class="wf-ctx-sep" />
          <button v-else type="button" class="wf-ctx-item" role="menuitem"
            @click="runCtxItem(item)">
            <AppIcon v-if="item.icon" :name="item.icon" :size="16" class="wf-ctx-icon" />
            <span class="wf-ctx-label">{{ item.label }}</span>
            <span v-if="item.hint" class="wf-ctx-hint">{{ item.hint }}</span>
          </button>
        </template>
      </div>
    </Teleport>

  </div>
</template>
