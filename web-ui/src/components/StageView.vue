<script setup>
/* 右侧舞台：画布 + 预览自适应 + 播放/录制传输条（引擎在此接线）。 */
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { state, engineOptions } from '../store.js'
import { Engine, frameSize } from '../engine/kinetype.js'
import { probeRenderCapability } from '../engine/capabilities.js'
import { detectSystemFonts, loadSavedLocalFonts, restoreImportedFonts } from '../engine/fonts.js'
import { AppIcon } from '../icons/index.js'

const stageEl = ref(null)
const phoneEl = ref(null)
const cvEl = ref(null)

let engine = null
let ro = null
let refreshTimer = 0
const pendingFits = []

function fitPhone() {
  if (!engine || !engine.prog || !stageEl.value || !phoneEl.value) return
  const rect = stageEl.value.getBoundingClientRect()
  if (rect.width < 40 || rect.height < 40) return
  const w = engine.prog.W, h = engine.prog.H
  const availW = Math.max(120, rect.width - 32)
  const availH = Math.max(120, rect.height - 32)
  let dw = availW, dh = dw * h / w
  if (dh > availH) { dh = availH; dw = dh * w / h }
  phoneEl.value.style.width = Math.round(dw) + 'px'
  phoneEl.value.style.height = Math.round(dh) + 'px'
}

/* 布局稳定前多试几拍：onMounted 的首次量测可能拿到未展开的 stage 尺寸 */
function scheduleFits() {
  for (const delay of [0, 120, 360, 900]) {
    pendingFits.push(setTimeout(fitPhone, delay))
  }
  pendingFits.push(requestAnimationFrame(() => requestAnimationFrame(fitPhone)))
}
function clearPendingFits() {
  for (const t of pendingFits.splice(0)) clearTimeout(t)
}

function drawAtSavedProgress() {
  if (!engine || !engine.prog) return
  const p = Math.max(0, Math.min(1, Number(state.progress) || 0))
  engine.drawFrame(p * engine.prog.total)
}
function refreshPreview() {
  if (state.playing) return
  engine.setOptions(engineOptions())
  engine.prog = engine.prepare(engine.opts)
  if (engine.prog) { fitPhone(); scheduleFits(); drawAtSavedProgress() }
}

/* 状态变化 → 防抖刷新预览（与原版 oninput 行为一致） */
watch(() => engineOptions(), () => {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(refreshPreview, 120)
}, { deep: true })

watch(() => state.systemFonts, refreshPreview)

function togglePlay() {
  if (state.playing) engine.stop(true)
  else { engine.setOptions(engineOptions()); engine.play() }
}
function record() {
  if (state.playing) engine.stop(true)
  state.recording = true
  engine.setOptions(engineOptions())
  engine.record({
    format: state.exportFormat,
    name: state.exportName,
    /* Browsers without WebCodecs go straight to real-time capture. */
    prefer: state.renderTier === 'mediarecorder' || state.renderTier === 'none' ? 'compat' : 'auto',
  })
}
/* 拖动 Slider 定位：Value 0~1000 → 比例 0~1 */
function onSeek(sender, args) {
  const v = (args && args.NewValue != null) ? args.NewValue : (sender && sender.Value)
  if (v == null) return
  const r = Math.max(0, Math.min(1, Number(v) / 1000))
  /* 播放中 onProgress 会持续同步 Value；这里只处理用户真实拖动（值发生实质变化），
     避免「播放→同步 Value→再次 seek」的回环 */
  if (Math.abs(r - state.progress) < 0.002) return
  state.progress = r
  engine && engine.seek(r)
}
function onSpaceKey(e) {
  const tag = (e.target && e.target.tagName) || ''
  const inField = tag === 'TEXTAREA' || tag === 'INPUT' ||
    (e.target && e.target.isContentEditable)
  if (e.code === 'Space' && !inField) {
    e.preventDefault()
    togglePlay()
  }
}

onMounted(() => {
  engine = new Engine(cvEl.value)
  engine.onStatus = s => { state.status = s }
  engine.onPlayState = v => {
    state.playing = v
    /* 停止后不清零：保留当前进度，便于续播/下次打开恢复 */
  }
  engine.onProgress = p => { state.progress = p }
  engine.onRecorded = () => { state.recording = false }

  /* 恢复上次播放进度：预览程序准备好后定位到该时间点 */
  const saved = Math.max(0, Math.min(1, Number(state.progress) || 0))
  if (saved > 0.001) requestAnimationFrame(() => { engine.seek(saved) })

  engine.setOptions(engineOptions())
  engine.prog = engine.prepare(engine.opts)
  if (engine.prog) { fitPhone(); scheduleFits(); drawAtSavedProgress() }

  ro = new ResizeObserver(() => { fitPhone() })
  ro.observe(stageEl.value)
  window.addEventListener('resize', fitPhone)

  function mergeFonts(detected) {
    /* 合并 canvas 探测 + 已授权的系统字体全集存档 + 自定义/导入字体（去重、排序） */
    const base = detected.length ? detected : ['Microsoft YaHei']
    const all = [...base, ...loadSavedLocalFonts(), ...state.customFonts]
    state.systemFonts = [...new Set(all)].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }
  detectSystemFonts(mergeFonts)
  /* 恢复 IndexedDB 里导入过的字体文件（FontFace 重新注册），并并入候选列表 */
  restoreImportedFonts().then(names => {
    if (names.length) {
      for (const n of names) if (!state.customFonts.includes(n)) state.customFonts.push(n)
      mergeFonts(state.systemFonts)
    }
  })

  /* Pick the fastest encoder this device can actually run. */
  probeRenderCapability().then(cap => {
    state.renderTier = cap.tier
    state.renderLabel = cap.label
  })

  window.addEventListener('keydown', onSpaceKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onSpaceKey)
  window.removeEventListener('resize', fitPhone)
  clearPendingFits()
  if (ro) ro.disconnect()
  engine && engine.stop(false)
})
</script>

<template>
  <div class="wf-stage-wrap">
    <div class="wf-stage" ref="stageEl">
      <div class="wf-phone" ref="phoneEl">
        <canvas ref="cvEl"></canvas>
      </div>
      <div class="wf-rec" :class="{ on: state.recording }"><i></i>REC</div>
    </div>

    <div class="wf-transport">
      <Button Style="AccentButtonStyle" @Click="togglePlay" class="wf-btn-play">
        {{ state.playing ? '停止' : '播放' }}
      </Button>
      <Button :IsEnabled="!state.playing" @Click="record" class="wf-btn-rec"
        :title="state.renderLabel ? `导出（${state.renderLabel}）` : '导出'">
        导出
      </Button>
      <div class="grow wf-seek">
        <Slider
          :Value="Math.round(state.progress * 1000)"
          :Minimum="0" :Maximum="1000" :StepFrequency="1"
          :SmallChange="10" :LargeChange="100"
          @ValueChanged="onSeek"
          aria-label="播放进度"
        />
      </div>
      <TextBlock class="wf-status" :Text="state.status || '空格 = 播放 / 停止'" />
    </div>
  </div>
</template>
