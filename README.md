# Kinetype

**Turn a script into a waterfall-typography video with one command — no After Effects, no timeline scrubbing, no manual keyframing.**

Kinetype reproduces the "倒鸭子 / 瀑布流字幕 / TypeMonkey / 快闪文字混排" look: words flash on
screen one beat at a time, stack upward like a waterfall, and slide away as the next
line arrives. You give it text; it gives you an MP4.

> **多端支持与渲染引擎策略：见 [`PLATFORM.md`](PLATFORM.md)**（支持矩阵、老设备边界、低端机优化）。
>
> **网页版（主交付）：[`web-ui/`](web-ui/)** —— WinUI 3 风格前端（Vue 3 + [WinUIonWeb](https://github.com/Furry-Xiyi/WinUIonWeb)）：
> 界面全部使用 WinUI 控件（TextBox / ComboBox / Slider / Expander / ProgressBar…），
> 窗体背景用 **WinUIonWeb 官方默认黑灰**（浅色 `#f3f3f3`，深色 `#202020` + `#282828` 顶层），
> 强调色用**中国传统蓝**（景泰蓝/睛蓝）或跟随 Windows 系统强调色（CSS `AccentColor`）与**自动深浅色**（`prefers-color-scheme`）。
> 左下角「设置」按钮弹出 **ContentDialog**（外观 + 关于），并内置「国风青绿」视频预设。
> 运行：`cd web-ui && npm install && npm run dev`；构建：`npm run build`（产物在 `dist/`，需静态服务器托管）。
> 构建同时产出 **legacy 包**（`index-legacy-*.js` + `polyfills-legacy-*.js`），浏览器低于 ES Module 基线时自动加载，见 [`PLATFORM.md`](PLATFORM.md)。
>
> 网页版可直接调：**画幅比例**（9:16 / 16:9 / 3:4 / 4:3 / 4:5 / 1:1 / 21:9）、
> **清晰度**（720p / 1080p / 1440p / **4K 2160p**）、**默认字体（含 Bold）+ 可增删的字体对照表**、
> **整块旋转**（`{转}` 符号或自动触发）、语速、节奏、配色，
> 以及一套**逐字样式语法**（界面内置速查表）。

![画幅与文字变换](preview/ratios.png)

### 排版模型（按参考视频校准）

参考视频用的是 AE 的 **TypeMonkey** 插件，面板上写着「间距 10 / 样式随机 / 速度快 /
运动模糊 / 自动摄像机」。据此校准出这些规则：

| 规则 | 实现 |
|------|------|
| **每行各自居中** | 每一行的文字都水平居中；当前正在显示的那一行钉在画面正中心（水平+垂直都是正中），旧行被顶上去 |
| **正在播放的内容在屏幕正中心** | 最新一行钉在画面垂直中线，更早的行被下方行的包围盒高度顶上去 |
| **只有上面那堆会转** | 到 `{转}` 点时，**标记之前的行作为一整块刚体**，绕**触发瞬间正在显示那一行的角**一起甩 90°：向右转用最后一个字的右上角、向左转用第一个字的左上角，并留出间距。**标记这一行及之后的行永远保持正的**，继续向上堆。转过的那堆也只往上移动 |
| **瞬间消失** | 行移出画面就**直接消失**，不淡出、不闪；行不按定时器消失，只被新行顶出去 |

![A/B/C/D 六帧：正的 → 上面的整堆转过去 → C 居中 → 整堆一起往上 → 出画瞬间消失](preview/rotation-flow.png)

> 另外「远近缩放」控制纵深：正的行越往上越小（或越大），参照距离 = 短边的 0.34 倍。

![真实文案里的旋转：当前行正着读，旧行变成旁边的竖条](preview/rotation-live.png)

触发方式两种：**手动** 在任意一行前写 `{转}`（可带角度 `{转:-90}`）；**自动** 当竖排
堆叠快放不下时自动触发（横屏 16:9 尤其明显）。旋转方向下拉框只影响自动触发的手性；
`{转}` 符号永远优先。

```bash
cd web-ui && python -m kinetype render samples/daoyazi.zh.txt -p meme-punch \
    --audio samples/music/daoyazi_beat.wav -o out/daoyazi.mp4
```

---

## 1. What that effect actually is (原理拆解)

Strip away the branding and the 快闪文字混排 effect is four stacked mechanisms. Kinetype
implements all four from scratch — no video editor, no plugin, no stock template.

| # | Layer | What it does | Where it lives |
|---|-------|--------------|----------------|
| 1 | **Beat segmentation** | Cuts prose into flashes of 0.3–1.2 s using a *reading budget* (glyphs for CJK, words for Latin). Beats close on punctuation and on phrase boundaries so a word is never chopped in half. | `script.py` |
| 2 | **Waterfall grid** | The newest beat sits on an anchor line (~68 % down the frame); every older beat is pushed above it by the heights in between, so the stack grows and slides off the top. | `renderer.py → StackMotion` |
| 3 | **Second-order motion** | A beat *earns* its slot over `motion.scroll` seconds. At the instant it lands its contribution is still zero, so it sits on the anchor and then rises by its own height while the beats above glide away. That lag is the "flowing water" feel. | `renderer.py → StackMotion.ramp` |
| 4 | **Per-beat choreography + camera** | Entrance (pop / rise / drop / zoom / swing / typewriter), exit (shrink / fade / drift / crumble), random size / colour / tilt per beat, plus breathe-zoom, on-beat shake, colour pulses, speed lines and a progress bar. | `renderer.py`, `layout.py` |

Three things that surprise people who try to rebuild this by hand:

* **Nothing is animated per glyph.** Each beat is rasterised **once** into an RGBA sprite
  (`layout.py`); per-frame work is pure compositing. That is why this renders 60 fps at
  1080×1920 in plain Python at all.
* **The "designed" feel comes from variation, not from more motion.** Sizes come from a
  weighted range, colours from a weighted palette, entrance styles at random — all driven
  by one seed, so a re-render is identical frame-for-frame.
* **The stack must be described relative to the newest beat, not as a travel counter.**
  A global "distance travelled" grows without bound and eventually scrolls the whole stack
  off the top of the frame. Kinetype computes `y(i) = anchor − Σ heights(i+1 … newest)`,
  which is bounded by construction, and there is a regression test for it
  (`web-ui/tests/test_renderer.py::test_stack_height_stays_bounded`).

### The rendering pipeline

```
script.txt / .srt / .json
        │  script.py       beat segmentation + reading-time model
        ▼
   list[Chunk] ──► layout.py ──► list[Block]        one RGBA sprite per beat
        │                              │
        │  audio.py                    │  renderer.py   per-frame compositing
        ▼                              ▼
   beat onsets ────────────────►  RGB frames ──► ffmpeg (rawvideo pipe) ──► MP4
```

---

## 2. Install & run

Requirements: Python 3.10+, Pillow, numpy, and `ffmpeg` on `PATH`.

```bash
pip install -e .              # or run from the repo root with python -m kinetype
python -m kinetype fonts      # verify a CJK + latin font was found
python -m kinetype presets    # list the built-in looks
```

### The one-liner you actually want

```bash
python -m kinetype render script.txt -p meme-punch -o out.mp4
```

### Iterate on the look without rendering a video

```bash
python -m kinetype preview script.txt -p beat-flash -n 8 --size 540x960 --out preview/look.png
```

### Use a real voice-over (字幕对齐)

Export an `.srt` from 剪映 / CapCut / Premiere and hand both files over — beats then follow
the subtitle timings exactly, and the audio sets the video length:

```bash
python -m kinetype render subtitles.srt --audio voice.wav --fit-audio -o out.mp4
```

### Inspect the rhythm before spending render time

```bash
python -m kinetype render script.txt --dry-run              # print the beat sheet
python -m kinetype render script.txt --dump-config c.json   # snapshot the resolved look
python -m kinetype sheet out.mp4 -n 12 -o sheet.png --gif peek.gif   # contact sheet + gif
```

---

## 3. Writing a script

Plain text is enough. Blank lines are hard beat breaks.

### 网页版语法（完整）

样式用指令块：`{指令}文字{/}`，作用到 `{/}` 或行尾为止，可嵌套。像 Python 一样一行一指令：

| 指令 | 例子 | 效果 |
|------|------|------|
| `color:` | `{color:#FFD84D}保险公司{/}` | 颜色（hex 或 red/gold 等英文名） |
| `size:` | `{size:1.6}倒鸭子{/}` | 字号倍数 |
| `font:` | `{font:kai}您说{/}` | 字体，走**对照表短名**，也可直接写系统字体名 |
| `weight:` / `bold` | `{weight:900}字{/}` `{bold}字{/}` | 粗细 |
| `shadow:` | `{shadow:off}字{/}` | 阴影关 / 0–2 强度 |
| `stroke:` `strokew:` | `{stroke}字{/}` `{stroke:#00E5FF}字{/}` `{strokew:0.12}` | 描边**默认关**，写了才开；颜色 / 粗细（em） |
| `spacing:` | `{spacing:0.12}倒鸭子{/}` | 字距（em） |
| `hl` | `{hl}词{/}` | 高亮块（等价于 `[词]`） |
| `转` | `{转} 这一行起整块旋转`，`{转:-90}` 指定方向 | 整块旋转触发 |
| `/` | `{/}` 关整段；`{/color}` **只关颜色**，其他属性保留 | 结束样式 |

基础符号照旧：`[词]` 高亮块 · `**粗体**` · `|` 强制换行 · `#` 注释行 · `\{` `\[` 转义。

字体对照表是页面里的一个**可增删列表**：左边下拉选系统字体，右边填短名，点「＋ 添加一行」加一行。
页面启动时会自动检测已安装字体（已添加的字体不会再出现在其他行的下拉里）。

```text
[ 楷体 ▾ ] [ kai ] [×]      →  {font:kai} 就能用
[ 黑体 ▾ ] [ hei ] [×]
```

```text
喂，您好，这里是 {color:#FFD84D bold}保险公司{/}。

{转} 用 {color:#4DA3FF}别的工具{/}，{font:kai}我老手艺人了{/}

{size:1.6 spacing:0.12 color:#FF4D5E}倒鸭子{/} 特效时
```

### Python 版语法（子集）

`[词]` 高亮、`**粗体**`、`{#FF4D5E:文字}` 颜色、`|` 换行。指令块与 `{转}` 目前只在网页版生效。

节奏（网页版「节奏」下拉框 / Python 版 `text.chunk_mode`）是最影响观感的旋钮：

```bash
--set text.chunk_mode=punch      # 4 glyphs / beat  – the classic 倒鸭子 flurry (~2 beats/s)
--set text.chunk_mode=tight      # 6 glyphs / beat  – default
--set text.chunk_mode=balanced   # 8 glyphs / beat
--set text.chunk_mode=wide       # 13 glyphs / beat – calmer, more readable
```

### JSON beats (frame-accurate control)

Pin the beats that matter and let the rest flow — untimed beats are interpolated
between the anchors. See [`web-ui/samples/beats.json`](web-ui/samples/beats.json):

```json
[
  { "text": "喂，您好", "start": 0.25, "end": 1.10 },
  { "text": "[倒鸭子]？", "start": 1.10, "end": 2.05 }
]
```

---

## 4. Presets

| Preset | Look |
|--------|------|
| `meme-punch` | 抖音爆款：深色底 + 高饱和撞色 + 弹入 + 抖屏（默认） |
| `beat-flash` | 音乐卡点：背景色随节拍跳变，速度线全开 |
| `neon-terminal` | 终端极客：黑绿辉光、打字机入场 |
| `sakura-pop` | 日系小清新：奶油底、马卡龙色、飘入 |
| `broadcast` | 新闻播报：白底黑字 + 单一强调色 |
| `retro-print` | 复古印刷：米黄纸纹 + 墨黑描边 |

Any field can be overridden from the CLI:

```bash
python -m kinetype render s.txt -p meme-punch \
    -s style.accent=#00E5FF \
    -s motion.scroll=0.24 \
    -s layout.linger=2 \
    -s 'background.beats=["#FF2E63","#00E5FF"]' \
    -s font.base_size=52
```

`--dump-config out.json` writes the fully resolved config, so a look can be committed next
to the script and reproduced later with `-c out.json`.

---

## 5. Tuning cheat sheet

### 自定义矢量图标（全部界面图标可替换）

所有界面图标都是 `web-ui/src/icons/` 里的 SVG 文件（24×24、`fill="currentColor"` 跟随文字色）。
**用你自己画的 SVG 覆盖同名文件即可生效**，不用改任何代码（dev 热更新，构建后需重新 build）。
浏览器标签页图标（favicon）放在 `web-ui/src/assets/favicon.svg`，由 Vite 处理哈希，引用位于 `web-ui/index.html` 的 `<link rel="icon">`。

| 文件名 | 用在哪里 |
|--------|----------|
| `theme-auto.svg` / `theme-light.svg` / `theme-dark.svg` | 标题栏右上角主题按钮（三态） |
| `theme.svg` | 设置弹窗 · 主题行 |
| `accent.svg` | 设置弹窗 · 强调色来源行 |
| `app.svg` | 设置弹窗 · 关于行品牌图标 |
| `settings.svg` | 左栏底部「设置」项 |
| `text.svg` | 侧栏「文案」卡 |
| `screen.svg` | 侧栏「画面」卡 |
| `rhythm.svg` | 侧栏「节奏与字号」卡 |
| `font.svg` | 侧栏「字体与旋转」卡 |
| `play.svg` / `pause.svg` | 传输条播放/停止按钮 |
| `add.svg` / `remove.svg` | 字体对照表「添加一行」/「删除行」按钮 |

画图要点：`viewBox="0 0 24 24"`，线条描边色写 `stroke="currentColor"`、填充写 `fill="currentColor"`，
这样图标自动跟随深浅主题的文字颜色；写死颜色（如 `#fff`）则不跟随。
组件实现：`web-ui/src/icons/index.js`（编译期把 icons 目录全部 SVG 打包内联）。

| Want | Knob |
|------|------|
| Faster / slower cadence | `text.chunk_mode`, `timing.cps_cjk`, `timing.cps_latin` |
| More flashes on screen at once | `layout.linger` (beat-gaps), `layout.max_live` |
| Springier stack | `motion.scroll` (smaller = quicker catch-up), `motion.scroll_ease` |
| Bigger / smaller type | `font.base_size` (44 at 1080×1920 ≈ 5 stacked rows) |
| Longer entrances | `motion.enter_duration`, `motion.exit_duration` |
| Less chaos | `motion.enter=rise`, `motion.exit=fade`, `style.rotation_range=0`, `motion.x_scatter=0` |
| Steadier camera | `camera.mode=scroll`, `camera.shake=0`, `camera.breathe=0` |
| Different seed look | `--seed 1234` |

Everything is a dataclass field — run `python -m kinetype presets --json` for the full
schema, or read [`config.py`](web-ui/kinetype/config.py).

### 画幅与文字变换（网页版）

| 控件 | 可选值 | 说明 |
|------|--------|------|
| 画幅 | `9:16` `16:9` `3:4` `4:3` `4:5` `1:1` `21:9` | 切换后画布立刻重建，字体按画幅面积自动归一，横竖屏字号视觉权重一致 |
| 清晰度 | 720p / 1080p / 1440p / **4K 2160p** | 以**短边**为准，例如 9:16@1080p = 1080×1920、16:9@4K = 3840×2160 |

### 录制导出（MP4 / WebM 自动选择）

录制按钮文字会显示浏览器实际支持的格式（本项目实测 Edge/Chrome 为 **MP4**）：
`detectRecordFormat()` 依次探测 `video/mp4;codecs=avc1` → `video/mp4` → `video/webm;codecs=vp9/vp8` → 默认，
优先 MP4（H.264）；Firefox 等不支持 MP4 录制的浏览器自动回退 WebM，无需用户设置。
录制码率随画布面积自动提升（1080p≈8Mbps，4K≈32Mbps，上限 48Mbps）。
**4K 录制提示**：4K 实时渲染 + 编码很吃性能，老机器建议先用 1080p 调好效果，录制时再切 4K，
并保持标签页在前台（切走会掉帧）。
| 文字大小 | 40% – 200% | 相对基准字号的缩放；放大会自动多折行，不会横向溢出 |
| 远近缩放 | -50% – 60% | 越往上越小（正）或越大（负），参照距离 = 短边的 0.34 倍；0 = 不缩放 |
| 默认字体 | 下拉选择 | 全篇默认字体 + 字重；逐字覆盖用 `{font:短名}` 或 `{font:KaiTi}` |
| 自动旋转方向 | 向右 90° / 向左 90° / 左右随机 / 不自动 | 只决定**自动触发**（堆叠放不下时）的手性；`{转}` 符号永远优先且自带角度 |

> 旋转只作用于 **`{转}` 标记上面的旧行**：它们甩 90° 后变成并排竖条，之后同样只往上移动；
> 标记这一行以及之后永远是正的。行是被新行**推出画面后**才消失（无定时器）。详见上方「排版模型」。

Python 版用 `--size` 指定任意尺寸（同样支持横竖屏）：

```bash
python -m kinetype render s.txt --size 1920x1080 -o out.mp4   # 横屏
python -m kinetype render s.txt --size 1080x1080 -o out.mp4   # 方形
```

---

## 6. Using it as a library

```python
from kinetype import RenderConfig, Renderer, load_script, assign_timeline

cfg = RenderConfig()
cfg.output.width, cfg.output.height, cfg.output.fps = 1080, 1920, 60
cfg.style.accent = "#00E5FF"

chunks = load_script("script.txt", cfg)
duration = assign_timeline(chunks, cfg, target=15.0)

renderer = Renderer(cfg)
renderer.write(renderer.prepare(chunks, duration), "out.mp4")
```

---

## 7. Project layout

`web-ui/` is the single core folder — the web app, its samples, tests and the
optional Python batch renderer all live inside it. The repository root holds only
docs, the licence and a thin command forwarder.

```
web-ui/                    ← core
  src/
    engine/                kinetype.js (render) · presets.js · fonts.js
    components/            SettingsPane · SettingsDialog · StageView
    icons/                 SVG glyph set + AppIcon factory
    styles/                theme.css — Traditional-Chinese palette on WinUI tokens
    App.vue · store.js · main.js
  src/assets/              favicon (hashed by Vite)
  samples/                 demo script, beat sheet, config, beat generator
  tests/                   pytest suite (67 tests)
  kinetype/                optional batch renderer (Python + Pillow + ffmpeg)
    config.py     dataclass config, presets, JSON round-trip
    script.py     markup parser, phrase segmentation, SRT/JSON loaders, timing
    layout.py     font fitting, line breaking, text rasterisation into sprites
    renderer.py   StackMotion, entrance/exit choreography, camera, ffmpeg pipe
    background.py procedural backgrounds (gradient/radial/dots/noise/vignette)
    audio.py      WAV decode, onset detection for on-beat flashes
    fonts.py      CJK/latin font resolution
    cli.py        command line interface
  scripts/                 engine-smoke.mjs (16 checks) · shot.mjs (headless shots)
  pyproject.toml · package.json · vite.config.js
```

Regenerate the demo exactly as shipped (run from `web-ui/`; install the Python
package once with `pip install -e .`):

```bash
cd web-ui
python samples/music/make_daoyazi_beat.py samples/music/daoyazi_beat.wav
python -m kinetype render samples/daoyazi.zh.txt -p meme-punch \
    --audio samples/music/daoyazi_beat.wav -o out/daoyazi.mp4

# or take a config file / beat sheet for a spin
python -m kinetype render samples/daoyazi.zh.txt -c samples/meme-punch.json -o out/from-config.mp4
python -m kinetype render samples/beats.json -p neon-terminal -o out/from-beats.mp4
```

The bundled `make_daoyazi_beat.py` asks Kinetype for the *actual* beat times of the
script before placing its clicks, so the audio can never drift out of sync when the
cadence is retuned.

---

## 8. Notes & limits

* Roughly **8–12 output fps** on a modern laptop at 1080×1920 in pure Python (≈5 min for a
  30 s clip at 60 fps). `--size 720x1280 --fps 30` is about 4× faster and usually
  indistinguishable on a phone. `Renderer.scale` (default `0.5`) trades sharpness for speed.
* Text is drawn with Pillow, so beats animate as units — there is no per-letter cascade.
  That is what the reference style does too.
* CJK segmentation knows punctuation but not a dictionary: a long clause with no comma is
  cut at the reading budget, which can occasionally land mid-word. Writing your script with
  commas (or using `|` to force a break) avoids it.
* Music under `web-ui/samples/music/` is synthesised by the bundled script, so the demo carries no
  third-party audio.
