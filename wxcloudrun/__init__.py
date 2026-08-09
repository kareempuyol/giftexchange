import logging
import os
import threading
import time

from flask import Flask, g, jsonify, request

from wxcloudrun.database import DB, init_schema
from wxcloudrun.helpers import current_user
from wxcloudrun.observability import (
    get_request_id,
    log_event,
    make_request_id,
    set_request_id,
    set_user_id,
)
from wxcloudrun.views import api, site


def _deadline_scanner_loop(interval_seconds=3600):
    """后台线程：每小时扫描一次即将到期的活动并发送截止提醒（幂等去重，可重复跑）。

    轻量实现（threading + sleep），不引 APScheduler——当前单实例规模足够；
    未来多进程部署时应换 cron / 独立 worker，避免重复扫描（notify 自带去重兜底）。
    """
    while True:
        try:
            from wxcloudrun.jobs import scan_deadlines
            sent = scan_deadlines()
            if sent:
                print(f"[deadline-scanner] sent {sent} reminder notification(s)")
        except Exception as exc:
            print(f"[deadline-scanner] error: {exc}")
        time.sleep(interval_seconds)


def create_app():
    flask_app = Flask(__name__)
    flask_app.register_blueprint(api)
    flask_app.register_blueprint(site)

    # 可观测性：app.logger 与结构化日志统一 INFO 级
    flask_app.logger.setLevel(logging.INFO)

    # 可观测性：每个请求生成/透传 request_id，并记录登录用户（仅日志用）
    @flask_app.before_request
    def attach_request_context():
        # 客户端透传 X-Request-ID（跨层追踪）优先，否则生成新的；非法值回退新生成
        incoming = (request.headers.get("X-Request-ID") or "").strip()
        if incoming and len(incoming) <= 128:
            request_id = incoming
        else:
            request_id = make_request_id()
        set_request_id(request_id)
        g._gift_request_start = time.perf_counter()
        # verify_token 永不抛异常；解析失败/未登录即空（每次请求无条件重置，防串号）
        user = current_user()
        set_user_id(user.get("userId") if user else None)

    # 可观测性：请求级日志（method/path/status/耗时/request_id）+ X-Request-ID 回显
    @flask_app.after_request
    def log_request(response):
        response.headers["X-Request-ID"] = get_request_id() or ""
        start = getattr(g, "_gift_request_start", None)
        duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None
        log_event(
            "request",
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    # 生产安全：500 错误不泄露堆栈/内部信息，统一友好提示（用户可感知「服务开小差」而非裸堆栈/英文报错）
    @flask_app.errorhandler(500)
    def internal_error(exc):
        # 异常只进日志（stdout 结构化 JSON），绝不进响应体
        try:
            log_event(
                "error_500",
                path=request.path,
                method=request.method,
                error=repr(exc) if exc else "",
            )
        except Exception:
            pass
        return jsonify({"code": -1, "data": None, "message": "服务开小差了，请重试"}), 500

    @flask_app.errorhandler(404)
    def not_found(_e):
        return jsonify({"code": -1, "data": None, "message": "Not found"}), 404

    @flask_app.after_request
    def add_security_headers(response):
        # 安全头（P2 修复）：nosniff 防 MIME 嗅探、DENY 防点击劫持、Referrer 最小化泄露、
        # CSP 收紧（前端资源全部自托管，index.html 无内联脚本，见 templates/index.html）
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'",
        )
        return response

    @flask_app.after_request
    def add_cors_headers(response):
        # CORS 收紧：优先级 环境变量 CORS_ORIGIN > DB app_settings.cors_origin > 同源（无跨域）。
        # 仅当请求 Origin 与配置一致（或配置为 *）时才回显，防止任意 Origin 获得跨域读权限。
        origin = os.getenv("CORS_ORIGIN", "").strip()
        try:
            with DB() as db:
                row = db.get("SELECT value FROM app_settings WHERE key_name = ?", ("cors_origin",))
                if not origin and row and row.get("value"):
                    origin = row["value"].strip()
        except Exception:
            pass
        if not origin:
            return response
        if origin == "*":
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        elif request.headers.get("Origin") == origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Vary"] = "Origin"
        return response

    init_schema()

    # 截止提醒后台扫描（可用环境变量 DEADLINE_SCANNER=0 关闭；间隔秒数可用 DEADLINE_SCAN_INTERVAL 覆盖）
    if os.getenv("DEADLINE_SCANNER", "1").strip() not in ("0", "false", "False"):
        try:
            interval = int(os.getenv("DEADLINE_SCAN_INTERVAL", "3600"))
        except ValueError:
            interval = 3600
        t = threading.Thread(target=_deadline_scanner_loop, args=(interval,), daemon=True)
        t.start()

    return flask_app


app = create_app()
