"""Task A：活动流程步骤条 —— derive_flow_state 纯函数边界 + event detail 接口返回 flowState。

- 纯函数边界：recruiting（open+未截止/无截止）→ drawing（open+已过截止）
  → active（drawn+部分晒）→ completed（drawn+全晒）
- 接口：detail 返回 flowState，且与 status/截止时间/晒图进度推导一致
"""
import os
import tempfile

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module", autouse=True)
def _env():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量（与 test_draw_api.py 同模式）。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_flow_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-flow"
    try:
        from wxcloudrun.database import init_schema  # noqa: E402

        init_schema()
        yield
    finally:
        if saved_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved_db
        if saved_jwt is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = saved_jwt


def flow(event, posted=0, total=0):
    from wxcloudrun.event_routes import derive_flow_state  # 懒导入：env 已就位

    return derive_flow_state(event, posted, total)


# ---------- 纯函数边界 ----------

def test_recruiting_open_no_deadline():
    # 无截止时间 → 视为未截止 → recruiting
    assert flow({"status": "open", "sign_up_deadline": ""}) == "recruiting"


def test_recruiting_open_future_deadline():
    assert flow({"status": "open", "sign_up_deadline": "2999-01-01"}) == "recruiting"


def test_recruiting_ignores_posted_counts():
    # open 阶段不看 posted/total（抽签前 matches 不存在，posted 恒为 0）
    assert flow({"status": "open", "sign_up_deadline": ""}, posted=0, total=5) == "recruiting"


def test_drawing_open_past_deadline():
    assert flow({"status": "open", "sign_up_deadline": "2020-01-01"}) == "drawing"


def test_drawing_open_past_deadline_iso():
    # ISO datetime 带偏移（前端 toISOString 产物）
    assert flow({"status": "open", "sign_up_deadline": "2020-06-01T12:00:00+00:00"}) == "drawing"


def test_active_drawn_partial_posted():
    assert flow({"status": "drawn"}, posted=1, total=3) == "active"


def test_active_drawn_none_posted():
    assert flow({"status": "drawn"}, posted=0, total=3) == "active"


def test_completed_drawn_all_posted():
    assert flow({"status": "drawn"}, posted=3, total=3) == "completed"


def test_completed_drawn_over_posted():
    # 边界：posted 数超过 total 也按全晒处理（posted 不会越界，防御性断言）
    assert flow({"status": "drawn"}, posted=4, total=3) == "completed"


def test_drawn_zero_participants_not_completed():
    # 0 人参与不能算完结
    assert flow({"status": "drawn"}, posted=0, total=0) == "active"


def test_unknown_status_falls_back_active():
    # 未知状态（历史/异常数据）兜底进行中
    assert flow({"status": "cancelled"}) == "active"


# ---------- detail 接口返回 flowState ----------

@pytest.fixture(scope="module")
def client(_env):
    from wxcloudrun import app as flask_app  # noqa: E402

    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def register_and_login(client, name):
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.local", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def create_event(client, headers, title, draw_date=""):
    payload = {"title": title}
    if draw_date:
        payload["drawDate"] = draw_date
    r = client.post("/api/events", json=payload, headers=headers)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["code"]


def detail_flow(client, headers, code):
    r = client.get(f"/api/events/{code}", headers=headers)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    assert "flowState" in data, "detail 必须返回 flowState"
    return data["flowState"]


class TestDetailFlowState:
    def test_open_future_deadline_recruiting(self, client):
        h1, _ = register_and_login(client, "flow_owner1")
        code = create_event(client, h1, "招募中活动", draw_date="2999-01-01")
        assert detail_flow(client, h1, code) == "recruiting"

    def test_open_past_deadline_drawing(self, client):
        h1, _ = register_and_login(client, "flow_owner2")
        code = create_event(client, h1, "待抽签活动", draw_date="2020-01-01")
        assert detail_flow(client, h1, code) == "drawing"

    def test_open_no_deadline_recruiting(self, client):
        h1, _ = register_and_login(client, "flow_owner3")
        code = create_event(client, h1, "无截止活动")
        assert detail_flow(client, h1, code) == "recruiting"

    def test_drawn_partial_active(self, client):
        h1, _ = register_and_login(client, "flow_owner4")
        h2, _ = register_and_login(client, "flow_member4")
        h3, _ = register_and_login(client, "flow_member4b")
        code = create_event(client, h1, "进行中活动")
        for h in (h1, h2, h3):
            r = client.post(f"/api/events/{code}/join", json={}, headers=h)
            assert r.status_code == 201, r.get_json()
        r = client.post(f"/api/events/{code}/draw", headers=h1)
        assert r.status_code == 200, r.get_json()
        # 抽签后无人晒图 → active
        assert detail_flow(client, h1, code) == "active"

    def test_drawn_all_posted_completed(self, client):
        # 3 人互送：全部晒图 → completed
        h1, _ = register_and_login(client, "flow_owner5")
        h2, _ = register_and_login(client, "flow_member5")
        h3, _ = register_and_login(client, "flow_member5b")
        code = create_event(client, h1, "完结活动")
        for h in (h1, h2, h3):
            r = client.post(f"/api/events/{code}/join", json={}, headers=h)
            assert r.status_code == 201, r.get_json()
        r = client.post(f"/api/events/{code}/draw", headers=h1)
        assert r.status_code == 200, r.get_json()
        for h in (h1, h2, h3):
            # 晒图的是「我收到的礼物」：match 中我是 receiver
            r = client.get(f"/api/events/{code}/received-gift", headers=h)
            assert r.status_code == 200, r.get_json()
            match_id = r.get_json()["data"]["matchId"]
            r = client.put(
                f"/api/events/{code}/received-gift",
                json={"matchId": match_id, "rating": 5, "review": "超喜欢！", "privacy": "text"},
                headers=h,
            )
            assert r.status_code == 200, r.get_json()
        assert detail_flow(client, h1, code) == "completed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
