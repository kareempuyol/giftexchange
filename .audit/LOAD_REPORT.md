# LOAD_REPORT — 真实使用模式负载模拟（hackathon 轮16）

日期：2026-08-10（未 commit）· 引擎：SQLite（WAL + busy_timeout=5s）· 服务：隔离实例 `127.0.0.1:8085`
脚本：`.audit/load_sim.py`（50 虚拟用户线程池 × 独立 token × 0.5–3s 真人节奏，300s）
结果数据：`.audit/load_results.json`（含 59 次资源采样）
验证：pytest **269 passed** · 独立 DB（`/tmp/load_sim.db`，跑完删除，开发库零接触）

---

## 一、执行方式

```bash
.venv/bin/python .audit/load_sim.py --users 50 --duration 300 --port 8085
```

- 脚本自动拉起隔离 Flask 服务（`DB_PATH=/tmp/load_sim.db`，`database.py` 原生支持 DB_PATH 覆盖，
  无需改代码；`LOAD_DB_PATH` 环境变量亦可传入），stdout 结构化日志写 `/tmp/load_sim_server.log`；
  跑完停服并删除独立 DB。
- 种子阶段（API 直建，计入运行前）：50 用户注册+登录 → 14 活动（10 抽签、4 开放留空位）
  → 4 个抽签活动全员晒图解锁礼物墙 → 部分 giver 填物流。
- 行为分布（每用户每步独立抽样）：40% 浏览（public/mine/joined/详情/preview/participants/config）、
  25% 礼物墙/my-match/received-gift/matches、15% 操作（加入/发货/晒图/点赞）、
  10% 通知（列表/已读/偏好/清空）、10% 混合（创建+邀请/抽签/归档/恢复/退出/催办/重置短码）。

## 二、负载结果表（客户端视角，10,646 请求）

| 指标 | 值 |
|---|---|
| 总请求 | **10,646**（≈35 req/s 均值） |
| 2xx | 10,378（**97.48%**） |
| 4xx | 268（2.52%）— 全部业务 400，见下 |
| 5xx | **0** |
| 网络错误（连接/超时） | **0** |
| 服务端 request 日志 | 10,866 行，p50 **6.8ms** / p95 **17.2ms** / p99 **32.9ms** / max 71.8ms |
| >500ms 请求 | **0** |
| `error_500` 结构化事件 | **0**（observability 全量核对） |

**4xx 全为业务语义拒绝（非错误）**：

| 端点 | 400 次数 | 语义 |
|---|---|---|
| events.join | 238 | 活动已满 / 已加入 / 已截止报名（模拟真实用户反复点已满活动） |
| events.leave | 16 | 已抽签不可退 / 尚未加入（列表刷新竞态） |
| events.draw | 14 | 成员中途退出后不足 3 人（「至少需要 3 人才能完成抽签」） |

**端点延迟（按请求量排序，客户端实测 ms）**：

| 端点 | n | 成功率 | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| events.mine | 1474 | 100% | 7.3 | 16.8 | 25.8 | 80.9 |
| events.gift-wall | 1448 | 100% | 7.4 | 18.5 | 29.7 | 84.2 |
| events.joined | 1401 | 100% | 8.2 | 18.4 | 25.6 | 72.4 |
| events.public | 1151 | 100% | 11.0 | 20.7 | 33.5 | 86.6 |
| events.my-match | 1086 | 100% | 7.1 | 17.4 | 23.0 | 56.0 |
| events.join | 847 | 71.9% | 6.3 | 15.8 | 25.4 | 73.4 |
| events.received-gift.get | 627 | 100% | 6.4 | 17.4 | 26.3 | 60.3 |
| events.detail | 450 | 100% | 9.7 | 19.6 | 28.2 | 46.3 |
| notifications.list | 349 | 100% | 9.6 | 20.6 | 31.3 | 75.0 |
| events.create | 203 | 100% | 11.6 | 20.8 | 35.1 | 39.0 |
| notifications.read | 203 | 100% | 10.7 | 22.1 | 29.6 | 34.5 |
| events.preview | 172 | 100% | 7.6 | 15.6 | 20.2 | 23.8 |
| site.config | 171 | 100% | 7.3 | 17.1 | 21.1 | 33.9 |
| events.received-gift.put | 167 | 100% | 7.8 | 14.6 | 16.8 | 32.4 |
| events.participants | 162 | 100% | 10.6 | 20.4 | 37.5 | 75.1 |
| events.draw | 132 | 89.4% | 12.5 | 25.4 | 33.1 | 33.7 |
| events.matches | 112 | 100% | 9.6 | 24.0 | 36.0 | 38.0 |
| notifications.prefs.get | 108 | 100% | 10.5 | 20.7 | 72.9 | 84.3 |
| events.leave | 96 | 83.3% | 11.1 | 19.5 | 29.8 | 39.4 |
| events.archive | 70 | 100% | 10.2 | 19.5 | 21.9 | 23.9 |
| notifications.prefs.put | 59 | 100% | 10.0 | 23.0 | 25.7 | 26.0 |
| notifications.clear | 41 | 100% | 11.3 | 21.1 | 47.5 | 64.5 |
| events.like | 31 | 100% | 7.8 | 10.7 | 14.2 | 15.3 |
| events.remind | 30 | 100% | 11.3 | 17.2 | 27.2 | 31.2 |
| events.unarchive | 29 | 100% | 10.1 | 17.7 | 19.0 | 19.5 |
| events.reset-short-code | 27 | 100% | 10.3 | 16.9 | 18.8 | 19.3 |

