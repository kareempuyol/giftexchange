"""短码安全（reset-short-code + 短码查找限速，P0）API 测试。

验证：
- 组织者重置短码：旧短码解析失败（404），新短码解析成功（200），返回值带新短码
- 非组织者重置 → 403，旧短码仍有效
- 同 IP 连续 10 次无效短码查找 → 第 11 次 429（1 小时滑动窗口）
- 窗口过期（mock 时间 +2h）后计数重置，不再 429

复用 tests/test_gift_delete.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile
import time

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_shortcode_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-shortcode"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()
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


@pytest.fixture(autouse=True)
def clean_rate_limit():
    """每个测试前清空短码失败计数，避免跨测试污染（内存滑动窗口全局共享）。"""
    from wxcloudrun import helpers  # noqa: E402

    helpers._short_code_failures.clear()
    yield
    helpers._short_code_failures.clear()


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


def short_code_of(client, headers, code):
    r = client.get(f"/api/events/{code}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["shortCode"]


def preview_status(client, code):
    """游客短码落地页访问（无鉴权）——陌生人刷邀请链接的真实攻击面。"""
    return client.get(f"/api/events/{code}/preview")


class TestResetShortCode:
    def test_reset_invalidates_old_code_and_returns_new(self, client):
        h1, _ = register_and_login(client, "sc_creator_ok")
        code = create_event(client, h1, "SC reset ok")
        old = short_code_of(client, h1, code)
        assert old

        r = client.post(f"/api/events/{code}/reset-short-code", headers=h1)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["code"] == 0
        assert body["data"]["shortCode"] != old

        new = body["data"]["shortCode"]
        assert len(new) == 6
        # 旧短码失效：短码解析失败（404）；新短码成功
        r = client.get(f"/api/events/{old}", headers=h1)
        assert r.status_code == 404, r.get_json()
        r = client.get(f"/api/events/{new}", headers=h1)
        assert r.status_code == 200, r.get_json()
        # 持久化：详情接口返回的就是新短码
        assert short_code_of(client, h1, code) == new

    def test_non_organizer_cannot_reset(self, client):
        h1, _ = register_and_login(client, "sc_creator_perm")
        h2, _ = register_and_login(client, "sc_user_perm2")
        code = create_event(client, h1, "SC perm")
        old = short_code_of(client, h1, code)

        r = client.post(f"/api/events/{code}/reset-short-code", headers=h2)
        assert r.status_code == 403, r.get_json()
        # 旧短码未被改动，仍有效
        assert short_code_of(client, h1, code) == old
        assert client.get(f"/api/events/{old}", headers=h1).status_code == 200


class TestShortCodeRateLimit:
    def test_10_failures_then_429(self, client):
        register_and_login(client, "sc_ratelimit")
        bad = "ZZZZZZ"  # 合法字符集但不存在 → 短码查找失败
        for _ in range(10):
            r = preview_status(client, bad)
            assert r.status_code == 404, r.get_json()
        # 第 11 次：同 IP 已达 10 次失败 → 429
        r = preview_status(client, bad)
        body = r.get_json()
        assert r.status_code == 429, body
        assert body["data"] is None

    def test_window_expiry_resets_counter(self, client, monkeypatch):
        from wxcloudrun import helpers  # noqa: E402

        register_and_login(client, "sc_ratelimit_expire")
        bad = "QQQQQQ"
        for _ in range(10):
            assert preview_status(client, bad).status_code == 404
        assert preview_status(client, bad).status_code == 429

        # 窗口过期：mock time 前进 2 小时（> 1h 窗口），旧失败全部滑出
        real_now = time.time()
        monkeypatch.setattr(helpers.time, "time", lambda: real_now + 2 * 60 * 60)
        r = preview_status(client, bad)
        assert r.status_code == 404, r.get_json()  # 不再 429，且该次失败重新计时
