# 用户旅程补强报告（hackathon 波次4）

- 日期：2026-08-10
- 范围：`wxcloudrun/**`（event_routes / gift_routes / helpers）、`frontend/src/**`、`tests/**`（未 commit；无 migrations）
- 视口：375/390×812/844（移动端），puppeteer-core + 本地 Chrome
- 服务：http://127.0.0.1:8080（每次 build 后按 AGENTS.md 规范重启，`/api/health` 200）
- 测试账号：`verify_user / Verify123`（历史数据）+ 浏览器内新建事件
- 测试：`pytest tests -q` 全绿（228 passed，含新增 `tests/test_journey.py` 8 例）

## 一、任务清单逐项结论

### 1. 组织者创建活动后自动加入 ✅（行为变更）
- 现状：创建者不在 participants；详情页对组织者显示「加入这个活动」。
- 改动：
  - `wxcloudrun/event_routes.py` `create_event`：INSERT events 后立即 `add_participant(db, event_id, creator)`，`participant_count` 随之 +1；不加任何通知（创建者加入不打扰自己）。
  - `frontend/src/pages/EventDetailPage.tsx`：加入按钮改为 `!isOwner && !joined && status==='open'` 才显示；`isOwner && !joined`（旧活动兜底）显示「你是组织者，活动已创建，无需加入」。
- 连带影响（已核对）：
  - 抽签门槛 `len(rows) < 2 → 至少需要 2 人才能抽签` 不变（创建即 1 人仍提示）；2 人互送规则不变（仍拒绝，提示至少 3 人）。
  - 催办 `remind` 已有「组织者不催自己」显式跳过，不受影响。
  - 旧活动不回填（约束：不做 migrations）——旧活动组织者不在 participants 时显示上面的提示文案。
- 测试：
  - 新增 `tests/test_journey.py::TestCreatorAutoJoin`：创建后 participants 含创建者 / participantCount=1 / 1 人抽签 400 / 创建者重复 join 400「你已加入该活动」/ 创建者 +2 人可正常抽签 / 创建者 leave 400「创建者不能退出」。
  - 既有测试同步：9 个测试文件的 `join_event` helper 对「你已加入该活动」（400）幂等放行（组织者自动加入已满足"创建者参与"意图）；`test_flow_state.py` 两处内联 join 循环去掉创建者显式 join。
- 浏览器实测：新建活动 → 详情页「参与人数 1」、无「加入这个活动」、抽签按钮 disabled「至少 2 人才能抽签」；旧活动（组织者未加入）显示提示文案、无加入按钮。

### 2. 物流降级文案 ✅（区分原因 + 手动刷新）
- 现状：KDNiao 未配置/失败统一存「物流查询暂不可用，稍后自动更新」。
- 改动：
  - `wxcloudrun/helpers.py`：新增文案常量 `TRACKING_NOT_CONFIGURED_MSG`（「暂未接入物流查询，可通过单号自行查询」）、`TRACKING_QUERY_FAILED_MSG`（「物流信息查询失败，请稍后刷新重试」）、`tracking_degradation_copy(detail)` 按 detail 区分未配置/失败；`api_shipment` 新增 `trackingRefreshable`（失败文案时才可刷新，含旧版失败文案的历史行，无迁移兼容）。
  - `wxcloudrun/gift_routes.py` `update_shipment`：降级时写入区分后的文案。
  - 新增 `POST /api/events/<code>/shipment/refresh`：仅送礼人本人、必须有单号；失败结果不缓存故强制重查；成功更新 `tracking_summary`，不改发货状态、不重复通知。
  - `frontend/src/pages/EventDetailPage.tsx` `ShipmentSection`：`trackingRefreshable` 时显示「🔄 刷新物流信息」按钮，点击调 refresh 接口。
- 测试（`tests/test_journey.py::TestLogisticsDegradationCopy`）：
  - 未配置 → 存「暂未接入…」且 `trackingRefreshable=false`；
  - 查询失败（monkeypatch 外呼失败）→ 存「物流信息查询失败…」且可刷新；refresh 仍失败保持文案；refresh 成功 → summary 更新、不可再刷新；
  - 守卫：未登录 401 / 非参与者 403 / 缺 matchId 400 / 非本人任务 400。
