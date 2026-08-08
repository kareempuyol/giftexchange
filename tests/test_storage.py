"""存储抽象层单元测试（wxcloudrun/storage.py）"""
import os
import pytest

from wxcloudrun.storage import LocalStorage, save_image, save_upload


@pytest.fixture
def store(tmp_path):
    return LocalStorage(base_dir=str(tmp_path / "uploads"))


class TestLocalStorage:
    def test_save_read_roundtrip(self, store):
        data = b"\x89PNG\r\n\x1a\n" + b"hello"
        key = store.save(data, "png")
        assert key.startswith("uploads/")
        assert key.endswith(".png")
        assert store.exists(key)
        assert store.read(key) == data

    def test_save_generates_unique_keys(self, store):
        k1 = store.save(b"a", "png")
        k2 = store.save(b"a", "png")
        assert k1 != k2

    def test_delete(self, store):
        key = store.save(b"x", "jpg")
        assert store.exists(key)
        store.delete(key)
        assert not store.exists(key)

    def test_url_for(self, store):
        key = store.save(b"x", "webp")
        assert store.url_for(key) == "/" + key

    def test_rejects_disallowed_ext(self, store):
        with pytest.raises(ValueError, match="extension not allowed"):
            store.save(b"x", "exe")
        with pytest.raises(ValueError, match="extension not allowed"):
            store.save(b"x", "py")

    def test_uppercase_ext_normalized(self, store):
        key = store.save(b"x", "PNG")
        assert key.endswith(".png")

    def test_rejects_oversized(self, store):
        with pytest.raises(ValueError, match="file too large"):
            store.save(b"x" * (5 * 1024 * 1024 + 1), "png")

    def test_folder_organization(self, store):
        key = store.save(b"x", "png", folder="covers")
        assert key.startswith("covers/")
        assert store.exists(key)


class TestPathTraversal:
    def test_dotdot_rejected(self, store):
        for evil in ["../evil.png", "uploads/../../evil.png", "a/../b.png"]:
            with pytest.raises(ValueError, match="traversal"):
                store._path(evil)

    def test_absolute_rejected(self, store):
        with pytest.raises(ValueError, match="absolute"):
            store._path("/etc/passwd")

    def test_illegal_chars_rejected(self, store):
        with pytest.raises(ValueError, match="illegal"):
            store._path("uploads/a b.png")


class TestConvenience:
    def test_save_image(self, store, monkeypatch, tmp_path):
        from wxcloudrun import storage as storage_module
        monkeypatch.setattr(storage_module, "storage", store)
        key = save_image(b"\x89PNGdata", "png")
        assert key.startswith("uploads/") and key.endswith(".png")
        assert store.read(key) == b"\x89PNGdata"

    def test_save_upload(self, store, monkeypatch):
        from wxcloudrun import storage as storage_module
        monkeypatch.setattr(storage_module, "storage", store)
        key = save_upload(b"data", "photo.jpg")
        assert key.endswith(".jpg")

    def test_save_upload_rejects_bad_name(self, store, monkeypatch):
        from wxcloudrun import storage as storage_module
        monkeypatch.setattr(storage_module, "storage", store)
        with pytest.raises(ValueError, match="extension not allowed"):
            save_upload(b"data", "virus.exe")
        with pytest.raises(ValueError, match="extension not allowed"):
            save_upload(b"data", "noext")
