"""安全加固（波次1-A 审计修复）回归测试。

验证：
- 私密活动详情/参与者列表：非参与者 → 403；创建者/参与者 → 200；未登录 → 401
- 公开活动详情/参与者列表：任意登录用户 → 200（设计如此）
- 登录限速 IP 半区不可被 X-Forwarded-For 伪造绕过（默认不信任代理头）；
  TRUSTED_PROXIES 白名单开启后 XFF 生效（运维配置项）
- 安全头：X-Content-Type-Options / X-Frame-Options / Referrer-Policy 已下发
- CORS：仅 Origin 与配置一致（或配置为 *）时回显 ACAO

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
    saved_cors = os.environ.get("CORS_ORIGIN")
    tmp = tempfile.mkdtemp(prefix="gift_test_hardening_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-hardening"
    os.environ.pop("CORS_ORIGIN", None)
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
        if saved_cors is None:
            os.environ.pop("CORS_ORIGIN", None)
        else:
            os.environ["CORS_ORIGIN"] = saved_cors
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
def clean_limits():
    """每个测试前清空登录失败计数，避免跨测试污染（内存滑动窗口全局共享）。"""
    from wxcloudrun import helpers  # noqa: E402

    helpers._login_attempts.clear()
    yield
    helpers._login_attempts.clear()


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


def create_event(client, headers, title, **extra):
    payload = {"title": title}
    payload.update(extra)
    r = client.post("/api/events", json=payload, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def join_event(client, headers, code, contact=None):
    r = client.post(f"/api/events/{code}/join", json=contact or {}, headers=headers)
    # 组织者创建活动后自动加入：再次 join 幂等返回「你已加入该活动」（400），视为已加入
    if r.status_code == 400 and r.get_json().get("message") == "你已加入该活动":
        return
    assert r.status_code == 201, r.get_json()


class TestPrivateEventAccessControl:
    """P1 修复：私密活动详情/参与者列表仅创建者与参与者可见。"""

    def test_private_event_detail_403_for_outsider(self, client):
        owner, _ = register_and_login(client, "sec_owner_detail")
        outsider, _ = register_and_login(client, "sec_outsider_detail")
        code = create_event(client, owner, "SEC private detail", isPublic=False)

        r = client.get(f"/api/events/{code}", headers=outsider)
        assert r.status_code == 403, r.get_json()

    def test_private_event_detail_200_for_creator_and_participant(self, client):
        owner, _ = register_and_login(client, "sec_owner_ok")
        member, _ = register_and_login(client, "sec_member_ok")
        outsider, _ = register_and_login(client, "sec_outsider_ok")
        code = create_event(client, owner, "SEC private ok", isPublic=False)
        join_event(client, member, code)

        assert client.get(f"/api/events/{code}", headers=owner).status_code == 200
        assert client.get(f"/api/events/{code}", headers=member).status_code == 200
        assert client.get(f"/api/events/{code}", headers=outsider).status_code == 403

    def test_private_event_participants_403_for_outsider(self, client):
        owner, _ = register_and_login(client, "sec_owner_parts")
        member, _ = register_and_login(client, "sec_member_parts")
        outsider, _ = register_and_login(client, "sec_outsider_parts")
        code = create_event(client, owner, "SEC private parts", isPublic=False)
        join_event(client, member, code)

        r = client.get(f"/api/events/{code}/participants", headers=outsider)
        assert r.status_code == 403, r.get_json()
        # 创建者与参与者可看
        assert client.get(f"/api/events/{code}/participants", headers=owner).status_code == 200
        assert client.get(f"/api/events/{code}/participants", headers=member).status_code == 200

    def test_public_event_visible_to_any_logged_in(self, client):
        owner, _ = register_and_login(client, "sec_owner_pub")
        outsider, _ = register_and_login(client, "sec_outsider_pub")
        code = create_event(client, owner, "SEC public", isPublic=True)

        assert client.get(f"/api/events/{code}", headers=outsider).status_code == 200
        assert client.get(f"/api/events/{code}/participants", headers=outsider).status_code == 200

    def test_unauthenticated_401(self, client):
        owner, _ = register_and_login(client, "sec_owner_anon")
        code = create_event(client, owner, "SEC anon", isPublic=False)
        assert client.get(f"/api/events/{code}").status_code == 401
        assert client.get(f"/api/events/{code}/participants").status_code == 401


class TestLoginRateLimitSpoofing:
    """P1 修复：X-Forwarded-For 伪造不能再绕过登录 IP 限速。"""

    def test_spoofed_xff_cannot_bypass_ip_limit(self, client):
        """默认不信任代理头：换用户名避免触发用户名限速，验证 IP 半区不可被 XFF 绕过。"""
        for i in range(21):
            r = client.post(
                "/api/auth/login",
                json={"username": f"wronguser_{i}", "password": f"wrong{i}"},
                headers={"X-Forwarded-For": f"203.0.113.{i % 250 + 1}"},
            )
            if i < 20:
                assert r.status_code == 401, (i, r.get_json())
        # 第 21 次：同一真实来源 IP 已达 20 次失败阈值 → 429（XFF 伪造无效）
        assert r.status_code == 429, r.get_json()

    def test_trusted_proxy_xff_honored(self, client, monkeypatch):
        """运维配置 TRUSTED_PROXIES=127.0.0.1（测试客户端直连来源）后 XFF 才被信任。"""
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1")
        # 每请求换 XFF + 换用户名 → 任何单一 IP/用户名都不触达阈值
        for i in range(25):
            r = client.post(
                "/api/auth/login",
                json={"username": f"spoof_user_{i}", "password": f"wrong{i}"},
                headers={"X-Forwarded-For": f"203.0.113.{i % 250 + 1}"},
            )
        assert r.status_code == 401, r.get_json()  # 非 429：XFF 已生效（运维白名单场景）


class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        r = client.get("/")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        csp = r.headers.get("Content-Security-Policy") or ""
        assert "default-src 'self'" in csp

    def test_cors_no_header_without_config(self, client):
        """默认同源：任意 Origin 请求不获得跨域头。"""
        r = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
        assert r.headers.get("Access-Control-Allow-Origin") is None

    def test_cors_matching_origin_gets_header(self, client, monkeypatch):
        monkeypatch.setenv("CORS_ORIGIN", "https://gift.example.com")
        r = client.get("/api/health", headers={"Origin": "https://gift.example.com"})
        assert r.headers.get("Access-Control-Allow-Origin") == "https://gift.example.com"
        # 不匹配的 Origin 不回显
        r = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
        assert r.headers.get("Access-Control-Allow-Origin") is None

    def test_cors_star_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("CORS_ORIGIN", "*")
        r = client.get("/api/health", headers={"Origin": "https://anything.example.com"})
        assert r.headers.get("Access-Control-Allow-Origin") == "*"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
