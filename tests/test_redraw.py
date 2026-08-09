"""重置抽签（redraw，P0）API 测试。

验证：
- 组织者重抽成功：旧 matchId 失效（my-match 返回新 matchId），通知新增 draw_redraw
- 非组织者重抽 → 403，旧 matches 不变
- open 状态重抽 → 400「活动尚未抽签」
- 互避无解时重抽 → 400，且旧 matches 原样保留（posted 数不变）
- 重抽后旧物流/晒图被清（原收礼人 received-gift 无数据，旧 matchId 消失）

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
    tmp = tempfile.mkdtemp(prefix="gift_test_redraw_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-redraw"
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


def create_event(client, headers, title, excluded=None):
    payload = {"title": title}
    if excluded is not None:
        payload["excludedPairs"] = excluded
    r = client.post("/api/events", json=payload, headers=headers)
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


def redraw(client, headers, code):
    return client.post(f"/api/events/{code}/redraw", headers=headers)


def event_status(client, headers, code):
    r = client.get(f"/api/events/{code}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["status"]


def my_match(client, headers, code):
    r = client.get(f"/api/events/{code}/my-match", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def event_matches(client, headers, code):
    r = client.get(f"/api/events/{code}/matches", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def notifications_of_type(client, headers, code, type_name):
    r = client.get("/api/notifications", headers=headers)
    assert r.status_code == 200, r.get_json()
    return [
        n
        for n in r.get_json()["data"]["items"]
        if n["type"] == type_name and n["eventCode"] == code
    ]


def wall_posted(client, headers, code):
    r = client.get(f"/api/events/{code}/gift-wall", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["posted"]


def put_gift(client, headers, code, match_id):
    r = client.put(
        f"/api/events/{code}/received-gift",
        json={"matchId": match_id, "rating": 5, "review": "晒图了", "photoUrl": "/uploads/redraw_photo.png", "privacy": "photo"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["receivedAt"], "晒图必须置 received_at"


def put_shipment(client, headers, code, match_id):
    r = client.put(
        f"/api/events/{code}/shipment",
        json={"matchId": match_id, "carrier": "SF", "trackingNumber": "SF123456789", "status": "shipped"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["data"]["trackingNumber"] == "SF123456789"


class TestRedraw:
    def test_organizer_redraw_success(self, client):
        h1, _ = register_and_login(client, "rd_creator_ok")
        h2, _ = register_and_login(client, "rd_user_ok2")
        h3, _ = register_and_login(client, "rd_user_ok3")
        code = create_event(client, h1, "RD redraw ok")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        old = my_match(client, h2, code)
        assert old is not None
        old_id = old["matchId"]

        r = redraw(client, h1, code)
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["code"] == 0
        assert len(body["data"]) == 3
        # 状态仍 drawn（重抽不改状态）
        assert event_status(client, h1, code) == "drawn"

        # 旧 matchId 失效：my-match 返回新 matchId（自增 id 不复用）
        new = my_match(client, h2, code)
        assert new is not None
        assert new["matchId"] != old_id

        # 通知新增：每个成员都收到 draw_redraw（与 draw_result 并存）
        for headers in (h1, h2, h3):
            redraw_notifs = notifications_of_type(client, headers, code, "draw_redraw")
            assert len(redraw_notifs) == 1, redraw_notifs
            assert "重置" in redraw_notifs[0]["message"]
            assert notifications_of_type(client, headers, code, "draw_result"), "旧通知保留"

    def test_non_organizer_cannot_redraw(self, client):
        h1, _ = register_and_login(client, "rd_creator_perm")
        h2, _ = register_and_login(client, "rd_user_perm2")
        h3, _ = register_and_login(client, "rd_user_perm3")
        code = create_event(client, h1, "RD redraw perm")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        before = event_matches(client, h1, code)
        r = redraw(client, h2, code)
        assert r.status_code == 403, r.get_json()
        # 旧 matches 原样保留
        assert event_matches(client, h1, code) == before

    def test_open_event_redraw_rejected(self, client):
        h1, _ = register_and_login(client, "rd_creator_open")
        h2, _ = register_and_login(client, "rd_user_open2")
        h3, _ = register_and_login(client, "rd_user_open3")
        code = create_event(client, h1, "RD redraw open")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)

        r = redraw(client, h1, code)
        assert r.status_code == 400, r.get_json()
        assert "尚未抽签" in r.get_json()["message"]
        assert event_status(client, h1, code) == "open"

    def test_unsolvable_redraw_preserves_old_matches(self, client):
        h1, uid1 = register_and_login(client, "rd_creator_excl")
        h2, uid2 = register_and_login(client, "rd_user_excl2")
        h3, _ = register_and_login(client, "rd_user_excl3")
        code = create_event(client, h1, "RD redraw excl")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        # 组织者晒一张图，作为"旧结果不可丢"的观测锚点
        m1 = next(m for m in event_matches(client, h1, code) if m["receiverId"] == uid1)
        put_gift(client, h1, code, m1["id"])
        assert wall_posted(client, h1, code) == 1
        before = event_matches(client, h1, code)

        # 抽签后组织者把互避规则改成无解（3 人 + 1 互避对）
        r = client.patch(f"/api/events/{code}", json={"excludedPairs": [[uid1, uid2]]}, headers=h1)
        assert r.status_code == 200, r.get_json()

        r = redraw(client, h1, code)
        assert r.status_code == 400, r.get_json()
        assert "互避规则太严格" in r.get_json()["message"]
        # 旧 matches 原样保留：条数、id、giver/receiver 都不变
        assert event_matches(client, h1, code) == before
        # posted 数不变
        assert wall_posted(client, h1, code) == 1

    def test_redraw_clears_shipment_and_gift_data(self, client):
        h1, uid1 = register_and_login(client, "rd_creator_clr")
        h2, uid2 = register_and_login(client, "rd_user_clr2")
        h3, _ = register_and_login(client, "rd_user_clr3")
        code = create_event(client, h1, "RD redraw clear")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        # m1 = uid1 作为收礼人的 match；其送礼人是 uid2 或 uid3
        m1 = next(m for m in event_matches(client, h1, code) if m["receiverId"] == uid1)
        giver_headers = h2 if m1["giverId"] == uid2 else h3
        put_gift(client, h1, code, m1["id"])
        put_shipment(client, giver_headers, code, m1["id"])

        # 重抽前：物流/晒图都有数据
        rg = client.get(f"/api/events/{code}/received-gift", headers=h1)
        assert rg.get_json()["data"]["giftPost"]["receivedAt"]
        mm = my_match(client, giver_headers, code)
        assert mm["matchId"] == m1["id"]
        assert mm["shipment"]["trackingNumber"] == "SF123456789"

        r = redraw(client, h1, code)
        assert r.status_code == 200, r.get_json()

        # 旧 matchId 消失
        new_ids = {m["id"] for m in event_matches(client, h1, code)}
        assert m1["id"] not in new_ids
        assert len(new_ids) == 3
        # 原收礼人：received-gift 无旧数据（新 match 未发货/未晒图）
        rg = client.get(f"/api/events/{code}/received-gift", headers=h1)
        assert rg.status_code == 200, rg.get_json()
        post = rg.get_json()["data"]["giftPost"]
        assert post["receivedAt"] == ""
        assert post["rating"] is None
        # 原送礼人：my-match 返回新 matchId，物流/悄悄话清空
        mm = my_match(client, giver_headers, code)
        assert mm["matchId"] != m1["id"]
        assert mm["shipment"]["trackingNumber"] == ""
        assert mm["note"] == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
