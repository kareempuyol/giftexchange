# REPORTS_INDEX.md — 审计报告清单

项目：giftexchange（hackathon 轮1–轮7，omp 执行）
更新：2026-08-10（轮7 最终回归）

全部报告位于 `.audit/`，按轮次排列：

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
- 测试：`tests/`（pytest，248 用例）；`stress_test.py`（压测脚本）
- 脚本：`.audit/*.mjs`（puppeteer E2E/截图/扫描）、`/tmp/analyze_shot.py`（mimo-v2.5 视觉评审）
- 截图目录：`e2e-shots/`、`e2e-edge-shots/`、`ux-shots/`、`mobile2-shots/`、`desktop-shots/`、`xbrowser-shots/`、`final-shots/`
