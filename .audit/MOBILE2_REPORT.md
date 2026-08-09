# MOBILE2 报告 — 移动端体验深化（hackathon 轮 2-A）

日期：2026-08-10 ｜ 范围：frontend/public、frontend/src/**、frontend/index.html、wxcloudrun/site_routes.py（仅新增 PWA 静态路由）

## 一、完成情况

| 任务 | 状态 | 说明 |
|---|---|---|
| 1. PWA 化 | ✅ | manifest.json + 图标 + service worker，离线 shell 可用 |
| 2. iOS 细节 | ✅ | viewport-fit=cover、safe-area、tap-highlight、16px 输入框 |
| 3. 触觉与反馈 | ✅ | 按钮统一 :active、Toast slide-in、events 页下拉刷新 |
| 4. 深链接/剪贴板 | ✅ | 邀请码剪贴板自动检测弹窗（P2 项一并做了） |
| 5. 暗色模式 | ✅ | [data-theme=dark] 变量覆盖层 + 系统偏好跟随（完整实现，非仅预留） |

## 二、改动清单

### 新增文件
- `frontend/public/manifest.json` — name/短名/主题色 `#E8553D`/背景 `#FFFAF5`/display standalone/start_url "/"/scope "/"，图标 192+512（any）+512（maskable）
- `frontend/public/sw.js` — 缓存策略：静态资源（/assets、/icons、manifest、favicon）cache-first；页面导航 network-first、离线回退缓存 shell；/api 不拦截（含私有数据，天然网络优先，离线走页面自带错误/重试 UI）；发版 bump `VERSION` 自动清理旧缓存。quick tunnel 域名变化时 SW 按 origin 独立安装，scope "/" 相对路径，无跨域污染
- `frontend/public/app-icon-mondrian.svg` + `icons/icon-192.png` / `icon-512.png` / `apple-touch-icon.png` — 品牌暖橙渐变 + 礼物盒 + 蒙德里安角标。SVG→PNG 用 macOS QuickLook 渲染（ImageMagick 内建渲染器不支持渐变，初版背景渲染为黑色，已换渲染器并逐像素校验）
- `frontend/src/utils/theme.ts` — 主题应用：localStorage 手动覆盖 > 系统 prefers-color-scheme；系统变化自动跟随

### 修改文件
- `frontend/index.html` — viewport 加 `viewport-fit=cover`；加 manifest/apple-touch-icon/mobile-web-app-capable/apple-mobile-web-app-title
- `frontend/src/main.tsx` — 渲染前 `applyTheme()`（防暗色首帧闪白）；`import.meta.env.PROD` 下注册 SW（dev 不注册）
- `frontend/src/tokens/tokens.css` — 追加 `:root[data-theme='dark']` 语义层覆盖（暖深色板，品牌色提亮一档保对比度，color-scheme: dark）
- `frontend/src/styles/global.css` — `-webkit-tap-highlight-color: transparent`；`button/a/input/...` 加 `touch-action: manipulation`（消双击缩放延迟）；`.page-container`/`.toast-container` 底部 safe-area；`.btn:active:not(:disabled)` 统一 scale(0.97)+opacity(0.9)；toast 动画改底部 slide-in
- `frontend/src/styles/header.css` — 吸顶 header `padding-top: env(safe-area-inset-top)`（刘海屏背景延伸）
- `frontend/src/styles/event-detail.css` — `.modal` 底部 safe-area padding
- `frontend/src/styles/events.css` — `.event-card:active` 微缩放；`.ptr-indicator` 下拉刷新指示器（含 spinner、ready 态）
- `frontend/src/pages/EventsPage.tsx` — 下拉刷新（原生非 passive touch 监听接管手势，阻尼 0.45，阈值 72px；`overscroll-behavior-y: contain` 关浏览器原生 PTR 防双触发；刷新复用 `load(tab)`，ref 防闭包过期）+ 剪贴板检测（每会话一次，识别 `/events/<code>` 链接或纯 6 位码，自动打开「用邀请码加入」弹窗并预填；弹窗打开时也尝试预填）
- `wxcloudrun/site_routes.py` — 新增 4 条静态路由：`/manifest.json`（mimetype application/manifest+json）、`/sw.js`（text/javascript，SW 必需）、`/icons/<path>`、`/app-icon-mondrian.svg`（顺带修复了原本 404→HTML 的坏 favicon 引用）

## 三、验收证据（浏览器实测，390×844 headless Chrome）

```
manifest parse                    ok  name=互送礼物 display=standalone icons=3
SW registered + activated         ok  scope=http://127.0.0.1:8080/ controller=true
offline shell renders             ok  #root 渲染、文本输出（离线时 /api/me 失败 → 登录页 shell）
viewport-fit=cover                ok  meta 生效
safe-area env() rules in CSS      ok  toast/header/page-container 三处规则均存在
tap-highlight transparent         ok  rgba(0,0,0,0)
input font >= 16px                ok  16px
no horizontal scroll @390         ok  overflow=0px
dark theme (prefers-color-scheme) ok  body bg rgb(22,17,16)=#161110，卡片 rgb(36,30,25)=#251E1A
back to light                     ok  #FFFAF5
clipboard code -> modal prefilled ok  剪贴板 ABC123 → 弹窗自动打开并预填
pull-to-refresh                   ok  顶部下拉 → 列表重载（15 张卡 → 20 张），overscroll=contain
console/page errors               ok  全流程无异常（离线期 ERR_INTERNET_DISCONNECTED 为预期）
```

服务端：`/api/health` 200；`/manifest.json`/`/sw.js`/`/icons/icon-192.png`/`/app-icon-mondrian.svg` 均 200 且 MIME 正确（application/manifest+json、text/javascript、image/png、image/svg+xml）。

亮/暗色截图存档：`.audit/mobile2-shots/light.png`、`dark.png`（像素采样验证卡片与背景 token 生效；本环境无 vision 模型，未做人工目检）。

## 四、测试与构建

- `npm run build` ✅（139 模块，产物已含 gift-clip-prompted/ptr-indicator/dataset.theme/serviceWorker 注册；templates/index.html 与 static 同步）
- `py_compile wxcloudrun/site_routes.py` ✅
- `pytest tests -q` ⚠️ 1 个失败：`tests/test_consistency.py::TestDashboardCounts::test_dashboard_counts_follow_state`（`unpostedGifts` 期望 1 实得 0，断言在 `tests/test_consistency.py:488`）
  - **与本任务无关**：该文件是另一并行任务未提交的新文件（git untracked），且其依赖的 `wxcloudrun/event_routes.py` 正被该任务在途修改（git status 可见 M）。dashboard 统计逻辑在 event_routes.py，本任务唯一后端改动是 site_routes.py 新增 4 条静态路由（git diff 已确认）
  - 排除该文件后全量测试 ✅ 100% 通过（`pytest tests -q --ignore=tests/test_consistency.py`）

## 五、已知事项 / 取舍

- **SW 不缓存 /api**：含用户私有数据，多用户共用设备离线时会串数据；离线时页面走自带「加载失败 + 重试」UI，符合「网络优先 API」验收
- **剪贴板读取**：需 HTTPS + 权限；无权限/无手势时静默降级（不影响主流程），弹窗打开时二次尝试预填
- **暗色模式**：跟随系统偏好；SharePoster 画布为固定白底海报（设计如此，不随主题）；其余页面均走 token，实测无破版
- **PTR 与原生下拉刷新**：events 页挂载期间 `body.overscroll-behavior-y: contain`（Chrome Android / iOS 16.4+ 生效；旧 iOS 上两者并存，下拉均会刷新，行为无害）
- 未 commit（按要求）
