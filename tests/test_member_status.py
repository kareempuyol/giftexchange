"""成员状态列 + 催办（P0）API 测试。

验证：
- participants 每行返回 status：joined / ready / shipped / posted 随成员完成度流转
- 组织者视角 POST remind 只提醒未完成成员（未填收件信息 / 未发货 / 未晒图），组织者自己不算
- 已完成（posted）成员收不到 remind 通知
- 非组织者 remind → 403；未登录 remind → 401

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
    tmp = tempfile.mkdtemp(prefix="gift_test_member_status_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-member-status"
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


def create_event(client, headers, title):
    r = client.post("/api/events", json={"title": title}, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def join_event(client, headers, code, contact=None):
    """join；contact 非空时在加入时带上收件信息（phone/address → ready）。"""
    r = client.post(f"/api/events/{code}/join", json=contact or {}, headers=headers)
    # 组织者创建活动后自动加入：再次 join 幂等返回「你已加入该活动」（400），视为已加入
    if r.status_code == 400 and r.get_json().get("message") == "你已加入该活动":
        return
    assert r.status_code == 201, r.get_json()


def draw(client, headers, code):
    r = client.post(f"/api/events/{code}/draw", headers=headers)
    assert r.status_code == 200, r.get_json()


def participants(client, headers, code):
    r = client.get(f"/api/events/{code}/participants", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["participants"]


def status_of(parts, user_id):
    for p in parts:
        if p["userId"] == user_id:
            return p["status"]
    raise AssertionError(f"no participant row for user {user_id}")


def my_giving_match(client, headers, code):
    """该用户作为送礼人的 match（my-match：giver 视角）。"""
    r = client.get(f"/api/events/{code}/my-match", headers=headers)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    assert data, "no giving match"
    return data


def ship_gift(client, headers, code, match_id):
    r = client.put(
        f"/api/events/{code}/shipment",
        json={"matchId": match_id, "carrier": "SF", "trackingNumber": "SF123456", "status": "shipped"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()


def receiving_match(client, headers, code, user_id):
    """该 user_id 作为收礼人的 match（组织者可看 /matches 全量）。"""
    r = client.get(f"/api/events/{code}/matches", headers=headers)
    assert r.status_code == 200, r.get_json()
    for m in r.get_json()["data"]:
        if m["receiverId"] == user_id:
            return m
    raise AssertionError(f"no match receiving for user {user_id}")


def post_gift(client, headers, code, match_id):
    r = client.put(
        f"/api/events/{code}/received-gift",
        json={"matchId": match_id, "rating": 5, "review": "晒图了", "photoUrl": "/uploads/ms_photo.png", "privacy": "photo"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()


def remind(client, headers, code):
    return client.post(f"/api/events/{code}/remind", headers=headers)


def remind_notifications(client, headers):
    """该用户收到的 type='remind' 通知条数。"""
    r = client.get("/api/notifications", headers=headers)
    assert r.status_code == 200, r.get_json()
    return sum(1 for item in r.get_json()["data"]["items"] if item["type"] == "remind")


class TestMemberStatus:
    def test_status_lifecycle_joined_ready_shipped_posted(self, client):
        h1, uid1 = register_and_login(client, "ms_creator_life")
        h2, uid2 = register_and_login(client, "ms_user_life2")
        h3, uid3 = register_and_login(client, "ms_user_life3")
        code = create_event(client, h1, "MS lifecycle")

        # 组织者与 h3 不带收件信息 join → joined；h2 带收件信息 join → ready
        join_event(client, h1, code)
        join_event(client, h2, code, contact={"receiverName": "小明", "phone": "13800000001", "address": "北京市朝阳区"})
        join_event(client, h3, code)
        parts = participants(client, h1, code)
        assert status_of(parts, uid1) == "joined"
        assert status_of(parts, uid2) == "ready"
        assert status_of(parts, uid3) == "joined"

        draw(client, h1, code)

        # h2 发货后 → shipped（其送礼 match 有 shipment）
        ship_gift(client, h2, code, my_giving_match(client, h2, code)["matchId"])
        parts = participants(client, h1, code)
        assert status_of(parts, uid2) == "shipped"

        # h3 晒图后 → posted（其收礼 match 有 gift_review）
        post_gift(client, h3, code, receiving_match(client, h1, code, uid3)["id"])
        parts = participants(client, h1, code)
        assert status_of(parts, uid3) == "posted"
        # 组织者仍未填收件信息 → 保持 joined
        assert status_of(parts, uid1) == "joined"

    def test_remind_only_incomplete_members(self, client):
        h1, uid1 = register_and_login(client, "ms_creator_remind")
        h2, uid2 = register_and_login(client, "ms_user_remind2")
        h3, uid3 = register_and_login(client, "ms_user_remind3")
        code = create_event(client, h1, "MS remind")
        join_event(client, h1, code)
        join_event(client, h2, code, contact={"receiverName": "小张", "phone": "13800000002", "address": "上海市徐汇区"})
        join_event(client, h3, code, contact={"receiverName": "小李", "phone": "13800000003", "address": "广州市天河区"})
        draw(client, h1, code)

        # h2：发货但未晒图 → shipped（未完成）
        ship_gift(client, h2, code, my_giving_match(client, h2, code)["matchId"])
        # h3：发货且晒图 → posted（已完成）
        ship_gift(client, h3, code, my_giving_match(client, h3, code)["matchId"])
        post_gift(client, h3, code, receiving_match(client, h1, code, uid3)["id"])

        r = remind(client, h1, code)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["code"] == 0
        # 只提醒未完成的 h2（1 人）；组织者自己不算、已完成的 h3 不收
        assert r.get_json()["data"]["reminded"] == 1

        # 未完成者 h2 收到 remind 通知（message 含活动名）；h3 与组织者收不到
        assert remind_notifications(client, h2) == 1
        items = client.get("/api/notifications", headers=h2).get_json()["data"]["items"]
        n = next(item for item in items if item["type"] == "remind")
        assert n["eventCode"] == code
        assert "MS remind" in n["message"]
        assert remind_notifications(client, h3) == 0
        assert remind_notifications(client, h1) == 0

    def test_remind_non_organizer_forbidden(self, client):
        h1, _ = register_and_login(client, "ms_creator_perm")
        h2, _ = register_and_login(client, "ms_user_perm2")
        code = create_event(client, h1, "MS remind perm")
        join_event(client, h1, code)
        join_event(client, h2, code)

        r = remind(client, h2, code)
        assert r.status_code == 403, r.get_json()
        # 非组织者调用不产生任何通知
        assert remind_notifications(client, h2) == 0

    def test_remind_requires_login(self, client):
        h1, _ = register_and_login(client, "ms_creator_auth")
        code = create_event(client, h1, "MS remind auth")
        join_event(client, h1, code)

        r = client.post(f"/api/events/{code}/remind")
        assert r.status_code == 401, r.get_json()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
