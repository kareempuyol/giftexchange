---
name: hard-rules
alwaysApply: true
---

# 硬性红线（违反立即修正）

1. 不允许：在业务代码里硬编码颜色值（用 --gift-* CSS 变量）、硬编码域名（用相对路径/request.host_url）。
2. 不允许：往 matches/events 表写 base64 图片（用 storage.py + URL 引用）。
3. 不允许：改数据库历史 CREATE TABLE 语句（新列走 migrations.py，版本号 +1，双引擎幂等）。
4. 不允许：在路由里自行解析 JWT（用 helpers.login_required）。
5. 不允许：破坏 ok()/fail() 响应结构（前端依赖 {code,data,message}）。
6. 前端改动后必须执行 npm run build 并重启 Flask 服务，否则白屏。
