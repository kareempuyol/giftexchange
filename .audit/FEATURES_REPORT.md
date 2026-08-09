# FEATURES_REPORT — hackathon 轮13 功能增量

日期：2026-08-10 · 分支：未 commit（按约束）· 交付标准：pytest 全绿 + build 通过 + 浏览器实测

## 做了哪些（5/5 全部完成）

### 1. 活动模板复制（复制活动）✅
- 入口：已抽签活动详情页（组织者视角）「📋 复制活动」按钮（归档按钮下方）。
- 行为：把当前活动 title 加「（副本）」、budget/note/公开性/人数上限/互避规则/成员名单
  写入「再开一局」同款 `gift_draft` 草稿 → 跳转创建页（成员不自动加入）。
- 互避规则：excludedPairs 是 userId 对 → 用成员名单反查用户名，转成创建页
  「用户名1, 用户名2」行格式（`verify_user, r13demo_b`），成员不在名单时跳过该行。
- 改动：`EventDetailPage.tsx`（onCopyEvent + 按钮）、`CreateEventPage.tsx`
  （draft 读取扩展 isPublic/matchVisibility/maxParticipants/rulesText）。
- 实测：点击后 URL → `/events/new`，表单预填 title "R13 演示活动 (copy)"、预算 200、
  上限 5、公开态、4 人名单、互避规则 1 行（截图 03/04）。

### 2. 礼物墙分享文案 ✅
- 入口：礼物墙顶部「📋 复制分享文案」按钮（解锁前后都可用——分享给好友加入是
  未解锁时的核心诉求；高光海报仍仅解锁态显示）。
- 文案：`「{title}」互送礼物活动！{total} 人参与，{posted} 份心意已送出 🎁 邀请码：{shortCode}，快来加入：{url}`
- 后端：gift-wall 响应新增 `shortCode` 字段（`gift_routes.py`）。
- 实测：剪贴板读回 =
  `Gift exchange "R13 演示活动" is on! 4 people joined, 0 gifts already shared 🎁 Invite code: EY8CZH — join now: http://127.0.0.1:8080/events/EY8CZH`
  （活动名/人数/心意数/短码/加入链接齐全；截图 05）。

### 3. 心愿清单（wishlist）✅（P2 完成）
- 迁移 v12：`users.wishlist`（TEXT）+ `users.wishlist_visible`（TINYINT DEFAULT 0）。
- 个人资料页新增「心愿清单」输入框 + 「加入活动时展示给送礼人」开关
  （`ProfilePage.tsx`，PUT /profile 已支持两字段，500 字上限校验）。
- 送礼任务区显示 `🎁 TA 的心愿：{wish}`：my-match 返回 `receiverWishlist`，
  **仅当收礼人开启展示时返回**（隐私门控，`draw_routes.py`）。
- 实测：r13demo_d 开启展示 → verify_user 任务区显示 "🎁 TA 的心愿：想要一台 Kindle 阅读器 📚"；
  r13demo_b 未开启 → 送礼人侧为空字符串（截图 03/08）。

### 4. 截止提醒横幅 ✅
- 活动详情页（组织者视角）已过 drawDate 未抽签 → 顶部红色横幅
  「⏰ 已过截止时间，请尽快抽签」（纯前端计算，无后端改动）。
- 实测：过去截止日期的 open 活动显示横幅（en/zh 各验一次，截图 02/07）。

### 5. 参与人数实时感（X/N 人）✅
- 列表卡片：有 maxParticipants 时显示 `{count}/{max} 人`，否则维持 `{count} 人参与`
  （`EventsPage.tsx`，纯前端；participantCount/maxParticipants 接口已有）。
- 实测：列表卡片显示 "4/5 people"、"1/3 people"（截图 01）。

## 放弃的
无（5 项全部实现）。

## 改动文件
- 后端：`wxcloudrun/migrations.py`（v12）、`helpers.py`（public_user）、
  `auth_routes.py`（update_profile）、`draw_routes.py`（my-match）、`gift_routes.py`（gift-wall shortCode）
- 前端：`api/client.ts`、`i18n.ts`（12 组 zh/en key）、`pages/ProfilePage.tsx`、
  `pages/EventDetailPage.tsx`、`pages/GiftWallPage.tsx`、`pages/EventsPage.tsx`、
  `pages/CreateEventPage.tsx`、`styles/event-detail.css`
- 测试：`tests/test_features_r13.py`（新增 8 用例）、`tests/test_migrations.py`（v12 断言更新）

## 验证
- pytest：**265 用例全绿**（含新增 8 个：迁移 v12 / profile 读写 / wishlist 隐私门控 / gift-wall shortCode）
- py_compile：wxcloudrun/*.py 全部通过
- `npm run build` 通过（产物已更新 wxcloudrun/static + templates/index.html）
- 浏览器实测（headless Chromium，verify_user + 3 个演示账号）：5 项功能全部按预期，
  截图见 `r13_shots/01-08.webp`
