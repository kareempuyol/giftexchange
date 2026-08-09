# STRESS_REPORT — 并发与压力验证（hackathon 轮4）

日期：2026-08-10 · 引擎：SQLite（WAL + busy_timeout=5s）· 服务：`127.0.0.1:8080`
压测脚本：`.audit/stress_test.py`（线程池 + http.client 直连 8080，DB 真值直读 `data/gift_exchange.db`）

## 一、执行方式

```bash
.venv/bin/python .audit/stress_test.py --rounds 20   # 5 场景 × 20 轮，全部通过
```

每轮每场景使用独立前缀（`stress_r<N>_<rand>_*`）的用户/活动，结束后 SQL 清理（先删活动级联
participants/matches/likes/notifications，再删用户），不污染开发库。同轮内各场景互不依赖。

## 二、结果表（20 轮 × 5 场景，全通过）

| 场景 | 并发形态 | 状态分布（每轮一致） | DB 真值 | 通过轮次 |
|---|---|---|---|---|
| 并发抽签 | 8 线程 POST `/events/<code>/draw`（同一创建者） | `200:1, 409:7` | matches 恰 8 条，status=drawn | 20/20 |
| 并发加入 | 12 线程 join 空位 8 的活动 | `201:8, 400:4` | participants 恰 8，events.participant_count 恰 8 | 20/20 |
| 并发晒图 | 收礼人+送礼人同时 PUT `/received-gift` 同一 match | `200:1, 400:1`（无 500） | match 一份完整数据（review/rating/received_at 齐全） | 20/20 |
| 并发点赞 | 同用户 10 线程 POST `/gift-wall/like` 同一 match | `200:10`（无 500） | gift_likes 恰 1 行 | 20/20 |
| 并发重置码 | 同账号 5 线程 POST `/auth/forgot-password` | `200:5` | users.reset_code 恰 1 个；恰 1 个响应码 == DB 码；端到端重置成功 | 20/20 |

同收礼人并发双 PUT（附加验证）：均 200，最终 review 为两者之一（最后写入者胜），match 行数不变。

### 健康监测（压测全程，独立线程每 100ms 采样）

| 采样 | 失败 | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| 267 | 0 | 1.3ms | 2.4ms | 4.8ms | 11.1ms |

**无阻塞**：`/api/health` 不访问 DB（纯响应），且 SQLite WAL 下读不阻塞写；写请求持有锁的时间
为单个事务（条件 UPDATE + INSERT），12 并发 join 的写串行化总耗时远小于 busy_timeout。压测期间
健康检查零失败、max 11.1ms（远低于 1s 阈值），结论：当前规模下无慢请求防护问题。

## 三、发现的竞态与修复

### 1. 并发加入超员（已修复）— `wxcloudrun/helpers.py:add_participant` + `wxcloudrun/database.py`

**问题**：`join_event` 先 SELECT `participant_count` 判满，再 INSERT participant + UPDATE count，
两步不在同一原子操作内。N 个并发请求可同时读到 count < max，全部通过校验后各自插入 → 超员
（INSERT 前 SELECT count 的经典 TOCTOU 窗口）。原实现还依赖 MySQL 侧无唯一约束之外的保护。

**修复**：容量校验改为原子条件 UPDATE 占位：

```sql
UPDATE events SET participant_count = participant_count + 1
WHERE id = ? AND status = 'open'
  AND (max_participants IS NULL OR participant_count < max_participants)
```

- `rowcount = 0` → 容量不足（或活动已抽签），抛 `ValueError("活动人数已满"/"活动已截止报名")` → 400，不写任何数据；
- 占位 + INSERT 同一事务：SQLite 写锁串行化、MySQL 行锁（InnoDB）保证第二个并发 UPDATE 在第一个提交后重读 count，条件不再成立；
- 并发重复加入同一用户：INSERT 撞 `UNIQUE(event_id, user_id)` → `integrity_errors()` 捕获 → 确认已存在后抛 `ValueError("你已加入该活动")` 触发事务回滚，占位 +1 一并撤销（不返回既有记录，否则会提交脏 count）；
- 删除旧的双重递增（原代码在占位 UPDATE 之外还有一条 `participant_count + 1`，会导致每次成功加入计数 +2）；
- `status = 'open'` 守卫同时封死 join 与 draw 的竞态：并发抽签把活动置 drawn 后，占位失败，不再向已抽签活动插入参与者。

