# 多端支持与渲染引擎策略

> 本文只讨论**平台适配与性能**，不涉及业务代码。核心实现保持干净，平台差异集中在这里说明。
> 结论按"能验证的事实"写，不承诺物理上做不到的东西。

---

## 1. 结论先行

1. **这个项目的价值是"编辑 → 导出"，不是"看成品"。** 所以不做静态只读页：一个只能看不能改的页面，对生产力工具没有意义。
2. **策略是"尽可能扩大可编辑范围"**，而不是给跑不动的设备做一个降级假产品：
   - 现代浏览器 → 完整编辑器（现状）
   - 老一点的浏览器 → legacy 构建，仍然**能编辑、能导出**
   - 真的跑不了的设备 → 明确提示"请换浏览器/设备"，不假装能用
3. **一份代码吃不下所有设备。** Vue 3 依赖 `Proxy`，这是**无法 polyfill** 的语言级特性。`Proxy` 的下限是 Chrome 49 / Safari 10 / Firefox 18；低于这条线的设备（iOS 6–9、Android 4.0–4.4 自带内核）无法编辑，这是运行时缺失，不是优化问题。
4. **渲染引擎按设备能力自动选**，优先硬件编码，其次软件编码，最后实时录制。已实现，见第 4 节。
5. **UI 与性能不妥协**：WinUI 3 的观感保持不变，低端机靠"降分辨率 + 降编码档位"换流畅，而不是砍界面。

---

## 2. 支持矩阵

| 平台 | 浏览器 / 版本 | 档位 | 能做什么 | 限制 |
|---|---|---|---|---|
| Windows 10 / 11 | Chrome / Edge 90+ | **A 完整** | 编辑、预览、WebCodecs 硬件导出 | 无 |
| Windows 7 / 8.1 | Chrome 109 / Edge 109（最后支持版） | **A 完整** | 同上 | 无 |
| Windows XP | Chrome 49（最后支持版） | **实验性可编辑** | 编辑、预览、兼容导出 | 需 legacy 构建；无 ES Module、无 async/await |
| Windows XP | IE 8 | **不支持** | 明确提示换浏览器 | 无 ES5 以上能力 |
| macOS 11+ | Safari 14+ | **A 完整** | 编辑、预览 | Safari 16.4 之前无 WebCodecs，导出走 MediaRecorder |
| macOS 11+ | Chrome / Edge 90+ | **A 完整** | 编辑、预览、硬件导出 | 无 |
| macOS 10.12+ | Safari 10+ | **B 兼容可编辑** | 编辑、预览、兼容导出 | 需 legacy 构建 |
| Android 5.0+ | 可更新 WebView（Chrome 49+） | **B 兼容可编辑** | 编辑、预览、兼容导出 | 需 legacy 构建；低端机建议 720p |
| Android 8+ | Chrome 90+ | **A 完整** | 编辑、预览、硬件导出 | 低端机建议 720p |
| Android 4.0–4.4 | 原生浏览器（WebKit 534 / Chrome 30） | **不支持** | 明确提示更新系统或换设备 | 无 `Proxy`（2011 年内核） |
| iOS 14.3+ | Safari 14.3+ | **A 完整** | 编辑、预览、MediaRecorder 导出 | 无 WebCodecs（16.4 前） |
| iOS 10–14.2 | Safari 10–14 | **B 兼容可编辑** | 编辑、预览、兼容导出 | 需 legacy 构建；导出走 MediaRecorder |
| iOS 6–9 | Safari 6–9 | **不支持** | 明确提示更新系统或换设备 | 无 `Proxy`（2012 年内核） |

> **A 档**＝现代包直接可用。**B 档**＝构建时自动产出的 legacy 包（SystemJS + polyfills），两者都能编辑和导出；构建产物里 `index-legacy-*.js` 即 B 档入口。**不支持**＝页面给出明确说明，不提供降级假功能。

---

## 3. 为什么老设备不能跑完整编辑器

