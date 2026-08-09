"""公开站点配置 /api/site/config（微信轮：邀请制开关前端展示支撑）API 测试。

验证：
- 未登录可访问；默认 registration_enabled=true（无 app_settings 行时走默认值）
- registration_enabled=false 且已存在用户 → 配置返回 false，注册返回 403
- registration_enabled=false 但库中无用户（首个用户引导）→ 配置仍返回 true，注册放行
- 与 auth.register 的判定口径一致（首个用户豁免）

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
    tmp = tempfile.mkdtemp(prefix="gift_test_site_config_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-site-config"
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


def _get_config(client):
    r = client.get("/api/site/config")
    assert r.status_code == 200, r.get_json()
    payload = r.get_json()
    assert payload["code"] == 0, payload
    return payload["data"]


def test_config_public_and_default_enabled(client):
    """未登录可访问；无设置行时默认开放注册。"""
    data = _get_config(client)
    assert data["registration_enabled"] is True
    assert isinstance(data["site_name"], str) and data["site_name"]


def test_config_reflects_toggle_and_register_403(client):
    """关闭注册且库中有用户：配置返回 false，注册接口 403。"""
    from wxcloudrun.database import DB
    from wxcloudrun.helpers import save_setting

    # 先注册一个用户（此时仍是默认开放）
    r = client.post(
        "/api/auth/register",
        json={"username": "cfg_user1", "email": "cfg_user1@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()

    with DB() as db:
        save_setting(db, "registration_enabled", "false")

    data = _get_config(client)
    assert data["registration_enabled"] is False

    r = client.post(
        "/api/auth/register",
        json={"username": "cfg_user2", "email": "cfg_user2@test.com", "password": PASSWORD},
    )
    assert r.status_code == 403, r.get_json()
    assert r.get_json()["message"] == "注册已关闭"

    # 恢复默认，避免影响同模块后续测试
    with DB() as db:
        save_setting(db, "registration_enabled", "true")


def test_config_first_user_bootstrap(client):
    """关闭注册但库中无用户：配置返回 true（首个用户可注册引导），注册放行。"""
    from wxcloudrun.database import DB
    from wxcloudrun.helpers import save_setting

    with DB() as db:
        db.execute("DELETE FROM users")
        save_setting(db, "registration_enabled", "false")

    data = _get_config(client)
    assert data["registration_enabled"] is True

    r = client.post(
        "/api/auth/register",
        json={"username": "cfg_boot", "email": "cfg_boot@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()

    with DB() as db:
        save_setting(db, "registration_enabled", "true")
