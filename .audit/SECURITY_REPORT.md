# SECURITY_REPORT.md — giftexchange 安全审计（hackathon 波次1-A）

审计时间：2026-08-10　审计方式：代码走查 + 真跑 API（3 用户越权矩阵 + 漏洞利用复现）　基线：181 tests 全绿

结论速览：**2 个 P0/P1 高危已修复、2 个 P1 中危已修复、2 个 P2 已修复；pytest 195 全绿**。
剩余为部署配置项（代码无法修复，见 §8）。

---

## 1. 认证与会话

| 检查项 | 结论 | 证据 |
|---|---|---|
| JWT secret 来源 | ✅ 安全（fail-closed） | `wxcloudrun/auth.py:_secret()` 读 `JWT_SECRET` 环境变量，缺失即 `RuntimeError`，无默认值/无硬编码兜底。dev 启动脚本 `/tmp/gift_run.sh` 用 `gift-local-dev-2026`（仅本地） |
| token 过期 | ✅ | HS256，`exp` 7 天（`TOKEN_TTL_SECONDS`），`verify_token` 校验签名（hmac.compare_digest）+ 过期拒绝；无 `alg=none` 降级（不解析 header alg） |
| login_required 覆盖 | ✅ | 逐路由核对：所有敏感路由均挂 `@login_required`/`@admin_required`（§2 表）；仅公开路由无鉴权：register/login/forgot/reset/`preview`（邀请落地页，有意为之）/`health`/`uploads` |
| deactivated 检查 | ✅ | `login_required` 每次请求查 `users.deactivated`，注销后旧 token 立即 401（实测：注销后 `/api/auth/me` → 401「账号已注销」，原密码登录 → 401）；注销匿名化用户名/邮箱/密码 |
| 登录限速 | ❌→✅ 已修复（P1） | **原漏洞**：IP 取自 `X-Forwarded-For` 首段（可伪造），实测伪造 XFF + 换用户名 60 次凭据填充全部 401、永不 429；同一真实 IP 21 次 → 429（第 21 次）。**修复**：`helpers.client_ip()` 默认只用 `request.remote_addr`，仅当 `TRUSTED_PROXIES` 白名单（env，逗号分隔）包含直连来源时才信任 XFF。修复后实测：伪造 XFF 换用户名 60 次 → 第 21 次 429。用户名限速（10 次/15min）不受影响 |
| 找回密码限速 | ✅ 5 次/小时/IP+账号（原 XFF 伪造问题随 client_ip 修复一并解决） |

## 2. 授权矩阵（3 用户真跑 API，非猜测）

用户：`org_*`（创建者+参与者）、`part_*`（参与者）、`out_*`（无关普通用户）、`four_*`（第 3 参与者，凑抽签）。事件：私密（`isPublic=false, matchVisibility=private`），3 人抽签完成。

| 场景 | 期望 | 修复前 | 修复后 |
|---|---|---|---|
| 普通用户访问他人**私密**活动详情 | 403/404 | ❌ **200**（泄露 shortCode/excludedPairs/ownerName/participantCount/flowState） | ✅ 403 |
| 普通用户访问他人参与者列表 | 403/404 | ❌ **200**（泄露全部成员 username/displayName/avatar/contactComplete/status） | ✅ 403 |
| 普通用户访问他人匹配列表 | 403 | ✅ 403 | ✅ 403 |
| 普通用户访问他人仪表盘 | 403 | ✅ 403 | ✅ 403 |
| 参与者调 draw / redraw / archive / remind / reset-short-code / edit / delete | 403 | ✅ 全部 403 | ✅ 403 |
| 非参与者读他人 my-match | 隔离 | ✅ ok(null)，无数据 | ✅ |
| 非参与者读他人 gift-wall | 403 | ✅ 403 | ✅ 403 |
| 非参与者改他人晒图（PUT/DELETE received-gift） | 拒绝 | ✅ 403 / 403 | ✅ |
| 非参与者改他人物流/note | 拒绝 | ✅ 403 | ✅ |
| 非参与者点赞/取消点赞他人活动 | 拒绝 | ✅ 403 | ✅ |
| 创建者改参与者晒图/物流（越权） | 拒绝 | ✅ 400「未找到对应的送礼任务」（UPDATE 带 receiver_id/giver_id 作用域，rowcount=0，数据未动） | ✅ 同左 |
| 参与者本人填物流/晒图（正向控制组） | 200 | ✅ 200 | ✅ 200 |
| 公开活动详情/参与者列表（任意登录用户） | 200（设计如此） | ✅ | ✅ |
| 通知列表/偏好：只返回/只修改自己的 | ✅ | ✅ 实测 items=0（无他人通知）、U2 偏好不受 U3 修改影响 | ✅ |

