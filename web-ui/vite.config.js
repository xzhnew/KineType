import { execFileSync } from 'node:child_process'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import legacy from '@vitejs/plugin-legacy'

/* -------------------------------------------------------------------------- */
/* System colors bridge (dev / preview only)                                  */
/* -------------------------------------------------------------------------- */

/* Browsers do not hand out the Windows personalization color. CSS `AccentColor`
   is a fixed Chromium blue (#0075ff) on every machine, so a page cannot read the
   accent the user picked. This middleware publishes the registry values the OS
   itself uses; a static deployment simply 404s and the client falls back. */
const ACCENT_ROUTE = '/__wf/system-colors'
const DWM_KEY = 'HKCU\\Software\\Microsoft\\Windows\\DWM'
const PALETTE_KEY = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent'
const ACCENT_CACHE_MS = 1500

/** Runs `reg query` and returns the value text; '' when the key is missing. */
function readRegValue(key, name) {
  try {
    const out = execFileSync('reg', ['query', key, '/v', name], {
      encoding: 'utf8',
      windowsHide: true,
      timeout: 2000,
    })
    const m = /REG_(?:DWORD|BINARY)\s+([\s\S]+)/.exec(out)
    /* Long binary values wrap onto continuation lines ending with a backslash. */
    return m ? m[1].replace(/\\\s*\r?\n/g, ' ').trim() : ''
  } catch (_) {
    return ''
  }
}

/** 0xAABBGGRR (DWM layout) -> '#rrggbb'. */
export function dwordToHex(text) {
  const m = /0x([0-9a-fA-F]{8})/.exec(text) || /\b([0-9a-fA-F]{8})\b/.exec(text)
  if (!m) return null
  const v = parseInt(m[1], 16)
  const to2 = c => c.toString(16).padStart(2, '0')
  return ('#' + to2(v & 0xff) + to2((v >> 8) & 0xff) + to2((v >> 16) & 0xff)).toUpperCase()
}

/**
 * Parses the AccentPalette blob into the ramp Windows itself uses. Eight
 * entries, four bytes each; entry 3 is the base, 0..2 lighten, 4..6 darken.
 * The packed channel order is not documented consistently, so we read it both
 * ways and keep whichever base entry matches the DWM accent value.
 */
export function paletteFromText(text, accentHex) {
  const bytes = (String(text).match(/0x([0-9a-fA-F]{2})/g) || []).map(b => parseInt(b.slice(2), 16))
  if (bytes.length < 28 || !accentHex) return null

  const at = (order, i) => ('#' + order.map(k => bytes[i * 4 + k].toString(16).padStart(2, '0'))
    .join('').toUpperCase())
  const rgbOrder = [0, 1, 2]
  const bgrOrder = [2, 1, 0]
  const order = at(rgbOrder, 3) === accentHex ? rgbOrder
    : at(bgrOrder, 3) === accentHex ? bgrOrder : rgbOrder

  return {
    base: at(order, 3),
    light1: at(order, 2),
    light2: at(order, 1),
    light3: at(order, 0),
    dark1: at(order, 4),
    dark2: at(order, 5),
    dark3: at(order, 6),
  }
}

function readSystemColors() {
  if (process.platform !== 'win32') return { source: 'unsupported' }
  const accent = dwordToHex(readRegValue(DWM_KEY, 'AccentColor'))
  if (!accent) return { source: 'none' }
  const palette = paletteFromText(readRegValue(PALETTE_KEY, 'AccentPalette'), accent)
  return { source: 'registry', accent, ...(palette || {}) }
}

function systemColorsPlugin() {
  let cache = { at: 0, data: null }

  const middleware = (_req, res) => {
    const now = Date.now()
    if (!cache.data || now - cache.at > ACCENT_CACHE_MS) cache = { at: now, data: readSystemColors() }
    res.statusCode = 200
    res.setHeader('Content-Type', 'application/json; charset=utf-8')
    res.setHeader('Cache-Control', 'no-store')
    res.end(JSON.stringify(cache.data))
  }

  return {
    name: 'kinetype-system-colors',
    configureServer(server) { server.middlewares.use(ACCENT_ROUTE, middleware) },
    configurePreviewServer(server) { server.middlewares.use(ACCENT_ROUTE, middleware) },
  }
}

export default defineConfig({
  plugins: [
    vue(),
    systemColorsPlugin(),
    /* Emit a SystemJS build for browsers below the modern baseline. The real
       floor is `Proxy` (Chrome 49 / Safari 10 / Firefox 18) because it cannot
       be polyfilled; everything above that can still edit and export. */
    legacy({
      targets: ['chrome >= 49', 'safari >= 10', 'firefox >= 52', 'edge >= 15'],
    }),
  ],
  base: './',
  server: { port: 63200 },
  build: { target: 'es2015' },
})
