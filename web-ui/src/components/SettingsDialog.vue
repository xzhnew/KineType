<script setup>
/**
 * Settings dialog (Windows 11 style row cards).
 *
 * Hosted in a WinUIonWeb ContentDialog. Notes:
 * - "System fonts" triggers the Local Font Access permission prompt. Chromium
 *   requires transient user activation, so this must stay behind a click.
 * - Reset uses a two-step confirmation (arm, then confirm within 3 s).
 * - The theme dropdown is a lightweight inline flyout: a native ComboBox is
 *   unusable here because its portal-ed flyout is painted above the dialog but
 *   does not receive pointer events (hit-testing falls through to the dialog),
 *   so items can never be clicked. The flyout below replicates the native
 *   ComboBox look: opaque surface, 8 px radius, accent bar on the selection.
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { state, resetSettings, setUiAccent } from '../store.js'
import { AppIcon } from '../icons/index.js'
import { hasLocalFontAccess, requestLocalFonts, loadSavedLocalFonts } from '../engine/fonts.js'

/* ------------------------------------------------------------------ */
/* Theme mode dropdown                                                */
/* ------------------------------------------------------------------ */

const THEME_MODES = [
  { label: '跟随系统', value: 'auto' },
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' },
]

const comboRoot = ref(null)
const comboOpen = ref(false)
const themeModeLabel = computed(() =>
  (THEME_MODES.find(item => item.value === state.themeMode) || THEME_MODES[0]).label)

function toggleThemeCombo() {
  comboOpen.value = !comboOpen.value
}

function pickThemeMode(item) {
  state.themeMode = item.value
  comboOpen.value = false
}

function onDocumentPointerDown(event) {
  if (comboOpen.value && comboRoot.value && !comboRoot.value.contains(event.target)) {
    comboOpen.value = false
  }
  if (accentOpen.value && accentRoot.value && !accentRoot.value.contains(event.target)) {
    accentOpen.value = false
  }
}

function onDocumentKeyDown(event) {
  if (event.key === 'Escape') {
    comboOpen.value = false
    accentOpen.value = false
  }
}

/* ------------------------------------------------------------------ */
/* Accent palette dropdown                                            */
/* ------------------------------------------------------------------ */

/* Sampled from the Windows 11 主题色 swatch grid. Keeping the literals here
   (rather than generating a hue ramp) means the picker matches Windows exactly. */
const WINDOWS_COLORS = [
  '#FFB900', '#FF8C00', '#F7630C', '#CA5010', '#DA3B01', '#EF6950', '#D13438', '#FF4343', '#E74856',
  '#E81123', '#EA005E', '#C30052', '#E3008C', '#BF0077', '#C239B3', '#9A0089', '#0078D4', '#0063B1',
  '#8E8CD8', '#6B69D6', '#8764B8', '#744DA9', '#B146C2', '#881798', '#0099BC', '#2D7D9A', '#00B7C3',
  '#038387', '#00B294', '#018574', '#00CC6A', '#10893E', '#7A7574', '#5D5A58', '#68768A', '#515C6B',
  '#567C73', '#486860', '#498205', '#107C10', '#767676', '#4C4A48', '#69797E', '#4A5459', '#647C64',
  '#525E54', '#847545', '#7E735F',
]
const DEFAULT_RECENT = ['#0078D4', '#986C2E', '#8EE3F0', '#00B7C3', '#4C4A48']

const accentRoot = ref(null)
const accentOpen = ref(false)
const currentAccent = computed(() => (state.uiAccent || '#2775B6').toUpperCase())
const triggerColor = computed(() => state.useSystemAccent && state.accentValue
  ? state.accentValue : currentAccent.value)
const recentColors = computed(() => [...state.recentAccents,
  ...DEFAULT_RECENT.filter(color => !state.recentAccents.includes(color))].slice(0, 5))

function toggleAccentCombo() {
  accentOpen.value = !accentOpen.value
}

/* Picking any colour implies manual mode, exactly like Windows: the system
   mode is a separate switch at the top of the flyout. */
function pickAccent(hex) {
  state.useSystemAccent = false
  setUiAccent(hex)
  accentOpen.value = false
}

/* ------------------------------------------------------------------ */
/* System font scan (Local Font Access API)                           */
/* ------------------------------------------------------------------ */

