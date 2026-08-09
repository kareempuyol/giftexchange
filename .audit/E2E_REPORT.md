# E2E 用户全旅程测试报告

- 日期：2026-08-09
- 视口：390×844（移动端）
- 服务：http://127.0.0.1:8080（本地，build 后重启）
- 脚本：`.audit/e2e_user_journey.mjs`（puppeteer-core + 本地 Chrome，3 个独立 context = 3 个用户）
- 截图：`.audit/e2e-shots/`（39 张，编号前缀）
- 视觉审核：mimo-v2.5（`python3 /tmp/analyze_shot.py`），结果存 `.audit/visual-review/`
- 结果：**E2E 48/48 通过（0 缺陷）**、**pytest 181 全绿**、build + 重启 + health OK

## 一、E2E 旅程覆盖

| # | 步骤 | 断言 | 结果 |
|---|------|------|------|
| 1 | 注册新用户 → 自动登录 | 跳转 /events、显示用户名 | ✅ |
| 2 | 创建活动（标题/预算/截止/公开）→ 详情页 | 短码可见、标题正确、组织者加入 | ✅ |
| 3 | 复制邀请链接 | 反馈 toast（已复制/链接回退） | ✅ |
| 4 | 游客 B（新 context）打开邀请链接 → 落地页 → 登录页注册 → 回跳加入 | 落地页、from 参数、回跳、加入 | ✅ |
| 5 | 游客 C 同法加入 | 3 名参与者 | ✅ |
| 6 | 抽签 | 抽签完成、状态已抽签 | ✅ |
| 7 | 各自看到「我的送礼任务」+ 送礼对象 | A/B/C 三端 | ✅ |
| 8 | B 发货（快递公司/单号/悄悄话） | 发货信息已保存 | ✅ |
| 9 | 三人晒图（评分+评价，仅文字×2、公开照片×1） | 晒图成功 | ✅ |
| 10 | 礼物墙解锁 → 点击揭晓 → 高光海报 | 3/3 解锁、海报弹窗 | ✅ |
| 11 | 个人中心：改昵称→Header 立即更新；传头像→Header 头像更新；地址/收件人/偏好保存 | 4 项断言 | ✅ |
| 12 | 改密码 → 退出 → 旧密码失败 → 新密码成功 | 3 项断言 | ✅ |
| 13 | 通知铃铛：未读角标 → 全部已读 → 清空已读 | 4 项断言 | ✅ |
| 14 | 归档 → 列表消失 → 归档 tab 恢复 → 恢复 | 5 项断言 | ✅ |

测试账号（本轮）：`e2e_alice_mslziob9 / Alice123`（组织者，密码改为 Alice1234）、`e2e_bob_mslziob9 / Bob12345`、`e2e_carol_mslziob9 / Carol123`；活动短码 `AW9BCN`。

## 二、缺陷清单（发现 → 修复）

| 严重度 | 发现方式 | 截图 | 根因 | 修复 | 状态 |
|--------|----------|------|------|------|------|
| P1 | E2E 断言失败 | `07-07-guest-login-with-from.png` | 登录页「立即注册」链接硬编码 `/register`，丢失 `?from=` 参数 → 游客经邀请落地 → 登录页 → 注册后回到 /events 而非活动页 | `LoginPage.tsx`：注册链接透传 from 参数 | ✅ 修复后 B 回跳活动页断言通过 |
| P1 | E2E 断言失败 | `23-profile-nickname-saved.png`、`24-profile-avatar-saved.png` | ProfilePage 保存昵称/头像只更新本地 state，AuthContext.user 不同步 → Header 不更新（用户改完看不到变化） | `AuthContext.tsx` 新增 `updateUser`；`ProfilePage.tsx` saveProfile/uploadAvatar 调用同步 | ✅ 修复后「Header 立即更新」断言通过 |
| P1 | 视觉审核 | `05-alice-joined.png`、`09-b-joined.png`、`37-events-mine-after-archive.png` | `.toast-container` 定位 `top:24px`，悬浮在 sticky 顶栏之上，遮挡品牌、「+创建活动」「退出」等核心入口 | `global.css`：toast 改为底部弹出（`bottom: var(--gift-space-xl)`） | ✅ 复审确认无遮挡 |
| P2 | 视觉审核 | `09-b-joined.png` | 「你已加入，等待组织者抽签」同时渲染在流程步骤条 hint 与独立 ✅ 段落两处 | `EventDetailPage.tsx`：删除重复的独立段落（保留步骤条 hint） | ✅ 复审确认无重复文案 |
| P2 | 视觉审核 | `17-b-shipment-form.png` | 发货表单「快递公司（选填）」「快递单号 *」并排 flex，390px 下 placeholder 截断显示半个字 | `EventDetailPage.tsx`：行加 `flexWrap: 'wrap'`，输入框 `flex: 1 1 160px`，窄屏自动换行 | ✅ 复审确认无截断 |
| P2 | 视觉审核 | `02-events-home.png`、`37-events-mine-after-archive.png` | 活动列表页 page-header 自带「退出」按钮，与全局 Header 的「退出」重复（两个退出入口） | `EventsPage.tsx`：删除页头冗余退出按钮（Header 已有） | ✅ 复审确认仅一个退出入口 |
| P2 | 视觉审核 | `25-profile-before-edit.png` | 个人资料「手机号」字段 placeholder 为「收礼人电话」，个人资料语境下语义混淆 | `ProfilePage.tsx`：placeholder 改为「手机号」 | ✅ |

