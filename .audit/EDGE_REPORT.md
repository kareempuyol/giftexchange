# 异常路径 E2E 报告（hackathon 波次6）

日期：2026-08-10　视口：390×844（移动端）　脚本：`.audit/e2e_edge_cases.mjs`　截图：`.audit/e2e-edge-shots/`

## 结论

- **33/33 断言通过，0 缺陷，P0（白屏/崩溃/数据错误）清零**
- 发现并修复 6 处异常路径缺陷（见「修复清单」），其中 1 处为后端逻辑漏洞（截止后仍可加入）
- `pytest tests -q`：228 通过（含新增 `test_edge_cases.py` 7 条）；`npm run build` 通过；`py_compile` 通过

## 场景结果表

| # | 场景 | 断言结果 | 截图 |
|---|------|---------|------|
| 1 | 重复加入 | PASS：竞态下二次提交 → 弹窗内提示「你已加入该活动」，不崩溃 | `01-s1-dup-join-error.png` |
| 2 | 满员拒绝（maxParticipants=2，第 3 人） | PASS：后端 400「活动人数已满」→ 弹窗内中文提示 | `02-s2-full-error.png` |
| 3 | 截止后加入（drawDate 已过） | PASS：后端 400「活动已截止报名」→ 弹窗内中文提示 | `03-s3-deadline-join-error.png` |
| 4 | 未加入访问礼物墙 | PASS：非参与者 → 403「无权访问」错误页（非白屏） | `04-s4-wall-403.png` |
| 5 | 未抽签访问 my-match | PASS：open 态 my-match 200 无数据；详情页友好提示「等待组织者抽签」 | `05-s5-my-match-open-hint.png` |
| 6 | 并发抽签（Promise.all ×2） | PASS：恰一个 200 成功、恰一个 409「已抽签」 | `06-s6-concurrent-draw.png` |
| 7 | 晒图评分边界 | PASS：rating=0/6 → 400「评分需在 1-5 之间」；空评价 → 400「请填写评价内容」；UI 0 星 → toast 拦截 | `07-s7-rating-zero-toast.png` |
| 8 | 物流单号边界 | PASS：空单号 → 400「请填写快递单号」；121 字符 → 400「快递单号过长」；UI 空单号 → toast 拦截 | `08-s8-empty-tracking-toast.png` |
| 9 | 游客访问受限页 | PASS：/events/new、/profile 未登录 → `/login?from=…` 带 from；登录后回跳原页 | `09-s9-guest-events-new-redirect.png` `10-s9-guest-profile-redirect.png` `11-s9-login-return-profile.png` |
| 10 | 断网降级 | PASS：断网后操作 → toast「网络连接失败，请检查网络后重试」，页面非白屏/非无限 loading | `12-s10-offline-toast.png` |
| 11 | 404 活动 | PASS：无效短码/无效 uuid → 友好 404 页「活动不存在」+「回我的活动」 | `13-s11-notfound-shortcode.png` `14-s11-notfound-uuid.png` |
| 12 | 归档后访问 | PASS：归档成功回列表；直接 URL 详情仍可看、无报错（设计如此） | `15-s12-archived-detail-ok.png` |
| 13 | 注销用户旧会话 | PASS：注销后旧 token 调 API → 401「账号已注销」；访问受限页 → 跳 `/login?from=profile`，本地 token 清除 | `16-s13-deactivated-session-redirect.png` |
| 14 | 通知角标边界 | PASS：100 条未读 → 角标显示「9+」不溢出 | `17-s14-notif-badge-9plus.png` |

## 修复清单

| 严重度 | 位置 | 缺陷 | 修复 |
|--------|------|------|------|
| P0 | `wxcloudrun/event_routes.py` join_event | **截止后仍可加入**：open 状态 + drawDate 已过时 join 只查 `status != 'open'`，截止日形同虚设 | 增加 `draw_deadline_passed(event)` 判断 → 400「活动已截止报名」 |
| P1 | `wxcloudrun/gift_routes.py` received-gift | 空评价被接受 → 出现「已晒图成功但礼物墙不计 posted」的割裂状态 | 增加非空评价校验 → 400「请填写评价内容」；前端 submit 同步拦截（toast） |
| P1 | `wxcloudrun/helpers.py` fetch_event | 404 返回英文「Event not found」，游客/用户看到英文报错 | 改为中文「活动不存在或已失效」，join 路由 404 哨兵同步更新 |
| P1 | `frontend/src/pages/EventDetailPage.tsx` | 404 与普通加载失败共用「加载失败」页 | 按 `ApiError.status===404` 分流：标题「活动不存在」+ 提示 + 「回我的活动」按钮 |
| P1 | `frontend/src/api/client.ts` + `auth/AuthContext.tsx` | 401 只清 token 不跳转，旧会话页面停留在受限内容 | 401 广播 `gift:unauthorized` → AuthContext 置空 user → RequireAuth 自动跳 `/login?from=…`（保留回跳） |
| P1 | `frontend/src/pages/EventDetailPage.tsx` ReceivedGiftSection | 空评价可提交（与后端契约不一致） | 提交前校验评价非空，toast「请填写评价内容」 |

## 验证

- E2E：`.audit/e2e_edge_cases.mjs` 33/33 断言通过，结果 JSON：`.audit/e2e-edge-results.json`
- 回归：`pytest tests -q` 全绿（228 通过），新增 `tests/test_edge_cases.py`（7 条：截止后加入/截止前可加入/空评价 400/评分越界 400/三种 404）
- 契约变更同步：`tests/test_gift_privacy.py` 非法 privacy 用例补齐评价字段（评价已为新必填契约）
- 构建：`npm run build` 通过，Flask 已重启，`/` 200，served bundle = `index-C9dqMsiG.js`
- 未 commit
