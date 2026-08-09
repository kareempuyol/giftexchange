"""API 响应瘦身（性能轮）契约测试。

验证：
- 列表端点（mine/public）返回轻量载荷 api_event_summary：
  note 截断为预览（≤81 字符含省略号）、无 excludedPairs/ownerId/ownerName/
  archived/matchVisibility/isPublic/createdAt/updatedAt（列表零消费字段）
- 详情端点保持 api_event：note 全文不截断、仍带 excludedPairs；createdAt/updatedAt
  全前端零消费，从 api_event 移除

复用 tests/test_archive.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile

import pytest

PASSWORD = "Pass123!"
LONG_NOTE = "长" * 200  # 200 字符 > 80 截断阈值


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_api_slim_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-api-slim"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()  # 幂等：CREATE TABLE IF NOT EXISTS + run_migrations
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


def create_event(client, headers, title="瘦身测试活动", note=LONG_NOTE):
    r = client.post("/api/events", json={"title": title, "note": note, "budget": 100}, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


# 列表轻量载荷恰好这些字段
SUMMARY_FIELDS = {
    "code", "shortCode", "title", "budget", "note", "drawDate",
    "status", "participantCount", "coverImage", "maxParticipants",
}
# 列表零消费、必须从 summary 移除的字段
BANNED_IN_LIST = {
    "excludedPairs", "ownerId", "ownerName", "archived",
    "matchVisibility", "isPublic", "createdAt", "updatedAt",
}


class TestListSummaryPayload:
    def test_mine_list_slim(self, client):
        h, _ = register_and_login(client, "slim_mine")
        code = create_event(client, h)
        r = client.get("/api/events/mine", headers=h)
        assert r.status_code == 200, r.get_json()
        items = r.get_json()["data"]
        assert len(items) == 1
        ev = items[0]
        assert ev["code"] == code
        # note 截断为预览（80 字符 + 省略号）
        assert len(ev["note"]) == 81
        assert ev["note"].endswith("…")
        # 轻量载荷字段集合恰好
        assert set(ev) == SUMMARY_FIELDS
        assert not (BANNED_IN_LIST & set(ev))

    def test_public_list_slim(self, client):
        h, _ = register_and_login(client, "slim_public")
        create_event(client, h, title="公开瘦身活动", note=LONG_NOTE)
        r = client.get("/api/events/public?search=公开瘦身活动", headers=h)
        assert r.status_code == 200, r.get_json()
        events = r.get_json()["data"]["events"]
        assert len(events) == 1
        assert len(events[0]["note"]) == 81
        assert set(events[0]) == SUMMARY_FIELDS

    def test_short_note_untouched(self, client):
        h, _ = register_and_login(client, "slim_short")
        create_event(client, h, note="短说明")
        r = client.get("/api/events/mine", headers=h)
        assert r.status_code == 200, r.get_json()
        ev = r.get_json()["data"][0]
        assert ev["note"] == "短说明"  # 不截断、不加省略号


class TestDetailKeepsFullEvent:
    def test_detail_full_note_and_excluded_pairs(self, client):
        h, _ = register_and_login(client, "slim_detail")
        code = create_event(client, h)
        r = client.get(f"/api/events/{code}", headers=h)
        assert r.status_code == 200, r.get_json()
        ev = r.get_json()["data"]
        assert ev["note"] == LONG_NOTE  # 详情保持全文
        assert "excludedPairs" in ev  # 详情仍带互避规则
        # createdAt/updatedAt 全前端零消费，api_event 已移除
        assert "createdAt" not in ev
        assert "updatedAt" not in ev
