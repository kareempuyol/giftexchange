# REPORTS_INDEX.md — 审计报告清单

项目：giftexchange（hackathon 轮1–轮18，omp 执行）
更新：2026-08-10（轮18 终局回归）

全部报告位于 `.audit/`，按轮次排列：

## 轮18 — 终局回归（2026-08-10）
- `FINAL3_CHECK.md` — 终局全量回归核对（pytest 269 / CI 3 连绿 / build+重启+health+公网隧道 / E2E 48/48 复跑 / 公网终验 login / 工作区状态）
- 本轮文档更新：`HACKATHON_DELIVERY.md`（轮15/16/17 入时间线、commit 28、全仓 87、真实负载「可上线」）、`CHANGELOG.md`（补轮15/16/17 条目）、`REPORTS_INDEX.md`（本文件）
- 本轮复跑数据：`.audit/e2e-results.json`（主旅程 48 步，复跑后已还原）、`.audit/e2e-shots/`

## 轮17 — 收官功能补充（纯前端轮，2026-08-10）
- `R17_REPORT.md` — 5 项收官功能：活动热度/已抽签角标、礼物墙统计卡（规格前提勘误：
  后端无 totalPosted/totalStars，改前端从 items 计算）、通知角标点击清零、认证页品牌区
  统一（AuthBrand 组件）、预算均摊展示（¥100 · 平均每人 ¥33）；pytest 269 全绿 + build 通过
  + 浏览器实测；wxcloudrun/ 恢复无 diff
- 截图：`.audit/r17_shots/01-08.webp`

## 轮16 — 真实使用模式负载（2026-08-10）
- `LOAD_REPORT.md` — 50 虚拟用户 × 5 分钟真实节奏负载：10,646 请求 0 5xx / 0 错误事件 / 0 锁死，
  p99 33ms（服务端），可上线结论；慢端点 TOP3 与瓶颈分析
- 数据：`load_results.json`（含 59 次资源采样）、脚本 `load_sim.py`（独立 DB + 端口，跑完清理）

## 轮15 — 最终全量回归 + 报告更新（2026-08-10）
- `FINAL2_CHECK.md` — 全量回归核对（pytest 269 / CI 5 连绿 / build+重启+health+公网冒烟 / E2E 48/48 复跑 / 工作区状态）
- 本轮文档更新：`HACKATHON_DELIVERY.md`（轮13/14 入时间线、commit 25、测试 269）、`CHANGELOG.md`（补轮12/13/14 条目）、`REPORTS_INDEX.md`（本文件）
- 本轮复跑数据：`.audit/e2e-results.json`（主旅程 48 步）、`.audit/e2e-shots/`

## 轮14 — 性能极限 + 打磨（2026-08-10）
- `PERF3_REPORT.md` — vendor 拆分（发版重下 -74%）、上传图片压缩（-87.4%）、API 瘦身契约、404 页/标题打磨；修上传全挂 P0（ImageBitmap 顺序）
- 截图：`.audit/r14_shots/`（404-desktop/404-mobile）

## 轮13 — 功能增量 5 项（2026-08-10）
- `FEATURES_REPORT.md` — 复制活动 / 礼物墙分享文案 / 心愿清单（迁移 v12 + 隐私门控）/ 截止提醒横幅 / 列表 X/N 人；pytest 265（+8）
- 截图：`.audit/r13_shots/`（01–08.webp）

## 轮12 — 收官总报告（2026-08-10）
- `HACKATHON_DELIVERY.md`（项目根）+ `DELIVERY_CHECK.md` — 全量核对记录（pytest 258 / E2E 48/48 / CI 5 连绿）

## 轮7 — 最终回归 + 体验复核（2026-08-10）
- `FINAL_REPORT.md` — 全量回归 / 主旅程复测 / 视觉终审 / 遗漏扫描汇总（pytest 248 全绿、E2E 48/48、CI 3 连绿）
- 本轮截图与数据：
  - `.audit/final-shots/` — 6 核心页面终审截图（01-login ~ 06-create）+ `.txt` 视觉评审
  - `.audit/e2e-shots/` — 主旅程 48 步截图（本轮重跑生成）

## 轮6 — 浏览器兼容矩阵（2026-08-09）
- `BROWSER_REPORT.md` — Chrome/Edge 桌面+移动 4 矩阵回归
- `xbrowser_e2e.mjs` + `xbrowser_results.json` + `xbrowser-shots/`

## 轮5 — i18n / 移动端深查 / 无障碍（2026-08-09）
- `I18N_SEED_REPORT.md` — i18n 架构 + 演示种子数据
- `MOBILE2_REPORT.md` — 移动端亮/暗色复核（`mobile2-shots/`）
- `A11Y_DESKTOP_REPORT.md` — 桌面无障碍（a11y_scan.mjs、keyboard_walk.mjs、layout_assert.mjs、desktop_shots.mjs + `desktop-shots/`）

## 轮4 — 压测 / 边界 / 运维（2026-08-09）
- `STRESS_REPORT.md` — 并发压测（stress_test.py）
- `EDGE_REPORT.md` — 边界用例 E2E（e2e_edge_cases.mjs、`e2e-edge-shots/`）
- `OPS_REPORT.md` — 运维/可观测性

## 轮3 — 稳定性 / 部署 / 主旅程（2026-08-09）
- `STABILITY_REPORT.md` — 稳定性
- 部署：`DEPLOY.md`（项目根，非 .audit）
- `JOURNEY_REPORT.md` — 主旅程专项

## 轮2 — UX / 性能（2026-08-09）
- `UX_REPORT.md` — UX 体验审计（ux_audit*.mjs、ux_shots 脚本与 `ux-shots/`）
- `PERF_REPORT.md` — 性能

## 轮1 — E2E / 安全（2026-08-09）
- `E2E_REPORT.md` — 功能 E2E 48 步 + 视觉审核（e2e_user_journey.mjs，`visual-review/` 文本评审）
- `SECURITY_REPORT.md` — 安全审计

---

## 支撑数据（非报告，供复现）
- 测试：`tests/`（pytest，269 用例）；`stress_test.py`（压测脚本）
- 脚本：`.audit/*.mjs`（puppeteer E2E/截图/扫描）、`/tmp/analyze_shot.py`（mimo-v2.5 视觉评审）
- 截图目录：`e2e-shots/`、`e2e-edge-shots/`、`ux-shots/`、`mobile2-shots/`、`desktop-shots/`、`xbrowser-shots/`、`final-shots/`
