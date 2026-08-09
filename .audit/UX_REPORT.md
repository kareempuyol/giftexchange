# UX 打磨报告（hackathon 波次1-B）

- 日期：2026-08-10
- 范围：`frontend/src/**` + `.audit/**`（未 commit；`wxcloudrun/**` 仅含 `npm run build` 强制产物）
- 视口：375×812（移动端，deviceScaleFactor 2），puppeteer-core + 本地 Chrome
- 服务：http://127.0.0.1:8080（build 后按 AGENTS.md 规范重启，health 200）
- 测试账号：`e2e_alice_mslziob9 / Alice1234`（历史富数据：drawn 活动 AW9BCN、解锁礼物墙）+ 本轮新建 `ux_*` 新用户（空态素材）
- 验证脚本：`.audit/ux_audit.mjs`（修复前 375px 审计）、`.audit/ux_audit_after.mjs`（修复后全量复检 + 错误边界实测）、`.audit/ux_smoke_8080.mjs`（8080 冒烟）
- 截图：`.audit/ux-shots/`（35 张，A/C/D/B 前缀 = 修复后，数字前缀 = 修复前）

## 一、清单逐项结论

### 1. Loading 态 ✅（一处增强）
- 现状：全部页面（events/详情/管理台/礼物墙/个人中心）已有 `.page-loading` 文案；收到礼物区块加载中隐藏。
- 缺陷：纯文字无视觉反馈；通知面板首拉无 loading（打开即空白）。
- 修复：
  - `global.css`：新增纯 CSS `.spinner`，所有 `.page-loading` 升级为 spinner + 文案（无新依赖）。
  - `Header.tsx`：通知面板首拉完成前显示「加载中…」（`notifLoaded` 状态）。
- 证据：`B01-events-mine`、`B03-event-detail-drawn`、`B04-dashboard`、`B08-notif-panel-open`。
- 观察项（未改）：详情页「我收到的礼物」区块加载中返回 null（短暂空白，无布局抖动风险，属可接受）。

### 2. 空态 ✅（补 5 处 CTA/引导）
- 已有：我创建的（创建第一个活动 ✅）、我参与的（用邀请码加入 ✅）、已归档（无 CTA 合理 ✅）、通知空（暂无通知 ✅）。
- 缺陷与修复：
  - **发现活动无结果**：仅文案无动作 → 补「创建公开活动」CTA（`EventsPage.tsx`）。
  - **礼物墙未解锁**：仅进度文案 → 补「去晒出你的礼物」CTA 链接回详情页（`GiftWallPage.tsx`）。
  - **礼物墙解锁但空**：补「返回活动晒出第一份礼物」CTA。
  - **参与者（0）**：详情页参与者列表空白 → 组织者视角显示「复制邀请链接」CTA、参与者视角显示等待文案（`EventDetailPage.tsx`）。
  - **管理台无参与者**：进度明细空表 → 空态 + 「去复制邀请链接」CTA（`DashboardPage.tsx`）。
- 边缘缺陷：0 参与者活动礼物墙显示「0/0 已送出…还差 0 人解锁」→ 改为「还没有人加入活动，礼物墙稍后揭晓 🎁」（`GiftWallPage.tsx`，复验通过）。
- 证据：`A01-events-mine-empty`（DOM 断言：标题「你还没有创建活动」+ CTA「创建第一个活动」）、`A02/03/05`、`A06`、`A07`、`A08`。

### 3. 错误边界 ✅（新增，App 级 + 活动详情级）
- 现状：无任何 ErrorBoundary，渲染崩溃 = 白屏。
- 修复：新增 `components/ErrorBoundary.tsx`（class 组件，fallback「😵 页面出错了 / 渲染时遇到了一点问题，刷新重试即可」+ 刷新按钮）；`App.tsx` 包整个路由树 + 活动详情路由单独再包一层（详情崩溃不波及全局，Header 存活）。
- 实测（响应拦截注入崩溃数据，`ux_audit_after.mjs`）：
  - App 级：礼物墙接口返回 `items:[null]` → 渲染崩溃 → 兜底页出现（`D01-error-boundary-app.png`）。
  - 详情级：my-match 返回 `preference:null` → 详情崩溃 → 兜底页出现且 Header 仍在（`D02-error-boundary-detail.png`，`headerAlive:true`）。