| 依赖 | 首次可用版本 | 能否 polyfill |
|---|---|---|
| `Proxy`（Vue 3 响应式核心） | Chrome 49 / Safari 10 / Firefox 18 | **不能**（语言级，无法模拟） |
| ES Module `<script type="module">` | Chrome 61 / Safari 11 | 能（SystemJS 打包） |
| CSS 自定义属性 `var(--x)` | Chrome 49 / Safari 9.1 | 不能（需构建期展开） |
| `async/await` | Chrome 55 / Safari 10.1 | 能（转 Generator） |
| `MediaRecorder` | Chrome 47 / Safari 14.1 | 不能 |
| `Blob` 下载 + `download` 属性 | Chrome 14 / Safari 13 | 部分 |

iOS 6 的 Safari 6（2012）停在 ES5；Android 4.0 的 WebKit 534（2011）同样停在 ES5 且 Canvas 无硬件加速。**这不是优化能解决的，是运行时缺失。**

---

## 4. 渲染引擎分档（已实现）

`web-ui/src/engine/capabilities.js` 在启动时**直接问浏览器**能不能编码 H.264，不猜 User-Agent：

| 档位 | 判定方式 | 典型设备 | 相对速度 | 时间精度 |
|---|---|---|---|---|
| `webcodecs-hw` | `VideoEncoder.isConfigSupported` + `prefer-hardware` | 现代独显/集显机器 | **最快** | 逐帧精确 |
| `webcodecs-sw` | 同上，软件 H.264 | 无硬件编码器的机器 | 快 | 逐帧精确 |
| `mediarecorder` | 存在 `MediaRecorder`，无 WebCodecs | Safari 14.3–16.3 | 实时（1×） | 跟时钟，可能掉帧 |
| `none` | 两者皆无 | 极老浏览器 | — | 不可导出 |

实现要点：

- 探测结果**整个会话缓存**，能力不会中途变化。
- 导出按钮的悬停提示会显示当前档位，例如「导出（软件编码 · WebCodecs H.264）」。
- 命中 `mediarecorder` / `none` 时，`Engine.record({ prefer: 'compat' })` **直接跳过 WebCodecs**，不再浪费一次必然失败的尝试。
- WebCodecs 路径失败时仍保留自动回退，双保险。

**Python 引擎的定位**：`web-ui/kinetype/` 是离线批量渲染，纯 CPU（Pillow + ffmpeg），1080×1920 约 8–12 fps 输出。它**不适合低端机**，适合服务器或没有浏览器的环境。网页版 WebCodecs 比它快一个数量级，所以网页版是主路径。

---

## 5. 系统强调色（为什么需要本地桥接）

结论：**浏览器拿不到 Windows 的个性化颜色。** 所以"跟随系统强调色"必须由本地服务补一刀，纯前端做不到。

实测（Edge，headless 与真实窗口结果一致）：

| 检查项 | 结果 |
|---|---|
| `CSS.supports('color', 'AccentColor')` | `true` |
| `AccentColor` 解析值 | `rgb(0, 117, 255)` —— 固定的 Chromium 蓝，换系统色也不变 |
| `prefers-color-scheme` | 正确跟随系统深浅色 |
| 系统实际强调色 | `HKCU\…\DWM\AccentColor = 0xFF89009A` → `#9A0089` |

即**深浅色能同步，强调色不能**。任何"网页读系统强调色"的写法，读到的都是那个固定蓝。

实现是三段式、逐级降级：

1. **本地桥接（默认）**：`vite.config.js` 的 `systemColorsPlugin()` 在 dev / preview 上挂 `GET /__wf/system-colors`，用 `reg query` 读 `DWM\AccentColor` 与 `Explorer\Accent\AccentPalette`，返回基色 + Windows 原生八阶色阶（Light1–3 / Dark1–3）。前端每 3 秒及窗口获焦时拉一次，写入 `:root` 的内联变量。
2. **浏览器兜底**：桥接不可用时（静态托管、`file://`、非 Windows、`reg.exe` 被安全策略拦截）退回 `AccentColor`。
3. **手动指定**：关掉「跟随系统」后出现「强调色」取色器，值存 `uiAccent`，完全不依赖外部程序。

设置页会直接写明当前来源（`已跟随系统 · #9A0089` / `读不到系统颜色，暂用浏览器自带强调色` / `手动指定 · #9A0089`），不用猜。