- 浏览器实测：给历史 drawn 活动写入旧失败文案 → 详情页出现刷新按钮 → 点击 → 文案变为「暂未接入物流查询，可通过单号自行查询」（本机未配 KDNiao 的真实降级路径）、按钮消失。测试后已还原该行数据。

### 3. 品牌标题去重 ✅
- 现状：全局 Header 品牌「🎁 互送礼物」与活动列表页 h1「互送礼物」重复。
- 改动：`frontend/src/pages/EventsPage.tsx` h1 按 tab 显示：我创建的→「我的活动」、我参与的→「我参与的」、发现活动→「发现活动」、已归档→「已归档」；Header 品牌保留。
- 附带修复（验证中发现的前置阻塞 bug）：EventsPage 使用了 `<SafeImage>` 但从未 import，导致该页运行时 ReferenceError、整页白屏（ErrorBoundary 兜底）——这是改动前已存在的缺陷，且阻塞本次 h1 验收，补 `import SafeImage from '../components/SafeImage'`。
- 浏览器实测：mine tab h1「我的活动」、public tab h1「发现活动」（DOM 断言）。

### 4. 礼物墙体验 ✅（自查，未改代码）
- 未解锁引导：已有 mask（🎁 + 「点击揭晓」）+ 进度条 +「去晒出你的礼物」CTA，清晰（锁定态实测：进度/文案/CTA 均在）。
- 解锁后动作：卡片点击揭晓有明确「点击揭晓」提示；「🏆 生成高光海报」「🔁 再开一局」按钮位于礼物墙顶部（解锁态实测：3 张卡片 mask + 3 处「点击揭晓」）。
- 观察项（未改）：抽签前访问礼物墙，`total` 按 matches 计数为 0，文案「还没有人加入活动」——活动创建者已自动加入后此文案略不准确，但礼物墙语义以抽签配对为准，属既有设计，未动。

### 5. 错误提示可操作 ✅（抽查，已有行为符合，未改）
- 加入（JoinForm）：失败仅 `setError`，表单不关闭、输入保留。
- 创建（CreateEventPage）：失败 toast，title/note/预算等 state 不重置。
- 晒图（ReceivedGiftSection）：失败 toast，表单与输入保留。
- 物流（ShipmentSection）：失败 toast，表单保留（本次新增的刷新按钮失败同样只 toast）。
- 结论：四类表单提交失败后输入均保留，无缺失项。

## 二、验收标准对照

| 验收项 | 结果 |
|---|---|
| 创建后 participants 含创建者、详情页无「加入这个活动」、1 人时抽签仍提示至少 2 人 | ✅ API 测试 + 浏览器实测 |
| `pytest tests -q` 全绿（旧测试同步更新） | ✅ 228 passed |
| build + 重启 + health + 浏览器实测关键路径 | ✅ 见上（截图 `/tmp/j_*.png`：events-mine/public、detail-created、owner-hint、refresh-before/after、giftwall、wall-locked、375-detail） |
| 报告 `.audit/JOURNEY_REPORT.md` | ✅ 本文件 |

## 三、改动文件清单

- 后端：`wxcloudrun/event_routes.py`（create 自动加入）、`wxcloudrun/gift_routes.py`（降级文案 + refresh 端点）、`wxcloudrun/helpers.py`（文案常量 + `tracking_degradation_copy` + `api_shipment.trackingRefreshable`）
- 前端：`frontend/src/pages/EventDetailPage.tsx`（加入按钮/组织者提示/刷新按钮）、`frontend/src/pages/EventsPage.tsx`（h1 按 tab + SafeImage import 修复）、`frontend/src/api/client.ts`（`Shipment.trackingRefreshable`）
- 测试：`tests/test_journey.py`（新增 8 例）；`test_account/archive/draw_api/gift_delete/gift_privacy/member_status/redraw/security_hardening/stability/flow_state` 的 join 调用同步
- 构建产物：`wxcloudrun/static/**`、`wxcloudrun/templates/index.html`（`npm run build` 强制产物）
