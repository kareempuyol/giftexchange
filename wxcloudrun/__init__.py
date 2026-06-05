import os

from flask import Flask

from wxcloudrun.database import DB, init_schema
from wxcloudrun.views import api, site


def create_app():
    flask_app = Flask(__name__)
    flask_app.register_blueprint(api)
    flask_app.register_blueprint(site)

    @flask_app.after_request
    def add_cors_headers(response):
        origin = os.getenv("CORS_ORIGIN", "*")
        try:
            with DB() as db:
                row = db.get("SELECT value FROM app_settings WHERE key_name = ?", ("cors_origin",))
                if row and row.get("value"):
                    origin = row["value"]
        except Exception:
            pass
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
        return response

    init_schema()
    return flask_app


app = create_app()
