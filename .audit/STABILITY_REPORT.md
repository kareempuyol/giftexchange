# STABILITY_REPORT.md — giftexchange 稳定性审计（hackathon 波次2-B）

审计时间：2026-08-10　审计方式：代码走查（后端全部路由 + 前端请求链路）+ 回归测试 + 真跑验证
基线：`pytest tests -q` 全绿（含新增 5 项稳定性回归）　结论速览：**6/6 清单项有结论，3 处缺陷已修复、1 处加固，其余 ✅ 达标**

修复清单：
1. **500 兜底**：未捕获异常统一返回「服务开小差了，请重试」（原为英文 Internal server error），并打 `error_500` 结构化日志
2. **删除活动孤儿通知**：notifications 无 event_id 外键，删除活动时显式清理（原残留孤儿通知）
3. **前端请求超时 + GET 重试**：fetch 15s AbortController 硬超时；幂等 GET 网络失败自动重试一次
4. **图片加载兜底补齐**：新增 `SafeImage` 组件（占位色块，--gift-* token），补齐头像/预览/晒图图 onError（原有 4 处缺失）
5. **加固**：`run.py` 显式 `debug=False`（防 FLASK_DEBUG 环境变量误开）；`create_event` budget 非法输入不再 500（原 int() 直接抛）

---

## 1. 崩溃容错（路由 try/except + debug 开关）

| 检查项 | 结论 | 证据 |
|---|---|---|
| 未捕获异常不裸堆栈 | ✅ 达标（修复后文案更友好） | `wxcloudrun/__init__.py` 全局 `@errorhandler(500)` 返回 `{code:-1, data:null, message:"服务开小差了，请重试"}`（本次由 "Internal server error" 改为友好中文，且记录 `log_event("error_500", path, method, error)`）；路由层统一 `except ValueError → fail(msg, 404)`，其余异常全部落入全局 500 处理器。实测（`tests/test_stability.py::test_uncaught_db_error_returns_friendly_500`）：monkeypatch `fetch_event` 抛 `sqlite3.OperationalError` → 500 + 友好文案，响应体不含 "database is locked"/"traceback" |
| 路由 try/except 覆盖 | ✅ 结构合理 | 所有路由均 `with DB()` 事务包裹；业务校验异常 `ValueError` 逐路由捕获转 404/400；DB/IO 异常不逐路由捕获（有意为之），统一由全局 500 处理器兜底（不泄露堆栈、不中断请求线程）。无裸 `except: pass` 吞错 |
| 输入容错 | ❌→✅ 已修复 | `event_routes.create_event`：`budget = int(data.get("budget") or 0)` 遇非数字（"abc"/"12.5"）直接 ValueError → 500。已改为 try/except → `fail("预算格式无效")`，新增 2 个回归测试 |
| debug 开关 | ✅ 达标（加固） | `run.py` 无 debug 参数（默认 False）+ 本次显式 `debug=False`；`gift_run.sh` 走 `run.py 0.0.0.0 8080`；Dockerfile `CMD ["python", "run.py", "0.0.0.0", "80"]`。`config.py` 的 `DEBUG=True` 是死代码（无任何 import），已确认不被加载 |

## 2. DB 并发（WAL / busy_timeout / 回滚 / 连接泄漏）

| 检查项 | 结论 | 证据 |
|---|---|---|
| WAL + busy_timeout | ✅ | `database.py:DB.__init__`：`PRAGMA journal_mode = WAL` + `PRAGMA busy_timeout = 5000`（5s 忙等待，读不阻塞写）；`PRAGMA foreign_keys = ON` |
| 写事务失败回滚 | ✅ | `DB.__exit__`：异常 → `rollback()`，正常 → `commit()`，随后 `close()`。抽签/重抽/发货/晒图等写路径全部在同一 `with DB()` 事务内 |
| 连接泄漏 | ✅ | 全仓 grep 确认 `DB()` 仅以 `with DB() as db` 形式使用（21 处），无裸实例；`ensure_mysql_database` 的探测连接有显式 close。每请求 after_request 的 CORS 读库也走 `with` + try/except |
| MySQL 双引擎 | ✅ | busy_timeout/WAL 为 SQLite 专属（有 engine 判断）；事务语义由 pymysql 连接自带 |

## 3. 重试与降级（KDNiao / 前端 api / 图片 onError）

| 检查项 | 结论 | 证据 |
|---|---|---|
| KDNiao 超时 + 缓存 + 降级文案 | ✅ | `helpers.py`：3s 硬超时（`_KDNIAO_TIMEOUT_SECONDS`）+ 6h 内存缓存（仅缓存成功结果）+ 永不抛异常；路由侧降级文案「物流查询暂不可用，稍后自动更新」。`tests/test_kdniao.py` 全绿（无配置/超时/网络异常/缓存命中/解析 8 个用例） |
| 前端 api 网络失败重试 | ❌→✅ 已修复 | 原 `client.ts` 无重试、无超时（fetch 可无限挂起）。本次：幂等 GET 网络层失败自动重试一次；POST/PUT/DELETE 不重试（避免重复副作用）；上传不重试（大文件浪费流量） |
| 前端请求超时 | ❌→✅ 已修复 | `fetchWithTimeout`：15s AbortController 硬超时，超时 → 「请求超时，请稍后重试」；外部 signal 兼容（可随组件卸载取消） |
| 上传失败提示可操作 | ✅ | `ImageUpload`：客户端 5MB/类型预校验 → 服务端消息（ApiError.message，如「文件过大（最大 5MB）」）展示在表单内，可重新选择；失败不清空已填业务字段 |
| 图片 onError 兜底 | ❌→✅ 已修复 | 新增 `SafeImage` 组件（失败 → 占位色块，背景 `--gift-bg-muted`，不硬编码色值；失败瞬间测量原图尺寸保持布局不跳）。补齐 4 处缺失：Header 头像、ProfilePage 头像、ImageUpload 预览、EventDetailPage 晒图照片；统一 EventsPage 卡片封面 + EventDetailPage 固定高封面。GiftWallPage 原有兜底保留。浏览器实测：bogus 头像 URL → `.safe-img-fallback` 渲染、页面无裂图 |

