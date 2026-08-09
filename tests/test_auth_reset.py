"""忘记密码/找回密码（P0）API 测试。

验证：
- 生成 6 位数字码（15 分钟过期，单用户单码，新码覆盖旧码）→ 重置成功 → 新密码可登录、旧密码失效
- 错误码 → 400；过期码（手动把 expires_at 改为过去）→ 400
- 安全默认（P0 修复）：未开演示模式时响应不返回 code，账号不存在统一 200（防枚举）；
  演示模式（RESET_CODE_IN_RESPONSE=1）下响应返回 code（本模块 ctx 开启，测码语义）
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
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。

    本模块测「码的语义」（生成/覆盖/过期/单次使用），因此开演示模式
    RESET_CODE_IN_RESPONSE=1（响应返回 code）；安全默认行为在
    TestSecureDefault 里用 monkeypatch 关掉该变量单独验证。
    """
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    saved_reset = os.environ.get("RESET_CODE_IN_RESPONSE")
    tmp = tempfile.mkdtemp(prefix="gift_test_reset_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-reset"
    os.environ["RESET_CODE_IN_RESPONSE"] = "1"
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
        if saved_reset is None:
            os.environ.pop("RESET_CODE_IN_RESPONSE", None)
        else:
            os.environ["RESET_CODE_IN_RESPONSE"] = saved_reset
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

    def test_unknown_username_no_enumeration(self, client):
        """账号不存在统一 200 且无 code（防枚举，P0 修复）。"""
        r = forgot(client, "reset_ghost_user")
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert "code" not in data and data["expiresIn"] == 15 * 60

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

    def test_password_same_as_username_400(self, client):
        # P2：新密码不能与用户名相同（含大小写不敏感）
        register(client, "reset_same1")
        code = forgot(client, "reset_same1").get_json()["data"]["code"]
        r = reset(client, "reset_same1", code, password="reset_same1")
        assert r.status_code == 400, r.get_json()
        assert "用户名" in r.get_json()["message"]
        r = reset(client, "reset_same1", code, password="RESET_SAME1")  # 大写变体同样拒绝
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


class TestResetRateLimit:
    """P0 残留修复：reset-password 必须与 forgot 共用限速窗口（防暴力猜 6 位码）"""

    def test_reset_bruteforce_rate_limited(self, client):
        # 先发一次 forgot 拿到一个有效码（消耗 1 次限额）
        r = forgot(client, "reset_rl_victim")
        assert r.status_code == 200
        # 连续猜码：超过窗口上限后应 429
        got_429 = False
        for i in range(30):
            r = client.post(
                "/api/auth/reset-password",
                json={"username": "reset_rl_victim", "code": f"{i:06d}", "newPassword": "Brute123"},
            )
            if r.status_code == 429:
                got_429 = True
                break
        assert got_429, "reset-password 无限速：6 位码可被暴力猜解"


class TestSecureDefault:
    """P0 修复：默认（未开演示模式）响应绝不返回重置码，防止任意人重置他人密码。"""

    def test_code_not_in_response_by_default(self, client, monkeypatch):
        monkeypatch.delenv("RESET_CODE_IN_RESPONSE", raising=False)
        register(client, "reset_secure_default")
        r = forgot(client, "reset_secure_default")
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert "code" not in data
        assert data["expiresIn"] == 15 * 60
        # 码仍落库（走邮件/短信通道时凭库内码重置）
        row = user_reset_code("reset_secure_default")
        assert row["reset_code"] and row["reset_code_expires_at"]

    def test_reset_still_works_with_db_code(self, client, monkeypatch):
        monkeypatch.delenv("RESET_CODE_IN_RESPONSE", raising=False)
        register(client, "reset_secure_flow")
        forgot(client, "reset_secure_flow")
        row = user_reset_code("reset_secure_flow")
        r = reset(client, "reset_secure_flow", row["reset_code"])
        assert r.status_code == 200, r.get_json()
        # 新密码可登录
        r = client.post("/api/auth/login", json={"username": "reset_secure_flow", "password": "NewPass456"})
        assert r.status_code == 200, r.get_json()

    def test_unknown_account_200_no_code(self, client, monkeypatch):
        """账号不存在不返回 404（原 404 是账号枚举 oracle）。"""
        monkeypatch.delenv("RESET_CODE_IN_RESPONSE", raising=False)
        r = forgot(client, "reset_secure_ghost")
        assert r.status_code == 200, r.get_json()
        assert "code" not in r.get_json()["data"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