/* Re-checked on every open: the API surface can differ between contexts
   (e.g. plain http on a LAN address is not a secure context). */
const fontSupported = ref(hasLocalFontAccess())
const savedLocalFontCount = loadSavedLocalFonts().length
const fontGranted = ref(savedLocalFontCount > 0)
const fontCount = ref(savedLocalFontCount)
const fontBusy = ref(false)
const fontNote = ref('')

const fontSub = computed(() => {
  if (!fontSupported.value) return '当前环境未开放本地字体访问（需 Chrome/Edge，且通过 localhost 或 HTTPS 打开）'
  if (fontNote.value) return fontNote.value
  return fontGranted.value
    ? `已识别本机 ${fontCount.value} 种字体 · 可重新授权以更新`
    : '授权后读取本机全部字体（浏览器会弹窗确认）'
})
const fontBtnText = computed(() => {
  if (fontBusy.value) return '读取中…'
  return fontGranted.value ? '重新识别' : '授权读取'
})

/* Browsers hide the Windows accent color, so report where the current one came
   from instead of pretending the stylesheet always has it. */
const accentSub = computed(() => {
  if (!state.useSystemAccent) {
    return state.accentSource === 'custom'
      ? `手动指定 · ${state.accentValue}`
      : '使用景泰蓝 / 睛蓝，不读取系统颜色'
  }
  switch (state.accentSource) {
    case 'registry': return `已跟随系统 · ${state.accentValue}`
    case 'browser': return '读不到系统颜色，暂用浏览器自带强调色'
    case 'none': return '当前环境不提供强调色'
    default: return '正在读取系统强调色…'
  }
})

function onPickAccent(event) {
  state.useSystemAccent = false
  setUiAccent(event.target.value)
}

async function onGrantFonts() {
  if (!fontSupported.value || fontBusy.value) return
  fontBusy.value = true
  const result = await requestLocalFonts()
  fontBusy.value = false
  if (result.ok) {
    state.systemFonts = [...new Set([...state.systemFonts, ...result.names])]
      .sort((a, b) => a.localeCompare(b, 'zh-CN'))
    fontGranted.value = true
    fontCount.value = result.names.length
    fontNote.value = ''
  } else {
    fontNote.value = result.msg
    setTimeout(() => { if (fontNote.value === result.msg) fontNote.value = '' }, 4000)
  }
}

/* ------------------------------------------------------------------ */
/* Reset (two-step confirmation)                                      */
/* ------------------------------------------------------------------ */

const RESET_CONFIRM_WINDOW_MS = 3000
const resetLabel = ref('重置')
let resetArmed = false
let resetTimer = 0

/** First click arms the action; a second click within 3 s performs the reset. */
function onReset() {
  if (!resetArmed) {
    resetArmed = true
    resetLabel.value = '确认重置？'
    clearTimeout(resetTimer)
    resetTimer = setTimeout(() => {
      resetArmed = false
      resetLabel.value = '重置'
    }, RESET_CONFIRM_WINDOW_MS)
    return
  }
  clearTimeout(resetTimer)
  resetArmed = false
  resetLabel.value = '重置'
  resetSettings()
}

/* ------------------------------------------------------------------ */
/* Dialog plumbing                                                    */
/* ------------------------------------------------------------------ */

const dialogRef = ref(null)
let pending = false

/** Opens the dialog; resolves when it closes so the caller can sync its state. */
function open() {
  if (!dialogRef.value || pending) return Promise.resolve()
  fontSupported.value = hasLocalFontAccess()
  pending = true
  try {
    const promise = dialogRef.value.ShowAsync?.()
    if (promise && typeof promise.finally === 'function') {
      return promise.finally(() => { pending = false })
    }
    pending = false
  } catch {
    pending = false
  }
  return Promise.resolve()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown, true)
  document.addEventListener('keydown', onDocumentKeyDown)
  /* ?dialog=settings opens the dialog on launch (used by screenshots/tests). */
  if (new URLSearchParams(location.search).get('dialog') === 'settings') {
    setTimeout(open, 400)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
  document.removeEventListener('keydown', onDocumentKeyDown)
  clearTimeout(resetTimer)
})

defineExpose({ open })
</script>