**资源（59 次采样，5s 间隔）**：

| 指标 | 值 |
|---|---|
| DB 大小 | 180,224B → 737,280B（**+557KB**，数据量 10 倍于种子） |
| WAL 文件 | 恒 ≤ 2（-wal/-shm），WAL 体积峰值 32KB，无膨胀 |
| RSS | 43.9MB → 52.6MB（启动预热后平坦，avg 52.1MB） |
| CPU | avg 0.8%，max 4.9%（ps 采样） |

**后端错误日志**：`error_500` 事件 0；request 日志 5xx 0。业务事件与客户端计数完全对账：
`event_created` 217（= 14 种子 + 203 运行期创建）、`draw_success` 128（= 10 种子 + 132 次尝试 − 14 业务拒绝）、
`login_success` 50（50 用户全登录成功）。

## 三、最慢端点 TOP3（真实负载下，按 p99）

| # | 端点 | n | p50 | p95 | p99 | max | 判定 |
|---|---|---|---|---|---|---|---|
| 1 | notifications.prefs.get | 108 | 10.5 | 20.7 | **72.9** | 84.3 | 单条 SELECT users，1 个写锁等待离群点；均值 12.2ms |
| 2 | notifications.prefs.put | 59 | 10.0 | 23.0 | 25.7 | 26.0 | 正常 |
| 3 | events.participants | 162 | 10.6 | 20.4 | **37.5** | 75.1 | 双 JOIN + 成员状态推导，量级正常 |

注：TOP3 按 p99 排序；按均值排序前三是 events.draw（12.5ms）/ events.create（11.6ms）/ events.participants（11.4ms）。
所有端点 p50 < 13ms、服务端全局 p99 33ms、max 87ms——绝对延迟极小，无可用性风险。

## 四、瓶颈分析

1. **无瓶颈**。35 req/s × 50 并发对 SQLite WAL 是轻负载：读不阻塞写，写事务由条件 UPDATE 串行化
   （busy_timeout 5s 兜底），实测零 500、零锁死、零网络错误。
2. **延迟劣化监测**：全程无 >500ms 请求；早中晚期资源采样平坦（RSS 52MB 恒定、WAL 不增长），
   无累积性劣化。`notifications.prefs.get` 的 p99 离群点（84ms）为单次写锁等待（busy_timeout 生效），
   均值 12.2ms，属正常抖动。
3. **DB 增长**：5 分钟 +557KB（事件/参与/匹配/通知/点赞），量级健康；WAL 自动 checkpoint 正常（峰值 32KB）。

## 五、发现的问题 → 修复

**应用代码（wxcloudrun/）：零问题**。4xx 全部为业务语义（满员/重复加入/已抽签/成员退出后不足 3 人抽签），
属真实用户行为，非系统错误。无需改动。

**负载脚本（.audit/load_sim.py）自修 3 个 bug**（仅影响脚本自身，不涉及应用）：
1. `http.client` 请求体默认 latin-1 编码，中文 JSON body 抛 UnicodeEncodeError → 显式 UTF-8 编码。
2. 非 ASCII 查询参数（`?search=礼物`）http.client 路径编码同样失败 → `urllib.parse.quote` 百分号编码；
   此 bug 曾致 2 次「events.public 网络错误」误报（实为客户端编码异常）。
3. `call()` 成功/异常路径返回元组不一致（3 vs 4 元组），异常路径曾使工作线程静默死亡、压低请求量 →
   统一 4 元组并记录异常 repr 到结果 JSON。

## 六、结论

**可上线（当前规模）**：50 并发真实用户 × 5 分钟，10,646 请求 0 5xx、0 错误事件、0 锁死、
p99 33ms（服务端）/ 87ms（客户端 max）、无 WAL 膨胀、内存稳定。SQLite 单写者模型在当前量级完全胜任。

**需关注点（非阻塞）**：
- 写路径单写者串行化（busy_timeout 5s）——若目标并发再上 1–2 个数量级，建议切 MySQL
  （双引擎 SQL 已就绪，`MYSQL_*` 环境变量即切换），本轮不构成瓶颈。
- 4xx 中的 join「已满」高频（238 次）是模拟脚本有意让用户点满员活动的产物，前端已有对应提示文案，
  无改动必要。

## 七、验收对照

1. ✅ 负载结果表（成功率/延迟/错误分布）— 见第二节
2. ✅ 结论明确（可上线 + 关注点）— 见第六节
3. ✅ pytest 全绿 — `pytest tests`：**269 passed**
4. ✅ 报告 `.audit/LOAD_REPORT.md` + 数据 `.audit/load_results.json`
5. ✅ 独立 DB（`LOAD_DB_PATH`/`DB_PATH=/tmp/load_sim.db`）跑完删除，开发库零接触；未 commit
