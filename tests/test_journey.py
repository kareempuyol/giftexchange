"""用户旅程补强（波次4）API 测试。

覆盖：
- 组织者创建活动后自动加入：participants 含创建者、participantCount=1、
  1 人时抽签仍提示至少 2 人、创建者重复 join 幂等返回「你已加入该活动」
- 物流降级文案区分：
  * KDNiao 未配置 →「暂未接入物流查询，可通过单号自行查询」（不可刷新）
  * 查询失败 →「物流信息查询失败，请稍后刷新重试」（可刷新）
- 手动刷新接口 POST /events/<code>/shipment/refresh：
  * 失败后重试成功 → trackingSummary 更新、trackingRefreshable 复位
  * 失败重试仍失败 → 保留失败文案
  * 无单号 / 非送礼人 / 非参与者 → 明确报错

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
    tmp = tempfile.mkdtemp(prefix="gift_test_journey_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-journey"
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
def no_kdniao_env(monkeypatch):
    """确保 KDNiao 配置只来自测试可控渠道（默认未配置）。"""
    monkeypatch.delenv("KDNIAO_EBUSINESS_ID", raising=False)
    monkeypatch.delenv("KDNIAO_APP_KEY", raising=False)
    import wxcloudrun.helpers as helpers

    helpers._kdniao_cache.clear()


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
    return r.get_json()["data"]


def join_event(client, headers, code):
    return client.post(f"/api/events/{code}/join", json={}, headers=headers)


def detail(client, headers, code):
    r = client.get(f"/api/events/{code}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def participants(client, headers, code):
    r = client.get(f"/api/events/{code}/participants", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def my_giving_match(client, headers, code):
    r = client.get(f"/api/events/{code}/my-match", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


class TestCreatorAutoJoin:
    def test_creator_is_participant_after_create(self, client):
        h1, uid1 = register_and_login(client, "j_creator1")
        ev = create_event(client, h1, "J creator auto join")

        # 创建响应即含参与者计数 1
        assert ev["participantCount"] == 1
        d = detail(client, h1, ev["code"])
        assert d["participantCount"] == 1

        parts = participants(client, h1, ev["code"])
        assert parts["count"] == 1
        assert parts["participants"][0]["userId"] == uid1

        # 1 人时抽签门槛仍生效：提示至少 2 人
        r = client.post(f"/api/events/{ev['code']}/draw", headers=h1)
        assert r.status_code == 400, r.get_json()
        assert "至少需要 2 人" in r.get_json()["message"]

    def test_creator_join_is_idempotent_rejected(self, client):
        h1, _uid1 = register_and_login(client, "j_creator2")
        ev = create_event(client, h1, "J creator rejoin")
        r = join_event(client, h1, ev["code"])
        assert r.status_code == 400, r.get_json()
        assert r.get_json()["message"] == "你已加入该活动"

    def test_two_person_draw_still_rejected(self, client):
        # 创建者自动加入后共 2 人：业务规则仍拒绝 2 人互送（无随机性）
        h1, _uid1 = register_and_login(client, "j_creator3")
        h2, _uid2 = register_and_login(client, "j_member3")
        ev = create_event(client, h1, "J creator +1")
        r = join_event(client, h2, ev["code"])
        assert r.status_code == 201, r.get_json()
        assert detail(client, h1, ev["code"])["participantCount"] == 2
        r = client.post(f"/api/events/{ev['code']}/draw", headers=h1)
        assert r.status_code == 400, r.get_json()
        assert "至少需要 3 人" in r.get_json()["message"]

    def test_draw_success_with_creator_plus_two(self, client):
        # 创建者 + 2 名成员 = 3 人：可正常抽签（创建者参与抽签环）
        h1, _uid1 = register_and_login(client, "j_creator3b")
        h2, _uid2 = register_and_login(client, "j_member3b")
        h3, _uid3 = register_and_login(client, "j_member3c")
        ev = create_event(client, h1, "J creator +2")
        assert join_event(client, h2, ev["code"]).status_code == 201
        assert join_event(client, h3, ev["code"]).status_code == 201
        assert detail(client, h1, ev["code"])["participantCount"] == 3
        r = client.post(f"/api/events/{ev['code']}/draw", headers=h1)
        assert r.status_code == 200, r.get_json()
        assert len(r.get_json()["data"]) == 3

    def test_creator_cannot_leave(self, client):
        h1, _uid1 = register_and_login(client, "j_creator4")
        ev = create_event(client, h1, "J creator leave")
        r = client.delete(f"/api/events/{ev['code']}/leave", headers=h1)
        assert r.status_code == 400, r.get_json()
        assert "创建者不能退出" in r.get_json()["message"]


class TestLogisticsDegradationCopy:
    def _setup_shipped_match(self, client, monkeypatch, suffix):
        """h1 创建 + h2/h3 加入（3 人才可抽签）；h2 发货填单号。返回 (headers, code, match_id)。"""
        h1, _ = register_and_login(client, f"j_lg_{suffix}_creator")
        h2, _ = register_and_login(client, f"j_lg_{suffix}_member")
        h3, _ = register_and_login(client, f"j_lg_{suffix}_member2")
        ev = create_event(client, h1, "J logistics")
        assert join_event(client, h2, ev["code"]).status_code == 201
        assert join_event(client, h3, ev["code"]).status_code == 201
        assert client.post(f"/api/events/{ev['code']}/draw", headers=h1).status_code == 200
        match = my_giving_match(client, h2, ev["code"])
        return h2, ev["code"], match["matchId"]

    def test_not_configured_copy_and_no_refresh(self, client, monkeypatch):
        h2, code, match_id = self._setup_shipped_match(client, monkeypatch, "nc")
        r = client.put(
            f"/api/events/{code}/shipment",
            json={"matchId": match_id, "carrier": "SF", "trackingNumber": "JN123456", "status": "shipped"},
            headers=h2,
        )
        assert r.status_code == 200, r.get_json()
        shipment = r.get_json()["data"]  # PUT /shipment 的 data 即 api_shipment 形状
        assert shipment["trackingSummary"] == "暂未接入物流查询，可通过单号自行查询"
        assert shipment["trackingRefreshable"] is False

    def test_query_failure_copy_and_refresh_success(self, client, monkeypatch):
        import wxcloudrun.gift_routes as gift_routes

        h2, code, match_id = self._setup_shipped_match(client, monkeypatch, "fail")

        # 第一次发货：KDNiao 查询失败（模拟外呼异常）
        monkeypatch.setattr(
            gift_routes, "query_kdniao_tracking", lambda db, carrier, num: (False, "", "boom")
        )
        r = client.put(
            f"/api/events/{code}/shipment",
            json={"matchId": match_id, "carrier": "SF", "trackingNumber": "JN654321", "status": "shipped"},
            headers=h2,
        )
        assert r.status_code == 200, r.get_json()
        shipment = r.get_json()["data"]  # PUT /shipment 的 data 即 api_shipment 形状
        assert shipment["trackingSummary"] == "物流信息查询失败，请稍后刷新重试"
        assert shipment["trackingRefreshable"] is True

        # 手动刷新：仍失败 → 文案不变、仍可刷新
        r = client.post(f"/api/events/{code}/shipment/refresh", json={"matchId": match_id}, headers=h2)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["trackingSummary"] == "物流信息查询失败，请稍后刷新重试"
        assert r.get_json()["data"]["trackingRefreshable"] is True

        # 手动刷新：重试成功 → summary 更新、不可再刷新
        monkeypatch.setattr(
            gift_routes,
            "query_kdniao_tracking",
            lambda db, carrier, num: (True, "已签收 | 最新：包裹已送达", []),
        )
        r = client.post(f"/api/events/{code}/shipment/refresh", json={"matchId": match_id}, headers=h2)
        assert r.status_code == 200, r.get_json()
        assert "已签收" in r.get_json()["data"]["trackingSummary"]
        assert r.get_json()["data"]["trackingRefreshable"] is False

    def test_refresh_guardrails(self, client, monkeypatch):
        h1, _ = register_and_login(client, "j_lg_gc_creator")
        h2, _ = register_and_login(client, "j_lg_gc_member")
        h3, _ = register_and_login(client, "j_lg_gc_member2")
        outsider, _ = register_and_login(client, "j_lg_gc_out")
        ev = create_event(client, h1, "J logistics guards")
        assert join_event(client, h2, ev["code"]).status_code == 201
        assert join_event(client, h3, ev["code"]).status_code == 201
        assert client.post(f"/api/events/{ev['code']}/draw", headers=h1).status_code == 200
        match = my_giving_match(client, h2, ev["code"])
        code = ev["code"]

        # 未登录 → 401
        assert client.post(f"/api/events/{code}/shipment/refresh", json={"matchId": match["matchId"]}).status_code == 401
        # 非参与者 → 403
        r = client.post(f"/api/events/{code}/shipment/refresh", json={"matchId": match["matchId"]}, headers=outsider)
        assert r.status_code == 403, r.get_json()
        # 缺少 matchId → 400
        r = client.post(f"/api/events/{code}/shipment/refresh", json={}, headers=h2)
        assert r.status_code == 400, r.get_json()
        # 不是自己的送礼任务 → 400「未找到」
        r = client.post(f"/api/events/{code}/shipment/refresh", json={"matchId": match["matchId"]}, headers=h1)
        assert r.status_code == 400, r.get_json()
        assert "未找到" in r.get_json()["message"]
