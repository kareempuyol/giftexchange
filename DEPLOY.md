# DEPLOY.md — 生产部署指南

目标：**任何人拿到仓库 + 环境变量就能跑起来**。两种形态，任选其一：

- **A. Docker（推荐）**：`docker-compose.yml` 多阶段构建（node 构建前端 → python 跑 gunicorn），一键起。
- **B. 本机 Python 直接跑**：装依赖 + 构建前端 + gunicorn 启动（`Procfile` 同命令）。

后端入口是 Flask 应用工厂 `wxcloudrun:create_app()`（`wxcloudrun/__init__.py`），gunicorn 直接按工厂引用；迁移在启动时自动执行（见第 4 步）。

---

## 快速开始（10 步）

### 1. 获取仓库 + 前置环境
```bash
git clone <repo-url> giftexchange && cd giftexchange
# A 形态：需要 Docker（含 compose 插件）
docker --version && docker compose version
# B 形态：需要 Python 3.11+ 与 Node 18+
python3 --version && node --version
```

### 2. 安装依赖 / 准备镜像
```bash
# A 形态：构建镜像（node 阶段 npm ci 需要网络）
docker compose build
# B 形态：
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt gunicorn==22.0.0
cd frontend && npm ci && npm run build && cd ..   # 产物 → wxcloudrun/static + templates/index.html
```

### 3. 生成并配置 JWT_SECRET（必填，fail-closed）
```bash
openssl rand -hex 32
# A 形态：export JWT_SECRET="<上一步输出>"，或写入 .env（参考 .env.example，compose 自动读取）
# B 形态：export JWT_SECRET="<上一步输出>"
```
`JWT_SECRET` **没有默认值**：缺失或为空时，第一个需要签发/校验 token 的请求（登录等）会直接 500（`auth.py:_secret` 抛 `RuntimeError("JWT_SECRET is required")`）——fail-closed，绝不带默认密钥上线。

### 4. 启动（迁移自动执行，无需手工）
```bash
# A 形态：首次 -d 后加 --build 可选
docker compose up -d
# B 形态：
.venv/bin/gunicorn -w 1 -b 0.0.0.0:8080 "wxcloudrun:create_app()"
```
每次启动 `create_app()` → `init_schema()` 自动执行：
1. `CREATE TABLE IF NOT EXISTS`（双引擎方言，MySQL 带 ENGINE=InnoDB）；
2. `run_migrations`：版本化迁移链（v1–v11，`_column_exists` 幂等守卫 + `schema_migrations` 记录）+ 历史列补加 + 首个用户提权管理员 + 存量活动补短码。
3. MySQL 模式额外 `ensure_mysql_database()`（库不存在自动创建）。
**无需任何手工迁移命令；升级代码后重启容器即完成迁移。**

### 5. 验证健康检查
```bash
curl -s http://127.0.0.1:8080/api/health
# → {"code":0,"data":{"status":"ok","timestamp":"..."},"message":"ok"}
docker compose ps   # 健康状态（Dockerfile HEALTHCHECK 每 30s 打 /api/health）
```
`/api/health` 无需认证，适合负载均衡/探活。

### 6. 配置 CORS（前端域名）
```bash
export CORS_ORIGIN="https://gift.example.com"   # 正式前端域名
```
- 留空 = 同源无跨域（安全默认）。
- 仅当请求 `Origin` 与 `CORS_ORIGIN` 一致（或配置为 `*`）时才回显 CORS 头；**生产勿用 `*`**。
- 优先级：环境变量 `CORS_ORIGIN` > 数据库 `app_settings.cors_origin`（管理后台可改）> 同源。

### 7. （可选）切换 MySQL
见下方「MySQL 切换」章节。设置 `MYSQL_ADDRESS` 后引擎自动切换，无需改代码。

### 8. 反向代理 + 真实 IP
若前面有 nginx/网关，把其 IP 加入 `TRUSTED_PROXIES`（逗号分隔）：
```bash
export TRUSTED_PROXIES="10.0.0.5,172.17.0.1"
```
否则登录/找回密码限速按直连 IP 计（`X-Forwarded-For` 不信任，防伪造绕过限速）。

### 9. 数据持久化与备份
- SQLite 形态：`data/gift_exchange.db` + 上传图片 `data/uploads/`。A 形态挂在 `./data:/app/data`（bind mount）；**定期备份 `data/`**（停机时 `sqlite3 gift_exchange.db ".backup backup.db"`，WAL 模式不要直接拷文件）。
- MySQL 形态：备份走 MySQL 工具，`data/` 仅剩上传图片。

### 10. 日志与升级
```bash
docker compose logs -f web     # 结构化 JSON 日志（含 request_id）
```
- 升级：`git pull && docker compose up -d --build`；迁移自动跑（见第 4 步），建议先备份 `data/`。
- 降级风险：迁移只加列不删列，旧代码可读新库；但新列写入后降级字段即忽略。

---

## 环境变量清单

来源：`grep os.getenv|os.environ` 全库核对（`wxcloudrun/*.py`）。

### 运行时变量（直接读 env）