> 深色模式取色阶的 Light2——Windows 自己在深色表面上就是这么加亮的。所以手动选 `#9A0089` 在深色里显示成 `#FF35EE`，这是对齐系统色阶的结果，不是颜色没生效。

---

## 6. 为什么不做"静态只读页"

一开始考虑过给老设备做一个只读页（海报 + 示例视频）。**放弃**，理由：

- 产品的核心动作是**编辑 → 导出**。只能看不能改，等于把编辑器降级成宣传页，不解决任何真实需求。
- 维护成本不低：要单独维护一套模板、单独出构建产物，每次改设计都要同步两份。
- 真正需要的是"让更多设备**能编辑**"——这件事由 legacy 构建解决，ROI 高得多。

所以策略改为：**宁可明确说"不支持"，也不交付一个假装能用的页面。**

---

## 7. 低端机优化清单

已生效：

| 措施 | 位置 | 作用 |
|---|---|---|
| 逐拍精灵缓存 | `engine/kinetype.js` `layoutBeat` | 每拍只光栅化一次，逐帧仅 `drawImage` 合成，帧开销与文字量无关 |
| 背景预渲染 | `engine/kinetype.js` `prepare` | 渐变/噪点只画一次，之后整张贴图 |
| 预览刷新防抖 | `StageView.vue` 120 ms | 拖动滑块不会连续重排 |
| 画布固定分辨率 + CSS 缩放 | `frameSize()` | 不随 `devicePixelRatio` 放大，4K 屏不会悄悄变 4 倍开销 |
| 编码档位自动降级 | `capabilities.js` | 老设备不尝试硬件编码 |
| 导出分辨率可调 | 清晰度 720p / 1080p / 1440p / 2160p | 低端机选 720p，速度约 2.25× |
| **legacy 构建（已实现）** | `vite.config.js` + `@vitejs/plugin-legacy` | 额外产出 SystemJS 包 + polyfills，覆盖 Chrome 49 / Safari 10 / Firefox 52 |

建议但尚未实现（roadmap）：

1. **低端机首启提示**：`hardwareConcurrency <= 4` 或 `deviceMemory <= 4` 时，首次打开建议切到 720p。
3. **高亮层节流**：文案编辑器的 `v-html` 目前每次输入全量重绘，长文案在低端机可加 60 ms 防抖。
4. **不支持提示页**：`Proxy` 探测失败时显示一句明确说明（"当前浏览器版本过低，请升级到 Chrome 49+ / Safari 10+"），而不是白屏。

---

## 8. 如何验证

```bash
cd web-ui
npm run dev          # http://localhost:63200
npm run build        # 产物在 dist/
npm run smoke        # 解析器 16 项
node scripts/shot.mjs 63201   # 需先 npm run preview
```

验证设备档位：打开页面，把鼠标悬停在「导出」按钮上，提示里的括号内容就是当前档位。

---

## 9. 决策记录

| 日期 | 决定 | 原因 |
|---|---|---|
| 2026-11-21 | 目录收敛到 `web-ui/`，其余并入并重命名 | 避免根目录散落核心文件 |
| 2026-11-21 | 保留 Python 引擎但降为可选 | 离线批量仍有价值，网页版是主交付 |
| 2026-11-21 | 放弃"单一代码覆盖 iOS 6"的目标 | `Proxy` 不可 polyfill，硬做等于交付卡死页面 |
| 2026-11-21 | **取消静态只读页** | 产品价值是编辑→导出，只读页等于把工具降级成宣传页；改为 legacy 构建扩大可编辑范围 |
| 2026-11-21 | **legacy 构建落地** | `@vitejs/plugin-legacy@7` + `build.target: es2015`，支持面扩大到 Chrome 49 / Safari 10 / Firefox 52 |
| 2026-11-22 | **强调色改为「本地桥接 + 浏览器兜底 + 手动指定」三段式** | 实测 `AccentColor` 恒为 `#0075ff`，浏览器读不到 Windows 个性化颜色；只用 CSS 等于把"跟随系统"做成假功能 |
