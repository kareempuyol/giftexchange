# 场景扩展 E2E + 性能二次复测报告（hackathon 轮 8）

日期：2026-08-10 · 服务 http://127.0.0.1:8080（本地 SQLite，build 后已重启）
脚本：`.audit/e2e_scenarios2.mjs`（6 场景 59 断言）、`.audit/perf2_measure.py`（API 计时）、
`.audit/perf2_frontend.mjs`（前端指标 + 懒加载验证）
截图：`.audit/scen2-shots/`（23 张）· 结果 JSON：`scen2-results.json` / `perf2-results.json` / `perf2-frontend-results.json`

## 一、任务 A：场景扩展 E2E —— **59/59 通过，0 缺陷（最终轮）**

| # | 场景 | 断言 | 覆盖内容 | 结果 |
|---|------|------|----------|------|
| 1a–1c | 多活动工作流 | 5 | 组织 1 + 参与 2；「我创建的」仅 A；「我参与的」含 B、C（+创建者自动加入的 A，共 3）；详情数据隔离（B/C/A 参与者互不串台） | ✅ |
| 2a–2g | 礼品流全链路 | 23 | A 建 → B/C/D UI 加入 → 抽签 → B 发货（快递+悄悄话，状态=已发货）→ 悄悄话待揭晓/晒图后揭晓 → 全员晒图（D 公开照片）→ A 礼物墙解锁 → 高光海报 → canvas.toDataURL 前缀 = `data:image/png` → 下载反馈 | ✅ |
| 3a–3c | 通知驱动回流 | 11 | 铃铛角标≥1；「你已加入」→ 点击跳详情；「抽签结果已出」→ 点击看 my-match；B 的送礼人发货 →「你的礼物已发货」→ 点击回详情 | ✅ |
| 4a | 深链直达 | 5 | 游客直接输 `/events/<短码>` → 落地页（标题+CTA）→ `/login?from=events/<code>` → 登录回跳详情 | ✅ |
| 5a | 资料预填 | 7 | 个人中心保存 收件人/手机号/地址/偏好 → 加入另一活动表单自动带入（含预填提示）+ 预填数据直接加入成功 | ✅ |
| 6a–6d | 密码强度边界 | 8 | 纯数字/纯字母/5 位注册 → 400 中文提示（API + UI 各验）；改密接口拒弱新密码；正确改密 → 旧密码被拒 → 新密码立刻登录 | ✅ |

### 缺陷（发现 → 修复，2 个 P1）

| 严重度 | 发现方式 | 根因 | 修复 |
|--------|----------|------|------|
| P1 | 场景 3 断言失败 | 加入活动后**本人无确认通知**（原实现只通知组织者 `participant_joined`），「通知驱动回流」场景无法成立 | `wxcloudrun/event_routes.py`：`join_event` 成功后给加入者发 `join_success` 通知（"你已加入「…」"，含 eventCode 供点击跳转；自己的动作不受通知偏好拦截）。新增 `TestJoinSuccessNotification`（2 个回归测试） |
| P1 | 场景 5 断言失败 | ProfilePage 文案明示「保存后，加入新活动时会自动帮你填好收件信息」，但 JoinForm 从空状态开始、未读个人资料 | `frontend/src/pages/EventDetailPage.tsx`：JoinForm 挂载时拉 `/api/profile`，收件人/电话/地址/礼物偏好预填（仅填空字段，不覆盖手输）+「已从个人资料自动填入」提示 |

### 测试断言修正（1 处，非产品缺陷）
场景 1b 初版断言「我参与的 = 2（B、C）」失败：创建者自动加入是既有契约（`tests/test_journey.py`
`test_creator_is_participant_after_create`），A 同时出现在「我创建的」与「我参与的」。修正断言为
3 个（A+B+C），应用行为正确，未改产品代码。

## 二、任务 B：性能二次复测

### 2.1 后端 9 接口计时（curl 5 次中位数，ms）

