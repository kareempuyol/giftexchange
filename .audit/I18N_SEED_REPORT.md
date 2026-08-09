# I18N_SEED_REPORT — i18n 架构 + 演示种子数据（hackathon 轮5）

日期：2026-08-10 · 域：frontend/src/**、scripts/**、README.md/DEPLOY.md（小）
未触碰：wxcloudrun/**、tests/**（其他任务域）· 未 commit

---

## 任务 A：轻量 i18n 架构

### 交付物

**`frontend/src/i18n.ts`（新增，模块级，不引 react-i18next）**

- `t(key, vars?)`：key 即中文原文（key = source），zh 模式直接返回原文；en 模式查 `en` 字典，
  未收录的 key 回退原文 —— 存量中文 UI 天然不受影响，无翻译时永不缺文案。
- `zhKeys`：zh 公共串登记表（38 条：保存/取消/删除/确认/加载中/网络错误/登录/注册/通知等）。
- `en` 字典：38 条公共串翻译（Save/Cancel/Delete/Confirm/Loading…/Network error… 等）。
- 语言检测：`localStorage('gift_locale')` 可覆写（'zh'/'en'）→ 否则 `navigator.language`
  以 'en' 开头判定 en，其余 zh（zh 为默认，中文 UI 保持默认）。
- `document.documentElement.lang` 同步（en / zh-CN）。
- `useLocale()`（useSyncExternalStore）：setLocale 后订阅组件自动重渲染；模块级 locale 变化
  由 listener 集合通知（运行时集合，用 Set 语义正确）。

### 示范迁移（~40 处，超出要求的 ~10 处下限）

| 文件 | 迁移内容 |
|---|---|
| `components/Header.tsx` | 品牌/导航/通知铃铛 aria/通知面板/全部已读/清空已读/暂无通知/标记已读：{title}（插值）/查看活动 ↗/个人资料/退出/操作失败 toast 兜底 |
| `pages/LoginPage.tsx` | 品牌/标语/登录/用户名/密码/显示隐藏密码/忘记密码/必填校验/登录中/登录失败/还没有账号/立即注册 |
| `api/client.ts` | 网络层错误（Toast 公共文案）：请求已取消/请求超时/网络连接失败/请求失败/上传失败/服务响应异常 ({status})（插值） |

其余组件（App/Dashboard/CreateEvent/Profile/EventDetail/GiftWall/Events/ForgotPassword/Register/
SharePoster/PosterModal/ImageUpload/ErrorBoundary）保留中文，文件头已加注释：
「文案暂未接入 i18n（示范迁移仅 Header/登录页/Toast 公共文案）：后续按 i18n.ts 迁移指南接入」。

### 验收 1 验证：t() 可用 / en 检测生效 / 未翻译 key 回退

**t() 语义**（esbuild 打包真实 `i18n.ts` 后在 node 实测）：

| 调用 | 结果 |
|---|---|
| zh 默认 `t('保存')` | `保存` |
| zh 插值 `t('标记已读：{title}', {title:'抽签结果'})` | `标记已读：抽签结果` |
| en `t('保存')` / `t('加载中…')` | `Save` / `Loading…` |
| en 插值 | `Mark as read: Draw` |
| **未翻译 key** `t('这个 key 不在字典里')` | **回退原文：`这个 key 不在字典里`** |
| 插值缺参 `t('标记已读：{title}', {})` | 保留 `{title}` 占位 |

**浏览器实测（headless Chromium）**：

- `--lang=en-US` 启动 → `navigator.language=en-US`，`document.documentElement.lang=en`，
  登录页全英文：Gift Exchange / Exchange surprises with friends / Log in / Username / Password /
  Forgot password? / Don't have an account? / Sign up now。
- 同浏览器登录 demo_alice 后 Header 英文：`🎁 Gift Exchange`、`My events`、`+ Create`、
  `Notifications`（aria）、`Log out`。
- `localStorage.setItem('gift_locale','zh')` 覆写（navigator 仍 en-US）→ 全部回到中文
  （互送礼物/我的活动/+ 创建/退出，lang=zh-CN）→ 覆写优先级正确。
- 无覆写、en-US 浏览器 → 英文；`gift_locale=zh` → 中文（zh 默认路径 + 覆写均覆盖）。

---

## 任务 B：演示种子数据

### 交付物

**`scripts/seed_demo.py`（新增，幂等可重复执行）**

- 演示用户 `demo_alice/demo_bob/demo_carol`（密码 `Demo1234`，昵称 爱丽丝/鲍勃/卡罗尔）：
  按 username 查重，已存在则跳过（不覆盖密码/资料）。
- 示例活动「圣诞礼物交换 🎄」：公开、3 人、已抽签（status=drawn）、match_visibility=public
  （抽签结果全员可见）、短码（generate_short_code 生成）、预算 100。
- 3 条 match：1 条带完整物流（顺丰/单号/已签收摘要），2 条当面送达 → **部分发货**；
  3 条全部已收 + 已晒图 → **礼物墙解锁**；晒图覆盖隐私三模式
  （公开照片 / 模糊照片 / 仅文字 text），含评分 + 评价 + 照片。
- 3 个礼物墙点赞（互相点赞）。
- 10 条通知（抽签结果/发货/晒图/礼物墙解锁；已读未读混合，created_at 时间线错开）：
  走 `wxcloudrun.notify.notify()` 统一入口，再按 id 回填 read_at/created_at
  （避免 MySQL 1093「UPDATE 同表子查询」限制，双引擎通用）。
- 照片遵循项目红线「先传后引用」：zlib 手写合法 PNG（无 PIL 依赖）→ `storage.save(folder='')`
  平铺落盘 `data/uploads/<uuid>.png` → DB 存 `/uploads/<uuid>.png` URL，与 `/api/upload`
  同一约定（曾误用 `save_image()` 嵌套到 uploads/uploads/ 导致 404，已修复为平铺 + 手工拼
  `/uploads/` 前缀）。
- 幂等：活动按固定 code（`demo-christmas-2026`）查重，已存在则整个活动（参与者/match/通知）跳过；
  全部写入在单个 `with DB()` 事务内，失败整体回滚。

**文档**：README.md / DEPLOY.md 新增「演示数据」小节（`python3 scripts/seed_demo.py`，
含账号、内容清单、幂等说明）。

### 验收 2 验证：跑两遍幂等 + 新用户登录有内容

**幂等**（真实库 + 临时空库各验证）：

```
第 1 次：创建用户 3 / 活动 / 3 参与者 / 2 张照片 / 3 match / 3 点赞 / 10 通知
第 2 次：全部 [skip]（用户已存在 / 示例活动已存在）→ 数据零重复
```

**登录 demo_alice（API 实测）**：

- `GET /api/events/joined` → 返回 圣诞礼物交换 🎄（drawn、public、participantCount=3）。
- `GET /api/notifications` → 4 条（unread=1，已读/未读混合）。
- `GET /api/events/demo-christmas-2026/gift-wall` → `unlocked: true, posted: 3/3`，
  3 个 item（rating 5、review、photoUrl 指向 /uploads/ 真实文件、likeCount=1）。
- `GET /api/events/demo-christmas-2026/matches`（demo_bob 视角，match_visibility=public）→ 3 条可见。
- `/uploads/<uuid>.png` 两张均 `200 image/png`（180B，PNG 魔数合法）。

**浏览器实测（demo_alice 登录后访问礼物墙）**：解锁态（无进度锁卡，显示 生成高光海报/再开一局），
3 张卡片揭晓后显示 爱丽丝→鲍勃（照片+5 星+评价）、鲍勃→卡罗尔（📝 文字心意，无照片）、
卡罗尔→爱丽丝（照片+5 星），点赞计数 1。

---

## 验收 3：build + pytest + health

| 项 | 结果 |
|---|---|
| `npm run build`（frontend/） | ✅ 142 modules，产物 → wxcloudrun/static + templates/index.html |
| Flask 重启（lsof kill + /tmp/gift_run.sh） | ✅ 模板缓存刷新 |
| `GET /api/health` | ✅ `{"code":0,"data":{"status":"ok",...},"message":"ok"}` 200 |
| `pytest tests -q`（两轮） | ✅ 230 passed（改动前后均全绿） |
| `py_compile scripts/seed_demo.py wxcloudrun/*.py` | ✅ |

---

## 备注 / 风险

- i18n 字典目前 38 条公共串，全部命中示范迁移面；其余页面保留中文属本轮约定范围
  （注释已标注未来迁移路径），后续按 `i18n.ts` 头部迁移指南接入即可。
- seed 脚本照片为 64×64 纯色占位 PNG（无 PIL 依赖，zlib/struct 手写），演示视觉足够；
  生产演示如需真实照片，可替换 `_seed_photo` 为读取本地图片文件。
- seed 固定活动 code `demo-christmas-2026`：与真实活动 code（uuid）冲突概率可忽略，
  且按 code 查重保证幂等。
- `notify()` 受用户通知偏好过滤（demo 用户默认全开，正常写入 10 条；若被过滤会 skip 并计数不变）。
