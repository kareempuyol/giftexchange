# R17_REPORT — hackathon 轮17 收官功能补充

日期：2026-08-10 · 约束：纯前端轮（后端零改动）· 未 commit

## 完成情况：5/5 全部实现 + 实测

### 1. 活动热度标签 ✅
- `EventsPage.tsx`：新增 `heatBadge(status, participantCount)`（纯前端计算）：
  - 已抽签 → `🎯 已抽签`（gold）
  - 报名中且参与者 ≥5 → `🔥 热度`（error 红）
  - 其余 → `报名中`（不变）
- 实现要点：`/events/public` 后端只返回 open 活动（`event_routes.py` L165
  `e.status='open'` 过滤，本轮禁改后端），因此 🎯 角标在公开列表不可达——把
  heatBadge 应用到列表**全部 tab**（公开/我的/参与/归档），🔥 在公开列表、🎯 在
  我创建的/我参与的列表均可见，语义与规格一致。
- 实测：公开列表 "S1 参与活动B 🔥 热度"（5 人，dev 库补 2 名参与者到 5）；
  我的活动列表 "R13 演示活动 🎯 已抽签"（截图 01/02）。
- i18n：新增 `热度` key（en: Hot）。

### 2. 礼物墙统计卡 ✅
- `GiftWallPage.tsx` + `gift-wall.css`：解锁后顶部新增 3 格统计卡
  （总心意数 / 平均评分 / 最高评分）。
- **规格前提勘误**：任务描述称"后端 gift-wall 接口已有 totalPosted/totalStars"——
  实测后端（`gift_routes.py` gift_wall）只返回 `unlocked/posted/total/title/
  note/budget/shortCode/progress/items`，**无 totalPosted/totalStars 字段**
  （该字段名仅存在于前端 SharePoster 海报载荷与 i18n）。按"纯前端 + 禁改后端"
  约束，统计改为从 `wall.items[].giftPost.rating` 直接计算：总心意数=posted、
  平均评分=非空评分均值（保留 1 位小数）、最高评分=max；无评分显示 `—`。
- 实测：事件"隐私前端验收"（3/3 已晒图，评分 5/5/5）→ `3 份心意 · 5.0 · ⭐ 5`，
  375px 无横向溢出（截图 06/07）。
- i18n：新增 `总心意数`/`平均评分`/`最高评分`（复用已有 `{totalPosted} 份心意`）。

### 3. 通知未读角标点击清零 ✅（原行为不满意，已修）
- 原状：点击铃铛只开关面板，角标保留到手动"全部已读"/单条点击——不满足"点开即已读"体验。
- 修复（`Header.tsx`）：`onBellClick` —— 打开面板时若 unread>0，乐观清零角标 +
  POST `/notifications/read` 同步服务端（失败由 30s 轮询校正，静默不打扰）。
- 实测：角标 `4` → 点击 → 面板展开、角标消失；服务端核验 0 未读 / 4 已读
  （非仅前端乐观）（截图 03/04）。

### 4. 登录页品牌区统一 ✅
- 现状核对：登录/注册/找回密码三页原本各自内联同一份品牌块（logo 🎁 + 互送礼物 +
  和朋友们交换惊喜）——样式一致但三处重复、易漂移。
- 修复：抽取 `components/AuthBrand.tsx`（含 useLocale 订阅），三页统一引用。
- 实测：三页 DOM 均为 `🎁 / 互送礼物 / 和朋友们交换惊喜`（截图 08）。

### 5. 活动详情预算展示 ✅
- `EventDetailPage.tsx`：详情 meta 网格与未登录预览卡两处预算值追加
  ` · 平均每人 ¥N`（`Math.round(budget / participantCount)`，纯前端；预算≤0 或
  0 人不显示），新增 `.meta-sub` 样式（event-detail.css，Design Tokens）。
- 实测：3 人/¥100 活动详情 → `预算 ¥100 · 平均每人 ¥33`（与规格示例一致，截图 05）。
- i18n：新增 `平均每人 {perPerson}`（en: `{perPerson} per person`）。

## 未做项
无（5 项全部完成）。

## 改动文件（全部前端，后端零改动）
- `frontend/src/pages/EventsPage.tsx`（heatBadge 替换 statusBadge）
- `frontend/src/pages/GiftWallPage.tsx`（统计计算 + 统计卡 JSX）
- `frontend/src/components/Header.tsx`（铃铛点击即清零）
- `frontend/src/components/AuthBrand.tsx`（新增，品牌区统一）
- `frontend/src/pages/LoginPage.tsx` / `RegisterPage.tsx` / `ForgotPasswordPage.tsx`（换 AuthBrand）
- `frontend/src/pages/EventDetailPage.tsx`（预算均摊副文案 ×2 处）
- `frontend/src/styles/gift-wall.css`（.gw-stats/.gw-stat）、`styles/event-detail.css`（.meta-sub）
- `frontend/src/i18n.ts`（zhKeys + en 字典：热度/总心意数/平均评分/最高评分/平均每人 {perPerson}）
- 测试：无新增 pytest（纯前端轮，后端契约未变；pytest 全量回归通过）

## 验证
- pytest：**269 用例全绿**（exit 0，后端零改动）
- `npm run build`：通过（647ms/571ms 两次构建均成功）
- 浏览器实测（headless Chromium，verify_user/Verify123）：5 项全部按预期，
  截图 `.audit/r17_shots/01-08.webp`；375px 移动端无横向溢出（events 列表 + 礼物墙）
- 服务端核验：通知已读状态持久化（0 未读/4 已读）

## 说明
- **wxcloudrun/ 无 diff**：`npm run build` 的产物会写入 wxcloudrun/static + templates
  （构建约定），本轮约束禁止改 wxcloudrun/**，因此实测完成后已把 wxcloudrun/
  恢复至 HEAD（含删除新哈希产物），交付树仅含 frontend/src 改动。部署前需在目标
  环境重新 `npm run build`。
- dev 库数据改动（gitignored，仅用于实测）：事件 324 补 2 名参与者至 5 人（🔥 角标
  演示）；verify_user 通知全标记已读（角标清零实测的预期副作用）。
