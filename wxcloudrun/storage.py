"""存储抽象层：为未来切换对象存储（OSS/COS/S3）铺路。

用法：
    from wxcloudrun.storage import save_image, save_upload, storage

    key = save_image(data, "png")            # → "uploads/<uuid>.png"
    key = save_upload(data, "photo.jpg")     # 白名单扩展名校验
    url = storage.url_for(key)               # → "/uploads/<uuid>.png"

未来换对象存储：实现 S3Storage(Storage)（save/read/delete/exists/url_for），
把模块级 storage 实例替换即可，调用点不改。
"""
import os
import re
import uuid

# 默认上传目录（与 views.py /api/upload 的 UPLOAD_DIR 语义一致）
DEFAULT_UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "data/uploads")

# 图片扩展名白名单
ALLOWED_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB，与现有 /api/upload 一致

_SAFE_KEY = re.compile(r"^[\w./-]+$")


class Storage:
    """存储接口（抽象基类）。实现：LocalStorage；未来：S3Storage。"""

    def save(self, data: bytes, ext: str, folder: str = "") -> str:
        """保存字节，返回相对 key（如 uploads/<uuid>.png）。"""
        raise NotImplementedError

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def url_for(self, key: str) -> str:
        """返回可访问的相对 URL（如 /uploads/<uuid>.png）。"""
        raise NotImplementedError


def _validate_key(key: str) -> str:
    """防路径穿越：拒绝 ..、绝对路径、空 key、非法字符。"""
    if not key:
        raise ValueError("empty key")
    if key.startswith("/"):
        raise ValueError("absolute path not allowed")
    if ".." in key.split("/"):
        raise ValueError("path traversal not allowed")
    if not _SAFE_KEY.match(key):
        raise ValueError("illegal characters in key")
    return key


class LocalStorage(Storage):
    """本地文件系统实现（开发/单机部署默认）。"""

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or DEFAULT_UPLOAD_DIR or "data/uploads"
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        key = _validate_key(key)
        return os.path.join(self.base_dir, key)

    def save(self, data: bytes, ext: str, folder: str = "uploads") -> str:
        ext = ext.lower().lstrip(".")
        if ext not in ALLOWED_EXTS:
            raise ValueError(f"extension not allowed: {ext}")
        if len(data) > _MAX_FILE_BYTES:
            raise ValueError("file too large")
        filename = f"{uuid.uuid4().hex}.{ext}"
        rel = os.path.join(folder, filename).replace("\\", "/")
        path = self._path(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return rel

    def read(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def url_for(self, key: str) -> str:
        return "/" + _validate_key(key)


# 模块级便捷函数 ==================================================

storage = LocalStorage()


def save_image(data: bytes, ext: str) -> str:
    """保存图片，返回相对 key（uploads/<uuid>.<ext>）。"""
    return storage.save(data, ext, folder="uploads")


def save_upload(data: bytes, filename: str) -> str:
    """按原始文件名保存上传，校验扩展名白名单。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"extension not allowed: {ext}")
    return storage.save(data, ext, folder="uploads")
