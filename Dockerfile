# giftexchange 多阶段构建：node 构建前端 → python 运行后端（Flask + gunicorn）
# 用法：docker compose up -d --build   （或 docker build -t giftexchange .）

# ---- Stage 1：前端构建（node） ----
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite outDir=../wxcloudrun/static，build 脚本再同步 templates/index.html
RUN npm run build

# ---- Stage 2：后端运行（python + gunicorn） ----
FROM python:3.11-alpine
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 依赖：Flask + PyMySQL（requirements.txt）+ gunicorn（WSGI 服务器，仅容器内需要）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn==22.0.0

COPY wxcloudrun/ wxcloudrun/
# 前端产物覆盖源目录里的旧构建（.dockerignore 已排除 static/templates，避免陈旧文件）
COPY --from=frontend /wxcloudrun/static/ wxcloudrun/static/
COPY --from=frontend /wxcloudrun/templates/ wxcloudrun/templates/

EXPOSE 8080

# 健康检查：/api/health 无需认证（busybox wget）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/api/health || exit 1

# 单 worker：deadline scanner 是应用内线程，多 worker 会重复扫描；
# notify 自带幂等去重兜底，但单 worker 最稳（见 DEPLOY.md）。
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "wxcloudrun:create_app()"]
