# 礼物互赠 Python/Flask 后端

这套后端按微信云托管 Flask 模板 `WeixinCloud/wxcloudrun-flask` 的形态整理：

- 入口文件：`run.py`
- Flask 应用：`wxcloudrun/__init__.py`
- 路由接口：`wxcloudrun/views.py`
- 数据访问：`wxcloudrun/database.py`
- 容器启动：`python run.py 0.0.0.0 80`

## 本地运行

```bash
export JWT_SECRET="replace-with-a-long-random-secret"
python run.py 0.0.0.0 8080
```

没有配置 MySQL 时会自动使用本地 SQLite：`./data/gift_exchange.db`。

前端（React + Vite + Design Tokens）源码在 `frontend/`，构建产物输出到 `wxcloudrun/static/` 并同步 `templates/index.html`：

```bash
cd frontend && npm run build   # 构建后需重启 Flask 生效
```

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
