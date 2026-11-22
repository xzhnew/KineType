/**
 * Icon system.
 *
 * Usage — reference icons by glyph code, mirroring the Segoe Fluent convention:
 *   <AppIcon glyph="&#xE713;" :size="16" />
 *   <AppIcon glyph="E713" :size="16" />        // bare hex
 *   <AppIcon name="settings" :size="16" />     // semantic name
 *
 * Glyph codes resolve to inline SVG from ./icons/*.svg rather than an icon font.
 * Rationale: stroked glyphs survive (icon fonts only keep fills), currentColor
 * follows the theme, and no font licensing or cross-platform coverage issues.
 *
 * To add an icon: drop `xxx.svg` in this folder and register its code below.
 */
import { computed, defineComponent, h } from 'vue'

/* All SVG sources are inlined at build time — no runtime requests. */
const SVG_FILES = import.meta.glob('./*.svg', { query: '?raw', import: 'default', eager: true })

/** Glyph code -> SVG basename. Codes follow Segoe MDL2 / Fluent semantics. */
export const GLYPH_MAP = {
  0xE713: 'settings',     // Settings (gear)
  0xE710: 'add',          // Add (+)
  0xE711: 'remove',       // Remove (x)
  0xE768: 'play',         // Play
  0xE769: 'pause',        // Pause
  0xE8D3: 'font',         // Font (A)
  0xE8E5: 'text',         // Script (document)
  0xE7F9: 'screen',       // Frame (phone)
  0xE9E9: 'rhythm',       // Rhythm
  0xE72C: 'rotate',       // Rotate
  0xE943: 'code',         // Cheat sheet
  0xE65B: 'mode-brush',   // Selection mode (brush, spare)
  0xE771: 'theme',        // Theme / appearance
  0xE7C1: 'theme-light',  // Light
  0xE793: 'theme-auto',   // Auto: half-filled circle with rays
  0xE794: 'theme-dark',   // Dark
  0xE7B3: 'theme-auto',   // Title-bar theme button (same visual as auto)
  0xE790: 'palette',      // Accent color (palette)
  0xE7A2: 'app',          // App mark
}

/** Normalizes any accepted glyph notation to a numeric code point. */
export function normalizeGlyph(glyph) {
  if (glyph == null) return null
  if (typeof glyph === 'number') return glyph
  const s = String(glyph).trim()
  let m = /^&#?x([0-9a-fA-F]+);?$/.exec(s)          // &#xE713; / &#XE713; / #xE713
  if (m) return parseInt(m[1], 16)
  m = /^\\u([0-9a-fA-F]{4})$/.exec(s)                // \uE713
  if (m) return parseInt(m[1], 16)
  m = /^0x([0-9a-fA-F]+)$/.exec(s)                   // 0xE713
  if (m) return parseInt(m[1], 16)
  if (/^[0-9a-fA-F]{3,6}$/.test(s)) return parseInt(s, 16)   // bare E713
  if ([...s].length === 1) return s.codePointAt(0)   // already-parsed single char
  return null
}

/** Resolves a glyph code to its semantic icon name, or null. */
export function glyphToName(glyph) {
  const cp = normalizeGlyph(glyph)
  return cp == null ? null : (GLYPH_MAP[cp] || null)
}

/** Returns raw SVG markup for an icon name (used for Expander.HeaderIcon). */
export function svgFor(name) {
  return SVG_FILES[`./${name}.svg`] ?? ''
}

/* Glyphs are drawn inside a 24-unit viewBox with breathing room, so a 24 px
   box yields roughly a 16 px optical glyph. `size` is therefore the *visible*
   size, and the box is scaled up to compensate for that padding. Keeping this
   in one place is what makes every icon line up optically. */
const ICON_BOX_SCALE = 1.5

function toPixelSize(size) {
  const n = typeof size === 'number' ? size : parseFloat(String(size).replace('px', ''))
  return `${(Number.isFinite(n) ? n : 16) * ICON_BOX_SCALE}px`
}

/** Renders an icon as inline SVG; inherits color via currentColor. */
export const AppIcon = defineComponent({
  name: 'AppIcon',
  props: {
    glyph: { type: [String, Number], default: null },
    name: { type: String, default: null },
    size: { type: [String, Number], default: 16 },
  },
  setup(props) {
    const markup = computed(() => svgFor(glyphToName(props.glyph) || props.name || ''))
    const box = computed(() => toPixelSize(props.size))
    return () => h('span', {
      class: 'app-icon',
      style: { width: box.value, height: box.value },
      innerHTML: markup.value,
    })
  },
})
