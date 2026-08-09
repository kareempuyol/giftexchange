# giftexchange — 项目约定（omp 读取）

互送礼物 Web 应用。Flask + SQLite/MySQL 双引擎后端 + React 18/Vite/TS 前端。

## 架构红线（违反 = 打回）

1. **API 纯 REST+JSON**：所有接口返回 `ok(data, msg)` / `fail(msg, code)` 结构（helpers.py 定义），不用模板渲染业务页面。
2. **双引擎 SQL**：SQL 必须是 MySQL + SQLite 都能跑的通用语法（参数化 `?` 占位、`CURRENT_TIMESTAMP`、`IF NOT EXISTS`）。加列用 migrations.py 的 MIGRATIONS 列表（版本号 +1），不直接改 CREATE TABLE 历史。
3. **JWT 认证**：`login_required` 装饰器（helpers.py），不自己解析 token。users 表预留 openid/unionid/session_key 列（只加列，微信登录前不实现）。
4. **图片先传后引用**：文件走 `/api/upload` → `data/uploads/` → 字段存 URL。storage.py 抽象（魔数校验+5MB+扩展名白名单+防路径穿越）。不往 DB 存 base64 新数据（旧数据兼容不动）。
5. **域名不硬编码**：前端用相对路径 `/api/...`，后端用 `request.host_url`。
6. **Design Tokens**：前端颜色/间距/动效用 CSS 变量（`--gift-*`），禁硬编码色值。品牌色 `#E8553D`、背景 `#FFFAF5`。

## 代码组织

- 后端已按域拆分：`auth_routes.py` / `event_routes.py` / `draw_routes.py` / `gift_routes.py` / `notify_routes.py` / `site_routes.py` + `helpers.py`（共享）+ `migrations.py`（版本化迁移）+ `storage.py`（存储抽象）+ `notify.py` / `jobs.py`（通知/定时）+ `observability.py`（request_id 日志）。
- **改路由去对应模块，不新建重复逻辑**。跨模块共享函数从 helpers.py import。
- 新增功能先写 tests/ 下的 pytest（Flask 双引擎可测），跑 `pytest tests -q` 全绿再交付。

## 前端

- `npm run build`（在 frontend/ 下）→ 产物 `wxcloudrun/static/` + 自动 cp 到 `wxcloudrun/templates/index.html`。
- **build 后必须重启 Flask**（模板缓存引用旧 JS → 白屏，血泪坑）。
- 移动端 375px 必须不破版：flex 里 `.btn{width:100%}` 会撑爆兄弟元素。

## 验证纪律

- 服务 `127.0.0.1:8080`，重启：`lsof -ti :8080 | xargs kill` 后 `bash /tmp/gift_run.sh`（后台）。
- 测试账号：`verify_user` / `Verify123`（有历史数据）。
- 数据库：`data/gift_exchange.db`（SQLite，WAL 模式）。
- 交付前跑：pytest 全绿 + py_compile + 浏览器实测（若改前端）。
