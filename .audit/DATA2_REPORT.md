# DATA2_REPORT — 数据模型与查询深化（hackathon 轮2-B）

日期：2026-08-10 ｜ 范围：`wxcloudrun/**`（除 `site_routes.py`）、`tests/**` ｜ 未 commit

## 1. 事务边界审查结论表

| 路由 | 操作 | 原子性（现状） | 结论 / 改进 |
|---|---|---|---|
| `POST /events` (create_event) | events INSERT + 组织者 participant INSERT + participant_count+1 + log_event | ✅ 单 `with DB()` 事务，退出统一 commit / 异常 rollback | 无需改。测试锁定：`test_create_event_organizer_participant_atomic`（count=1、组织者必在 participants、创建者零通知） |
| `PUT /events/<code>/shipment` + `PUT /events/<code>/note`（前端顺序两次调用） | 两次独立写（各一事务） | ⚠️ 非单事务，但两个 PUT 均为**全量状态幂等写**：note 只改 note 列、shipment 只改物流列（互不覆盖）；shipment 重复提交由 `shipment_changed` 守卫 → 不重复通知、KDNiao 缓存 → 不重复外呼 | 后端无需合并（前端不可改，合并需改调用方）。**重试可收敛**：任一中间失败 → 客户端整体重放，两端各自幂等收敛。测试锁定：`test_shipment_note_pair_converges_under_retry`（重放不重复通知、单字段更新不覆盖另一字段） |
| `DELETE /events/<code>/received-gift` | matches 晒图字段清空 + gift_likes 删除 | ✅ 同一 `with DB()` 事务 | 无需改。测试锁定：`test_gift_delete_cleans_likes_and_reverts_wall` |
| `POST /notifications/read`（批量/全量） | 单条 UPDATE（IN 分块 500/批，仍同一事务） | ✅ 原子 | 无需改。测试锁定：`test_notifications_batch_read_clear_scoped` |
| `POST /notifications/clear` | 单条 DELETE（仅已读） | ✅ 原子 | 同上 |
| `DELETE /events/<code>` (delete_event) | notifications 显式删 + events 删（participants/matches/gift_likes 走 FK 级联） | ✅ 同一事务 | 无需改。测试锁定：`test_delete_open_event_cleans_all_tables`、`test_delete_one_event_does_not_touch_others` |
| `POST /events/<code>/draw` | open→drawn 条件 UPDATE（并发锁）+ 删旧 matches/likes + 插新 + 通知 | ✅ 同一事务；条件更新 rowcount=0 → 409，未触碰数据 | 无需改 |
| `POST /events/<code>/redraw` | 预判无解提前 400 → 删旧建新 + 通知 | ✅ 同一事务；失败不触碰旧结果 | 无需改。测试锁定：`test_redraw_replaces_matches_and_cleans_likes` |
| `POST /auth/deactivate` | users 匿名化 UPDATE（单语句） | ✅ 原子 | 无需改。测试锁定：`test_deactivate_keeps_events_and_revokes_access` |
| `POST /events/<code>/archive` / `unarchive` | 单 UPDATE archived 标记 | ✅ 原子 | 无需改（语义文档化，见 §2） |

**规则重申**：`DB.__enter__/__exit__` 是唯一事务边界——`with DB() as db:` 内全部写操作同生共死；路由层禁止手动 `conn.commit()`（数据库.py 无此 API，天然安全）。

## 2. 软删除 vs 硬删除语义（确认 + 补文档）

现状：
- `DELETE /api/events/<code>` = **硬删除**（物理删 events 行 + 级联清理），仅创建者。前端**无删除 UI**（grep 确认 EventDetailPage 只暴露「归档活动」按钮），为 API 直达入口。
- `POST /api/events/<code>/archive` = **软删除**（archived=1），仅 drawn 活动可归档；数据全保留、可 unarchive；影响列表可见性（mine/joined/public 隐藏，archived 列表可见，详情可访问）。
- 无管理台删除入口（`admin_required` 仅 gate settings，不越权删他人活动）。

判定：语义清晰、行为互补不重叠（任一状态都可执行，drawn 走归档、open 走删除由调用方选择），**无需改行为**——但此前两处 docstring 均未完整交代矩阵，已补齐：
- `delete_event`：新增完整 docstring（硬删级联路径 + 与归档的分工 + 无管理台删除说明）。
- `archive_event`：docstring 补「归档=软删、数据保留、可恢复；drawn 活动一律走归档」。
- 一致性测试 `test_archive_preserves…` 由既有 test_archive.py 覆盖（全绿）。

## 3. 数据一致性测试（tests/test_consistency.py，9 用例全过）

