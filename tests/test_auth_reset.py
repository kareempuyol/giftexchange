"""忘记密码/找回密码（P0）API 测试。

验证：
- 生成 6 位数字码（15 分钟过期，单用户单码，新码覆盖旧码）→ 重置成功 → 新密码可登录、旧密码失效
- 错误码 → 400；过期码（手动把 expires_at 改为过去）→ 400
- 未注册用户名 → 404 友好提示（不泄露账号是否注册）
- 重置后码失效（不能重复使用）
- 限速：同 IP+用户名 连发 6 次 → 第 6 次 429

复用 tests/test_gift_delete.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_reset_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-reset"
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


def register(client, name):
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()


def forgot(client, name, by_email=False):
    payload = {"email": f"{name}@test.com"} if by_email else {"username": name}
    return client.post("/api/auth/forgot-password", json=payload)


def reset(client, name, code, password="NewPass456"):
    return client.post(
        "/api/auth/reset-password",
        json={"username": name, "code": code, "newPassword": password},
    )


def user_reset_code(name):
    """直连临时库读重置码（测试自证用）。"""
    from wxcloudrun.database import DB

    with DB() as db:
        row = db.get("SELECT reset_code, reset_code_expires_at FROM users WHERE username = ?", (name,))
        return row


class TestForgotPassword:
    def test_generates_6_digit_code_with_expiry(self, client):
        register(client, "reset_gen_code")
        r = forgot(client, "reset_gen_code")
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert len(data["code"]) == 6 and data["code"].isdigit()
        assert data["expiresIn"] == 15 * 60
        # 落库：单用户单码
        row = user_reset_code("reset_gen_code")
        assert row["reset_code"] == data["code"]
        assert row["reset_code_expires_at"]

    def test_forgot_by_email(self, client):
        register(client, "reset_by_email")
        r = forgot(client, "reset_by_email", by_email=True)
        assert r.status_code == 200, r.get_json()
        assert len(r.get_json()["data"]["code"]) == 6

    def test_new_code_overwrites_old(self, client):
        register(client, "reset_overwrite")
        first = forgot(client, "reset_overwrite").get_json()["data"]["code"]
        second = forgot(client, "reset_overwrite").get_json()["data"]["code"]
        assert user_reset_code("reset_overwrite")["reset_code"] == second
        # 旧码立即失效
        r = reset(client, "reset_overwrite", first)
        assert r.status_code == 400, r.get_json()

    def test_unknown_username_friendly_404(self, client):
        r = forgot(client, "reset_ghost_user")
        assert r.status_code == 404, r.get_json()
        assert r.get_json()["data"] is None

    def test_missing_account_400(self, client):
        r = client.post("/api/auth/forgot-password", json={})
        assert r.status_code == 400, r.get_json()


class TestResetPassword:
    def test_reset_success_new_login_works_old_fails(self, client):
        register(client, "reset_flow")
        code = forgot(client, "reset_flow").get_json()["data"]["code"]

        r = reset(client, "reset_flow", code)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["code"] == 0

        # 新密码可登录
        r = client.post("/api/auth/login", json={"username": "reset_flow", "password": "NewPass456"})
        assert r.status_code == 200, r.get_json()
        # 旧密码失效
        r = client.post("/api/auth/login", json={"username": "reset_flow", "password": PASSWORD})
        assert r.status_code == 401, r.get_json()
        # 重置码已清除
        row = user_reset_code("reset_flow")
        assert row["reset_code"] is None
        assert row["reset_code_expires_at"] is None

    def test_wrong_code_400(self, client):
        register(client, "reset_wrong_code")
        forgot(client, "reset_wrong_code")
        r = reset(client, "reset_wrong_code", "000000")
        assert r.status_code == 400, r.get_json()

    def test_non_numeric_code_400(self, client):
        register(client, "reset_bad_code")
        forgot(client, "reset_bad_code")
        r = reset(client, "reset_bad_code", "abc123")
        assert r.status_code == 400, r.get_json()

    def test_expired_code_400(self, client):
        register(client, "reset_expired")
        code = forgot(client, "reset_expired").get_json()["data"]["code"]
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        from wxcloudrun.database import DB

        with DB() as db:
            db.execute(
                "UPDATE users SET reset_code_expires_at = ? WHERE username = ?",
                (past, "reset_expired"),
            )
        r = reset(client, "reset_expired", code)
        assert r.status_code == 400, r.get_json()
        assert "过期" in r.get_json()["message"]

    def test_code_single_use(self, client):
        register(client, "reset_reuse")
        code = forgot(client, "reset_reuse").get_json()["data"]["code"]
        assert reset(client, "reset_reuse", code).status_code == 200
        # 重置成功后码已删除，不能重复使用
        r = reset(client, "reset_reuse", code)
        assert r.status_code == 400, r.get_json()

    def test_weak_password_400(self, client):
        register(client, "reset_weak")
        code = forgot(client, "reset_weak").get_json()["data"]["code"]
        r = reset(client, "reset_weak", code, password="abcdef")  # 无数字
        assert r.status_code == 400, r.get_json()
        r = reset(client, "reset_weak", code, password="123456")  # 无字母
        assert r.status_code == 400, r.get_json()

    def test_reset_unknown_user_400(self, client):
        r = reset(client, "reset_ghost_user", "123456", password="NewPass456")
        assert r.status_code == 400, r.get_json()


class TestRateLimit:
    def test_forgot_rate_limited_after_5(self, client):
        register(client, "reset_ratelimit")
        for _ in range(5):
            r = forgot(client, "reset_ratelimit")
            assert r.status_code == 200, r.get_json()
        r = forgot(client, "reset_ratelimit")
        assert r.status_code == 429, r.get_json()
        assert r.get_json()["data"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
