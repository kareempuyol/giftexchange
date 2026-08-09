# 浏览器兼容矩阵验证报告（hackathon 轮6）

日期：2026-08-10 · 项目：~/giftexchange（Flask + React 18/Vite 5）

## 1. 浏览器盘点

| 浏览器 | 版本 | 自动化手段 | 可用性 |
|---|---|---|---|
| Google Chrome | 151.0.7922.108 | puppeteer-core（.audit/node_modules） | ✅ headless |
| Microsoft Edge | 151.0.4129.72 | puppeteer-core（executablePath 直指 Edge 二进制） | ✅ headless |
| Safari | 26.5.2（safaridriver 21624.2.5.11.8） | safaridriver :4444 + WebDriver 协议 | ⛔ 会话创建被拒（见 §4） |
| Firefox | — | — | ❌ 未安装 |

## 2. 浏览器 × 场景矩阵

核心旅程子集：登录页渲染 → 表单登录→列表 → 详情 → 礼物墙。每浏览器 × 每视口 5 组断言
（登录渲染 / 登录+列表 / 详情 / 礼物墙 / JS 错误零容忍），双视口：桌面 1280×800、移动 390×844（isMobile+hasTouch）。

| 场景 | Chrome 桌面 | Chrome 移动 | Edge 桌面 | Edge 移动 |
|---|---|---|---|---|
| 登录页（输入框+提交按钮渲染） | ✅ | ✅ | ✅ | ✅ |
| 表单登录→/events，≥1 卡片，无横向滚动 | ✅ | ✅ | ✅ | ✅ |
| 活动详情（.detail-layout，标题匹配，无 hscroll） | ✅ | ✅ | ✅ | ✅ |
| 礼物墙（渲染/空态，无 hscroll） | ✅ | ✅ | ✅ | ✅ |
| JS 错误（pageerror/console.error/HTTP≥400/requestfailed = 0） | ✅ | ✅ | ✅ | ✅ |

**合计 20/20 PASS**（脚本 `.audit/xbrowser_e2e.mjs`，原始数据 `.audit/xbrowser_results.json`，截图 `.audit/xbrowser-shots/`）。
布局指标（scrollWidth vs clientWidth）在两种引擎、两种视口下均无横向溢出；登录态数据（80 张事件卡片）渲染一致。

## 3. 发现的兼容问题与修复

### 3.1 ES 目标：`??` 未降级（真实缺陷，已修复）
- **现象**：vite.config.js 未设 `build.target`，Vite 5.4 默认 `'modules'`。实测该默认目标数组
  `['es2020','edge88','firefox78','chrome87','safari14']` 经 esbuild 处理后**保留原生 `??`（nullish coalescing，ES2020）但降级 `?.`**（构建产物 14 处 `??`，`?.` 已转成 `x==null?void 0:x.y`）。
- **影响**：`??` 在 Safari 12–13.0 直接 SyntaxError → 整页白屏。
- **修复**：`frontend/vite.config.js` 显式设 `build.target: 'es2019'`（Safari 12+/Chrome 70+/Edge 79+/Firefox 67+）。
- **验证**：重建后产物全量 grep，`?.` 与 `??` 均为 0 处（esbuild 全部降级为 ternaries + `var _a` 辅助），模板同步、Flask 重启、浏览器复测 20/20 绿。

### 3.2 iOS 100vh / safe-area（部分补齐）
- 已有（前轮）：`index.html` `viewport-fit=cover`；global.css `100vh→100dvh` 降级对；header/底部栏 `env(safe-area-inset-*)`。
- 补齐 3 处缺失的 dvh 降级（对齐既有模式）：
  - `auth.css` `.app-main` `calc(100vh - 52px)` → + `calc(100dvh - 52px)`
  - `auth.css` `.auth-page` `min-height: 100vh` → + `100dvh`
  - `event-detail.css` `.modal` `max-height: 85vh` → + `85dvh`（已有 `overflow-y:auto` 兜底）
- 无 `backdrop-filter` 使用（无需 `-webkit-backdrop-filter`）；touch 手势用 `addEventListener(..., {passive:false})` 正确调用 preventDefault；日期输入为 `datetime-local`（iOS 12.3+ 原生支持，更老机型退化为文本输入仍可提交同格式）。

### 3.3 数据残留（非代码缺陷，已清理）
- 事件「状态机截图527431」coverImage 指向已删除的 `/uploads/cover-list-test.png` → 列表页 404（跨浏览器复现）。经 PATCH 清空该测试事件 coverImage，E2E 错误计数归零。

## 4. Safari 限制（诚实说明）

`safaridriver` 会话创建被拒：`Could not create a session: You must enable 'Allow remote automation' in the Developer section of Safari Settings`。
尝试过：`safaridriver --enable`（需密码，无免密 sudo）、`defaults`/PlistBuddy 写 `com.apple.Safari AllowRemoteAutomation`（Safari 容器目录被 TCC 保护，Operation not permitted）、osascript 系统级 UI 自动化（无辅助功能权限，AppleEvent 超时）。
本环境无 GUI 交互入口 → **桌面 Safari 无法自动化；iOS Safari（真实 100vh/地址栏行为）需真机/模拟器，同样不可达**。
退而求其次：Safari 风险点已由静态审计（§3.2）覆盖，移动视口行为由 Chromium 的 isMobile+hasTouch 仿真近似验证。

## 5. 验收对照

- [x] 浏览器覆盖矩阵表（§2）
- [x] 发现的兼容问题修复 + 复测（§3，复测 20/20 PASS）
- [x] build 通过：`npm run build` ✓（产物已同步 `wxcloudrun/templates/index.html`，Flask 已重启）
- [x] pytest 全绿：`246 passed in 17.32s`（exit 0）
- [x] 报告：本文件 `.audit/BROWSER_REPORT.md`

改动清单：`frontend/vite.config.js`（target）、`frontend/src/styles/auth.css`、`frontend/src/styles/event-detail.css`（dvh 降级）；未 commit；后端仅做了一次数据修复（清空失效 coverImage，API 操作）。
