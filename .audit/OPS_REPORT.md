# 数据运维与健壮性报告（hackathon 波次5）

- 日期：2026-08-10
- 范围：`scripts/**`（新增 4 个运维脚本）、`tests/test_ops_scripts.py`（新增 11 例）、`DEPLOY.md` / `README.md`（运维文档）
- 数据库：`data/gift_exchange.db`（SQLite dev 库，WAL 模式）
- 未 commit；未改动业务路由 / migrations / 前端

## 一、任务清单逐项结论

### 1. 日志轮转 ✅（跳过并说明）
- `wxcloudrun/observability.py` 只写 **stdout**：`logging.StreamHandler(sys.stdout)` 一行一条 JSON（`log_event`），从不写日志文件 → **无需文件轮转，跳过**。
- 部署形态说明：容器内 stdout 由平台日志收集（`docker compose logs -f web`）接管，轮转/保留策略在采集侧（docker json-file max-size / 云平台日志服务），应用内不加文件 IO（保持 12 因子 + 多实例 sidecar 可接管的设计，见 observability.py 模块 docstring）。

### 2. 上传文件清理 ✅ `scripts/cleanup_orphans.py`
- 安全规则（三重保险，缺一不删）：
  1. 只扫 uploads 目录下的普通文件（不递归、不碰子目录）；
  2. 存在超过 `--min-age-days` 天（默认 **7，硬性下限**——传小于 7 报错退出，脚本内部对调用方入参再钳制一次）；
  3. 文件名不被任何 DB 引用列引用：`users.avatar_url` / `events.cover_image` / `matches.gift_photo_url`（支持相对 URL 与带 host 的完整 URL，兼容旧 base64 跳过）。
- 默认 **dry-run 只列不删**，`--delete` 才真删；双引擎（复用 `wxcloudrun.database.DB`，SQLite/MySQL 自动切换）。
- cron（注释内置）：`30 4 * * * .../scripts/cleanup_orphans.py --delete`。

### 3. 通知清理 ✅ `scripts/cleanup_notifications.py`
- 删「已读（`read_at` 非空）且创建超过 `--days`（默认 90）天」的通知；未读永不删。
- 截止时间 Python 侧算 UTC 字符串下推参数，SQLite `CURRENT_TIMESTAMP` 文本与 MySQL `DATETIME` 同一字符串比较语义（双引擎通用）。
- 默认 dry-run，`--delete` 才真删；cron（注释内置）：`0 4 * * 0`。
- 未引 APScheduler；后台线程方案未采用（任务给出二选一，脚本方案更可控、可审计，且 dev/生产通用）。

### 4. DB 备份脚本 ✅ `scripts/backup_db.sh`
- WAL 安全：优先 `sqlite3 .backup`（在线一致性快照），CLI 缺失回退 python3 `sqlite3` 模块 backup API；**不直接 cp 主库文件**（WAL 下会丢最新提交）。
- 时间戳命名 `gift_exchange-YYYYmmdd-HHMMSS.db`，滚动保留 `BACKUP_KEEP`（默认 7）份；`DB_PATH` / `BACKUP_DIR` / `BACKUP_KEEP` 环境变量可调；路径相对仓库根解析，cron 任意 cwd 可跑。
- MySQL 形态检测到 `MYSQL_ADDRESS/MYSQL_HOST` 时跳过并提示用 mysqldump（DEPLOY.md 已注明）。
- cron（注释内置）：`0 3 * * *`；DEPLOY.md「数据持久化与备份」第 9 步已同步。

### 5. 数据完整性核查 ✅ `scripts/healthcheck_data.py`
- 10 项检查（只报告不修改，退出码 0=通过 / 1=发现问题，供 cron 告警；`--json` 机器可读）：
  - 孤儿 matches：`event_id` 无活动、`giver_id` / `receiver_id` 无参与者
  - 孤儿 participants：`event_id` 无活动、`user_id` 无用户
  - 孤儿 notifications：`user_id` 无用户（另查 `event_id` / `match_id` 悬空引用）
  - gift_likes 引用完整性：`match_id` / `user_id`
- cron（注释内置）：`0 5 * * *`，发现问题接告警。

