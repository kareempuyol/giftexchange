"""异常路径边界回归测试（hackathon 波次6 新增契约）。

验证：
- 报名截止（drawDate 已过）后 join → 400「活动已截止报名」；未截止仍可加入
- 晒图 PUT 空评价 → 400「请填写评价内容」；带评价 → 200
- 无效短码/uuid 详情 → 404 + 中文「活动不存在或已失效」；join 不存在活动同样 404

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
    tmp = tempfile.mkdtemp(prefix="gift_test_edge_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-edge"
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


def create_event(client, headers, title, draw_date=""):
    payload = {"title": title}
    if draw_date:
        payload["drawDate"] = draw_date
    r = client.post("/api/events", json=payload, headers=headers)
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
    r = client.get(f"/api/events/{code}/matches", headers=headers)
    assert r.status_code == 200, r.get_json()
    for m in r.get_json()["data"]:
        if m["receiverId"] == user_id:
            return m
    raise AssertionError(f"no match receiving for user {user_id}")


# ---------- 截止后加入 ----------

class TestJoinAfterDeadline:
    def test_join_past_deadline_rejected(self, client):
        h1, _ = register_and_login(client, "edg_owner_dl")
        h2, _ = register_and_login(client, "edg_member_dl")
        code = create_event(client, h1, "已截止活动", draw_date="2020-01-01")
        r = client.post(f"/api/events/{code}/join", json={}, headers=h2)
        assert r.status_code == 400, r.get_json()
        assert r.get_json()["message"] == "活动已截止报名"

    def test_join_future_deadline_allowed(self, client):
        h1, _ = register_and_login(client, "edg_owner_fut")
        h2, _ = register_and_login(client, "edg_member_fut")
        code = create_event(client, h1, "招募中活动", draw_date="2999-01-01")
        r = client.post(f"/api/events/{code}/join", json={}, headers=h2)
        assert r.status_code == 201, r.get_json()


# ---------- 晒图评分/评价边界 ----------

class TestGiftPostBoundaries:
    def test_empty_review_rejected(self, client):
        h1, uid1 = register_and_login(client, "edg_owner_rev")
        h2, _ = register_and_login(client, "edg_member_rev2")
        h3, _ = register_and_login(client, "edg_member_rev3")
        code = create_event(client, h1, "晒图边界活动")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m = matches_for_user(client, h1, code, uid1)
        # 空评价（仅空格）→ 400
        r = client.put(
            f"/api/events/{code}/received-gift",
            json={"matchId": m["id"], "rating": 5, "review": "   ", "photoUrl": "/uploads/e.png", "privacy": "photo"},
            headers=h1,
        )
        assert r.status_code == 400, r.get_json()
        assert r.get_json()["message"] == "请填写评价内容"
        # 带评价 → 200
        r = client.put(
            f"/api/events/{code}/received-gift",
            json={"matchId": m["id"], "rating": 5, "review": "很喜欢", "photoUrl": "/uploads/e.png", "privacy": "photo"},
            headers=h1,
        )
        assert r.status_code == 200, r.get_json()

    def test_rating_out_of_range_rejected(self, client):
        h1, uid1 = register_and_login(client, "edg_owner_rate")
        h2, _ = register_and_login(client, "edg_member_rate2")
        h3, _ = register_and_login(client, "edg_member_rate3")
        code = create_event(client, h1, "评分边界活动")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m = matches_for_user(client, h1, code, uid1)
        for rating in (0, 6):
            r = client.put(
                f"/api/events/{code}/received-gift",
                json={"matchId": m["id"], "rating": rating, "review": "ok", "privacy": "text"},
                headers=h1,
            )
            assert r.status_code == 400, r.get_json()
            assert r.get_json()["message"] == "评分需在 1-5 之间"


# ---------- 无效活动 404 ----------

class TestEventNotFound:
    def test_detail_invalid_shortcode_404_chinese(self, client):
        h1, _ = register_and_login(client, "edg_owner_nf")
        r = client.get("/api/events/ZZZZZZ", headers=h1)
        assert r.status_code == 404, r.get_json()
        assert r.get_json()["message"] == "活动不存在或已失效"

    def test_detail_invalid_uuid_404_chinese(self, client):
        h1, _ = register_and_login(client, "edg_owner_nf2")
        r = client.get("/api/events/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", headers=h1)
        assert r.status_code == 404, r.get_json()
        assert r.get_json()["message"] == "活动不存在或已失效"

    def test_join_unknown_event_404(self, client):
        h1, _ = register_and_login(client, "edg_owner_jn")
        r = client.post("/api/events/does-not-exist/join", json={}, headers=h1)
        assert r.status_code == 404, r.get_json()
        assert r.get_json()["message"] == "活动不存在或已失效"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