| 变量 | 默认 | 必填 | 说明 |
|---|---|---|---|
| `JWT_SECRET` | 无 | **是** | JWT 签名密钥，`openssl rand -hex 32` 生成；缺失/为空即 fail-closed（认证请求 500） |
| `CORS_ORIGIN` | 空（同源） | 否 | 前端正式域名；留空=同源无跨域；生产勿用 `*` |
| `DEADLINE_SCANNER` | `1` | 否 | `0`/`false` 关闭截止提醒后台扫描 |
| `DEADLINE_SCAN_INTERVAL` | `3600` | 否 | 截止扫描间隔（秒） |
| `RESET_CODE_IN_RESPONSE` | `0` | 否 | `1`/`true`/`yes` 时把找回密码重置码放进响应体（演示用，生产勿开） |
| `DB_PATH` | `./data/gift_exchange.db` | 否 | SQLite 路径（容器内默认 `/app/data/gift_exchange.db`） |
| `UPLOAD_DIR` | `./data/uploads` | 否 | 上传图片目录（容器内默认 `/app/data/uploads`，已随 data 卷持久化） |
| `TRUSTED_PROXIES` | 空 | 否 | 逗号分隔反代 IP；仅白名单内来源信任 `X-Forwarded-For` |
| `ADMIN_USERNAMES` | 空 | 否 | 逗号分隔用户名，视为管理员（admin 面板/权限） |
| `ADMIN_EMAILS` | 空 | 否 | 逗号分隔邮箱，视为管理员 |
| `MYSQL_ADDRESS` / `MYSQL_HOST` | 空（=SQLite） | 否 | **设置即启用 MySQL**，格式 `host:port` |
| `MYSQL_PORT` | 地址内端口或 `3306` | 否 | MySQL 端口 |
| `MYSQL_USERNAME` / `MYSQL_USER` | `root` | 否 | MySQL 用户 |
| `MYSQL_PASSWORD` | 空 | 否 | MySQL 密码 |
| `MYSQL_DATABASE` / `MYSQL_DB` | `gift_exchange` | 否 | MySQL 库名（不存在自动创建） |

### 设置项 env 兜底（`SETTING_DEFINITIONS`，DB 设置面板 > 环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `SITE_NAME` | `Gift Exchange` | 站点名 |
| `REGISTRATION_ENABLED` | `true` | 是否开放注册 |
| `SHIPMENT_TRACKING_ENABLED` | `false` | 是否开启物流查询 |
| `TRACKING_PROVIDER` | `kdniao` | 物流商 |
| `KDNIAO_EBUSINESS_ID` | 空 | 快递鸟商户 ID（secret） |
| `KDNIAO_APP_KEY` | 空 | 快递鸟 key（secret） |
| `APP_BASE_URL` | 空 | 应用基础 URL |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USE_TLS` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_SENDER` | 空 / `587` / `true` / 空 / 空 / 空 | 邮件发送配置（当前代码未接 SMTP 发送，预留给通知扩展） |

优先级：DB `app_settings` 行 > env > 默认值（`helpers.setting_value`）。

---

## MySQL 切换

代码**不支持 `DB_TYPE=mysql` 或 `DATABASE_URL` 写法**——引擎由 `MYSQL_ADDRESS`（或 `MYSQL_HOST`）是否设置自动探测（`database.py:_mysql_config`）。切 MySQL 只需：

```bash
export MYSQL_ADDRESS="db.example.com:3306"     # 或 MYSQL_HOST="db.example.com"
export MYSQL_USERNAME="gift"                    # 默认 root
export MYSQL_PASSWORD="strong-password"
export MYSQL_DATABASE="gift_exchange"           # 默认 gift_exchange；不存在自动 CREATE DATABASE
docker compose up -d                            # A 形态；B 形态直接重启 gunicorn
```

- 连接串即 `MYSQL_ADDRESS=host:port`，无需 DATABASE_URL 解析。
- 迁移自动跑：启动时 `init_schema` 建表 + `run_migrations`（MySQL 走 `information_schema` 幂等检查），无需手工执行。
- 切 MySQL 后：SQLite 专属 `PRAGMA journal_mode=WAL` / `busy_timeout` 自动不执行；`?` 占位符自动转 `%s`。
- **SQLite → MySQL 数据迁移不自动**：需自行导出导入（如 `sqlite3 .dump` 适配后导入），或冷启动新库重新注册。

---

## 部署形态说明与已知事项

- **单 worker 原因**：deadline scanner 是应用内后台线程，多 worker 每进程一份会重复扫描；notify 幂等去重兜底（无害），但**单 worker 最稳**。镜像/Procfile 均为 `gunicorn -w 1`。未来扩实例时应把扫描独立成 cron/单独 worker。
- **模块级 `app = create_app()`**：`wxcloudrun/__init__.py` 末尾有模块级创建（`run.py` 与 pytest 依赖）。gunicorn 用 `wxcloudrun:create_app()` 时，import 阶段会先跑一次模块级创建（多起一个幂等的 scanner 线程），随后工厂再建正式 app——无害；若在意可改引 `wxcloudrun:app`（跳过二次创建）。
- **SQLite WAL 与网络卷**：`data/` 挂 NAS（NFS/SMB）时 WAL 可能不可用（journal_mode 报错）→ 换本地盘，或切 MySQL（见上）。
- **健康检查**：Dockerfile `HEALTHCHECK` 打 `/api/health`（无需认证）。
- **端口**：容器监听 `8080`（gunicorn `-b 0.0.0.0:8080`）；旧 `container.config.json`（微信云托管，端口 80）为本仓库遗留配置，未随本次部署更新。
- **静态资源**：前端由 Flask 直出（`/assets/<path>` + `templates/index.html`），无需单独 CDN；全部自托管，CSP `default-src 'self'`。
