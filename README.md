# 礼物互赠 Python/Flask 后端

这套后端按微信云托管 Flask 模板 `WeixinCloud/wxcloudrun-flask` 的形态整理：

- 入口文件：`run.py`
- Flask 应用：`wxcloudrun/__init__.py`
- 路由接口：`wxcloudrun/views.py`
- 数据访问：`wxcloudrun/database.py`
- 容器启动：`python run.py 0.0.0.0 80`

## 本地运行

```powershell
$env:JWT_SECRET="replace-with-a-long-random-secret"
python run.py 0.0.0.0 80
```

没有配置 MySQL 时会自动使用本地 SQLite：`./data/gift_exchange.db`。

## 微信云服务部署

后端类型选择 Python/Flask 或使用容器化部署。

环境变量：

- `JWT_SECRET`：必填，长随机字符串。
- `CORS_ORIGIN`：前端正式域名；测试期可以临时用 `*`。
- `MYSQL_ADDRESS`：MySQL 地址，例如 `host:3306`。
- `MYSQL_USERNAME`：MySQL 用户名。
- `MYSQL_PASSWORD`：MySQL 密码。
- `MYSQL_DATABASE`：MySQL 数据库名。

如果控制台没有绑定 MySQL，也可以先不填 MySQL 变量，服务会使用 SQLite；但正式上线建议使用 MySQL，因为容器本地磁盘不一定适合作为长期数据存储。
