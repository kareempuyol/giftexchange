"""活动归档（archive，P0）API 测试。

验证：
- 已抽签活动归档成功：mine 列表不再出现，archived 列表出现，详情仍可访问
- 恢复（unarchive）后回 mine 列表，archived 列表清空
- open 状态归档 → 400「未抽签活动请直接删除」
- 非组织者归档/恢复 → 403
- joined / public 列表同样过滤已归档活动

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
    tmp = tempfile.mkdtemp(prefix="gift_test_archive_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-archive"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()  # 幂等：CREATE TABLE IF NOT EXISTS + run_migrations（含 v10 archived 列）
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


def mine_codes(client, headers):
    r = client.get("/api/events/mine", headers=headers)
    assert r.status_code == 200, r.get_json()
    return {e["code"] for e in r.get_json()["data"]}


def archived_codes(client, headers):
    r = client.get("/api/events/archived", headers=headers)
    assert r.status_code == 200, r.get_json()
    return {e["code"] for e in r.get_json()["data"]}


def joined_codes(client, headers):
    r = client.get("/api/events/joined", headers=headers)
    assert r.status_code == 200, r.get_json()
    return {e["code"] for e in r.get_json()["data"]}


class TestArchive:
    def test_archive_drawn_hides_from_mine_and_shows_in_archived(self, client):
        h1, _ = register_and_login(client, "ar_creator_ok")
        h2, _ = register_and_login(client, "ar_user_ok2")
        h3, _ = register_and_login(client, "ar_user_ok3")
        code = create_event(client, h1, "AR archive ok")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        assert code in mine_codes(client, h1)
        assert archived_codes(client, h1) == set()

        r = client.post(f"/api/events/{code}/archive", headers=h1)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["code"] == 0
        assert body["data"]["archived"] is True

        # mine 不再出现，archived 出现；详情仍可访问（归档只影响列表可见性）
        assert code not in mine_codes(client, h1)
        assert code in archived_codes(client, h1)
        r = client.get(f"/api/events/{code}", headers=h1)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["archived"] is True

    def test_unarchive_restores_to_mine(self, client):
        h1, _ = register_and_login(client, "ar_creator_restore")
        h2, _ = register_and_login(client, "ar_user_restore2")
        h3, _ = register_and_login(client, "ar_user_restore3")
        code = create_event(client, h1, "AR restore")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)
        r = client.post(f"/api/events/{code}/archive", headers=h1)
        assert r.status_code == 200, r.get_json()

        r = client.post(f"/api/events/{code}/unarchive", headers=h1)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["data"]["archived"] is False

        assert code in mine_codes(client, h1)
        assert code not in archived_codes(client, h1)

    def test_open_event_archive_rejected_400(self, client):
        h1, _ = register_and_login(client, "ar_creator_open")
        code = create_event(client, h1, "AR open event")
        r = client.post(f"/api/events/{code}/archive", headers=h1)
        body = r.get_json()
        assert r.status_code == 400, body
        assert body["code"] == -1
        assert "未抽签活动请直接删除" in body["message"]
        # open 活动未被打上归档标记
        assert code in mine_codes(client, h1)
        assert code not in archived_codes(client, h1)

    def test_non_organizer_cannot_archive_or_unarchive(self, client):
        h1, _ = register_and_login(client, "ar_creator_perm")
        h2, _ = register_and_login(client, "ar_user_perm2")
        h3, _ = register_and_login(client, "ar_user_perm3")
        code = create_event(client, h1, "AR perm")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        r = client.post(f"/api/events/{code}/archive", headers=h2)
        assert r.status_code == 403, r.get_json()
        assert code not in archived_codes(client, h1)

        # 组织者归档后，非组织者也不能恢复
        client.post(f"/api/events/{code}/archive", headers=h1)
        r = client.post(f"/api/events/{code}/unarchive", headers=h2)
        assert r.status_code == 403, r.get_json()
        assert code in archived_codes(client, h1)

    def test_archived_event_hidden_from_joined_and_public(self, client):
        h1, _ = register_and_login(client, "ar_creator_join")
        h2, _ = register_and_login(client, "ar_user_join2")
        h3, _ = register_and_login(client, "ar_user_join3")
        code = create_event(client, h1, "AR joined list")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)
        assert code in joined_codes(client, h2)

        client.post(f"/api/events/{code}/archive", headers=h1)
        # 参与者视角：joined 列表不再出现已归档活动
        assert code not in joined_codes(client, h2)
        # 公开列表同样过滤（归档不改变 is_public，但列表隐藏）
        r = client.get("/api/events/public", headers=h2)
        assert r.status_code == 200, r.get_json()
        assert code not in {e["code"] for e in r.get_json()["data"]["events"]}
