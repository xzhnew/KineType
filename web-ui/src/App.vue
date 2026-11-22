<script setup>
import { ref } from 'vue'
import { state } from './store.js'
import SettingsPane from './components/SettingsPane.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import StageView from './components/StageView.vue'
import { AppIcon } from './icons/index.js'

/* 标题栏按钮：跟随系统 → 浅色 → 深色 → 跟随系统
   图标固定为「半明半暗 + 光芒」（theme-auto），不随主题变化 */
const THEME_ORDER = ['auto', 'light', 'dark']
const THEME_ICON = '&#xE7B3;'   /* 半明半暗图标，固定 */
function cycleTheme() {
  const i = THEME_ORDER.indexOf(state.themeMode)
  state.themeMode = THEME_ORDER[(i + 1) % THEME_ORDER.length]
}

/* 设置弹窗（左栏底部按钮） */
const settingsDialog = ref(null)
const settingsOpen = ref(false)
async function openSettings() {
  settingsOpen.value = true
  try { await settingsDialog.value?.open() } finally { settingsOpen.value = false }
}
</script>

<template>
  <div class="wf-root">
    <header class="wf-titlebar">
      <div class="wf-brand">
        <span class="mark"><AppIcon glyph="&#xE7A2;" :size="16" /></span>
        <span>KineType Studio</span>
      </div>
      <span class="wf-sub">快闪字幕「倒鸭子」</span>
      <span class="spacer" />
      <div class="wf-export-group">
        <TextBox
          class="wf-export-name"
          :Text="state.exportName"
          PlaceholderText="输入你的导出名称："
          @update:Text="v => state.exportName = v"
        />
      </div>
      <Button @Click="cycleTheme" class="wf-theme-btn">
        <AppIcon :glyph="THEME_ICON" :size="16" />
      </Button>
    </header>

    <div class="wf-body">
      <aside class="wf-sidebar">
        <ScrollViewer class="wf-scroll" VerticalScrollBarVisibility="Auto">
          <SettingsPane />
        </ScrollViewer>
        <div class="wf-sidebar-footer">
          <button type="button" class="wf-settings-nav" :class="{ open: settingsOpen }" @click="openSettings">
            <AppIcon glyph="&#xE713;" :size="16" />
            <span>设置</span>
          </button>
        </div>
      </aside>

      <StageView />
    </div>

    <SettingsDialog ref="settingsDialog" />
  </div>
</template>
