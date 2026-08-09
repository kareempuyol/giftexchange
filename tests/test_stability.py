"""稳定性专项回归测试（hackathon 波次2-B）。

覆盖：
1. 崩溃容错：未捕获 DB 异常 → 500 JSON「服务开小差了，请重试」，不泄露堆栈
2. 输入容错：create_event budget 非法字符串 → 400 明确提示（原实现 int() 会 500）
3. 数据完整性：删除活动 → notifications 显式清理 + participants/matches/gift_likes 级联清空

复用 tests/test_gift_delete.py 的临时 SQLite + Flask test client 模式。
"""
import os
import sqlite3
import tempfile

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_stability_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-stability"
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


# ---------- 1. 崩溃容错：未捕获 DB 异常 → 友好 500 ----------

def test_uncaught_db_error_returns_friendly_500(ctx, monkeypatch):
    """路由内未捕获的 DB 异常（如数据库锁定）→ 500 JSON「服务开小差了，请重试」，不泄露堆栈。"""
    saved_testing = ctx.config["TESTING"]
    ctx.config["TESTING"] = False  # TESTING 下异常会直接传播；关闭后才走 500 errorhandler
    try:
        from wxcloudrun import event_routes

        def boom(*_a, **_k):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(event_routes, "fetch_event", boom)

        c = ctx.test_client()
        headers, _uid = register_and_login(c, f"five_hundred_{os.getpid()}")
        r = c.get("/api/events/NOPE", headers=headers)
        assert r.status_code == 500
        body = r.get_json()
        assert body["code"] == -1
        assert body["data"] is None
        assert body["message"] == "服务开小差了，请重试"
        # 响应体不泄露异常细节/堆栈
        raw = r.get_data(as_text=True).lower()
        assert "database is locked" not in raw
        assert "traceback" not in raw
    finally:
        ctx.config["TESTING"] = saved_testing


# ---------- 2. 输入容错：budget 非法字符串不再 500 ----------

def test_create_event_budget_invalid_returns_400(client):
    headers, _uid = register_and_login(client, f"budget_{os.getpid()}")
    r = client.post("/api/events", json={"title": "预算测试", "budget": "abc"}, headers=headers)
    assert r.status_code == 400, r.get_json()
    assert r.get_json()["message"] == "预算格式无效"


def test_create_event_budget_float_returns_400(client):
    headers, _uid = register_and_login(client, f"budget2_{os.getpid()}")
    r = client.post("/api/events", json={"title": "预算测试", "budget": "12.5"}, headers=headers)
    assert r.status_code == 400, r.get_json()
    assert r.get_json()["message"] == "预算格式无效"


# ---------- 3. 数据完整性：删除活动级联清理完整 ----------

def test_delete_event_cascades_all_related_rows(client):
    """删除活动后：notifications（无 FK 需显式清）、participants/matches/gift_likes（FK 级联）全部清空。"""
    creator_headers, creator_id = register_and_login(client, f"del_owner_{os.getpid()}")
    user_headers, user_id = register_and_login(client, f"del_user_{os.getpid()}")
    third_headers, _third_id = register_and_login(client, f"del_user3_{os.getpid()}")

    code = create_event(client, creator_headers, "级联删除测试")
    join_event(client, creator_headers, code)  # 组织者需自己加入；3 人才能完成抽签
    join_event(client, user_headers, code)
    join_event(client, third_headers, code)

    # 抽签 → 产生 matches + draw_result 通知
    r = client.post(f"/api/events/{code}/draw", headers=creator_headers)
    assert r.status_code == 200, r.get_json()

    from wxcloudrun.database import DB

    with DB() as db:
        event = db.get("SELECT id FROM events WHERE code = ?", (code,))
        event_id = event["id"]
        match = db.get("SELECT id FROM matches WHERE event_id = ? LIMIT 1", (event_id,))
        assert match is not None
        # 再造一条点赞（gift_likes）+ 一条站内通知，验证全链路清理
        db.execute(
            "INSERT INTO gift_likes (match_id, user_id) VALUES (?, ?)",
            (match["id"], user_id),
        )
        db.execute(
            "INSERT INTO notifications (user_id, event_id, match_id, type, title, message) "
            "VALUES (?, ?, ?, 'unit_test', 't', 'm')",
            (user_id, event_id, match["id"]),
        )

    r = client.delete(f"/api/events/{code}", headers=creator_headers)
    assert r.status_code == 200, r.get_json()

    with DB() as db:
        assert db.get("SELECT id FROM events WHERE id = ?", (event_id,)) is None
        assert db.get("SELECT id FROM matches WHERE event_id = ?", (event_id,)) is None
        assert db.get("SELECT id FROM participants WHERE event_id = ?", (event_id,)) is None
        assert db.get("SELECT id FROM gift_likes WHERE match_id = ?", (match["id"],)) is None
        # 核心回归点：notifications 无 event_id 外键，必须显式清理，不允许孤儿通知残留
        orphan = db.get("SELECT id FROM notifications WHERE event_id = ?", (event_id,))
        assert orphan is None, f"删除活动后残留孤儿通知: {orphan}"


def test_delete_event_non_creator_forbidden(client):
    headers, _uid = register_and_login(client, f"del_other_{os.getpid()}")
    owner_headers, _owner_id = register_and_login(client, f"del_owner2_{os.getpid()}")
    code = create_event(client, owner_headers, "越权删除测试")
    r = client.delete(f"/api/events/{code}", headers=headers)
    assert r.status_code == 403, r.get_json()
