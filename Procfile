# 平台型部署（Heroku/Render 等）入口；Docker 部署由 Dockerfile CMD 提供同等命令
# 单 worker：deadline scanner 是应用内线程，多 worker 会重复扫描（notify 去重兜底，但单 worker 最稳）
web: gunicorn -w 1 -b 0.0.0.0:8080 "wxcloudrun:create_app()"
