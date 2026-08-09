"""hackathon 轮13 功能增量 API 测试。

验证：
- 个人心愿单：users.wishlist / users.wishlist_visible 经 PUT /profile 可写、GET /profile 可读
- my-match 返回 receiverWishlist：仅当收礼人开启 wishlistVisible 时返回（隐私门控）
- gift-wall 返回 shortCode（分享文案按钮依赖）

复用 tests/test_gift_privacy.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表（含 v12 迁移），结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_r13_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-r13"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()  # 幂等：CREATE TABLE IF NOT EXISTS + run_migrations（含 v12），落在临时库
        from wxcloudrun import app as flask_app  # noqa: E402

        flask_app.config["TESTING"] = True
        yield flask_app
    finally:
        if saved_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved_db
        if saved_jwt is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = saved_jwt
        if saved_db and saved_db.startswith(tempfile.gettempdir()):
            try:
                from wxcloudrun.database import init_schema as _heal

                _heal()
            except Exception:
                pass


@pytest.fixture(scope="module")
def client(ctx):
    return ctx.test_client()


def register_and_login(client, name):
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def create_event(client, headers, title):
    r = client.post("/api/events", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def join_event(client, headers, code):
    r = client.post(f"/api/events/{code}/join", json={}, headers=headers)
    if r.status_code == 400 and r.get_json().get("message") == "你已加入该活动":
        return
    assert r.status_code == 201, r.get_json()


def draw(client, headers, code):
    r = client.post(f"/api/events/{code}/draw", headers=headers)
    assert r.status_code == 200, r.get_json()


class TestWishlistProfile:
    def test_default_hidden_and_empty(self, client):
        h, _ = register_and_login(client, "r13_default")
        r = client.get("/api/profile", headers=h)
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert data["wishlist"] == ""
        assert data["wishlistVisible"] is False

    def test_save_and_read_wishlist(self, client):
        h, _ = register_and_login(client, "r13_saver")
        r = client.put(
            "/api/profile",
            json={"wishlist": "想要一个保温杯和香薰 🕯️", "wishlistVisible": True},
            headers=h,
        )
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert data["wishlist"] == "想要一个保温杯和香薰 🕯️"
        assert data["wishlistVisible"] is True
        # 再读一次（GET 路径）
        r = client.get("/api/profile", headers=h)
        assert r.get_json()["data"]["wishlist"] == "想要一个保温杯和香薰 🕯️"

    def test_wishlist_too_long_rejected(self, client):
        h, _ = register_and_login(client, "r13_long")
        r = client.put("/api/profile", json={"wishlist": "长" * 501}, headers=h)
        assert r.status_code == 400, r.get_json()

    def test_wishlist_visible_off(self, client):
        h, _ = register_and_login(client, "r13_hide")
        client.put("/api/profile", json={"wishlist": "秘密心愿", "wishlistVisible": True}, headers=h)
        r = client.put("/api/profile", json={"wishlist": "秘密心愿", "wishlistVisible": False}, headers=h)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["wishlistVisible"] is False


class TestWishlistInMyMatch:
    def _receiver_wishlist_for_giver(self, client, h_creator, headers_by_uid, code, receiver_uid):
        """返回把 receiver_uid 作为收礼人的 match 的送礼人 my-match 的 receiverWishlist。"""
        r = client.get(f"/api/events/{code}/matches", headers=h_creator)
        assert r.status_code == 200, r.get_json()
        target = next((m for m in r.get_json()["data"] if m["receiverId"] == receiver_uid), None)
        assert target, "no match gifting to receiver_uid"
        giver_headers = headers_by_uid[target["giverId"]]
        mm = client.get(f"/api/events/{code}/my-match", headers=giver_headers)
        assert mm.status_code == 200, mm.get_json()
        data = mm.get_json()["data"]
        assert data and data["receiverId"] == receiver_uid
        return data["receiverWishlist"]

    def test_wishlist_shown_when_visible(self, client):
        h1, uid1 = register_and_login(client, "r13_wl_org")
        h2, uid2 = register_and_login(client, "r13_wl_b")
        h3, uid3 = register_and_login(client, "r13_wl_c")
        headers_by_uid = {uid1: h1, uid2: h2, uid3: h3}
        # b、c 都写下心愿并开启展示
        for h, text in ((h2, "B 的心愿：机械键盘"), (h3, "C 的心愿：手账本")):
            r = client.put("/api/profile", json={"wishlist": text, "wishlistVisible": True}, headers=h)
            assert r.status_code == 200, r.get_json()
        code = create_event(client, h1, "R13 wishlist event")
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)
        # 每个收礼人的心愿都展示给了对应的送礼人
        for uid, expected in ((uid1, ""), (uid2, "B 的心愿：机械键盘"), (uid3, "C 的心愿：手账本")):
            assert self._receiver_wishlist_for_giver(client, h1, headers_by_uid, code, uid) == expected

    def test_wishlist_hidden_when_not_visible(self, client):
        h1, uid1 = register_and_login(client, "r13_wl2_org")
        h2, uid2 = register_and_login(client, "r13_wl2_b")
        h3, uid3 = register_and_login(client, "r13_wl2_c")
        headers_by_uid = {uid1: h1, uid2: h2, uid3: h3}
        # b 开启展示，c 不开启
        client.put("/api/profile", json={"wishlist": "B 心愿", "wishlistVisible": True}, headers=h2)
        client.put("/api/profile", json={"wishlist": "C 秘密心愿", "wishlistVisible": False}, headers=h3)
        code = create_event(client, h1, "R13 hidden wishlist")
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)
        # uid2（开启）→ 非空；uid3（未开启）→ 空字符串（隐私门控）
        assert self._receiver_wishlist_for_giver(client, h1, headers_by_uid, code, uid2) == "B 心愿"
        assert self._receiver_wishlist_for_giver(client, h1, headers_by_uid, code, uid3) == ""


class TestGiftWallShortCode:
    def test_gift_wall_returns_short_code(self, client):
        h1, _ = register_and_login(client, "r13_wall_org")
        h2, _ = register_and_login(client, "r13_wall_b")
        h3, _ = register_and_login(client, "r13_wall_c")
        code = create_event(client, h1, "R13 wall event")
        join_event(client, h2, code)
        join_event(client, h3, code)
        # 抽签前 gift-wall 也可访问（未解锁视图），shortCode 必须存在
        r = client.get(f"/api/events/{code}/gift-wall", headers=h1)
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert data["shortCode"], "gift-wall 必须返回短码"
        # 与事件短码一致
        detail = client.get(f"/api/events/{code}", headers=h1).get_json()["data"]
        assert data["shortCode"] == detail["shortCode"]
