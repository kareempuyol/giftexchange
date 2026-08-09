# 礼物互赠 Python/Flask 后端

这套后端按微信云托管 Flask 模板 `WeixinCloud/wxcloudrun-flask` 的形态整理：

- 入口文件：`run.py`（开发）；生产：`wxcloudrun:create_app()` 应用工厂 + gunicorn
- Flask 应用：`wxcloudrun/__init__.py`
- 路由接口：`wxcloudrun/views.py`
- 数据访问：`wxcloudrun/database.py`
- 容器启动：`gunicorn -w 1 -b 0.0.0.0:8080 "wxcloudrun:create_app()"`

## 本地运行

```bash
export JWT_SECRET="replace-with-a-long-random-secret"
python run.py 0.0.0.0 8080
```

没有配置 MySQL 时会自动使用本地 SQLite：`./data/gift_exchange.db`。

## Docker 部署（生产）

```bash
export JWT_SECRET="$(openssl rand -hex 32)"   # 必填，无默认值（fail-closed）
docker compose up -d --build                  # 多阶段构建：node 前端 → python gunicorn
curl http://127.0.0.1:8080/api/health         # 健康检查
```

完整步骤、环境变量清单、MySQL 切换与已知事项见 **[DEPLOY.md](DEPLOY.md)**。

前端（React + Vite + Design Tokens）源码在 `frontend/`，构建产物输出到 `wxcloudrun/static/` 并同步 `templates/index.html`：

```bash
cd frontend && npm run build   # 构建后需重启 Flask 生效
```

## 运维脚本（备份 / 清理 / 核查）

`scripts/` 提供上线必备的数据运维手段（用法 + cron 建议见 **DEPLOY.md「数据运维」**）：

- `backup_db.sh` — SQLite 在线备份（WAL 安全），时间戳命名 + 保留 7 份
- `cleanup_orphans.py` — 清理 uploads 无引用、超 7 天的孤儿文件（默认 dry-run，`--delete` 才真删）
- `cleanup_notifications.py` — 删除已读超 90 天的通知（默认 dry-run，`--delete` 才真删）
- `healthcheck_data.py` — 孤儿数据/引用完整性核查，只报告不修改

## 演示数据

体验/演示用种子数据（幂等，可重复执行，已存在的用户与活动自动跳过、不覆盖）：

```bash
python3 scripts/seed_demo.py
```

- 3 个 demo 账号：`demo_alice` / `demo_bob` / `demo_carol`（密码 `Demo1234`）
- 1 个示例活动「圣诞礼物交换 🎄」：公开、3 人、已抽签、部分发货/晒图、礼物墙已解锁，
  含物流单号、晒图（公开照片 / 模糊照片 / 仅文字三种隐私形态）、礼物墙点赞
- 10 条已读/未读混合的通知（抽签结果 / 发货 / 晒图 / 礼物墙解锁）

首次部署后跑一次即可给新用户一个「有内容可看」的起点；重复执行不会重复造数据。

## 快速公网部署（cloudflared 临时隧道）

适合联调/体验，不需要域名：

```bash
cloudflared tunnel --url http://127.0.0.1:8080 --protocol http2
# 输出 https://xxx.trycloudflare.com 即可访问
```

> 若 QUIC 连接失败（`Application error 0x0`），加 `--protocol http2`。

## 正式部署（微信云托管 / 任意服务器）

环境变量：

- `JWT_SECRET`：**必填，上线前必须换成强随机值**（`openssl rand -hex 32`）。
- `CORS_ORIGIN`：前端正式域名，如 `https://your-domain.com`；**留空=同源无跨域**（安全默认，勿用 `*`）。
- `MYSQL_ADDRESS`：MySQL 地址，例如 `host:3306`。
- `MYSQL_USERNAME`：MySQL 用户名。
- `MYSQL_PASSWORD`：MySQL 密码。
- `MYSQL_DATABASE`：MySQL 数据库名。

如果控制台没有绑定 MySQL，也可以先不填 MySQL 变量，服务会使用 SQLite；但正式上线建议使用 MySQL，因为容器本地磁盘不一定适合作为长期数据存储。
