# Kinetype 部署记录

## 本次提交

| 项目 | 值 |
|---|---|
| 源码仓库 | `https://github.com/xzhnew/kinetype` |
| 源码分支 | `main` |
| 源码 commit | `7fab85a`（Initial import of Kinetype (GPL-3.0-only)） |
| 部署分支 | `gh-pages` |
| 部署 commit | `503739a` |
| 部署方式 | `npx gh-pages -d web-ui/dist -b gh-pages` |
| 许可证 | GPL-3.0-only（WinUIonWeb 是 GPL-3.0-only，捆绑编译后整个产物必须同许可证） |

## 上传的文件（97 个）

- 根目录：`README.md`、`SUMMARY.md`、`PLATFORM.md`、`LICENSE`、`THIRD_PARTY_NOTICES.md`、`licenses/winuionweb-GPL-3.0.txt`、`package.json`、`.editorconfig`、`.gitignore`
- 前端：`web-ui/index.html`、`vite.config.js`、`package.json`、`package-lock.json`、`pyproject.toml`
- 源码：`web-ui/src/`（组件、引擎、图标、样式）、`web-ui/kinetype/`（Python 包）、`web-ui/scripts/`、`web-ui/samples/`、`web-ui/tests/`

## 没有上传

- `web-ui/node_modules/`（128 MB 依赖，可 `npm install` 还原）
- `web-ui/dist/`（构建产物，单独发到 `gh-pages` 分支）
- `.workbuddy/`（本地工作记录）、`备份文件/`（本地备份）
- `web-ui/.edge-shot-profile/`、`favicon-*.svg` 等临时验证文件
- `*.mp4` / `*.wav` / `__pycache__` / `*.pyc` / `out/` / `preview/`

## 验证状态

| 检查项 | 结果 |
|---|---|
| `npm run smoke` | 16 passed, 0 failed |
| `npm run build` | 通过 |
| `git push -u origin main` | 成功，远端已有 `main` |
| `npx gh-pages ...` | 成功，远端已有 `gh-pages` |
| Pages 站点 API | **404 — 尚未在网页端启用 Pages** |
| 访问 `https://xzhnew.github.io/kinetype/` | 跳到 `https://blog.oxzh.top/kinetype/`，当前 404（站点未启用） |

## 待完成（需要你在网页上点一次）

1. 打开 `https://github.com/xzhnew/kinetype/settings/pages`
2. Build and deployment → Source 选 **Deploy from a branch**
3. Branch 选 **`gh-pages`** / `/ (root)` → Save
4. 等 1–2 分钟构建，再访问 `https://blog.oxzh.top/kinetype/`（账号已绑定自定义域名，所以会重定向到这里）

> 每次更新源码：`git add . && git commit -m "..." && git push`，然后 `npm run build && npx gh-pages -d web-ui/dist -b gh-pages`，最后把新 commit hash 更新到本文件。
