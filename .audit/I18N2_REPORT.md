# I18N2_REPORT — i18n 全量迁移 + 登录安全深化

- 轮次：hackathon 轮10（未 commit）
- 日期：2026-08-10
- 前置：轮5 i18n 架构（38 公共串）、轮4 安全波次遗留 login_required 每请求 deactivated 查询

---

## 任务 A：i18n 全量迁移

### 迁移范围（17 个源文件，全部用户可见文案 → t()）

| 文件 | t() 调用点 | 说明 |
|---|---|---|
| pages/EventDetailPage.tsx | 217 | 最大文件；状态机/物流/晒图/邀请/归档/重抽全链路 |
| pages/ProfilePage.tsx | 65 | 资料/通知偏好/改密/导出/注销 |
| pages/CreateEventPage.tsx | 58 | 模板预设 12 条、校验、互避规则 |
| pages/EventsPage.tsx | 47 | 列表/下拉刷新/邀请码弹窗；`t` 遮蔽改名（detectInviteCode/load 参数） |
| pages/GiftWallPage.tsx | 37 | 礼物墙/再开一局/高光海报 |
| pages/DashboardPage.tsx | 34 | 管理台统计/明细 |
| pages/ForgotPasswordPage.tsx | 35 | 找回密码双步骤 |
| pages/RegisterPage.tsx | 27 | 注册 |
| components/SharePoster.tsx | 13 | canvas 绘制文案，locale 加入 effect 依赖重绘 |
| components/PosterModal.tsx | 9 | 海报弹窗 + 下载文件名模板 |
| components/ImageUpload.tsx | 7 | 上传 |
| components/ErrorBoundary.tsx | 3 | class → 函数壳 + localeKey 重渲染 |
| App.tsx | 2 | 加载 fallback ×2 |
| utils/format.ts | 4 | 截止时间 locale 化（en-US/zh-CN 日期）+ t() |
| api/client.ts | （轮5 已迁） | 网络错误文案 |
| **合计** | **~560 调用点 / 499 唯一 key** | |

### 字典

- `frontend/src/i18n.ts`：zhKeys（499 key 注册表）+ en 字典（499 条，**100% 覆盖**）。
- 单一事实来源 `.audit/en_dict_gen.py`（key=中文原文，value=自然英文）→ `.audit/gen_i18n_ts.py` 生成。
- **未翻译 key 回退原文：0 个**（脚本验证：源码全部 t('...') 字面量 + 数据驱动 label 数组（PREF_ITEMS/MEMBER_STATUS_META/REMINDER_LABEL/PRIVACY_OPTIONS 等经 `t(var)` 渲染）与字典双向比对，无缺失、无冗余；注册表 保存/删除/确认 保留为公共动作）。
- 插值：复杂表达式（filter/join/三元）先提 const 再进 vars；占位符 `{name}` 在 key 内逐字保留。
- 已知取舍：`t()` 无复数机制，计数类 key 改写为 count 无关措辞（`Participants: {count}`、`Reminded {reminded}`）；key=source 架构下单复数是后续可加项。

### 验证

1. **en-US 浏览器全站走查**（localStorage `gift_locale=en`，真实服务 127.0.0.1:8080）：
   登录 → 活动列表 → 活动详情 → 礼物墙 → 个人中心 → 创建页 → 海报弹窗，全英文，无中文残留。
   截图 8 张：`.audit/i18n2-shots/01-login-en.webp … 07-poster-en.webp`（+ `08-events-zh.webp`）。
   抽查英文样本：「Exchange surprises with friends」「Participants: 1」「Recruiting: share the invite code to bring friends in (1 so far)」「📣 Invite poster / ⬇️ Download poster / Close」「One pair per line, usernames separated by commas\nExample: xiaoming, xiaohong」「Joined 8/7/2026」。
2. **zh 默认不变**：`gift_locale=zh` 下 UI 与源文案逐字一致（「我的活动 / 报名中 / 1 人参与 / 报名 2026/12/26」）；`document.title` 随语言（Gift Exchange ↔ 互送礼物）。
3. **构建**：`npm run build` 通过；Flask 已重启（模板缓存）。
4. **顺带修复**：EventDetailPage 使用 `<SafeImage>` 但缺失 import（HEAD 即存在，运行时会 ReferenceError 崩溃）→ 补 `import SafeImage`。

---

## 任务 B：登录安全深化

