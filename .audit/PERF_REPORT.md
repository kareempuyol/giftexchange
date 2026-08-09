# 性能优化报告（hackathon 波次 2-A）

日期：2026-08-10 · 范围：后端（N+1 / 索引 / 批量写）+ 前端（分包 / 渲染）
方法：现状测量 → 优化 → 复测（curl 计时 5 次取中位数；Flask test client 统计 SQL 语句数；
`EXPLAIN QUERY PLAN` 验证索引生效）。

## 1. 测量结果（接口 × 耗时中位数，ms）

测试账号 `verify_user`；规模数据 = 179 活动 / 471 参与者 / 220 matches / 482 通知
（50 个「性能测试活动」× 5 参与者 + 100 通知，测量后已清理，库恢复 129/221/170/382/4）。

| 接口 | 小库基线 | 规模·优化前 | 规模·优化后 | 变化 |
|---|---|---|---|---|
| /api/events/mine | 5.61 | 4.78 | 5.99 | ±噪声 |
| /api/events/public | 5.47 | 4.77 | 4.73 | → |
| /api/events/\<code\> | 5.47 | 4.42 | 4.29 | → |
| /api/events/joined | 5.26 | 4.17 | 5.41 | ±噪声 |
| /api/events/\<code\>/gift-wall | 5.23 | 4.57 | 4.53 | → |
| /api/events/\<code\>/participants | 5.12 | 4.23 | 4.86 | ±噪声 |
| /api/notifications | 5.07 | 4.27 | 5.99 | ±噪声 |
| /api/events/\<code\>/dashboard | 4.86 | 4.65 | 5.70 | ±噪声 |
| /api/profile | 3.93 | 4.33 | 5.18 | ±噪声 |

**基线 TOP3 最慢**：`mine`(5.61) / `public`(5.47) / `detail`(5.47)。

结论（诚实声明）：SQLite 在几千行内单查询亚毫秒，9 个接口全部 4–6ms，中位数差
（±1.2ms）落在运行噪声内（同轮 min/max 波动即 ±2–10ms）。**墙钟收益在本数据量下不可测**；
索引收益由查询计划证明（见 §4），规模收益在真实生产（MySQL、万级行）下兑现。优化后无
任何接口恶化。

## 2. 后端改动

### 2.1 DB 索引（migrations.py 版本 11，+10 个索引）
新增 `create_index` 迁移语句类型（`_create_index` 描述符 + `_index_exists` 幂等守卫，
MySQL 5.7 无 `CREATE INDEX IF NOT EXISTS`，守卫保证双引擎幂等）：

- `events(short_code)` — fetch_event 短码查找
- `events(creator_id, archived)` — mine / archived 列表
- `events(status, is_public, archived)` — public 列表
- `participants(user_id)` — joined 列表（此前无索引）
- `matches(event_id)` — 礼物墙 / 仪表盘 / 流程状态 / remind（此前全表扫描）
- `matches(giver_id)`、`matches(receiver_id)` — received-gift / dashboard 连接
- `notifications(user_id, created_at)` — 列表排序（免临时 B-tree）
- `notifications(user_id, read_at)` — 未读数（covering index）
- `gift_likes(user_id)`

### 2.2 N+1 排查结果
读路径抽查结论：`mine/joined/public/participants/dashboard/gift-wall/notifications` 已是
JOIN + 批量查询（gift-wall 点赞数按 `match_id IN (...)` 聚合，无逐条 COUNT）。唯一真 N+1：

- **POST /notifications/read**：逐条 `UPDATE ... WHERE id = ?`（N 条）→ 单条
  `UPDATE ... WHERE id IN (...)`（每 500 个分块）。10 个 ids：12 → 3 条 SQL
  （另 2 条为 login_required 注销检查 + CORS 设置查询）。

### 2.3 顺带修复：单条通知已读契约 bug
前端 `markRead` 发 `{id}`，后端契约读 `ids` → 原实现落入「全部已读」分支（点一条 = 全读）。
改为 `{ids:[id]}`（Header.tsx），与后端契约对齐；新增 `TestReadIds` 回归测试
（只标记指定 ids，其余保持未读）。

## 3. 前端改动

### 3.1 路由分包（React.lazy + Suspense）
非首屏页面改动态导入：EventDetailPage / CreateEventPage / DashboardPage / GiftWallPage /
ProfilePage（登录、注册、找回密码、活动列表保持首屏直出）。

| 产物 | 优化前 | 优化后 |
|---|---|---|
| 主 bundle index-*.js | 282.5 KB（gzip 85 KB） | **188.1 KB（gzip 60.7 KB）** |
| 拆出 chunk | — | EventDetailPage 29.8K / PosterModal+qrcode 28.6K / GiftWall 7.2K / Profile 9.5K / CreateEvent 7.5K / Dashboard 4.6K / ImageUpload 1.1K |

qrcode（海报生成，仅 EventDetailPage 用）随 PosterModal chunk 移出首屏加载路径。
gzip 主 bundle 60.7KB，远低于 200KB 目标。

### 3.2 渲染 / 图片
- 列表 key 检查：events/participants/gift-wall/dashboard/notifications 各列表 key 均稳定
  （code/id/matchId/participantId），无需改。
- `loading="lazy"`：EventsPage 活动列表封面（GiftWallPage 照片已有）。
- useMemo 排查：各页均为小列表直出 JSX，无重复计算热点，未加无谓 memo。
- 已确认的并行加载模式（Promise.all 并发拉 participants + my-match）保持不变。

## 4. 验证

- **EXPLAIN QUERY PLAN（规模库副本，drop 索引前后对比）**：
  8 条热查询中 7 条由 `SCAN`（全表扫）→ `SEARCH ... USING INDEX`；
  notifications 列表免去 `USE TEMP B-TREE FOR ORDER BY`；
  joined 由 autoindex 覆盖扫描升级为 `idx_participants_user` 定点查找。
- **批量已读实测**：10 ids → 3 条 SQL（原 12 条）；线上 curl 验证 34 未读 → 只标记 2 条 → 32。
- **pytest tests -q：exit 0 全绿**（含更新后的 test_migrations.py v11 断言 + 新增 TestReadIds）。
- **npm run build 通过**；Flask 已重启（模板缓存已刷新，index.html 引用 index-hQwwedgY.js）。
- **浏览器实测（390×844）**：登录 → 活动列表（含性能测试活动卡片）→ 活动详情页
  （drawn 组织者视图）→ 礼物墙（3 张卡片，懒加载 chunk 正常出图）均通过。

## 5. 遗留观察（未改）

- 每请求固定开销：`login_required` 注销检查 + `add_cors_headers` 读 `app_settings.cors_origin`
  各 1 条 PK 查询（≈0.05ms/条，非感知项；多实例可换进程内 TTL 缓存）。
- `notify()` 写路径按参与者逐条 INSERT（抽签/催办一次性动作，非热路径）。
- 抽签/催办通知循环保留（写路径，与读路径无关）。
