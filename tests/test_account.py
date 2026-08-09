"""账号注销 + 数据导出（P0）API 测试。

验证：
- 注销后旧 token 调用任意接口 → 401；登录（deleted_<id>）→ 401「账号已注销」
- 错误密码注销 → 400（账号保持可用）
- 注销不物理删除：活动/晒图数据保留，只是用户被匿名化
- 注销后原名可被新用户重新注册
- 导出数据含个人资料 + 创建/参与的活动 + 晒图记录；未登录 401

复用 tests/test_gift_delete.py 的临时 SQLite + Flask test client 模式。
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
    tmp = tempfile.mkdtemp(prefix="gift_test_account_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-account"
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


def deactivate(client, headers, password=PASSWORD):
    return client.post("/api/auth/deactivate", json={"password": password}, headers=headers)


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
    """返回该 user_id 作为收礼人的 match（receiverId 是 user id）。"""
    r = client.get(f"/api/events/{code}/matches", headers=headers)
    assert r.status_code == 200, r.get_json()
    for m in r.get_json()["data"]:
        if m["receiverId"] == user_id:
            return m
    raise AssertionError(f"no match receiving for user {user_id}")


def put_gift(client, headers, code, match_id):
    r = client.put(
        f"/api/events/{code}/received-gift",
        json={"matchId": match_id, "rating": 5, "review": "晒图了", "photoUrl": "/uploads/acc_photo.png", "privacy": "photo"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()


class TestDeactivate:
    def test_old_token_401_after_deactivate(self, client):
        h1, _ = register_and_login(client, "acc_creator_token")
        h2, _ = register_and_login(client, "acc_user_token2")
        h3, _ = register_and_login(client, "acc_user_token3")
        code = create_event(client, h1, "ACC token event")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        # 注销前旧 token 正常
        assert client.get("/api/auth/me", headers=h1).status_code == 200
        r = deactivate(client, h1)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["code"] == 0

        # 旧 token 调用任意接口 → 401
        r = client.get("/api/auth/me", headers=h1)
        assert r.status_code == 401, r.get_json()
        assert "已注销" in r.get_json()["message"]
        assert client.get("/api/events/mine", headers=h1).status_code == 401
        assert client.get("/api/profile", headers=h1).status_code == 401

        # 注销不物理删除：活动仍存在（匿名化用户仍关联）
        r = client.get(f"/api/events/{code}/preview")
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["title"] == "ACC token event"

    def test_login_deactivated_returns_401(self, client):
        h1, uid = register_and_login(client, "acc_login_after")
        assert deactivate(client, h1).status_code == 200

        # 注销后用户名已改为 deleted_<id>，用该用户名登录 → 401「账号已注销」
        r = client.post("/api/auth/login", json={"username": f"deleted_{uid}", "password": PASSWORD})
        assert r.status_code == 401, r.get_json()
        assert "已注销" in r.get_json()["message"]

    def test_wrong_password_deactivate_400(self, client):
        h1, _ = register_and_login(client, "acc_wrong_pwd")
        r = deactivate(client, h1, password="WrongPass999")
        assert r.status_code == 400, r.get_json()
        # 账号未被注销，旧 token 仍可用
        assert client.get("/api/auth/me", headers=h1).status_code == 200

    def test_missing_password_deactivate_400(self, client):
        h1, _ = register_and_login(client, "acc_no_pwd")
        r = client.post("/api/auth/deactivate", json={}, headers=h1)
        assert r.status_code == 400, r.get_json()
        assert client.get("/api/auth/me", headers=h1).status_code == 200

    def test_username_reusable_after_deactivate(self, client):
        h1, _ = register_and_login(client, "acc_reuse_name")
        assert deactivate(client, h1).status_code == 200
        # 原名已释放，可被新用户注册（原邮箱同样可复用）
        r = client.post(
            "/api/auth/register",
            json={"username": "acc_reuse_name", "email": "acc_reuse_name@test.com", "password": PASSWORD},
        )
        assert r.status_code == 201, r.get_json()


class TestPasswordPolicy:
    """P2：密码不能与用户名相同（注册/修改密码，大小写不敏感）。"""

    def test_register_password_same_as_username_400(self, client):
        r = client.post(
            "/api/auth/register",
            json={"username": "pw_eq_name1", "email": "pw_eq_name1@test.com", "password": "pw_eq_name1"},
        )
        assert r.status_code == 400, r.get_json()
        assert "密码不能与用户名相同" in r.get_json()["message"]

    def test_register_password_case_insensitive_username_400(self, client):
        r = client.post(
            "/api/auth/register",
            json={"username": "pw_case1", "email": "pw_case1@test.com", "password": "PW_CASE1"},
        )
        assert r.status_code == 400, r.get_json()

    def test_change_password_same_as_username_400(self, client):
        h1, _ = register_and_login(client, "pw_change1")
        r = client.put(
            "/api/profile/password",
            json={"oldPassword": PASSWORD, "newPassword": "pw_change1"},
            headers=h1,
        )
        assert r.status_code == 400, r.get_json()
        assert "用户名" in r.get_json()["message"]
        # 账号不受影响：旧密码仍可登录
        r = client.post("/api/auth/login", json={"username": "pw_change1", "password": PASSWORD})
        assert r.status_code == 200, r.get_json()


class TestExportData:
    def test_export_contains_profile_events_and_gift_post(self, client):
        h1, uid1 = register_and_login(client, "acc_export_owner")
        h2, _ = register_and_login(client, "acc_export_user2")
        h3, _ = register_and_login(client, "acc_export_user3")
        code = create_event(client, h1, "ACC export event")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)
        m1 = matches_for_user(client, h1, code, uid1)
        put_gift(client, h1, code, m1["id"])

        r = client.get("/api/auth/export-data", headers=h1)
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]

        # 个人资料
        assert data["profile"]["username"] == "acc_export_owner"
        assert data["profile"]["email"] == "acc_export_owner@test.com"
        assert data["profile"]["displayName"]
        assert "phone" in data["profile"] and "address" in data["profile"] and "preference" in data["profile"]

        # 我创建的活动（标题/状态/日期）
        created = [e for e in data["createdEvents"] if e["title"] == "ACC export event"]
        assert created, data["createdEvents"]
        assert created[0]["status"] == "drawn" and created[0]["date"]

        # 我参与的活动
        joined = [e for e in data["joinedEvents"] if e["title"] == "ACC export event"]
        assert joined, data["joinedEvents"]

        # 我的晒图记录（rating/review/时间）
        posts = [g for g in data["giftPosts"] if g["review"] == "晒图了"]
        assert posts, data["giftPosts"]
        assert posts[0]["rating"] == 5 and posts[0]["date"]

    def test_export_requires_login(self, client):
        r = client.get("/api/auth/export-data")
        assert r.status_code == 401, r.get_json()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