<template>
  <ContentDialog ref="dialogRef" Title="设置" CloseButtonText="关闭" DefaultButton="Close">

    <!-- Appearance -->
    <div class="sd-group">
      <div class="sd-section">外观</div>

      <div class="sd-row-card">
        <AppIcon class="sd-row-icon" glyph="&#xE793;" :size="16" />
        <div class="sd-row-text">
          <div class="sd-row-title">选择模式</div>
          <div class="sd-row-sub">选择应用颜色模式</div>
        </div>

        <div class="wc sd-theme-combo" ref="comboRoot">
          <button type="button" class="wc-combo" :class="{ open: comboOpen }"
            :aria-expanded="comboOpen" aria-label="选择模式" @click="toggleThemeCombo">
            <span class="wc-value">{{ themeModeLabel }}</span>
            <svg class="wc-chev" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 6 L8 10.5 L12.5 6" fill="none" stroke="currentColor"
                stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <transition name="wc-pop">
            <div v-if="comboOpen" class="wc-flyout" role="listbox">
              <button v-for="item in THEME_MODES" :key="item.value" type="button"
                class="wc-item" :class="{ selected: item.value === state.themeMode }"
                role="option" :aria-selected="item.value === state.themeMode"
                @click="pickThemeMode(item)">
                <span class="wc-item-label">{{ item.label }}</span>
              </button>
            </div>
          </transition>
        </div>
      </div>

      <!-- One card for colour: the follow-system switch lives at the top of the
           flyout, mirroring Windows Settings instead of stacking two cards. -->
      <div class="sd-row-card">
        <AppIcon class="sd-row-icon" glyph="&#xE790;" :size="16" />
        <div class="sd-row-text">
          <div class="sd-row-title">主题色</div>
          <div class="sd-row-sub">{{ accentSub }}</div>
        </div>
        <div class="wc sd-accent-combo" ref="accentRoot">
          <button type="button" class="wc-combo" :class="{ open: accentOpen }"
            :aria-expanded="accentOpen" aria-label="主题色" @click="toggleAccentCombo">
            <span class="sd-accent-chip" :style="{ background: triggerColor }" />
            <span class="wc-value">{{ state.useSystemAccent ? '跟随系统' : currentAccent }}</span>
            <svg class="wc-chev" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 6 L8 10.5 L12.5 6" fill="none" stroke="currentColor"
                stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <transition name="wc-pop">
            <div v-if="accentOpen" class="wc-flyout sd-accent-flyout">
              <div class="sd-accent-auto">
                <div class="sd-accent-auto-text">
                  <div class="sd-accent-auto-title">跟随系统</div>
                  <div class="sd-accent-auto-sub">使用 Windows 个性化颜色</div>
                </div>
                <!-- Empty labels would fall back to 开/关 and crowd the flyout. -->
                <ToggleSwitch v-model:IsOn="state.useSystemAccent"
                  OnContent=" " OffContent=" " class="sd-switch-bare" />
              </div>
              <div class="sd-palette-title">最近使用的颜色</div>
              <div class="sd-swatch-row">
                <button v-for="color in recentColors" :key="color" type="button"
                  class="sd-swatch" :class="{ selected: !state.useSystemAccent && color === currentAccent }"
                  :style="{ background: color }" :title="color" :aria-label="color"
                  @click="pickAccent(color)">
                  <span v-if="!state.useSystemAccent && color === currentAccent" class="sd-check">✓</span>
                </button>
              </div>
              <div class="sd-palette-title">Windows 颜色</div>
              <div class="sd-swatch-grid">
                <button v-for="color in WINDOWS_COLORS" :key="color" type="button"
                  class="sd-swatch" :class="{ selected: !state.useSystemAccent && color === currentAccent }"
                  :style="{ background: color }" :title="color" :aria-label="color"
                  @click="pickAccent(color)">
                  <span v-if="!state.useSystemAccent && color === currentAccent" class="sd-check">✓</span>
                </button>
              </div>
              <div class="sd-palette-custom">
                <span>自定义颜色…</span>
                <input class="sd-color-well" type="color" aria-label="自定义强调色"
                  :value="currentAccent" @input="onPickAccent" @change="accentOpen = false" />
              </div>
            </div>
          </transition>
        </div>
      </div>
    </div>

    <!-- Fonts -->
    <div class="sd-group">
      <div class="sd-section">字体</div>

      <div class="sd-row-card">
        <AppIcon class="sd-row-icon" glyph="&#xE8D3;" :size="16" />
        <div class="sd-row-text">
          <div class="sd-row-title">系统字体全集</div>
          <div class="sd-row-sub">{{ fontSub }}</div>
        </div>
        <Button v-if="fontSupported" class="sd-reset-btn" @Click="onGrantFonts">{{ fontBtnText }}</Button>
      </div>
    </div>

    <!-- Reset -->
    <div class="sd-group">
      <div class="sd-section">重置</div>

      <div class="sd-row-card">
        <!-- Monochrome on purpose: E72C maps to the two-tone rotate icon used
             by the script toolbar, which made this row look like a status LED. -->
        <AppIcon class="sd-row-icon" name="reset" :size="16" />
        <div class="sd-row-text">
          <div class="sd-row-title">重置设置</div>
          <div class="sd-row-sub">恢复全部默认值（含主题、文案、配色）</div>
        </div>
        <Button class="sd-reset-btn" @Click="onReset">{{ resetLabel }}</Button>
      </div>
    </div>

    <!-- About -->
    <div class="sd-group">
      <div class="sd-section">关于</div>

      <div class="sd-row-card">
        <span class="sd-mark"><AppIcon glyph="&#xE7A2;" :size="16" /></span>
        <div class="sd-row-text">
          <div class="sd-row-title">
            <HyperlinkButton
              class="sd-link sd-title-link"
              Content="Kinetype Studio"
              FontSize="14"
              Padding="0"
              NavigateUri="https://github.com/Furry-Xiyi/WinUIonWeb" />
          </div>
          <div class="sd-row-sub">
            快闪字幕生成器「倒鸭子」基于
            <HyperlinkButton
              class="sd-link"
              Content="WinUIonWeb"
              NavigateUri="https://github.com/Furry-Xiyi/WinUIonWeb"
              FontSize="12"
              Padding="0"
            />
            构建
          </div>
        </div>
        <span class="sd-ver">v0.1.0</span>
      </div>
    </div>

  </ContentDialog>