### 6. 资源上限 ✅（确认 + 文档）
- 上传图片：单文件上限 **5MB**（`helpers.MAX_UPLOAD_BYTES` / `storage._MAX_FILE_BYTES`，`/api/upload` 前置校验 + storage 层兜底）、扩展名白名单 `png/jpg/jpeg/gif/webp` + 魔数校验；**无数量/总大小配额**——已文档化：增长靠孤儿清理 cron + 磁盘监控（`du -sh data/uploads`）控制，DEPLOY.md「资源上限」章节。
- `maxParticipants` 上限**已有**：创建/编辑校验 2–999（`event_routes.py`），满员拒绝加入 → 确认无需改动。

## 二、现有 dev 库扫描结果

表规模：users=290、events=131、participants=223、matches=170、notifications=382、gift_likes=4。

### healthcheck_data.py（10 项全过）
```
[healthcheck] 全部 10 项核查通过，无孤儿/悬空数据
total_issues: 0 | failed_checks: 0 | exit_code: 0
```
逐项：matches_no_event / matches_no_giver / matches_no_receiver / participants_no_event / participants_no_user / notifications_no_user / notifications_no_event / notifications_no_match / gift_likes_no_match / gift_likes_no_user 均 0 条。

### cleanup_orphans.py（0 候选）
```
[cleanup_orphans] 无孤儿文件（目录 .../data/uploads，引用窗口 7 天）
```
- 磁盘 29 个文件，全部落盘 < 7 天（最新 0.0d，最旧 1.5d）→ 均在 7 天安全窗口内，**0 候选**。
- 引用覆盖：28 个不同文件名被 DB 三列引用；11 个文件当前无引用但落盘未满 7 天（跨过窗口后将成为首批可清理对象，属正常生命周期，非数据问题）。

### cleanup_notifications.py（0 可删）
```
[cleanup_notifications] 可删 0 条已读超过 90 天的通知（--delete 才真删）：
```
- 382 条通知中无「已读且创建超 90 天」记录（库龄 < 3 天，正常）。

### 孤儿修复
- **无需修复**：上述扫描 0 问题，未执行任何 DELETE/UPDATE。约束「不要真的删除 dev 库数据（除非孤儿且报告确认）」——无孤儿，故未删任何行。

### backup_db.sh（已验证）
```
[backup_db] 已备份: .../data/backups/gift_exchange-20260810-010339.db
[backup_db] 完成，当前备份 2/7 份
```
- 连跑 4 次：备份成功、滚动保留生效（同秒重跑不重复堆积）。`bash -n` 语法通过。macOS 自带 bash 3.2 无 `mapfile`，已用可移植循环替代（实测通过）。

## 三、验收标准对照

| 验收项 | 结果 |
|---|---|
| 每个脚本可运行（python/bash 直接执行不报错） | ✅ `py_compile` 3 个 Python 脚本通过；`bash -n` 通过；4 个脚本均对 dev 库实际执行成功（见上） |
| 孤儿扫描在 dev 库跑一遍 + 报告 + 修复孤儿 | ✅ 10 项核查 0 问题；上传 0 候选；通知 0 可删；无需修复（报告见上） |
| `pytest tests -q` 全绿 | ✅ **221 passed**（`python3 -m pytest tests`；新增 `tests/test_ops_scripts.py` 11 例：孤儿扫描 7 天下限/引用列/子目录/完整 URL、通知保留期可配、healthcheck 全类检出与干净库通过） |
| 报告 `.audit/OPS_REPORT.md` | ✅ 本文件 |

> 注：`pytest tests -q` 需以 `python3 -m pytest` 运行（console 脚本不把 cwd 加入 sys.path，`wxcloudrun` 不可导入——既有测试同样依赖此调用方式）。

## 四、改动文件清单

- 新增：`scripts/cleanup_orphans.py`、`scripts/cleanup_notifications.py`、`scripts/healthcheck_data.py`、`scripts/backup_db.sh`（均 chmod +x）
- 新增：`tests/test_ops_scripts.py`
- 文档：`DEPLOY.md`（第 9 步备份 + 「数据运维」章节 + 「资源上限」章节）、`README.md`（运维脚本小节）
- 未改动：`wxcloudrun/**` 业务代码、migrations、前端；未 commit