## 4. 数据完整性（抽签事务 / 晒图物流 / 删除活动）

| 检查项 | 结论 | 证据 |
|---|---|---|
| 抽签 matches + 通知同事务 | ✅ | `draw_routes.draw`：条件 UPDATE `open→drawn` 先抢锁（rowcount=0 → 409，未触碰数据）→ `_insert_matches`（DELETE 旧 gift_likes/matches + INSERT 新）+ `send_draw_notifications` 全部在同一 `with DB()` 事务；任何异常 rollback，不会出现「状态改了 matches 没写」 |
| 重抽原子性 | ✅ | `draw_routes.redraw`：先 `draw_solvable` 预判 + `draw_matches` 兜底，无解提前 400 **不删旧数据**；`_insert_matches` 的清理+重建+通知同事务提交。`tests/test_redraw.py` 覆盖 |
| 删除活动级联 | ❌→✅ 已修复 | participants/matches/gift_likes 有 FK `ON DELETE CASCADE`（线上库 `PRAGMA foreign_key_list` 实测确认）；**notifications 无 event_id 外键 → 删活动残留孤儿通知**。已在 `delete_event` 显式 `DELETE FROM notifications WHERE event_id = ?`。新增回归测试：抽签后插入点赞+通知 → 删除活动 → events/matches/participants/gift_likes/notifications 全清空（含孤儿通知断言） |
| 晒图/物流/资料保存失败不丢输入 | ✅ | 前端表单 state 仅在成功后 setState（ProfilePage/EventDetailPage 保存失败只 toast，输入保留）；删除晒图有二次确认 + 拒重删（404 幂等） |

## 5. 超时与取消（fetch 超时 / 卸载后 setState）

| 检查项 | 结论 | 证据 |
|---|---|---|
| fetch 超时 | ❌→✅ 已修复 | 见 §3：15s AbortController（`client.ts:fetchWithTimeout`），普通请求与上传统一走该封装 |
| 组件卸载后 setState 警告 | ✅ 无需修复 | React 18 已移除该 warning（卸载后 setState 为无害 no-op），代码中亦无此警告残留；请求 15s 硬超时已限制在途工作。`client.ts` 兼容外部 `signal`，未来页面需要卸载取消时直接传入即可 |

## 6. 资源清理（上传限制 / uploads 增长 / 日志轮转）

| 检查项 | 结论 | 证据 |
|---|---|---|
| 上传大小上限复核 | ✅ | `site_routes.upload_image`：读取 `MAX_UPLOAD_BYTES + 1` 判超 → 「文件过大（最大 5MB）」；扩展名白名单（png/jpg/jpeg/gif/webp）+ content_type 白名单 + 魔数校验（`check_image_magic`）+ storage 层防路径穿越（`_validate_key`）双层兜底 |
| data/uploads 无限增长 | ⚠️ 提示项（不阻塞上线） | 当前 29 文件 / 116K，规模极小。无删除/过期策略：图片上传后即使业务字段被清空/活动删除也不落盘清理。建议上线后接对象存储 + 定期清理（非本期代码范围） |
| 日志轮转 | ✅ 无文件可轮转 | `observability.py` 只写 **stdout**（一行一条 JSON，logger `giftexchange`，propagate=False），不写文件；生产 `container.config.json` `customLogs: stdout`。日志大小由部署平台日志采集侧负责，应用内无需轮转 |

---

## 验收核对

| 验收项 | 结果 | 证据 |
|---|---|---|
| 每清单项有结论 | ✅ | 上表 6/6，含修复前后对比 |
| pytest tests -q 全绿 | ✅ | 全量通过（含新增 `tests/test_stability.py` 5 项：500 友好文案、budget 非法输入 ×2、删除活动级联清理、非创建者删除 403） |
| 前端 build 通过 | ✅ | `npm run build` 成功（551ms），templates/index.html 已引用新 bundle `index-DlFuMgRH.js`，Flask 已重启 |
| curl health 200 | ✅ | `GET /api/health` → `{"code":0,"data":{"status":"ok",...},"message":"ok"}`；`GET /` → 200 |
| 浏览器实测（改前端） | ✅ | 未登录 /events → 正确跳 /login；登录态 /events 正常渲染无 JS 报错；坏头像 → SafeImage 占位块，无裂图 |

## 改动文件清单

后端：`wxcloudrun/__init__.py`（500 文案+日志）、`wxcloudrun/event_routes.py`（budget 容错、删除活动清通知）、`run.py`（debug=False）
前端：`frontend/src/api/client.ts`（15s 超时 + GET 重试）、`frontend/src/components/SafeImage.tsx`（新增）、`frontend/src/styles/global.css`（占位块样式）、`Header.tsx`/`ProfilePage.tsx`/`ImageUpload.tsx`/`EventDetailPage.tsx`/`EventsPage.tsx`（接入 SafeImage）
测试：`tests/test_stability.py`（新增 5 项）

## 遗留说明（非本期范围）

- 多实例部署时：内存限速/KDNiao 缓存/短码限速需换 Redis（代码注释已标明改造点）
- 生产 WSGI 服务器（gunicorn/waitress）属安全波次 P1 项，未在本期处理
- uploads 目录无清理策略（见 §6）
