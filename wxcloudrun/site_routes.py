"""站点/静态/平台路由（/、/api-health、/api/health、/assets、/uploads、/api/upload、SPA 兑底）。"""
import os
import uuid
from pathlib import Path

from flask import jsonify, render_template, request, send_from_directory

from wxcloudrun.helpers import (
    ALLOWED_IMAGE_EXTS,
    MAX_UPLOAD_BYTES,
    api,
    fail,
    login_required,
    now_iso,
    ok,
    site,
    uploads_dir,
)


@api.route("/health")
def health():
    return ok({"status": "ok", "timestamp": now_iso()})


@site.route("/api-health")
def platform_health():
    return ok({"status": "ok", "timestamp": now_iso()})


@site.route("/")
def index():
    return render_template("index.html")


@site.route("/assets/<path:filename>")
def vite_assets(filename):
    return send_from_directory("static/assets", filename)


@api.route("/upload", methods=["POST"])
@login_required
def upload_image(_user):
    file = request.files.get("file")
    if file is None or not file.filename:
        return fail("No file provided")
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_IMAGE_EXTS:
        return fail("Only image files are allowed (png/jpg/jpeg/gif/webp)")
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        return fail("Only image files are allowed (png/jpg/jpeg/gif/webp)")
    content = file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return fail("File too large (max 5MB)")
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(uploads_dir(), filename), "wb") as fh:
        fh.write(content)
    return ok({"url": f"/uploads/{filename}"}, "Uploaded", 201)


@site.route("/uploads/<filename>")
def uploads_file(filename):
    # send_from_directory 自带 safe_join，防路径穿越；<filename> 转换器不含斜杠
    return send_from_directory(uploads_dir(), filename)


@site.route("/<path:_path>")
def spa_fallback(_path):
    # API 路径拼错时返回 JSON 404（避免前端拿到 HTML 报错困惑）
    if _path.startswith("api/"):
        return jsonify({"code": -1, "data": None, "message": "Not found"}), 404
    return render_template("index.html")