**双引擎**：`database.py` 新增 `integrity_errors()`，统一返回当前引擎的唯一约束冲突异常类型
（sqlite3.IntegrityError / pymysql.err.IntegrityError），业务层不直接 catch 具体引擎类型。

### 2. 并发点赞（已修复）— `wxcloudrun/gift_routes.py:gift_wall_like`

**问题**：SELECT 存在性 → INSERT，并发下多个请求同时通过 SELECT，败者撞 `UNIQUE(match_id, user_id)`
→ IntegrityError → 500（"不炸"不满足）。表内数据不会重复（唯一约束兜底），但响应是 500。

**修复**：INSERT 包 `integrity_errors()`，冲突视为已点赞幂等成功（`pass` 后照常返回 `liked: true`）。
同用户 10 线程：10×200，gift_likes 恰 1 行。不同用户 10 线程（均为参与者）：10×200，恰 10 行无重复。

### 3. 并发重复注册（已修复）— `wxcloudrun/auth_routes.py:register`

**问题**：SELECT 预检 username/email → INSERT，并发同名注册时败者撞 UNIQUE → 500。

**修复**：INSERT 包 `integrity_errors()`，落库后按唯一约束真值重查冲突字段（username/email），
返回 409 `"xxx already exists"`。2 线程同名注册：`1×201 + 1×409`，无 500。

## 四、复核无问题的路径（不改代码）

| 路径 | 结论 | 依据 |
|---|---|---|
| 抽签抢锁 `draw` | **安全** | 条件 UPDATE `status='open'→'drawn'` + `rowcount==0 → 409` 原子抢锁；抢锁成功者才写 matches（DELETE 旧 + INSERT 新随事务提交），败者在触碰 matches 数据前已返回。8 线程实测恰 1×200 + 7×409，matches 恰一份 |
| 晒图 `update_received_gift` | **安全** | 单行 UPDATE 由写锁串行化，最终为最后写入者数据；礼物墙解锁通知的去重检查在写事务内，串行写者提交后可见，不会重复发 |
| 重置码 `forgot_password` | **安全** | 单行 UPDATE 覆盖写，最后提交者胜 → 恰 1 个有效码；实测 5 响应码中恰 1 个 == DB 码 |

**遗留说明**：forgot 与 reset 共用 IP+账号 5 次/小时的限速窗口（auth_routes.py 注释明示），
5 个并发 forgot 会耗尽预算导致随后的 reset-password 429 —— 属既有设计（防 6 位码爆破），
非本轮竞态。压测拆分为：A）5 线程并发 forgot 验证单码不变量；B）独立账号 1 次 forgot 端到端
验证「DB 码可重置、旧码清空、旧密码失效、新密码可登录」。

## 五、验收对照

1. ✅ 每场景 N 轮结果表（成功/失败分布）+ 一致性校验（DB 真值）— 见第二节
2. ✅ 修复的竞态有测试覆盖 — `tests/test_concurrency.py`（8 用例）：
   - join 超员原子化（12 线程恰 8 成功 / 同用户并发幂等不虚增 count）
   - 抽签抢锁（8 线程恰一成功）
   - 晒图并发（同收礼人双 PUT 最后写入者胜）
   - 点赞去重（同用户 10 线程恰 1 行 / 10 用户恰 10 行）
   - 重置码单码（5 线程恰 1 码）
   - 重复注册（2 线程 1×201 + 1×409）
3. ✅ `pytest tests -q` 全绿 — 246 tests collected, 0 failed
4. ✅ 本报告 `.audit/STRESS_REPORT.md`

## 六、复现方法（失败场景）

脚本对任何断言失败会打印 `轮次 N tag=<tag>` 与错误信息，复现步骤：
以 `stress_<tag>_*` 前缀重建同组用户/活动后，仅重跑对应场景函数即可。
20 轮 × 5 场景本次全部通过，无 flake。