### 观察项（未改，记录供产品决策）

- **创建者不自动加入活动**：后端 `event_routes.py` 明确"组织者自己加入"为预期流程（加入不通知自己）。首次用户创建活动后可能误以为自己已在局内（详情页仍显示「加入这个活动」）。建议产品侧考虑创建时自动加入，属行为变更，需后端 + 测试协同，本次未动。
- **「物流查询暂不可用，稍后自动更新」**（`gift_routes.py:446`）：KDNiao 未配置/查询失败时的静默降级文案，有 `test_kdniao.py` 覆盖。文案对用户稍显"永不再更新"，建议接入物流后自然消失。
- **品牌标题重复**：「互送礼物」在全局 Header 与活动列表页 h1 同时出现（视觉审核多次提及），属品牌层级设计取舍。
- **风格类 P3**：emoji 图标风格不一、进度条节点间距、注销账号按钮红色与品牌色接近等，均为主观设计项。

## 三、视觉审核汇总（mimo-v2.5，39 张全量）

- **布局**：修复后全量复审无布局错乱/文字重叠/元素溢出（每张均确认）。
- **入口可见性**：各页核心操作按钮（加入/抽签/发货/晒图/解锁/海报/保存/修改密码/归档）全部可见可点。
- **测试数据暴露**：`e2e_*` 用户名、`@test.com` 邮箱、`13800138000` 电话、`2026/8/9` 日期为测试产物（本轮 E2E 数据），非产品缺陷。
- 其余发现均为 P3 风格建议（详见各图 `visual-review/*.txt`）。

## 四、修复后全旅程截图（39 张）

```
01-register-alice         02-events-home             03-create-form-filled
04-event-detail-created   05-alice-joined            05-invite-copy-toast
06-guest-landing          07-guest-login-with-from   08-b-joined
09-c-joined               10-alice-3-participants    11-draw-confirm-modal
12-alice-after-draw       13-A/B/C-my-task（×3）      14-b-shipment-form
15-b-shipped              16-alice-posted-text       17-b-posted-text
18-c-posted-photo         19-gift-wall-unlocked      20-gift-wall-revealed
21-highlight-poster       22-profile-before-edit     23-profile-nickname-saved
24-profile-avatar-saved   25-profile-contact-saved   26-password-change-form
27-logout-login-page      28-login-old-password-fail 29-login-new-password-ok
30-notification-bell      31-notification-all-read   32-notification-cleared
33-archive-confirm        34-events-mine-after-archive 35-events-archived-tab
36-events-mine-restored
```

## 五、验证结果

| 项 | 结果 |
|----|------|
| E2E 全旅程 | **48/48 通过，0 缺陷**（最终轮 `runAt=2026-08-09T15:57Z`） |
| pytest | **181 passed**（`python3 -m pytest tests`） |
| 前端构建 | `npm run build` 成功，产物已同步 `wxcloudrun/static/` + `templates/index.html` |
| 服务 | kill -9 兜底重启后 `GET /api/health` → `{"code":0,...}` |

## 六、改动文件

- `frontend/src/pages/LoginPage.tsx` — 立即注册透传 from（P1）
- `frontend/src/auth/AuthContext.tsx` — 新增 updateUser（P1）
- `frontend/src/pages/ProfilePage.tsx` — 保存后同步 Header；手机号 placeholder（P1/P2）
- `frontend/src/styles/global.css` — toast 底部弹出（P1）
- `frontend/src/pages/EventDetailPage.tsx` — 删重复文案；发货表单窄屏换行（P2）
- `frontend/src/pages/EventsPage.tsx` — 删冗余退出按钮（P2）
- `.audit/e2e_user_journey.mjs`、`.audit/e2e-shots/`、`.audit/visual-review/`、`.audit/e2e-results.json` — 新增测试资产
- `wxcloudrun/static/*`、`templates/index.html` — build 产物（自动更新）

未 commit；未触碰数据库历史/迁移。