**修复内容**（P1）：`helpers.event_visible_to()` — 公开活动所有登录用户可见；私密活动仅创建者与参与者。应用于 `event_detail` 与 `participants`。私密活动详情对无关用户 403（与 preview 的邀请落地语义不冲突：preview 面向持有邀请链接的访客，属有意设计）。

## 3. 注入与数据校验

| 检查项 | 结论 | 证据 |
|---|---|---|
| SQL 注入 | ✅ | 全部 `db.execute/get/all` 走 `?` 参数化（MySQL 由 `DB._sql` 转 `%s`）。`public_events` 的 WHERE 由常量列表拼接 + params；`gift_wall` 的 `IN (?,?...)` 由 ID 列表生成占位符；`edit_event` 的列名来自白名单字段 dict；`database.py` 遗留 `ALTER TABLE ... ADD COLUMN {name}` 的 name 来自硬编码常量列表。无用户输入进 SQL 文本 |
| XSS | ✅ | `frontend/src` 无 `innerHTML` / `dangerouslySetInnerHTML` / `document.write` / `eval`（grep 零命中）；React 默认转义 |
| 短码暴力枚举 | ✅（残余风险 P2） | 32 字母表（去 0/O/1/I）× 6 位 ≈ 10.7 亿组合，盲猜不可行；同 IP 1 小时 10 次失败 → 429（用 `request.remote_addr`，不可伪造）。多用户多 IP 轮换可分摊计数（单实例内存滑动窗口的固有限制，代码注释已声明需 Redis）。登录态用户同样受限速约束 |
| 登录暴力破解 | ✅（残余 P3） | 用户名限速 10 次/15min 不可绕（实测同用户名多 IP 15 次 → 429）；密码策略 ≥6 位且含字母+数字（建议后续提为 ≥8 位） |

## 4. 上传安全

