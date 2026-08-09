"""晒图隐私（Luna 独到项：晒图不阻塞）API 测试。

验证：
- PUT received-gift 带 privacy='text' 且不传照片 → 成功（仅文字也能算晒出）
- 礼物墙解锁不因单人缺图阻塞（received_at 非空即算 posted）
- gift-wall items 返回 privacy 字段（item 级 + giftPost 级）
- privacy 非法值被拒绝；缺省为 photo

复用 tests/test_draw_api.py 的临时 SQLite + Flask test client 模式。
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
    tmp = tempfile.mkdtemp(prefix="gift_test_privacy_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-privacy"
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
    # 组织者创建活动后自动加入：再次 join 幂等返回「你已加入该活动」（400），视为已加入
    if r.status_code == 400 and r.get_json().get("message") == "你已加入该活动":
        return
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


def put_gift(client, headers, code, match_id, payload):
    return client.put(f"/api/events/{code}/received-gift", json=payload, headers=headers)


class TestGiftPrivacy:
    def test_text_privacy_without_photo_posts_successfully(self, client):
        h1, uid1 = register_and_login(client, "gp_creator_txt")
        h2, uid2 = register_and_login(client, "gp_user_txt2")
        h3, _ = register_and_login(client, "gp_user_txt3")
        code = create_event(client, h1, "GP text event")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m = matches_for_user(client, h1, code, uid1)
        r = put_gift(
            client,
            h1,
            code,
            m["id"],
            {"matchId": m["id"], "rating": 5, "review": "只有文字心意，没有照片", "privacy": "text"},
        )
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["code"] == 0, body
        post = body["data"]
        assert post["privacy"] == "text"
        assert post["receivedAt"], "仅文字晒图也必须置 received_at（不阻塞礼物墙）"
        assert post["photoUrl"] == ""

        # 再次 GET received-gift：privacy 持久化
        rg = client.get(f"/api/events/{code}/received-gift", headers=h1)
        assert rg.status_code == 200, rg.get_json()
        assert rg.get_json()["data"]["giftPost"]["privacy"] == "text"

        # 未晒完：礼物墙仍锁定，但 posted 已 +1（不因缺图而丢统计）
        wall = client.get(f"/api/events/{code}/gift-wall", headers=h1)
        assert wall.status_code == 200, wall.get_json()
        w = wall.get_json()["data"]
        assert w["unlocked"] is False
        assert w["posted"] == 1 and w["total"] == 3

    def test_blur_and_photo_and_default_privacy_in_wall(self, client):
        h1, uid1 = register_and_login(client, "gp_creator_wall")
        h2, uid2 = register_and_login(client, "gp_user_wall2")
        h3, uid3 = register_and_login(client, "gp_user_wall3")
        code = create_event(client, h1, "GP wall event")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m1 = matches_for_user(client, h1, code, uid1)
        m2 = matches_for_user(client, h1, code, uid2)  # 组织者可见全部匹配
        m3 = matches_for_user(client, h1, code, uid3)

        # ① 仅文字（无照片）
        r = put_gift(client, h1, code, m1["id"], {"matchId": m1["id"], "rating": 4, "review": "文字晒图", "privacy": "text"})
        assert r.status_code == 200, r.get_json()
        # ② 模糊照片（传照片 + privacy='blur'，后端不处理图像，仅标记）
        r = put_gift(client, h2, code, m2["id"], {"matchId": m2["id"], "rating": 5, "review": "模糊晒图", "photoUrl": "/uploads/gp_blur.png", "privacy": "blur"})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["privacy"] == "blur"
        # ③ 默认公开照片（不传 privacy 字段 → photo）
        r = put_gift(client, h3, code, m3["id"], {"matchId": m3["id"], "rating": 3, "review": "默认照片", "photoUrl": "/uploads/gp_photo.png"})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["privacy"] == "photo"

        # 全部晒完 → 解锁，items 带 privacy（item 级 + giftPost 级）
        wall = client.get(f"/api/events/{code}/gift-wall", headers=h1)
        assert wall.status_code == 200, wall.get_json()
        w = wall.get_json()["data"]
        assert w["unlocked"] is True, w
        assert w["posted"] == 3 and w["total"] == 3
        by_match = {it["matchId"]: it for it in w["items"]}
        assert len(by_match) == 3

        t = by_match[m1["id"]]
        assert t["privacy"] == "text" and t["giftPost"]["privacy"] == "text"
        assert t["giftPost"]["photoUrl"] == ""
        b = by_match[m2["id"]]
        assert b["privacy"] == "blur" and b["giftPost"]["privacy"] == "blur"
        assert b["giftPost"]["photoUrl"] == "/uploads/gp_blur.png"
        p = by_match[m3["id"]]
        assert p["privacy"] == "photo" and p["giftPost"]["privacy"] == "photo"

    def test_invalid_privacy_rejected(self, client):
        h1, uid1 = register_and_login(client, "gp_creator_inv")
        h2, _ = register_and_login(client, "gp_user_inv2")
        h3, _ = register_and_login(client, "gp_user_inv3")
        code = create_event(client, h1, "GP invalid privacy")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m = matches_for_user(client, h1, code, uid1)
        r = put_gift(client, h1, code, m["id"], {"matchId": m["id"], "rating": 5, "privacy": "vip"})
        assert r.status_code == 400, r.get_json()
        assert "隐私设置无效" in r.get_json()["message"]

        # 非法提交后仍可正常提交（未被写入）
        r = put_gift(client, h1, code, m["id"], {"matchId": m["id"], "rating": 5, "review": "修正后晒出", "privacy": "text"})
        assert r.status_code == 200, r.get_json()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
