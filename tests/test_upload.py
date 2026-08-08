"""上传安全加固测试（R-上传加固）：魔数校验纯函数 + /api/upload 集成。

集成部分用 Flask test client 走真实 HTTP 层：临时 SQLite 库 + 临时 UPLOAD_DIR，
并把 site_routes.storage 替换为指向临时目录的 LocalStorage（模块级实例在导入时
已固定 base_dir，无法靠环境变量重定向）。
"""
import base64
import io
import os
import tempfile

import pytest

from wxcloudrun.storage import LocalStorage
from wxcloudrun.site_routes import check_image_magic

PASSWORD = "Pass123!"

# 1x1 透明 PNG（真实魔数 + 完整合法结构）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def env():
    """独立临时 DB + 临时上传目录；结束恢复环境变量与 site_routes.storage。"""
    saved = {k: os.environ.get(k) for k in ("DB_PATH", "JWT_SECRET", "UPLOAD_DIR")}
    tmp = tempfile.mkdtemp(prefix="gift_test_upload_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-upload"
    uploads = os.path.join(tmp, "uploads")
    os.environ["UPLOAD_DIR"] = uploads
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()
        from wxcloudrun import app as flask_app  # noqa: E402
        from wxcloudrun import site_routes  # noqa: E402

        flask_app.config["TESTING"] = True
        saved_storage = site_routes.storage
        site_routes.storage = LocalStorage(base_dir=uploads)
        yield flask_app, uploads
        site_routes.storage = saved_storage
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="module")
def client(env):
    return env[0].test_client()


@pytest.fixture(scope="module")
def uploads_dir(env):
    return env[1]


def register_and_login(client, name):
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}


def upload(client, auth, filename, data, part_content_type=None):
    if part_content_type:
        file_tuple = (io.BytesIO(data), filename, part_content_type)
    else:
        file_tuple = (io.BytesIO(data), filename)
    return client.post(
        "/api/upload",
        data={"file": file_tuple},
        content_type="multipart/form-data",
        headers=auth,
    )


def saved_files(uploads_dir):
    """storage.save(folder='') 扁平落盘在 base_dir 下（与 /uploads 读取路由同目录）。"""
    return os.listdir(uploads_dir) if os.path.isdir(uploads_dir) else []


class TestCheckImageMagic:
    def test_png(self):
        assert check_image_magic(b"\x89PNG\r\n\x1a\n" + b"rest-of-file")

    def test_jpeg(self):
        assert check_image_magic(b"\xff\xd8\xff\xe0\x00\x10JFIF")

    def test_gif(self):
        assert check_image_magic(b"GIF89a" + b"\x01\x00\x01\x00")

    def test_webp(self):
        assert check_image_magic(b"RIFF\x00\x00\x00\x00WEBPVP8 ")

    def test_text_rejected(self):
        assert not check_image_magic(b"hello world, definitely not an image")

    def test_empty_rejected(self):
        assert not check_image_magic(b"")

    def test_too_short_rejected(self):
        assert not check_image_magic(b"\x89PN")  # PNG 头不足 4 字节

    def test_webp_without_tag_rejected(self):
        assert not check_image_magic(b"RIFF\x00\x00\x00\x00NOTW")

    def test_webp_too_short_rejected(self):
        assert not check_image_magic(b"RIFF\x00\x00\x00\x00WEB")  # <12 字节


class TestUploadApi:
    def test_upload_png_ok(self, client, uploads_dir):
        auth = register_and_login(client, "upload_png_ok")
        r = upload(client, auth, "avatar.png", PNG_1PX)
        assert r.status_code == 201, r.get_json()
        url = r.get_json()["data"]["url"]
        assert url.startswith("/uploads/") and url.endswith(".png")
        # 文件真实落盘（uuid 命名，扁平存于 uploads 目录）
        filename = os.path.basename(url)
        saved = os.path.join(uploads_dir, filename)
        assert os.path.isfile(saved)
        with open(saved, "rb") as fh:
            assert fh.read() == PNG_1PX
        # /uploads/<filename> 读取路由可回源
        r2 = client.get(url)
        assert r2.status_code == 200
        assert r2.data == PNG_1PX

    def test_upload_fake_png_rejected_by_magic(self, client, uploads_dir):
        auth = register_and_login(client, "upload_fake_png")
        before = saved_files(uploads_dir)
        r = upload(client, auth, "evil.png", b"this is just text pretending to be a png")
        assert r.status_code == 400
        assert "有效图片" in r.get_json()["message"]
        # 未新增落盘文件
        assert saved_files(uploads_dir) == before

    def test_upload_oversized_rejected(self, client, uploads_dir):
        auth = register_and_login(client, "upload_oversized")
        before = saved_files(uploads_dir)
        big = PNG_1PX + b"\x00" * (5 * 1024 * 1024 + 1)  # > 5MB
        r = upload(client, auth, "big.png", big)
        assert r.status_code == 400
        assert "文件过大" in r.get_json()["message"]
        assert saved_files(uploads_dir) == before

    def test_upload_non_image_content_type_rejected(self, client, uploads_dir):
        auth = register_and_login(client, "upload_ct")
        before = saved_files(uploads_dir)
        # 真 PNG 内容 + 非图片 content-type（伪装 multipart 部分头）
        r = upload(client, auth, "avatar.png", PNG_1PX, part_content_type="application/octet-stream")
        assert r.status_code == 400
        assert "文件类型" in r.get_json()["message"]
        assert saved_files(uploads_dir) == before

    def test_upload_bad_ext_rejected(self, client, uploads_dir):
        auth = register_and_login(client, "upload_bad_ext")
        before = saved_files(uploads_dir)
        r = upload(client, auth, "virus.exe", PNG_1PX)
        assert r.status_code == 400
        assert "文件格式" in r.get_json()["message"]
        assert saved_files(uploads_dir) == before

    def test_upload_requires_login(self, client):
        r = upload(client, {}, "avatar.png", PNG_1PX)
        assert r.status_code == 401
