"""「我的收件信息」更新端点：创建者自动加入后补填收件信息/心愿单的入口。

覆盖用户反馈的真实缺口：创建活动自动报名 → 状态「待填信息」→ 但没有任何
地方可以填。PUT /events/<code>/my-contact 就是那个入口。

复用 tests/test_member_status.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile
import uuid

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_my_contact_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-my-contact"
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


def unique(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def create_event(client, headers, title="测试活动"):
    r = client.post("/api/events", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def my_contact(client, headers, code):
    r = client.get(f"/api/events/{code}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["myContact"]


def test_creator_autofill_contact(client):
    """创建者自动加入 → myContact 为空 → PUT 补填 → 详情可读回（缺口闭环）"""
    headers, _ = register_and_login(client, unique("creator"))
    code = create_event(client, headers, "自动报名补填测试")

    # 1. 自动加入后，详情里 myContact 存在但收件字段为空（缺口复现）
    mc = my_contact(client, headers, code)
    assert mc is not None, "创建者自动加入后应有自己的 myContact"
    assert mc["phone"] == ""
    assert mc["address"] == ""

    # 2. PUT 补填
    r = client.put(
        f"/api/events/{code}/my-contact",
        json={
            "receiverName": "张三",
            "phone": "13900001111",
            "address": "上海市南京路 100 号",
            "preferenceLikes": "科幻小说",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["code"] == 0

    # 3. 读回验证（详情接口预填数据源）
    mc = my_contact(client, headers, code)
    assert mc["receiverName"] == "张三"
    assert mc["phone"] == "13900001111"
    assert mc["address"] == "上海市南京路 100 号"
    assert mc["preferenceLikes"] == "科幻小说"


def test_update_profile_passthrough(client):
    """updateProfile=true 同步回写个人常用信息（与 join 语义一致）"""
    headers, _ = register_and_login(client, unique("prof"))
    code = create_event(client, headers)

    r = client.put(
        f"/api/events/{code}/my-contact",
        json={
            "receiverName": "李四",
            "phone": "13700002222",
            "address": "广州市天河路 2 号",
            "preferenceLikes": "手办",
            "updateProfile": True,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()

    prof = client.get("/api/profile", headers=headers)
    assert prof.status_code == 200
    data = prof.get_json()["data"]
    assert data["receiverName"] == "李四"
    assert data["address"] == "广州市天河路 2 号"


def test_non_participant_forbidden(client):
    """没加入活动的人不能改（403）"""
    headers, _ = register_and_login(client, unique("outsider"))
    owner_headers, _ = register_and_login(client, unique("owner"))
    code = create_event(client, owner_headers)

    r = client.put(
        f"/api/events/{code}/my-contact",
        json={"receiverName": "X", "phone": "136", "address": "某地"},
        headers=headers,
    )
    assert r.status_code == 403


def test_unauthenticated_401(client):
    r = client.put("/api/events/ABCD12/my-contact", json={"receiverName": "X"})
    assert r.status_code == 401


def test_wish_links_round_trip(client):
    """wishLinks 数组 → 存 JSON → myContact 返回换行文本（编辑表单往返）"""
    headers, _ = register_and_login(client, unique("wish"))
    code = create_event(client, headers)

    r = client.put(
        f"/api/events/{code}/my-contact",
        json={
            "receiverName": "心愿人",
            "phone": "13600001234",
            "address": "某地",
            "wishLinks": ["https://a.com/1", "https://b.com/2"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    mc = my_contact(client, headers, code)
    assert mc["wishLinks"] == "https://a.com/1\nhttps://b.com/2"


def test_validation_rejects_overlong_phone(client):
    """校验与 join 同步：超长字段被拒"""
    headers, _ = register_and_login(client, unique("val"))
    code = create_event(client, headers)

    r = client.put(
        f"/api/events/{code}/my-contact",
        json={"receiverName": "王五", "phone": "1" * 51, "address": "某地"},
        headers=headers,
    )
    assert r.status_code == 400


def test_editable_after_draw(client):
    """抽签后仍可改自己的收件信息（送礼人看到更新后的值）"""
    creator_headers, _ = register_and_login(client, unique("postdraw"))
    code = create_event(client, creator_headers)
    joiner_headers, _ = register_and_login(client, unique("joiner"))
    r = client.post(
        f"/api/events/{code}/join",
        json={"receiverName": "接", "phone": "13800000001", "address": "旧地址"},
        headers=joiner_headers,
    )
    assert r.status_code == 201, r.get_json()
    # 抽签要求 ≥3 人（2 人只是互送）——补第三个参与者
    joiner2_headers, _ = register_and_login(client, unique("joiner2"))
    r = client.post(
        f"/api/events/{code}/join",
        json={"receiverName": "接二", "phone": "13800000002", "address": "旧地址二"},
        headers=joiner2_headers,
    )
    assert r.status_code == 201, r.get_json()

    r = client.post(f"/api/events/{code}/draw", json={}, headers=creator_headers)
    assert r.status_code == 200, r.get_json()

    r = client.put(
        f"/api/events/{code}/my-contact",
        json={"receiverName": "新收件人", "phone": "13500003333", "address": "成都市春熙路 3 号"},
        headers=creator_headers,
    )
    assert r.status_code == 200, r.get_json()
    mc = my_contact(client, creator_headers, code)
    assert mc["address"] == "成都市春熙路 3 号"