规模数据：50 个「性能测试活动」× 5 人（组织者 verify_user + 4 成员）+ 环形 matches + 100 通知
（造数后计时，测完已清理，库恢复 259/826/544/1389/386，与测前完全一致）。账号 `verify_user / Verify123`。

| 接口 | 轮 2 基线（规模·优化后） | 本轮（规模） | Δ |
|---|---|---|---|
| /api/events/mine | 5.99 | **4.97** | −1.02 |
| /api/events/public | 4.73 | **4.65** | −0.08 |
| /api/events/\<code\> | 4.29 | **4.12** | −0.17 |
| /api/events/joined | 5.41 | **5.17** | −0.24 |
| /api/events/\<code\>/gift-wall | 4.53 | **4.63** | +0.10 |
| /api/events/\<code\>/participants | 4.86 | **4.70** | −0.16 |
| /api/notifications | 5.99 | **4.48** | −1.51 |
| /api/events/\<code\>/dashboard | 5.70 | **4.69** | −1.01 |
| /api/profile | 5.18 | **4.47** | −0.71 |

结论：9 接口全部 4–5ms，8/9 持平或更优，`gift-wall` +0.10ms 在运行噪声内（同轮 min/max 波动
±2–10ms，见 `perf2-results.json` 原始样本）。**无任何接口恶化**；与轮 2 一致，SQLite 千行级
下墙钟差异不可测，索引收益由轮 2 的 EXPLAIN 证明、在 MySQL 万级行下兑现。复测未发现新回归。

### 2.2 前端首屏指标（puppeteer performance API，390×844）

| 页面 | TTFB | DOMContentLoaded | Load | 主 bundle |
|---|---|---|---|---|
| /login（游客） | 3 ms | 25 ms | 25 ms | index-CPTIH9ph.js |
| /events（登录） | 6 ms | 23 ms | 23 ms | index-CPTIH9ph.js |

主 bundle 传输大小：**200,868 B（≈196 KB）**，构建产物 198.33 kB / gzip **64.00 kB**。
对比轮 2（188.1 kB / gzip 60.7 kB）：原始体积 +10.2 kB，来自轮 2 之后的功能增量
（i18n、下拉刷新、分享海报扩展等），仍在 gzip 200 KB 目标内。

### 2.3 懒加载验证（network 面板断言，7/7）

- `/login`（游客）：**0 个懒加载 chunk** —— 不加载 海报 chunk（PosterModal-*）、详情 chunk（EventDetailPage-*）、也不加载其余页面 chunk；仅主 bundle + CSS。
- `/events`（登录，校验确为登录态列表页、非重定向）：**不加载详情 chunk、不加载海报 chunk**。

## 三、验收标准核对

| 标准 | 结果 |
|------|------|
| 场景 E2E 全过（记录断言数） | ✅ 59/59（断言数按场景记录于 §一；JSON `scen2-results.json`） |
| 性能对比表（基线 vs 现在） | ✅ §2.1 / §2.2（含轮 2 基线列） |
| build 通过 + pytest 全绿 | ✅ `npm run build` 成功（index-CPTIH9ph.js 已同步 static + templates，Flask 已重启）；**pytest 250 passed** |
| 报告 | ✅ 本文件 |

## 四、改动文件

- `frontend/src/pages/EventDetailPage.tsx` — JoinForm 资料预填（P1 修复）
- `wxcloudrun/event_routes.py` — 加入确认通知 join_success（P1 修复）
- `tests/test_journey.py` — TestJoinSuccessNotification（2 个回归测试）
- `wxcloudrun/static/*`、`wxcloudrun/templates/index.html` — build 产物（自动更新）
- `.audit/e2e_scenarios2.mjs` + `scen2-shots/`（23 张）+ `scen2-results.json` — 场景测试资产
- `.audit/perf2_measure.py` + `perf2-results.json`、`.audit/perf2_frontend.mjs` + `perf2-frontend-results.json` — 性能复测资产

未 commit；未触碰数据库历史/迁移；规模数据已清理（DB 计数与测前一致）。