| 用例 | 验证场景 |
|---|---|
| `test_delete_open_event_cleans_all_tables` | 删 open 活动：participants/matches/notifications 无孤儿 |
| `test_delete_one_event_does_not_touch_others` | 跨活动隔离：删 A 活动 B 活动的 participants/matches/gift_likes 原样保留 |
| `test_redraw_replaces_matches_and_cleans_likes` | 重抽后旧 match id 物理删除、API（/matches、/my-match）只返回新结果、旧点赞清零 |
| `test_gift_delete_cleans_likes_and_reverts_wall` | 晒图删除 → gift_likes 清零、晒图字段全复位、礼物墙 posted 回退 |
| `test_deactivate_keeps_events_and_revokes_access` | 注销：events/participants/matches/likes/notifications 一行未动、旧用户名登录 401、旧 JWT 401、其他参与者视角数据完整 |
| `test_create_event_organizer_participant_atomic` | 创建活动单事务：participant_count=1 + 组织者 participant + 零打扰通知 |
| `test_shipment_note_pair_converges_under_retry` | shipment+note 两写重放幂等收敛、互不覆盖、单号变更才再通知 |
| `test_notifications_batch_read_clear_scoped` | 批量已读只影响指定 id；clear 只删已读；全量已读+清空 |
| `test_dashboard_counts_follow_state` | dashboard 统计与 DB 真值一致（发货/晒图推进），响应形状回归 |

实测：`python3 -m pytest tests/test_consistency.py -q` → 9 passed；连续 3 次运行稳定（无抽签随机性 flake，随机相关的断言与 DB 真值比对）。

## 4. 查询收敛（dashboard 组织者视图）

审查结果：dashboard 组装 = 3 条 SQL + 1 层 Python 循环（无 3 层循环、无 N+1）：
1. `participant_rows`（participants JOIN users）
2. matches LEFT JOIN participants（按收礼 match 拉齐）
3. 催办统计 COUNT 聚合

改进：**统计查询并入循环**（3 → 2 条 SQL）。每行即该参与者的收礼 match，`pending = shipment_status='pending'`、`unposted = status≠'pending' AND received_at IS NULL` 与独立 COUNT 语义严格等价（每个 match 必有 receiver 参与者）。响应字段不变，测试锁定。

全局 N+1 排查（其余路由）：gift-wall 点赞计数/我的点赞已用 `IN (...)` 批量查询（非逐行）；remind/通知为 N 次 INSERT（写入、有界，非读放大）；其余列表接口均单查询。无 3 层循环。

## 5. DB 迁移健全性

- `_column_exists`/`_index_exists` 覆盖 MIGRATIONS v1-v11 全部语句：add_column 全部带列守卫、create_index 全部带索引守卫（新增 `table` 限定，修复 MySQL 索引名仅表内唯一导致的跨表误判）、create_table 全 IF NOT EXISTS。
- **修复真实缺陷（排序 bug）**：`run_migrations` 中版本化链先于历史列兜底执行——老库若缺 `events.is_public`（v11 `idx_events_status_public_archived` 的依赖列），迁移会在建索引时炸。改为：历史列守卫 → 版本化链 → 数据兜底。回归测试：`test_legacy_db_missing_index_dependency_columns`。
- **移除异常吞噬**：历史列兜底由 `try/except Exception: pass` 改为 `_column_exists` 守卫（真实 SQL 错误不再被静默跳过）。
- 双路径实测（独立脚本，非 pytest）：
  - **fresh 库**：init_schema → schema_migrations 记录 v1-v11、10 个索引齐备、`run_migrations_v2` 重跑应用 0 个。
  - **老库增量**（故意缺 is_public/match_visibility 的最小 schema）：run_migrations 一次补齐历史列 + v1-v11 + 10 索引，short_code 不重复加列；重跑幂等。
- 测试：`tests/test_migrations.py` 5 用例全过（fresh/幂等/legacy/入口幂等/迁移契约/新回归）。

## 6. 验证

- `python3 -m pytest tests -q` → **234 passed**（含新增 9 + 回归 1）。
- `python3 -m py_compile` 全部改动文件通过。
- **build 不受影响**：本任务零前端改动（frontend/ 与 site_routes.py 的 git 改动来自并行任务，未触碰）。git status 确认本任务仅改 `wxcloudrun/{database,event_routes,migrations}.py` + `tests/{test_consistency,test_migrations}.py` + 本报告。

## 7. 遗留风险（未改，仅记录）

- `events.short_code` 无 UNIQUE 约束：`generate_short_code` 的 SELECT-再插入存在并发竞态窗口（两请求同码），v11 索引非唯一。修复需唯一索引 + 存量查重，超出本任务范围，建议后续单独立项。
- `login_required` 每次请求多 1 次 `SELECT deactivated`（注销即时生效的正确性代价），量级可忽略，不建议优化。
