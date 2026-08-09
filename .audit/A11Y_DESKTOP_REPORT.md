# A11Y + 桌面端深化报告（轮 3）

日期：2026-08-10 ｜ 范围：frontend/src/**、frontend/index.html、frontend/public/**（未 commit；wxcloudrun/static 仅为 build 产物，非源码改动）

---

## 1. 对比度（WCAG AA 4.5:1）— token 调整

全部按 `--gift-*` token 调整（`tokens.css` 与 `tokens/index.ts` 同步），品牌色 `#E8553D → #C93B24`（同色相系加深一档，白字/文字双双过线）。新增 4 个状态色文字变体 token（暗色主题提亮，浅色主题=主色）：

| 场景 | 旧值 → 新值 | 旧对比度 | 新对比度 |
|---|---|---|---|
| 品牌按钮白字 / 品牌文字(浅底) | `#E8553D → #C93B24` | 3.62 / 3.29–3.49 | 5.08 / 4.59–4.90 |
| badge-success 文字 | `#2DA05A → #1B7A43` | 2.97 ❌ | 4.77 ✓ |
| badge-warning 文字 | `#E8930C → #8A5E00` | 2.22 ❌ | 5.19 ✓ |
| badge-error / 表单错误 | `#D84040 → #C22F2F` | 3.85–4.44 | 4.87–5.61 ✓ |
| badge-info 文字 | `#4A7FB5 → #2F5F8F` | 3.69 | 5.84 ✓ |
| 星星图标/金色点缀 | `#D4A017 → #A97A00` | 2.29（图标 3:1 不足） | 3.84（图标 3:1 ✓） |
| 暗色主题按钮白字（亮珊瑚底） | `text-on-primary` 白 → `#2C211E` 深 | 2.21 ❌ | 6.04 ✓ |
| 暗色 badge 文字（新增 `*-text`） | error `#E57A7A` / warning `#E8B054` / success `#6FC99B` / info `#8FB8E8` | 2.2–2.9 ❌ | 5.7–9.2 ✓ |

正文/次要文字本就达标：text-primary 11.7–12.9、text-secondary 4.65–5.14（全部 ≥4.5）。暗色主题下状态色背景用法（白字 on `--gift-error`/`--gift-success`）保持白字（5.6/5.4 ✓），与文字变体 token 分离设计。

## 2. 每页 a11y 结论表

| 页面 | 语义化 | 键盘 | ARIA | 对比度 | 结论 |
|---|---|---|---|---|---|
| 登录 | ✅ 修复：placeholder→sr-only label + htmlFor/id | ✅ 修复：密码显隐按钮移除 `tabIndex=-1` | ✅ 错误 `role=alert` + aria-describedby | ✅ token 全过 | ✅ |
| 注册 | ✅ 同上（4 字段） | ✅ 同上 | ✅ 两次密码不一致 inline 错误 id + alert | ✅ | ✅ |
| 找回密码 | ✅ 同上（4 字段） | ✅ 同上 | ✅ 错误/不一致 aria 接线 | ✅ | ✅ |
| 活动列表 | ✅ 唯一 h1；事件卡片本为 Link | ✅ Tab 按钮 aria-pressed；下拉刷新对键盘无干扰 | ✅ 搜索框 sr-only label | ✅ | ✅ |
| 创建活动 | ✅ 全部 label htmlFor/id（含模板区） | ✅ | ✅ 错误 role=alert | ✅ | ✅ |
| 活动详情（含游客落地页） | ✅ 唯一 h1（游客/错误态各一） | ✅ 修复：全部弹窗 ESC/焦点圈定/回焦；揭晓按钮 Enter 可操作 | ✅ FlowSteps/ShipmentProgress/加入步骤条 `aria-current="step"`；发货表单 aria-label | ✅ 重新抽签/归档文字切 `*-text` token | ✅ |
| 管理台 | ✅ | —（无交互缺陷） | ✅ 表格 th scope=col | ✅ stat-num 切 `*-text` | ✅ |
| 礼物墙 | ✅ 揭晓为 button（非 div）；星星/照片 alt 正确 | ✅ 揭晓按钮焦点可见 + Enter 揭晓；点赞 aria-pressed | ✅ 未揭晓内容 visibility:hidden（读屏/焦点双隔离） | ✅ 星星 gold 3:1 | ✅ |
| 个人资料 | ✅ 头像按钮 aria-label | ✅ | ✅ 偏好开关本有 aria-label | ✅ 注销文字切 error-text | ✅ |

统一组件：新增 `Modal.tsx`（role=dialog + aria-modal + aria-labelledby + ESC + 焦点圈定 + 回焦，回焦目标失效时回焦页面 h1）；全部 9 处弹窗（加入/抽签/重抽/归档/重置码/删除晒图/注销/再开一局/海报）改用之。Toast 容器 `role="status" aria-live="polite"`。Header：铃铛 `aria-expanded/aria-controls` + 面板 `role="region" aria-label` + ESC 关闭；通知行无链接时 `role="button"`+Enter/Space 可标记已读；nav `aria-label` + `aria-current="page"`。

## 3. 键盘走查（.audit/keyboard_walk.mjs，11/11 PASS）

- 登录页连续 Tab 焦点环全程可见（`:focus-visible` 2px 品牌色 outline）
- 加入弹窗打开焦点入内（首个可聚焦元素）→ ESC 关闭 → 焦点回触发元素（自动弹窗回焦 h1）
- 弹窗内 Tab 从末尾循环回弹窗内（无焦点逃逸/卡死）
- 礼物墙揭晓按钮可聚焦、焦点可见、Enter 揭晓后内容可见
- 通知铃铛 aria-expanded 切换、ESC 关闭面板
- `prefers-reduced-motion` 下动画时长 0.01ms（揭晓/海报/Toast 全部禁用）

## 4. 三视口响应式（截图 .audit/desktop-shots/{w1280,w1440,w768}/，每视口 8 页 × metrics.json）

| 视口 | 横滚 | 礼物墙列数 | 详情页布局 | 活动列表 | 触控目标 <40px |
|---|---|---|---|---|---|
| 1280×800 | 无 | 4 列（卡片等宽等高 260px） | 两栏（左 447px / 右 625px） | 2 列栅格 | 0 |
| 1440×900 | 无 | 4 列 | 两栏 | 2 列栅格 | 0 |
| 768×1024（iPad） | 无 | 2 列 | 单列堆叠 | 单列 | 0 |

实现：`.page-container--wide`（1120px，礼物墙/详情页）；`.event-list` ≥1024 双列 grid；`.detail-layout` ≥1024 `5fr/7fr` 两栏；`.gw-grid` minmax 300→250 使 4/2/1 列自适应。全部页面 h1 唯一（程序化扫描 0 缺陷）。

## 5. 减少动效 & 打印

- `@media (prefers-reduced-motion: reduce)`：全局动画/过渡压至 0.01ms，揭晓翻转/星星散落/Toast 弹入/礼盒浮动全部禁用（保留静态呈现，读屏无碍）
- `@media print`：隐藏顶栏/按钮/揭晓遮罩/点赞；礼物墙未揭晓卡片打印时直接展示内容（`visibility: visible`）、`break-inside: avoid`、2 列；海报弹窗去遮罩仅输出画布

## 6. 验证

- `npm run build`（frontend/）✓ → Flask 已重启（模板缓存坑规避）
- `pytest tests`：**238 passed in 15.43s** ✓（未改 tests/**）
- `py_compile` 全过 ✓；`/api/health` 200 ✓
- git：仅 frontend/** 源码改动 + build 产物（wxcloudrun/static 哈希更新属构建常规输出）；未 commit

## 7. 遗留说明

- 暗色主题为预置可用主题：本轮补齐其文字对比度（`*-text` 变体 + text-on-primary 深色）；若产品后续上线暗色主题，建议再人工走查一遍状态色背景组合。
- 海报 Canvas 为位图输出，无法引用 CSS 变量：已改为从 `tokens/index.ts` primitive 取值（单源），顺带修复二维码失败兜底分支引用 try 作用域变量的潜在 bug。