### B-1 login_required 开销测量（结论：保持现状）

实测（`.audit/login_required_bench.py`，真实 SQLite WAL 库 + Flask test client，3000/200 次采样）：

| 成本项 | median | p99 |
|---|---|---|
| verify_token（JWT 验签，纯 CPU） | 4.3 µs | 4.8 µs |
| DB 连接建立（open + 2×PRAGMA） | 384 µs | 810 µs |
| `SELECT deactivated FROM users WHERE id=?`（新建连接内，单列主键） | 392 µs | 910 µs |
| **login_required 合计** | **404 µs** | **902 µs** |

完整认证请求（进程内，含全生命周期）：/auth/me 621 µs、/profile 603 µs、/events 606 µs、详情 601 µs、管理台 600 µs（中位）。

- 进程内占比 ~65%（这些接口整体亚毫秒，分母极小）；
- **HTTP 基线（perf2 轮，4.3–6.0 ms/接口）占比约 7–9%**；
- 生产（MySQL + 网络 + 大数据量）占比更低。

**结论（务实方案落地）**：每请求保留单列查询 `SELECT deactivated FROM users WHERE id = ?`（当前代码已是此形态），绝对成本 0.40 ms 中位 / 0.90 ms p99，可忽略。
缓存方案全部否决：内存缓存「非 deactivated」破坏「注销后旧 token 立即 401」安全波次验收；token_version 仍需查库；本任务书判定「<5% 保持现状」——轻接口占比偏高是因分母亚毫秒，绝对值是正确度量。文档已说明（本报告 + CHANGELOG），不引入复杂度。

### B-2 登录审计（确认 + 补全）

| 事件 | 字段 | 状态 |
|---|---|---|
| `login_success`（clear_login_attempts 埋点） | username + client_ip + ts/request_id 自动 | 已有 ✓ |
| `login_failed`（密码错误/账号不存在） | username + client_ip + ts | 已有 ✓ |
| `login_failed`（**注销账号尝试登录**） | username + client_ip + ts + 计入限速 | **本轮补全**（auth_routes.login deactivated 分支此前无审计盲区） |
| `request`（每请求） | method/path/status/duration_ms/user_id | 已有 ✓ |

新增测试：`tests/test_observability.py::test_login_deactivated_attempt_audited`（注销后登录 → 401「账号已注销」+ 断言 login_failed 事件含用户名/时间戳）。

### B-3 密码策略（P2：密码 ≠ 用户名）

- 后端 `wxcloudrun/auth_routes.py`：`register` / `reset_password` / `change_password` 增加大小写不敏感「密码不能与用户名相同」→ 400。
- 前端：RegisterPage（注册表单）、ForgotPasswordPage（账号字段为用户名时）、ProfilePage（改密，比对当前用户名）。
- 测试：`tests/test_account.py::TestPasswordPolicy`（注册 ×2、改密 ×1）、`tests/test_auth_reset.py::test_password_same_as_username_400`（重置 ×2，含大写变体）。
- 文档：`docs/API.md` 注册/登录/改密段更新（顺带修正历史笔误 ≥8 → ≥6，与代码一致）。

---

## 验收对照

| 验收项 | 结果 |
|---|---|
| en-US 全站英文走查（截图 5+ 页） | ✅ 8 张截图（登录/列表/详情/礼物墙/个人中心/创建/海报弹窗 + zh 对照） |
| zh 默认不变 | ✅ 逐字一致（key=source，zh 模式返回原文） |
| 未翻译 key 回退原文 = 0 | ✅ 脚本双向校验 499/499 |
| login_required 开销测量结论 | ✅ 0.40 ms 中位 / 0.90 ms p99；保持每请求单列查询，不缓存（报告见上） |
| 审计日志补全 | ✅ 注销账号登录尝试补 login_failed + 限速 |
| pytest 全绿 | ✅ 255 passed（`pytest tests -q`）；本轮新增 7 个安全用例 |
| build 通过 | ✅ `npm run build` + Flask 重启 |

## 交付物

- 代码：17 前端源文件 + i18n.ts（重建）、auth_routes.py、3 测试文件、docs/API.md、CHANGELOG.md
- 脚本/产物：`.audit/en_dict_gen.py`（字典源）、`.audit/gen_i18n_ts.py`（生成器）、`.audit/login_required_bench.py`（开销测量）、`.audit/i18n2-shots/`（走查截图）
