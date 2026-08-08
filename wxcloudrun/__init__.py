import os
import threading
import time

from flask import Flask, jsonify

from wxcloudrun.database import DB, init_schema
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

    # 生产安全：500 错误不泄露堆栈/内部信息
    @flask_app.errorhandler(500)
    def internal_error(_e):
        return jsonify({"code": -1, "data": None, "message": "Internal server error"}), 500

    @flask_app.errorhandler(404)
    def not_found(_e):
        return jsonify({"code": -1, "data": None, "message": "Not found"}), 404

    @flask_app.after_request
    def add_cors_headers(response):
        # CORS 收紧：优先级 环境变量 CORS_ORIGIN > DB app_settings.cors_origin > 同源（无跨域）
        origin = os.getenv("CORS_ORIGIN", "").strip()
        try:
            with DB() as db:
                row = db.get("SELECT value FROM app_settings WHERE key_name = ?", ("cors_origin",))
                if not origin and row and row.get("value"):
                    origin = row["value"].strip()
        except Exception:
            pass
        if origin:
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
