# API 参考 — giftexchange

> 全部接口 REST + JSON，前缀 `/api`。响应统一 `{code, data, message}`：`code=0` 成功，`code=-1`（或 `-2` 未登录）失败；HTTP 状态码与 `code` 配合（401 未登录 / 403 无权限 / 404 不存在 / 429 限速）。
> 认证：`Authorization: Bearer <JWT>`（`/auth/login` 或 `/auth/register` 返回 `token`）。`<code>` 兼容 uuid 与 6 位短码。
> 本文档与 `wxcloudrun/*_routes.py` 的 `@api.route` 清单核对一致：**49 个接口，100% 覆盖**。

## 目录

- [1. 认证与账号 auth_routes（12）](#1-认证与账号)
- [2. 活动 event_routes（17）](#2-活动)
- [3. 抽签 draw_routes（4）](#3-抽签)
- [4. 送礼与礼物墙 gift_routes（9）](#4-送礼与礼物墙)
- [5. 通知 notify_routes（5）](#5-通知)
- [6. 站点与上传 site_routes（2）](#6-站点与上传)
- [附录 A：站点页面路由（非 API）](#附录-a站点页面路由非-api)
- [附录 B：通知类型表](#附录-b通知类型表)

---

## 1. 认证与账号

### 注册
- **POST** `/api/auth/register` · 公开
- 参数（JSON）：`username`（必填）、`email`（必填）、`password`（必填，≥8 位且含字母+数字）
- 响应：`{token, user}`；密码强度不合规返回 400 中文提示

### 登录
- **POST** `/api/auth/login` · 公开
- 参数：`username`、`password`
- 响应：`{token, user}`；失败 401；登录限速（超限 429）

### 忘记密码（获取重置码）
- **POST** `/api/auth/forgot-password` · 公开
- 参数：`username` 或 `email`（二选一）
- 行为：生成 6 位数字重置码（15 分钟有效，单用户单码，新码覆盖旧码），**不返回给请求方**（防任意重置）；按 `(IP, 账号)` 限速 429
- 响应：通用成功提示（不泄露账号是否存在）

### 重置密码
- **POST** `/api/auth/reset-password` · 公开
- 参数：`username`、`code`（6 位重置码）、`newPassword`（同注册强度规则）
- 响应：成功即新密码可用；码错/过期 400

### 当前用户
- **GET** `/api/auth/me` · 登录
- 响应：`public_user`（id/username/displayName/avatarUrl/isAdmin…）

### 注销账号
- **POST** `/api/auth/deactivate` · 登录
- 参数：`password`（验证身份）
- 行为：匿名化（释放原名/邮箱、密码置随机串）+ `deactivated=1`，不物理删除（保留活动/礼物墙数据完整性）；deactivated 用户登录一律 401

### 导出我的数据
- **GET** `/api/auth/export-data` · 登录
- 响应：个人资料 + 我创建/参与的活动 + 我的晒图记录（各类超量截断最近 100 条）

### 个人资料
- **GET** `/api/profile` · 登录 — 当前用户公开资料
- **PUT** `/api/profile` · 登录
- 参数：`displayName`、`avatarUrl`、`phone`、`address`、`receiverName`、`giftPreference`（部分更新）
- 响应：更新后的 `public_user`

### 修改密码
- **PUT** `/api/profile/password` · 登录
- 参数：`oldPassword`、`newPassword`（强度规则同注册）

### 管理设置
- **GET** `/api/admin/settings` · 管理员（`ADMIN_USERNAMES` env 或 `is_admin`）
- 响应：`SETTING_DEFINITIONS` 当前值（site_name / registration_enabled / shipment_tracking_enabled）
- **PUT** `/api/admin/settings` · 管理员
- 参数：设置键 → 新值（按定义校验类型）

---

## 2. 活动

### 创建活动
- **POST** `/api/events` · 登录
- 参数：`title`（必填 ≤100）、`note`（≤500）、`budget`（≥0）、`drawDate`（报名截止）、`matchVisibility`（private/public）、`isPublic`、`maxParticipants`（2–999）、`coverImage`（上传 URL）、`excludedPairs`（互避用户对数组）
- 行为：创建者自动成为参与者；生成 uuid `code` + 6 位 `shortCode`
- 响应：201 + 完整活动对象

### 活动列表（3 个视角）
- **GET** `/api/events/mine` · 登录 — 我创建的（未归档）
- **GET** `/api/events/joined` · 登录 — 我参与的
- **GET** `/api/events/archived` · 登录 — 我创建的（已归档）

### 公开活动广场
- **GET** `/api/events/public` · 登录
- Query：`search`（标题模糊）、`sort`（newest/…）、`filter`（all/…）
- 响应：公开活动列表（不含私密活动）

### 活动详情
- **GET** `/api/events/<code>` · 登录
- 响应：活动对象 + `flowState`（recruiting/drawing/active/completed）+ 权限字段；404「活动不存在或已失效」

### 游客预览（邀请落地页）
- **GET** `/api/events/<code>/preview` · **公开（无需登录）**
- 响应：标题/时间/人数等概要，**不泄露收件人/发货/匹配等敏感信息**

### 编辑活动
- **PATCH** `/api/events/<code>` · 登录，仅组织者
- 参数：同创建（部分字段）

### 删除活动（硬删除）
- **DELETE** `/api/events/<code>` · 登录，仅创建者
- 行为：物理删除（级联参与者/匹配）；与归档互补——前端 UI 无删除入口，仅归档

### 归档 / 恢复
- **POST** `/api/events/<code>/archive` · 登录，仅组织者 — 软删除：`drawn` 活动置 `archived=1`（`open` 直接删除）；归档只影响列表可见性，详情仍可访问
- **POST** `/api/events/<code>/unarchive` · 登录，仅组织者 — 置回 `archived=0`

### 重置邀请短码
- **POST** `/api/events/<code>/reset-short-code` · 登录，仅组织者
- 行为：生成新 6 位短码覆盖旧码，**旧链接立即失效**

### 加入活动
- **POST** `/api/events/<code>/join` · 登录
- 参数：`nickname`、`receiverName`/`phone`/`address`（收件信息）、`preferenceLikes`/`preferenceDislikes`/`preferenceNotes`、`updateProfile`（同时更新个人资料）
- 约束：仅 `open` 且未过截止、未满员、未重复加入
- 响应：201 + `{id, eventCode, userName}`；通知本人 `join_success` + 通知组织者 `participant_joined`

### 退出活动
- **DELETE** `/api/events/<code>/leave` · 登录
- 约束：仅 `open` 状态；创建者不能退出（须删除活动）

### 参与者列表
- **GET** `/api/events/<code>/participants` · 登录（公开活动所有登录用户可见；私密仅创建者+参与者）
- 响应：`{participants: [{id, userId, displayName, avatarUrl, contactComplete, preferenceComplete, joinedAt, status}], count}`；`status ∈ joined/ready/shipped/posted`

### 催办未完成成员
- **POST** `/api/events/<code>/remind` · 登录，仅组织者
- 行为：给所有 `status != posted` 的非组织者成员发 `remind` 通知（按阶段给不同文案）
- 响应：`{reminded: n}`

### 组织者仪表盘
- **GET** `/api/events/<code>/dashboard` · 登录，仅组织者
- 响应：`{participants: [...含 hasMatch/shipmentStatus/received/postedGift], count, pendingShipments, unpostedGifts, reminders: [{type, message}]}`

---

## 3. 抽签

### 抽签
- **POST** `/api/events/<code>/draw` · 登录，仅组织者
- 约束：仅 `open` 状态、已过截止可抽；人数 ≥2；互避规则无解时返回友好错误（预判见 `is_draw_solvable`）
- 行为：随机送礼环写入 matches（幂等：旧 matches 先清后建），通知全员 `draw_result`

### 重置抽签（重抽）
- **POST** `/api/events/<code>/redraw` · 登录，仅组织者
- 约束：仅 `drawn` 状态；清空旧 matches（含物流/晒图/点赞，级联）后重新分配；通知 `draw_redraw`

### 活动匹配总览
- **GET** `/api/events/<code>/matches` · 登录（参与者/组织者）
- 响应：全部 matches（giver/receiver 参与者信息 + 送礼状态）；`match_visibility` 控制详情字段

### 我的匹配
- **GET** `/api/events/<code>/my-match` · 登录（参与者）
- 响应：我的送礼对象 + 收礼人（含悄悄话/物流状态；敏感字段按权限裁剪）

---

## 4. 送礼与礼物墙

### 我的晒图
- **GET** `/api/events/<code>/received-gift` · 登录（参与者）
- 响应：我收到的礼物 + 是否已晒

### 晒图
- **PUT** `/api/events/<code>/received-gift` · 登录（仅收礼人本人）
- 参数：`matchId`（必填）、`rating`（1–5）、`review`（必填 ≤500）、`photoUrl`（上传 URL）、`privacy`（`photo` 公开照片 / `text` 仅文字 / `blur` 模糊照片）
- 行为：通知送礼人 `gift_posted`；全员晒完触发 `gift_wall_unlocked`（按事件去重，仅一次）

### 删除晒图
- **DELETE** `/api/events/<code>/received-gift` · 登录（仅收礼人本人）
- 参数：`matchId`；清空晒图字段并回退 `received_at`

### 礼物墙
- **GET** `/api/events/<code>/gift-wall` · 登录（参与者/组织者）
- 响应：已晒礼物列表（含隐私脱敏：blur 返回模糊图、text 无图）+ 点赞数；全员晒完才解锁

### 点赞 / 取消点赞
- **POST** `/api/events/<code>/gift-wall/like` · 登录（参与者）— 参数 `matchId`
- **DELETE** `/api/events/<code>/gift-wall/like` · 登录（参与者）— Query 参数 `matchId`

### 悄悄话
- **PUT** `/api/events/<code>/note` · 登录（仅送礼人本人）
- 参数：`matchId`、`note`（≤500）；失败可重试；越权（非本人 match）400/403

### 填写发货信息
- **PUT** `/api/events/<code>/shipment` · 登录（仅送礼人本人）
- 参数：`matchId`、`carrier`（快递公司）、`trackingNumber`（单号）、`status`（pending/shipped/delivered，默认按单号推导）
- 行为：单号变化触发 KDNiao 查询（未配置/失败静默降级文案）；首次发货通知收礼人 `shipment_sent`
- 响应：更新后的 shipment（含 trackingSummary）

### 刷新物流
- **POST** `/api/events/<code>/shipment/refresh` · 登录（仅送礼人本人）
- 参数：`matchId`；上次查询失败后的重试入口——强制重新外呼，不改变状态、不重复通知

---

## 5. 通知

### 通知列表
- **GET** `/api/notifications` · 登录
- 响应：通知列表（未读优先，分页）；铃铛角标据此计算

### 标记已读
- **POST** `/api/notifications/read` · 登录
- 参数：`ids`（通知 id 数组）；幂等

### 清空已读
- **POST** `/api/notifications/clear` · 登录
- 行为：删除已读通知，保留未读

### 通知偏好
- **GET** `/api/notifications/preferences` · 登录 — 返回 `{deadline, draw, giftReceived, remind}`（缺省全开）
- **PUT** `/api/notifications/preferences` · 登录 — 参数：上述键的子集（部分更新，未知键忽略）；响应合并后的完整偏好

---

## 6. 站点与上传

### 健康检查
- **GET** `/api/health` · 公开
- 响应：`{status: "ok", timestamp}`

### 图片上传
- **POST** `/api/upload` · 登录
- 参数：multipart `file`
- 校验：魔数（PNG/JPEG/GIF）+ 扩展名白名单 + 5MB 上限；存储 `data/uploads/`，响应 URL（**DB 只存 URL，不存 base64**）

---

## 附录 A：站点页面路由（非 API）

| 路径 | 说明 |
|---|---|
| `GET /` | SPA 首页（render_template index.html） |
| `GET /api-health` | 平台健康检查（site） |
| `GET /assets/<path>` | Vite 构建产物 |
| `GET /manifest.json`、`/sw.js`、`/icons/<path>`、`/app-icon-mondrian.svg` | PWA |
| `GET /uploads/<filename>` | 上传文件（send_from_directory 防路径穿越） |
| `GET /<path>` | SPA fallback；`api/` 前缀拼错返回 JSON 404 |

## 附录 B：通知类型表

| type | 触发 | 偏好键（可关闭） |
|---|---|---|
| `deadline_48h` / `deadline_24h` | 报名截止前提醒组织者（后台线程每小时扫描） | deadline |
| `draw_result` | 抽签完成，通知全员 | draw |
| `draw_redraw` | 重置抽签 | draw |
| `gift_posted` | 礼物被晒图评价 | giftReceived |
| `gift_wall_unlocked` | 全员晒完解锁礼物墙（按事件去重一次） | giftReceived |
| `participant_joined` | 有人加入活动（通知组织者） | remind |
| `shipment_sent` | 礼物已发货（通知收礼人） | remind |
| `join_success` | 加入成功（通知本人，不拦截） | — |
| `remind` | 组织者催办 | — |
