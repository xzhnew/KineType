# KineType 部署记录

## 仓库

| 项目 | 值 |
|---|---|
| 仓库 | `https://github.com/xzhnew/KineType`（公开） |
| 源码分支 | `main` |
| 源码 commit | `cde2ef6`（Rename display name to KineType and rewrite README） |
| 部署分支 | `gh-pages` |
| 部署 commit | `10dc7f1` |
| 部署命令 | `npm run build && npx gh-pages -d web-ui/dist -b gh-pages` |
| 线上地址 | <https://blog.oxzh.top/KineType/>（账号已绑自定义域名，`xzhnew.github.io/KineType/` 会重定向到这里） |
| 许可证 | GPL-3.0-only（WinUIonWeb 是 GPL-3.0-only，捆绑编译后整个产物必须同许可证） |

## 仓库内的根目录文件

| 文件 | 是否保留 | 说明 |
|---|---|---|
| `README.md` | 保留 | 项目介绍、本地部署、脚本语法、许可证说明 |
| `LICENSE` | 保留 | GPL-3.0 全文，必须保留 |
| `THIRD_PARTY_NOTICES.md` | 保留 | 第三方依赖与 WinUIonWeb 许可证说明 |
| `licenses/winuionweb-GPL-3.0.txt` | 保留 | 上游 GPL 原文 |
| `package.json` | 保留 | 根目录 npm 脚本转发（dev/build/preview/smoke） |
| `.gitignore` | 保留 | 排除依赖、构建产物与本地文件 |
| `.editorconfig` | 保留 | 2 空格 JS / 4 空格 Python 的统一格式约定 |
| `PLATFORM.md` | 保留 | 多端支持与低端机策略；不放进 README 以免主文档过长 |
| `DEPLOY.md` | 保留 | 本文件，部署记录 |
| `SUMMARY.md` | **已删除** | 与新 README 内容重复 |

## 没有上传

- `web-ui/node_modules/`（依赖，可 `npm install` 还原）
- `web-ui/dist/`（构建产物，单独发到 `gh-pages` 分支）
- `.workbuddy/`（本地工作记录）、`备份文件/`（本地备份）
- `web-ui/.edge-shot-profile/`、`favicon-*.svg` 等临时验证文件
- `*.mp4` / `*.wav` / `__pycache__` / `*.pyc` / `out/` / `preview/`

## 验证状态

| 检查项 | 结果 |
|---|---|
| `npm run smoke` | 16 passed, 0 failed |
| `npm run build` | 通过 |
| 源码推送 | 成功，`main` = `cde2ef6` |
| gh-pages 发布 | 成功，`gh-pages` = `10dc7f1` |
| 线上页面 | `https://blog.oxzh.top/KineType/` 返回 200 |

## 更新流程

```bash
git add . && git commit -m "..." && git push
npm run build
npx gh-pages -d web-ui/dist -b gh-pages
```

然后把新的 commit hash 更新到本文件。