- 证据：`D01`、`D02` 截图 + 控制台断言。

### 4. 表单体验 ✅（补 4 处校验 + 1 处防连点）
- 已有：标题必填、提交中 disabled+loading（创建/加入/晒图/发货/资料/改密码/注销/登录注册全覆盖）、失败后表单保留输入（React state，未丢数据 ✅）。
- 缺陷与修复（`CreateEventPage.tsx`）：
  - **预算负数/非法数字**：`type=number min=0` 不阻止手输 → 前端显式校验「预算不能为负数或无效数字」。
  - **报名截止早于现在**：`datetime-local` 可选过去日期 → 校验「报名截止日期不能早于现在」。
  - **人数上限 <2 或 >999**：→ 校验「人数上限至少为 2 人 / 不能超过 999」。
- **恢复活动**：`EventsPage.tsx` 恢复按钮无防连点/无加载态 → 增加 per-row `restoring` 状态（disabled + 「恢复中…」），失败 toast 透传后端错误。
- 证据：`B06-create`、`A06b-join-form`。

### 5. 移动端 375px ✅（0 横滚，点击目标全部 ≥40px）
- 修复前审计（`ux_audit.mjs`，11 页）：全部无页面级横滚；但两项边缘缺陷：
  - **通知面板左缘被裁 3px**：移动端 `right:-60px` 绝对定位在 375px 下 panel 左缘出视口（实测 left=-3）→ 改为 `position:fixed; top:60px; right:12px; width:min(320px, calc(100vw-24px))`（`header.css`），任意宽度均不裁切。
  - **点击目标 <40px**：`.app-brand`（89×26）、`.app-username`（30×30）、`.gw-like-btn`（≈32 高）、晒图评分星星（≈28）、`.notif-mark-all`（36 高）→ 全部补齐 min-height/min-width 40px（`header.css` / `gift-wall.css` / `EventDetailPage.tsx` 星星内联样式）。
- 修复后复检（`ux_audit_after.mjs`，21 个页面状态）：**0 横滚**；tap-targets 断言 events/详情/礼物墙 **全部 ≥40px**。
- iOS 键盘遮挡：此前已有 `scroll-margin-bottom:80px`，维持 ✅。
- 额外保险：管理台表格包 `.dash-table-wrap{overflow-x:auto}` + `min-width:480px`（375px 内滚动不撑破页面）。
- 证据：`B01`-`B08`、`C01`-`C03`（DOM scrollWidth==375 断言）。

### 6. 按钮一致性 ✅（无代码缺陷）
- 全部危险操作（归档/重新抽签/删除晒图/注销账号）均为 error 色（`--gift-error`）+ 二次确认弹窗，无直接执行。
- 每个视图主操作仅一个 primary（列表页「+ 创建活动」、详情页随状态唯一、礼物墙「生成高光海报」），其余 secondary/ghost。
- 「重置邀请码」为中性操作，ghost + 确认弹窗，符合层级。结论：符合既有规范，无改动。

### 7. Toast 体验 ✅（补 2 处失败提示）
- 已有：加入/抽签/发货/晒图/删图/保存资料/头像/偏好/改密码/归档/恢复/复制链接/点赞失败 均有 toast ✅。
- 缺陷与修复：
  - **通知操作失败静默**（全部已读/清空已读 `catch{}`）→ 失败弹 error toast（`Header.tsx`）；成功保持静默（角标即时变化即为反馈，避免噪音）。
  - **列表/详情/管理台加载失败误导为空态/不存在**：`EventsPage` 失败显示「加载失败 + 重试」而非「你还没有创建活动」；`EventDetailPage` 与 `DashboardPage` 同理（不再伪装成「活动不存在/无权限」）。
- 证据：`D01` 系列 + 代码断言（loadError 分支）。

### 8. 时间与数字格式 ✅（新增统一工具）
- 现状：截止时间用 `toLocaleDateString`（2026/8/20），预算裸拼 `¥100`（无千分位）。
- 修复：新增 `utils/format.ts` 三个共用函数，替换全部散落实现：
  - `formatDeadline`：`还剩 N 天 / 明天截止 / 今天截止 / 已截止（日期）`，>30 天回退日期。
  - `formatMoney`：`¥1,000` 千分位。
  - `formatCount`：千分位（预留）。
  - 应用点：`EventsPage` 卡片（「报名 还剩 11 天」）、`EventDetailPage` 元信息格 + 预览页 + 「预算参考」。