</template>

<style scoped>
/* ------------------------------------------------------------------ */
/* Theme mode dropdown (native ComboBox look)                         */
/* ------------------------------------------------------------------ */
.wc { position: relative; display: inline-block; min-width: 170px; }

/* Trigger: same surface/border/radius as the native ComboBox. */
.wc-combo {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  height: 32px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 8px 0 10px;
  margin: 0;
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  color: var(--TextFillColorPrimaryBrush, #1a1a1a);
  background: var(--ControlFillColorDefaultBrush, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--ControlStrokeColorDefaultBrush, rgba(0, 0, 0, 0.12));
  border-radius: 4px;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.wc-combo:hover { background: var(--ControlFillColorSecondaryBrush, rgba(255, 255, 255, 0.10)); }
/* No bright focus ring — match the native trigger. */
.wc-combo.open,
.wc-combo:focus-visible {
  border-color: var(--ControlStrokeColorDefaultBrush, rgba(0, 0, 0, 0.12));
  outline: none;
}
.wc-value { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wc-chev {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  color: var(--TextFillColorSecondaryBrush, #616161);
  transition: transform 0.15s ease;
}
.wc-combo.open .wc-chev { transform: rotate(180deg); }

/* Flyout: covers the trigger like the native ComboBox flyout does — same top
   edge, wider than the trigger, 8 px radius, near-invisible dark hairline. */
.wc-flyout {
  position: absolute;
  top: 0;
  right: 0;
  left: auto;
  min-width: 220px;
  width: max-content;
  max-width: 320px;
  z-index: 5000;
  padding: 0;
  box-sizing: border-box;
  border-radius: 8px;
  overflow-y: auto;
  overflow-x: hidden;
  max-height: 320px;
  background: var(--MenuBackground, var(--SolidBackgroundFillColorBaseBrush, #2b2b2b));
  border: 1px solid var(--ControlStrokeColorDefaultBrush, rgba(0, 0, 0, 0.2));
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32), 0 2px 6px rgba(0, 0, 0, 0.22);
}
.wc-flyout::-webkit-scrollbar { width: 8px; }
.wc-flyout::-webkit-scrollbar-track { background: transparent; }
.wc-flyout::-webkit-scrollbar-thumb { background: rgba(128, 128, 128, 0.4); border-radius: 4px; }
.wc-flyout::-webkit-scrollbar-thumb:hover { background: rgba(128, 128, 128, 0.6); }

/* Items mirror the native metrics: 36 px tall, 14 px text, 3 px corner. */
.wc-item {
  appearance: none;
  -webkit-appearance: none;
  position: relative;
  width: 100%;
  height: 36px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  padding: 0 14px;
  margin: 0;
  border: none;
  border-radius: 3px;
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  color: var(--TextFillColorPrimaryBrush, #1a1a1a);
  background: transparent;
  white-space: nowrap;
}
.wc-item:hover { background: var(--SubtleFillColorSecondaryBrush, rgba(255, 255, 255, 0.06)); }
.wc-item.selected { background: rgba(255, 255, 255, 0.08); }
.wc-item.selected::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 18px;
  border-radius: 2px;
  background: var(--AccentFillColorDefaultBrush, #2775b6);
}
.wc-item-label { flex: 1; min-width: 0; }

/* ---------- Accent palette flyout (Windows 主题色 layout) ---------- */
.sd-accent-combo { min-width: 150px; margin-left: auto; }
.sd-accent-chip {
  width: 16px; height: 16px; border-radius: 3px;
  flex: 0 0 auto;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.22);
}
/* Open below the trigger so the current colour stays visible, and leave enough
   height for the 48-swatch grid plus the custom-colour row. */
/* The stock --MenuBackground is #2b2b2b in dark mode, which made this panel
   look like a hole in the dialog. One step lighter reads as a surface again. */
.sd-accent-flyout {
  --sd-flyout-bg: #424242;
  top: calc(100% + 4px);
  width: 290px; max-width: 290px; max-height: 400px;
  padding: 9px 12px 10px;
  background: var(--sd-flyout-bg);
}
html.theme-light .sd-accent-flyout { --sd-flyout-bg: #ffffff; }
.sd-accent-auto {
  display: flex; align-items: center; gap: 8px;
  padding-bottom: 8px; margin-bottom: 8px;
  border-bottom: 1px solid var(--ControlStrokeColorDefaultBrush, rgba(0, 0, 0, 0.14));
}
.sd-accent-auto-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.sd-accent-auto-title { font-size: 13px; color: var(--TextFillColorPrimaryBrush, #1a1a1a); }
.sd-accent-auto-sub { font-size: 11px; color: var(--TextFillColorSecondaryBrush, #616161); }
.sd-accent-auto .sd-switch-bare { margin-left: 0 !important; }
.sd-palette-title {
  font-size: 12px;
  color: var(--TextFillColorSecondaryBrush, #4b4b4b);
  margin: 0 0 6px 2px;
}
/* Fixed 24 px cells with an equal 4 px gutter keep every swatch square and
   stop the grid from stretching them with `1fr` columns. */
.sd-swatch-row { display: flex; gap: 4px; margin-bottom: 12px; }
.sd-swatch-grid {
  display: grid; grid-template-columns: repeat(9, 24px);
  gap: 4px; justify-content: center;
}
.sd-swatch {
  width: 24px; height: 24px; padding: 0;
  display: grid; place-items: center;
  border: 1px solid rgba(0, 0, 0, 0.25); border-radius: 2px;
  box-sizing: border-box;
  cursor: pointer; flex: 0 0 auto;
}
.sd-swatch:hover { outline: 2px solid var(--AccentFillColorDefaultBrush, #2775b6); outline-offset: 1px; }
.sd-swatch.selected {
  box-shadow: 0 0 0 2px var(--sd-flyout-bg, #3a3a3a),
              0 0 0 4px var(--AccentFillColorDefaultBrush, #2775b6);
}
.sd-check {
  color: #fff; font-size: 15px; font-weight: 700; line-height: 1;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
}
.sd-palette-custom {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 12px; padding-top: 8px;
  border-top: 1px solid var(--ControlStrokeColorDefaultBrush, rgba(0, 0, 0, 0.14));
  font-size: 12px;
}
.sd-color-well {
  width: 34px; height: 24px; padding: 0; cursor: pointer;
  border: 1px solid var(--ControlStrokeColorDefaultBrush, rgba(0, 0, 0, 0.14));
  border-radius: 3px; background: transparent;
}
.sd-color-well::-webkit-color-swatch-wrapper { padding: 2px; }
.sd-color-well::-webkit-color-swatch { border: 0; border-radius: 2px; }

.wc-pop-enter-active, .wc-pop-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.wc-pop-enter-from, .wc-pop-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