| 检查项 | 结论 | 证据 |
|---|---|---|
| 魔数校验 | ✅ | `site_routes.check_image_magic`：PNG/JPEG/GIF/WEBP 文件头校验。实测：PHP 内容伪造成 `.png` → 400「不是有效图片」；SVG 内容伪造成 `.png` → 400 |
| 扩展名白名单 | ✅ | png/jpg/jpeg/gif/webp。实测 `.php` → 400 |
| 大小限制 | ✅ | 5MB。实测 5MB+10 字节 → 400 |
| 路径穿越 | ✅ | 文件名仅用于取扩展名，落盘名 `uuid4().hex.<ext>`；`storage._validate_key` 拒绝 `..`/绝对路径/非法字符；读取端 `send_from_directory` safe_join。实测 `../../evil.png` 落盘为扁平 uuid 名（uploads 目录无穿越产物） |
| 脚本执行 | ✅ | 只能以图片扩展名落盘 → 以 image/* 服务；`X-Content-Type-Options: nosniff`（本次新增）防 MIME 嗅探；无 `.php/.html/.svg` 路径 |
| content_type 白名单 | ✅ | 与扩展名一一对应 |

## 5. 敏感信息泄露

| 检查项 | 结论 | 证据 |
|---|---|---|
| participants 接口泄露手机/地址 | ✅ | 查询含 phone/address 但序列化只输出 `contactComplete` 布尔；修复前的问题是接口本身对无关用户开放（§2，已修） |
| my-match 收件人信息 | ✅ | 仅送礼方（giver）可见 receiver 的收件人/电话/地址/偏好；非参与者 ok(null) |
| preview 接口 | ✅ | 游客可见 title/note/budget/count/cover，无收件人/发货/地址 |
| matches 接口 | ✅ | 只输出 giver/receiver 用户名，无联系方式；私密活动仅创建者（参与者可见需 matchVisibility=public，设计如此） |
| 错误消息 | ✅ | 500 handler 统一「Internal server error」；路由异常收敛为业务消息，无堆栈/路径（实测各 400/404 响应均为业务文案） |
| /api/health | ✅ | `{status, timestamp}`，无版本/依赖信息 |
| Server 头 | ⚠️ 部署项 | `Werkzeug/3.1.8 Python/3.14.5` — 生产应换 gunicorn/waitress 并抑制版本头（见 §8） |
| 账号枚举 | ❌→✅（P2，随 P0 修复） | 原 forgot-password 对未注册账号返回 404（枚举 oracle）→ 现统一 200 无 code |

## 6. 安全头与 CORS

| 检查项 | 修复前 | 修复后（`__init__.py` after_request） |
|---|---|---|
| X-Content-Type-Options | ❌ 缺失 | ✅ `nosniff` |
| X-Frame-Options | ❌ 缺失 | ✅ `DENY` |
| Referrer-Policy | ❌ 缺失 | ✅ `strict-origin-when-cross-origin` |
| Content-Security-Policy | ❌ 缺失 | ✅ `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'`（index.html 全自托管，浏览器实测页面正常渲染、无 console 报错） |
| CORS | ⚠️ 配置值无条件回显（不匹配 Origin 也发） | ✅ 仅当请求 Origin 与配置一致（或配置为 `*`）才回显 ACAO；默认同源不发任何跨域头（实测恶意 Origin → 无 ACAO） |
| 生产 CORS 配置 | ⚠️ `container.config.json` 设 `CORS_ORIGIN="*"` | Bearer token 机制下风险可控，但建议上线前收敛为真实域名（见 §8） |

## 7. 通知与越权

| 检查项 | 结论 | 证据 |
|---|---|---|
| notifications 只返回自己的 | ✅ | `WHERE n.user_id = ?`（实测 outsider 列表为空） |
| read/clear 只动自己的 | ✅ | UPDATE/DELETE 均带 `user_id = ?` |
| preferences 只改自己的 | ✅ | `UPDATE users ... WHERE id = ?`；实测 U3 改 draw=false 不影响 U2 |

## 8. 部署前必做（代码已无法修复，需运维配置）

1. **【P1·必须】`container.config.json` envParams 无 `JWT_SECRET`** → 生产首登即 `RuntimeError`（fail-closed，不泄露但不工作）。须在环境变量中注入强随机 secret（如 `openssl rand -base64 48`）。
2. **【P1·必须】生产换 WSGI 服务器**：当前 `run.py` 用 Flask 内置 Werkzeug dev server，暴露 `Server: Werkzeug/... Python/...` 版本头；改 gunicorn/waitress。
3. **【P2】`CORS_ORIGIN` 收敛**为真实前端域名（当前 `*`）。
4. **【P2】短码限速多实例化**：内存滑动窗口单实例有效；多实例部署时按代码注释换 Redis（key: `shortcode_fail:<ip>`，TTL 1h，原子 INCR）。
5. **【P3】找回密码通道**：当前无邮件/短信通道，重置码仅落库 + 服务端 `log_event` 记录；生产必须接 SMTP（配置项已预留 smtp_*）并把 `RESET_CODE_IN_RESPONSE` 保持关闭（见修复记录 #2）。
6. **【P3】首个注册用户自动成为 admin**（`register` 中 `is_first_user`）——上线前确认运营账号先注册，或改用 ADMIN_USERNAMES/ADMIN_EMAILS 环境变量。

## 修复记录

| # | 严重级 | 文件 | 变更 |
|---|---|---|---|
| 1 | P1 | `wxcloudrun/helpers.py` | 新增 `client_ip()`：默认 `request.remote_addr`，仅 `TRUSTED_PROXIES` 白名单内的直连代理才信任 `X-Forwarded-For`（封死限速绕过） |
| 2 | P0 | `wxcloudrun/auth_routes.py` | `forgot_password`：默认响应不含重置码（防任意人重置他人密码 → 账号接管）；未注册账号统一 200 无 code（防枚举）；仅 `RESET_CODE_IN_RESPONSE=1` 演示模式返回 code；下发埋点 `password_reset_code_issued` |
| 3 | P1 | `wxcloudrun/auth_routes.py` | `login` / `forgot_password` 改用 `client_ip()`（原直取 X-Forwarded-For） |
| 4 | P1 | `wxcloudrun/helpers.py` | 新增 `event_visible_to()`：公开活动全登录用户可见；私密活动仅创建者/参与者 |
| 5 | P1 | `wxcloudrun/event_routes.py` | `event_detail`、`participants` 应用 `event_visible_to`，无关用户 403 |
| 6 | P2 | `wxcloudrun/__init__.py` | after_request 下发 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy`、`Content-Security-Policy` |
| 7 | P2 | `wxcloudrun/__init__.py` | CORS 收紧：仅 Origin 匹配配置（或配置为 `*`）时回显 ACAO，`Vary: Origin` |
| 8 | — | `tests/test_auth_reset.py` | ctx 开启演示模式（码语义测试不变）；新增 `TestSecureDefault`（默认无 code / DB 码可重置 / 未注册 200） |
| 9 | — | `tests/test_security_hardening.py`（新增） | 私密活动访问控制、XFF 伪造不可绕过 IP 限速、TRUSTED_PROXIES 白名单生效、安全头、CORS 匹配/星号/默认 |

未改动：`frontend/src/**`（另一任务在改）；未 commit；无需数据库迁移（本次无 schema 变更）。

## 验收标准对照

1. ✅ 越权矩阵全部场景真跑 API 实测（§2 表，修复前后对比）。
2. ✅ `pytest tests -q`：基线 181 → 修复后 **195 passed**（`-o addopts=''` 输出确认）；`py_compile wxcloudrun/*.py` 通过。
3. ✅ 报告完整（本文件）；服务 `127.0.0.1:8080` 已用修复后代码重启，浏览器实测首页正常渲染（CSP 未破坏前端）。
