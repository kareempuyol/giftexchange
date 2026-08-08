"""站点/静态/平台路由（/、/api-health、/api/health、/assets、/uploads、/api/upload、SPA 兑底）。"""
import os

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
from wxcloudrun.storage import storage

# content_type 白名单（与扩展名白名单一一对应；浏览器对 .jpg 一律报 image/jpeg）
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def check_image_magic(data: bytes) -> bool:
    """魔数校验：读取文件头判断真实图片格式，防止改扩展名/伪造 content_type 的恶意文件。

    PNG: 89 50 4E 47 | JPEG: FF D8 FF | GIF: 47 49 46 38（"GIF8"）|
    WEBP: "RIFF" + 4 字节长度 + "WEBP"
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 4:
        return False
    if data[:4] == b"\x89PNG":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:4] == b"GIF8":
        return True
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


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
        return fail("未选择文件")
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_IMAGE_EXTS:
        return fail("不支持的文件格式（仅支持 png/jpg/jpeg/gif/webp）")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        return fail("不支持的文件类型（仅支持 png/jpg/jpeg/gif/webp 图片）")
    content = file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return fail("文件过大（最大 5MB）")
    if not check_image_magic(content):
        return fail("文件内容不是有效图片，请上传真实图片文件")
    try:
        # storage 抽象层：uuid 命名 + 扩展名白名单 + 5MB + 防路径穿越（内部实现）。
        # folder=""：storage 默认 base_dir 即 uploads 目录（与 /uploads/<filename>
        # 读取路由的 uploads_dir() 同一目录），保持扁平落盘，读取路由与 URL 不变。
        key = storage.save(content, ext, folder="")
    except ValueError:
        # 兜底（预校验已挡掉绝大多数情况）：扩展名/大小不合规
        return fail("文件格式或大小不符合要求")
    return ok({"url": f"/uploads/{key}"}, "Uploaded", 201)


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
