import os

from flask import Flask, jsonify

from wxcloudrun.database import DB, init_schema
from wxcloudrun.views import api, site


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
    return flask_app


app = create_app()
