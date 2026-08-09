# PERF3_REPORT — 性能极限 + 细节打磨（hackathon 轮14）

日期：2026-08-10（未 commit）· 域：frontend/src/**、frontend/vite.config.js、wxcloudrun/helpers.py、wxcloudrun/event_routes.py、tests/test_api_slim.py
验证：pytest **269 passed**（+4 新用例）· `npm run build` 通过 · Flask 已重启 · 浏览器实测端到端
截图：`.audit/r14_shots/404-desktop.png`、`.audit/r14_shots/404-mobile.png`

---

## 任务 A：性能极限

### A1 bundle 再压缩

**未用依赖核查**：`package.json` 仅 react / react-dom / react-router-dom / qrcode，全部在用。
qrcode 只在懒加载的 PosterModal chunk（EventDetailPage 用）——首屏不加载，无未用依赖可删。

**vendor 拆分（vite manualChunks）**：react 运行时（react/react-dom/scheduler）→ `vendor-react`；
react-router-dom/history/@remix-run → `vendor-router`。应用代码更新时两个 vendor chunk 哈希不变，
浏览器缓存命中，每次发版只重下应用 chunk。

| 产物（首屏 JS） | 优化前 | 优化后 |
|---|---|---|
| 主 bundle index | 231,464 B（gzip 75,861 / brotli 65,517） | **56,237 B**（gzip 19,738 / brotli 16,494） |
| vendor-react | — | 142,377 B（gzip 45,600） |
| vendor-router | — | 21,568 B（gzip 8,052） |
| **匿名首屏合计** | **231,464 B（gzip 75,861）** | **220,182 B（gzip 73,390）**（-4.9% raw / -3.3% gzip） |
| **单次发版重下量** | gzip 75,861 | **gzip 19,738（-74%）** |

懒加载拆分：EventsPage 10.6K / EventDetailPage 37.2K / PosterModal+qrcode 29.2K / Profile 12.5K /
CreateEvent 9.5K / GiftWall 8.7K / Dashboard 5.3K / ImageUpload 2.5K / NotFound 0.6K（gzip 后 0.4K）。

**压缩率**：首屏 JS brotli 63,565 vs gzip 73,390（**brotli 再省 13.4%**）。nginx 为平台托管层，
代码侧无法配置 gzip_static/brotli；若部署层支持 brotli 模块可直接再省（数字已给出，未改代码）。

### A2 图片优化 — 上传前前端压缩（实现并实测）

`frontend/src/utils/imageCompress.ts` + `ImageUpload.tsx` 接入：

- 长边 >1600 降采样；JPEG/WebP 重编码 quality 0.8；PNG 仅降采样时重编码（保 alpha）；
  GIF 跳过（canvas 丢动画）；≤256KB 跳过（无收益）；结果不小于原文件则回退原文件。
- **扩展名同步改写**：JPEG 内容文件名必改 `.jpg`——后端 /api/upload 按「扩展名 + content-type +
  魔数」三重校验（JPEG 内容配 .png 会被拒）。
- 解码主路径 `createImageBitmap`（线程外解码 + EXIF from-image），Safari 12–14 回退 Image+objectURL。

**实测**（无头 Chromium 端到端，3000×2000 噪声 JPEG 4,532,987 B）：上传后存储 **569,871 B（-87.4%）**，
魔数 `FF D8 FF` 正确，扩展名 `.jpg`，预览正常。

**过程中发现并修复一个真 bug**：原实现 `ImageBitmap.close()` 在 `drawImage` **之前**调用，
绘制已关闭 bitmap 抛 `InvalidStateError`（DOMException，非 ApiError）→ 上传被 catch 误报
「上传失败，请稍后重试」→ 所有上传全挂。修复：先 drawImage 再 close（imageCompress.ts 有注释防回归）。

### A3 API 响应瘦身（2 处）

后端字段核对（scout 全端点比对「返回字段 vs 前端消费」）后落地：

1. **列表端点轻量载荷** `helpers.api_event_summary()`：mine/joined/public/archived 4 个列表
   改返回 10 字段（code/shortCode/title/budget/note/drawDate/status/participantCount/coverImage/
   maxParticipants）。移除列表零消费的 excludedPairs/ownerId/ownerName/archived/matchVisibility/
   isPublic（public 列表 50 条 × 每条 excludedPairs 数组 + 元数据 = 最大冗余）；note 服务端截断
   至 80 字符+「…」（前端卡片单行 ellipsis，视觉一致）。详情端点保持 api_event 全文。
2. **api_event 移除 createdAt/updatedAt**：全前端（含详情）零消费，从序列化中删除。

新契约测试 `tests/test_api_slim.py`（4 用例）：mine/public 载荷字段集合恰为 summary、
note 截断 81 字符、短 note 不截断；detail note 全文 + excludedPairs 保留、无 createdAt/updatedAt。
线上 curl 验证 mine 首条 keys = 10 个 summary 字段。

### A4 预加载 — 登录后预取路由 chunk

- `EventsPage` 由首屏直出改为懒加载（React.lazy）；`clearListState` 拆到
  `utils/listState.ts`（Header 在首屏 bundle，直接 import EventsPage 会把它拉回主包，故解耦）。
- `AuthContext`：user 就绪（登录 / 注册 / 会话恢复三路径统一）→ `import()` 预热
  EventsPage + EventDetailPage（列表点击第一去向）。登录响应返回前 chunk 已开始下载，
  /events 首帧无额外等待。浏览器实测：登录后直接渲染列表，无 spinner 闪烁；
  会话恢复路径下 EventsPage/EventDetailPage chunk 在页面加载 26ms 即被请求。

---

## 任务 B：细节打磨（走查）

### B1 统一 404 页 — 已实现
`pages/NotFoundPage.tsx`：React Router `*` 路由从「静默跳 /events」改为 404 页
（🎁 logo + 404 + 「页面不存在」+「回到首页」按钮，复用 auth-card 布局）。
实测：`/no-such-page` → 标题「页面不存在 - 互送礼物」，按钮可回 /events；
375px 视口 scrollW==clientW==375 无横向溢出。截图：`r14_shots/404-desktop.png`、`404-mobile.png`。

### B2 浏览器标题 — 已实现
新增 `utils/usePageTitle.ts`（随语言切换，格式 `{页名} - 互送礼物`），9 个页面接入：
登录/注册/找回密码/我的活动/创建活动/活动详情（**加载后显示活动名**，如
「R13 截止提醒演示 - 互送礼物」）/活动管理台/礼物墙/个人资料/404。
实测：zh 与 en 标题均正确（en 无头浏览器默认 navigator.language=en，显式 zh 验证通过）。

### B3 图标统一 — 结论：无混用，无需改
Header 全部 emoji（品牌 🎁、铃铛 🔔、avatar 首字母），与全站 emoji 设计语言一致；
Header.tsx 无任何内联 SVG。P3 项「简单做」——结论即达，未引入 SVG 增加复杂度。

### B4 favicon / 404 静态检查 — 通过
- `/app-icon-mondrian.svg` → **200 image/svg+xml**（site_routes 显式 mimetype）✓
- 未知 `/api/*` → JSON 404（`{code:-1,...}`，前端不拿到 HTML）✓
- 未知 `/assets/*` → 404（Flask send_from_directory）✓
- PWA manifest/apple-touch-icon 均就位（manifest.json 显式 application/manifest+json）✓

---

## 验证汇总

- pytest tests：**269 passed**（258 存量 + 4 新 API 瘦身契约 + 7 前一既有计数）
- `npm run build` 通过；Flask 已重启（模板缓存刷新，index-ByB0iX3f.js）
- py_compile helpers.py / event_routes.py / site_routes.py 通过
- 浏览器实测：登录流、/events 懒加载渲染、详情页活动名标题、404 页、上传压缩端到端
  （存储文件 -87.4% + 魔数 + 扩展名）、375px 无破版、中英标题

## 遗留观察（未改，原因明确）

- **i18n en 字典在主包**：全量 en 字典（~500 条）随 i18n.ts 进首屏 bundle（估算 ~20KB raw /
  ~7KB gzip），zh 默认用户并不需要。可拆「en 字典懒加载」但需把 t() 改为异步/分区加载——
  触及 i18n 核心（50KB、全站依赖），收官轮判定风险 > 收益，记录数字供后续评估。
- **sw.js 对 /assets 为 cache-first**：发版靠内容哈希换 URL 天然避开旧缓存，无需改动；
  若未来手动改同 URL 产物需记得 bump VERSION。
- 压缩后体积受内容影响（噪声图 0.8 质量重编码 569–818KB 波动），常规照片预期 200–500KB。
