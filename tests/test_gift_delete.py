"""删除晒图（P0）API 测试。

验证：
- 收礼人本人删除后：礼物墙 posted 计数 -1、卡片恢复未揭晓（received_at 回 NULL）
- 晒图字段（照片/评价/评分/隐私）全部清空
- 非收礼人删除 → 404；非参与者删除 → 403
- 未登录 → 401
- 删除后再次删除 → 404

复用 tests/test_gift_privacy.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_delete_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-delete"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()  # 幂等：CREATE TABLE IF NOT EXISTS + run_migrations，落在临时库
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
        # 治愈同仓其他测试文件的临时库（与 test_draw_api.py 相同的自愈逻辑）
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
    assert r.status_code == 201, r.get_json()


def draw(client, headers, code):
    r = client.post(f"/api/events/{code}/draw", headers=headers)
    assert r.status_code == 200, r.get_json()


def matches_for_user(client, headers, code, user_id):
    """返回该 user_id 作为收礼人的 match（receiverId 是 user id）。

    /matches 默认私密（仅组织者可看），因此本函数需用组织者 headers 调用。
    """
    r = client.get(f"/api/events/{code}/matches", headers=headers)
    assert r.status_code == 200, r.get_json()
    for m in r.get_json()["data"]:
        if m["receiverId"] == user_id:
            return m
    raise AssertionError(f"no match receiving for user {user_id}")


def put_gift(client, headers, code, match_id):
    r = client.put(
        f"/api/events/{code}/received-gift",
        json={"matchId": match_id, "rating": 5, "review": "晒图了", "photoUrl": "/uploads/del_photo.png", "privacy": "photo"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["receivedAt"], "晒图必须置 received_at"


def delete_gift(client, headers, code, match_id):
    return client.delete(f"/api/events/{code}/received-gift?matchId={match_id}", headers=headers)


def wall_posted(client, headers, code):
    r = client.get(f"/api/events/{code}/gift-wall", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["posted"]


class TestDeleteGift:
    def test_delete_reverts_wall_and_clears_fields(self, client):
        h1, uid1 = register_and_login(client, "gd_creator_own")
        h2, uid2 = register_and_login(client, "gd_user_own2")
        h3, uid3 = register_and_login(client, "gd_user_own3")
        code = create_event(client, h1, "GD delete own")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m1 = matches_for_user(client, h1, code, uid1)
        put_gift(client, h1, code, m1["id"])
        assert wall_posted(client, h1, code) == 1

        # 删除前：received-gift 有完整晒图
        rg = client.get(f"/api/events/{code}/received-gift", headers=h1)
        assert rg.get_json()["data"]["giftPost"]["receivedAt"]

        r = delete_gift(client, h1, code, m1["id"])
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["code"] == 0
        assert "删除" in r.get_json()["message"]

        # 礼物墙：posted 计数 -1，未解锁
        assert wall_posted(client, h1, code) == 0

        # 卡片恢复未揭晓：received-gift 晒图字段清空、received_at 回 NULL、隐私回默认 photo
        rg = client.get(f"/api/events/{code}/received-gift", headers=h1)
        assert rg.status_code == 200, rg.get_json()
        post = rg.get_json()["data"]["giftPost"]
        assert post["receivedAt"] == ""
        assert post["rating"] is None
        assert post["review"] == ""
        assert post["photoUrl"] == ""
        assert post["privacy"] == "photo"

        # my-match（送礼人视角）：同样恢复未揭晓（悄悄话重新隐藏）
        mm = client.get(f"/api/events/{code}/my-match", headers=h2)
        assert mm.status_code == 200, mm.get_json()
        assert mm.get_json()["data"]["giftPost"]["receivedAt"] == ""

    def test_non_receiver_cannot_delete(self, client):
        h1, uid1 = register_and_login(client, "gd_creator_perm")
        h2, uid2 = register_and_login(client, "gd_user_perm2")
        h3, uid3 = register_and_login(client, "gd_user_perm3")
        h4, _ = register_and_login(client, "gd_user_perm4")
        code = create_event(client, h1, "GD delete perm")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m1 = matches_for_user(client, h1, code, uid1)
        put_gift(client, h1, code, m1["id"])

        # 参与者但非收礼人 → 404（match 不属于他）
        r = delete_gift(client, h2, code, m1["id"])
        assert r.status_code == 404, r.get_json()
        # 未参与该活动的人 → 403
        r = delete_gift(client, h4, code, m1["id"])
        assert r.status_code == 403, r.get_json()
        # 收礼人的晒图未被删掉
        assert wall_posted(client, h1, code) == 1

    def test_delete_requires_login(self, client):
        h1, uid1 = register_and_login(client, "gd_creator_auth")
        h2, uid2 = register_and_login(client, "gd_user_auth2")
        h3, uid3 = register_and_login(client, "gd_user_auth3")
        code = create_event(client, h1, "GD delete auth")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m1 = matches_for_user(client, h1, code, uid1)
        put_gift(client, h1, code, m1["id"])

        r = client.delete(f"/api/events/{code}/received-gift?matchId={m1['id']}")
        assert r.status_code == 401, r.get_json()
        assert wall_posted(client, h1, code) == 1

    def test_delete_again_returns_404(self, client):
        h1, uid1 = register_and_login(client, "gd_creator_twice")
        h2, uid2 = register_and_login(client, "gd_user_twice2")
        h3, uid3 = register_and_login(client, "gd_user_twice3")
        code = create_event(client, h1, "GD delete twice")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m1 = matches_for_user(client, h1, code, uid1)
        put_gift(client, h1, code, m1["id"])

        r = delete_gift(client, h1, code, m1["id"])
        assert r.status_code == 200, r.get_json()
        # 再次删除 → 404（已删/未晒图）
        r = delete_gift(client, h1, code, m1["id"])
        assert r.status_code == 404, r.get_json()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
