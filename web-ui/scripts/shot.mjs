// Screenshot the WinUI app for visual review (light + dark).
// Usage: node scripts/shot.mjs [port] – expects `vite preview` running on that port.
// Shots land in the web-ui root so they sit next to the app, not inside scripts/.
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const BROWSER = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].find(p => fs.existsSync(p))
if (!BROWSER) { console.error('no chrome/edge found'); process.exit(1) }

const port = process.argv[2] || '63201'
/* One level up: keep screenshots and the throwaway profile out of scripts/. */
const outDir = path.resolve(import.meta.dirname, '..')
const shoot = (url, out) => {
  const abs = path.join(outDir, out)
  execFileSync(BROWSER, [
    '--headless=new', '--disable-gpu', '--window-size=1640,1000', '--hide-scrollbars',
    '--no-proxy-server', '--no-first-run', '--no-default-browser-check',
    `--user-data-dir=${path.join(outDir, '.edge-shot-profile')}`,
    '--virtual-time-budget=8000', `--screenshot=${abs}`,
    url,
  ], { stdio: 'ignore' })
  console.log(fs.existsSync(abs) ? `shot ok: ${out}` : `MISSING: ${out}`)
}

shoot(`http://localhost:${port}/?theme=light`, 'shot-light.png')
shoot(`http://localhost:${port}/?theme=dark`, 'shot-dark.png')