- 证据：`B01-events-mine`（视觉复审确认「报名 还剩 11 天」「¥100」）。

## 二、验收结果

| 项 | 结果 |
|----|------|
| `npm run build` | ✅ 通过（vite 5.4.21，136 modules；产物 `index-DC0Pn1-3.js`，已同步 templates/） |
| 重启 Flask + health | ✅ `GET /api/health` → `{"code":0,"data":{"status":"ok",…}}`；8080 返回新 bundle，asset 200 |
| 截图 .audit/ux-shots/ | ✅ 35 张（修复前 13 + 修复后 22） |
| pytest tests -q | ✅ **196 passed**（10.3s；后端零改动） |
| 375px 横滚 | ✅ 修复前 11 页 + 修复后 21 个状态，全部 `scrollWidth==375` |

## 三、修复前后对照（截图）

| 缺陷 | 修复前 | 修复后 |
|------|--------|--------|
| 通知面板 375px 左缘裁切 | `12-notif-panel-open.png`（left=-3） | `B08-notif-panel-open.png`（无裁切） |
| 列表加载失败误导空态 | （代码审计：catch 后置空） | `D01-error-boundary-app` 同款 error UI 模式 |
| 渲染崩溃白屏 | 无兜底 | `D01-error-boundary-app.png`、`D02-error-boundary-detail.png` |
| 我创建的/发现活动空态无 CTA | `01-events-mine`（旧版文案） | `A01-events-mine-empty.png`、`A03-events-public-no-result.png` |
| 礼物墙未解锁无动作 | `06-gift-wall-locked.png` | `A08-gift-wall-locked-empty.png`（含「去晒出你的礼物」CTA） |
| 截止时间 ISO 日期 | `01-events-mine`（2026/8/20） | `B01-events-mine`（报名 还剩 11 天） |
| 0 参与者礼物墙「还差 0 人」 | `A08`（旧文案） | 复验断言「还没有人加入活动，礼物墙稍后揭晓 🎁」 |

## 四、改动文件（仅 frontend/src + .audit）

- 新增：`frontend/src/components/ErrorBoundary.tsx`、`frontend/src/utils/format.ts`、`.audit/ux_audit.mjs`、`.audit/ux_audit2.mjs`、`.audit/ux_audit_after.mjs`、`.audit/ux_empty_shot.mjs`、`.audit/ux_wall_verify.mjs`、`.audit/ux_smoke_8080.mjs`、`.audit/ux_shots/*`
- 修改：`App.tsx`（双级 ErrorBoundary）、`pages/EventsPage.tsx`（加载错误+重试、public 空态 CTA、恢复防连点、时间/金额格式）、`pages/EventDetailPage.tsx`（加载错误+重试、参与者空态、截止格式、星星点击热区）、`pages/GiftWallPage.tsx`（未解锁/空态 CTA、0 参与者文案）、`pages/DashboardPage.tsx`（加载错误+重试、空表、表格横滚容器）、`pages/CreateEventPage.tsx`（预算/日期/人数上限校验）、`components/Header.tsx`（通知面板 loading + 失败 toast）、`styles/global.css`（spinner、错误边界样式）、`styles/header.css`（面板视口定位、点击热区）、`styles/gift-wall.css`（点赞热区）、`styles/dashboard.css`（表格容器）
- `wxcloudrun/static/*`、`templates/index.html`：`npm run build` 自动产物（验收要求，非手工改动）
- 未 commit；未改数据库/迁移/后端代码。

## 五、备注

- **8080 端口双实例**：并发「安全审计」任务另起了一个 `127.0.0.1:8080` Flask 实例（早于本轮 build），缓存旧模板引用已删除的 bundle（实测 asset 404 → 白屏风险）。已按 AGENTS.md 规范 `lsof -ti :8080 | xargs kill` 后重启单实例，8080 现返回新 bundle 且 asset 200。该任务若需自起实例，重启即可读到共享产物。
- 登录限速（15 分钟窗口，内存态）为既有后端行为，非本轮缺陷；验证期间通过独立 8081 实例隔离，未触碰任何账号密码。
- 观察项（未改）：收到礼物区块加载中为空白；通知读取单条/全部已读成功无 toast（角标即时反馈，避免噪音）——均为设计取舍，留待产品决策。
