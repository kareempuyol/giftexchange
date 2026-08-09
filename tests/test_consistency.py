"""数据一致性测试（hackathon 轮2-B：数据模型与查询深化）。

验证五个核心一致性场景：
1. 删活动后所有关联表无孤儿：participants / matches / gift_likes（FK 级联）+
   notifications（无 event_id 外键，须显式清理），且不影响其他活动数据
2. 重抽（redraw）后旧 matches 不可见：API 只返回新结果，旧行物理删除、旧点赞清理
3. 晒图删除（received-gift DELETE）后 gift_likes 一并清理，礼物墙计数回退
4. 账号注销（deactivate）后活动数据完整保留，旧凭据立即失效
5. 事务边界：create_event 组织者参与原子性、shipment+note 两写重试收敛、
   通知批量已读/清空作用域

复用 tests/test_gift_delete.py 的临时 SQLite + Flask test client 模式。
"""
import os
import tempfile

import pytest

# DB_PATH 在 fixture 内设置（import wxcloudrun 前）；DB() 每次实例化时读 DB_PATH，
# 因此模块级 import 安全（class 定义不绑定路径）。
from wxcloudrun.database import DB  # noqa: E402

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_test_consistency_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-consistency"
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


def join_event(client, headers, code):
    r = client.post(f"/api/events/{code}/join", json={}, headers=headers)
    # 组织者创建活动后自动加入：再次 join 幂等返回「你已加入该活动」（400），视为已加入
    if r.status_code == 400 and r.get_json().get("message") == "你已加入该活动":
        return
    assert r.status_code == 201, r.get_json()


def draw(client, headers, code):
    r = client.post(f"/api/events/{code}/draw", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def matches_for_user(client, headers, code, user_id):
    """返回该 user_id 作为收礼人的 match（/matches 默认私密，用组织者 headers 调用）。"""
    r = client.get(f"/api/events/{code}/matches", headers=headers)
    assert r.status_code == 200, r.get_json()
    for m in r.get_json()["data"]:
        if m["receiverId"] == user_id:
            return m
    raise AssertionError(f"no match receiving for user {user_id}")


def my_match(client, headers, code):
    """当前用户作为送礼人的 match（含 matchId）。"""
    r = client.get(f"/api/events/{code}/my-match", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


def like_match(client, headers, code, match_id):
    r = client.post(f"/api/events/{code}/gift-wall/like", json={"matchId": match_id}, headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["likeCount"]


def wall_posted(client, headers, code):
    r = client.get(f"/api/events/{code}/gift-wall", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]["posted"]


def db_scalar(sql, params=()):
    from wxcloudrun.database import DB

    with DB() as db:
        row = db.get(sql, params)
        return row["count"] if row else None


# ========== 场景 1：删活动后无孤儿（含跨活动隔离） ==========

class TestDeleteEventNoOrphans:
    def test_delete_open_event_cleans_all_tables(self, client):
        h1, _ = register_and_login(client, "co_open_owner")
        h2, _ = register_and_login(client, "co_open_u2")
        code = create_event(client, h1, "CO open delete")
        join_event(client, h1, code)
        join_event(client, h2, code)  # 产生 participant_joined 通知

        with DB() as db:
            event = db.get("SELECT id FROM events WHERE code = ?", (code,))
            event_id = event["id"]
            assert db_scalar("SELECT COUNT(*) AS count FROM participants WHERE event_id = ?", (event_id,)) == 2
            assert db_scalar("SELECT COUNT(*) AS count FROM notifications WHERE event_id = ?", (event_id,)) >= 1

        r = client.delete(f"/api/events/{code}", headers=h1)
        assert r.status_code == 200, r.get_json()

        for table in ("participants", "matches", "notifications"):
            assert db_scalar(f"SELECT COUNT(*) AS count FROM {table} WHERE event_id = ?", (event_id,)) == 0, f"{table} 残留孤儿"
        assert db_scalar("SELECT COUNT(*) AS count FROM events WHERE id = ?", (event_id,)) == 0

    def test_delete_one_event_does_not_touch_others(self, client):
        h1, _ = register_and_login(client, "co_iso_owner")
        h2, _ = register_and_login(client, "co_iso_u2")
        h3, uid3 = register_and_login(client, "co_iso_u3")
        code_a = create_event(client, h1, "CO keep me")
        join_event(client, h1, code_a)
        join_event(client, h2, code_a)
        join_event(client, h3, code_a)
        draw(client, h1, code_a)

        code_b = create_event(client, h1, "CO delete me")
        join_event(client, h1, code_b)
        join_event(client, h2, code_b)
        join_event(client, h3, code_b)
        draw(client, h1, code_b)
        match_b = matches_for_user(client, h1, code_b, uid3)
        like_match(client, h2, code_b, match_b["id"])

        with DB() as db:
            b_id = db.get("SELECT id FROM events WHERE code = ?", (code_b,))["id"]
            a_id = db.get("SELECT id FROM events WHERE code = ?", (code_a,))["id"]

        r = client.delete(f"/api/events/{code_b}", headers=h1)
        assert r.status_code == 200, r.get_json()

        # 被删活动全清（gift_likes 无 event_id 列，经 matches 关联计数）
        for table in ("participants", "matches", "notifications"):
            assert db_scalar(f"SELECT COUNT(*) AS count FROM {table} WHERE event_id = ?", (b_id,)) == 0, f"{table} 残留孤儿"
        assert db_scalar(
            "SELECT COUNT(*) AS count FROM gift_likes gl JOIN matches m ON m.id = gl.match_id WHERE m.event_id = ?",
            (b_id,),
        ) == 0
        assert db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id = ?", (match_b["id"],)) == 0
        # 另一活动原样保留
        assert db_scalar("SELECT COUNT(*) AS count FROM participants WHERE event_id = ?", (a_id,)) == 3
        assert db_scalar("SELECT COUNT(*) AS count FROM matches WHERE event_id = ?", (a_id,)) == 3


# ========== 场景 2：重抽后旧 matches 不可见 + 旧点赞清理 ==========

class TestRedrawHidesOldMatches:
    def test_redraw_replaces_matches_and_cleans_likes(self, client):
        h1, _ = register_and_login(client, "co_rd_owner")
        h2, _ = register_and_login(client, "co_rd_u2")
        h3, _ = register_and_login(client, "co_rd_u3")
        code = create_event(client, h1, "CO redraw")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        first = draw(client, h1, code)
        old_ids = {m["id"] for m in first}
        assert len(old_ids) == 3

        # 旧 match 点赞后重抽：点赞必须随旧结果一起清掉（FK 级联 + 显式 DELETE 双兜底）
        like_match(client, h2, code, next(iter(old_ids)))
        with DB() as db:
            e = db.get("SELECT id FROM events WHERE code = ?", (code,))
            assert db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id IN (SELECT id FROM matches WHERE event_id = ?)", (e["id"],)) == 1

        r = client.post(f"/api/events/{code}/redraw", headers=h1)
        assert r.status_code == 200, r.get_json()
        second = r.get_json()["data"]
        new_ids = {m["id"] for m in second}
        assert len(new_ids) == 3
        assert old_ids.isdisjoint(new_ids), "重抽后旧 match id 仍出现"

        # API 层：/matches 只返回新结果；my-match 返回新 match
        r = client.get(f"/api/events/{code}/matches", headers=h1)
        assert r.status_code == 200, r.get_json()
        assert {m["id"] for m in r.get_json()["data"]} == new_ids
        for headers in (h2, h3):
            mm = my_match(client, headers, code)
            assert mm and mm["matchId"] in new_ids

        # DB 层：旧行物理删除、旧点赞清零
        with DB() as db:
            e = db.get("SELECT id FROM events WHERE code = ?", (code,))
            assert db_scalar("SELECT COUNT(*) AS count FROM matches WHERE event_id = ?", (e["id"],)) == 3
            assert db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id IN (SELECT id FROM matches WHERE event_id = ?)", (e["id"],)) == 0


# ========== 场景 3：晒图删除后 likes 清理 ==========

class TestGiftDeleteCleansLikes:
    def test_delete_post_removes_likes_and_reverts_wall(self, client):
        h1, uid1 = register_and_login(client, "co_gd_owner")
        h2, uid2 = register_and_login(client, "co_gd_u2")
        h3, uid3 = register_and_login(client, "co_gd_u3")
        code = create_event(client, h1, "CO gift delete")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        m1 = matches_for_user(client, h1, code, uid1)
        r = client.put(
            f"/api/events/{code}/received-gift",
            json={"matchId": m1["id"], "rating": 5, "review": "好评", "photoUrl": "/uploads/co.png", "privacy": "photo"},
            headers=h1,
        )
        assert r.status_code == 200, r.get_json()
        assert wall_posted(client, h1, code) == 1
        assert like_match(client, h2, code, m1["id"]) == 1
        assert db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id = ?", (m1["id"],)) == 1

        r = client.delete(f"/api/events/{code}/received-gift?matchId={m1['id']}", headers=h1)
        assert r.status_code == 200, r.get_json()

        # 点赞随晒图删除清空（卡片恢复未揭晓，点赞失去意义）
        assert db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id = ?", (m1["id"],)) == 0
        assert wall_posted(client, h1, code) == 0
        with DB() as db:
            row = db.get("SELECT gift_review, gift_photo_url, gift_rating, received_at FROM matches WHERE id = ?", (m1["id"],))
            assert row["received_at"] is None and row["gift_review"] == "" and row["gift_photo_url"] == "" and row["gift_rating"] is None


# ========== 场景 4：注销后活动数据完整 ==========

class TestDeactivatePreservesData:
    def test_deactivate_keeps_events_and_revokes_access(self, client):
        h1, uid1 = register_and_login(client, "co_da_owner")
        h2, _ = register_and_login(client, "co_da_u2")
        h3, _ = register_and_login(client, "co_da_u3")
        code = create_event(client, h1, "CO deactivate")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)
        m1 = matches_for_user(client, h1, code, uid1)
        like_match(client, h2, code, m1["id"])

        with DB() as db:
            e = db.get("SELECT id FROM events WHERE code = ?", (code,))
            before = {
                "participants": db_scalar("SELECT COUNT(*) AS count FROM participants WHERE event_id = ?", (e["id"],)),
                "matches": db_scalar("SELECT COUNT(*) AS count FROM matches WHERE event_id = ?", (e["id"],)),
                "likes": db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id = ?", (m1["id"],)),
                "notifications": db_scalar("SELECT COUNT(*) AS count FROM notifications WHERE event_id = ?", (e["id"],)),
            }
            assert before["participants"] == 3 and before["matches"] == 3

        r = client.post("/api/auth/deactivate", json={"password": PASSWORD}, headers=h1)
        assert r.status_code == 200, r.get_json()

        # 旧凭据立即失效：账号已匿名化（原名释放），旧用户名登录 → 401；旧 JWT → 401
        r = client.post("/api/auth/login", json={"username": "co_da_owner", "password": PASSWORD})
        assert r.status_code == 401, r.get_json()
        assert "错误" in r.get_json()["message"]  # 用户不存在（原名已被 deleted_<id> 替换）
        r = client.get("/api/events/mine", headers=h1)
        assert r.status_code == 401, r.get_json()
        assert "已注销" in r.get_json()["message"]

        # 数据完整：活动/参与者/matches/点赞/通知一行未动，只是用户被匿名化
        with DB() as db:
            e = db.get("SELECT id FROM events WHERE code = ?", (code,))
            assert db_scalar("SELECT COUNT(*) AS count FROM participants WHERE event_id = ?", (e["id"],)) == before["participants"]
            assert db_scalar("SELECT COUNT(*) AS count FROM matches WHERE event_id = ?", (e["id"],)) == before["matches"]
            assert db_scalar("SELECT COUNT(*) AS count FROM gift_likes WHERE match_id = ?", (m1["id"],)) == before["likes"]
            assert db_scalar("SELECT COUNT(*) AS count FROM notifications WHERE event_id = ?", (e["id"],)) == before["notifications"]
            u = db.get("SELECT username, deactivated FROM users WHERE id = ?", (uid1,))
            assert u and u["deactivated"] == 1 and u["username"].startswith("deleted_")

        # 其他参与者视角：活动照常可访问，注销用户仍在成员列表（数据未断链）
        r = client.get(f"/api/events/{code}", headers=h2)
        assert r.status_code == 200, r.get_json()
        r = client.get(f"/api/events/{code}/participants", headers=h2)
        assert r.status_code == 200, r.get_json()
        assert len(r.get_json()["data"]["participants"]) == 3


# ========== 场景 5：事务边界 ==========

class TestTransactionBoundaries:
    def test_create_event_organizer_participant_atomic(self, client):
        """创建活动 = events 行 + 组织者 participant + participant_count，单事务原子。"""
        h1, uid1 = register_and_login(client, "co_tx_owner")
        code = create_event(client, h1, "CO tx create")
        with DB() as db:
            e = db.get("SELECT id, participant_count FROM events WHERE code = ?", (code,))
            assert e["participant_count"] == 1
            p = db.get("SELECT id FROM participants WHERE event_id = ? AND user_id = ?", (e["id"], uid1))
            assert p is not None, "组织者必须自动成为参与者"
            # 创建者加入不通知自己（无打扰）
            assert db_scalar("SELECT COUNT(*) AS count FROM notifications WHERE event_id = ?", (e["id"],)) == 0

    def test_shipment_note_pair_converges_under_retry(self, client):
        """前端两次调用（shipment PUT + note PUT）中途失败：两端各自幂等、可整体重试收敛。

        验证：重复提交同一 shipment 不重复通知（shipment_changed 守卫）、不重复外呼
        （KDNiao 未配置时静默降级）；note 只改 note 列、shipment 只改物流列，互不覆盖。
        """
        h1, _ = register_and_login(client, "co_tx_ship_owner")
        h2, _ = register_and_login(client, "co_tx_ship_u2")
        h3, _ = register_and_login(client, "co_tx_ship_u3")
        code = create_event(client, h1, "CO tx shipment")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        mm = my_match(client, h2, code)
        match_id = mm["matchId"]
        with DB() as db:
            e = db.get("SELECT id FROM events WHERE code = ?", (code,))
            event_id = e["id"]

        def put_shipment(status="shipped"):
            return client.put(
                f"/api/events/{code}/shipment",
                json={"matchId": match_id, "carrier": "顺丰", "trackingNumber": "SF123456", "status": status},
                headers=h2,
            )

        def shipment_sent_count():
            return db_scalar(
                "SELECT COUNT(*) AS count FROM notifications WHERE event_id = ? AND type = 'shipment_sent'",
                (event_id,),
            )

        # 第一次：shipment 成功 + note 成功
        assert put_shipment().status_code == 200
        assert client.put(f"/api/events/{code}/note", json={"matchId": match_id, "note": "悄悄话"}, headers=h2).status_code == 200
        assert shipment_sent_count() == 1

        # 模拟「shipment 已提交但客户端收到网络错误后整体重试」：重放两个请求
        assert put_shipment().status_code == 200
        assert client.put(f"/api/events/{code}/note", json={"matchId": match_id, "note": "悄悄话"}, headers=h2).status_code == 200
        assert shipment_sent_count() == 1, "重复提交同一单号不得重复通知"

        # 只改 note：shipment 字段原样保留
        assert client.put(f"/api/events/{code}/note", json={"matchId": match_id, "note": "新悄悄话"}, headers=h2).status_code == 200
        with DB() as db:
            row = db.get("SELECT carrier, tracking_number, note, shipment_status FROM matches WHERE id = ?", (match_id,))
            assert row["carrier"] == "顺丰" and row["tracking_number"] == "SF123456" and row["note"] == "新悄悄话"

        # 只改 shipment：note 原样保留
        assert client.put(
            f"/api/events/{code}/shipment",
            json={"matchId": match_id, "carrier": "顺丰", "trackingNumber": "SF999999", "status": "shipped"},
            headers=h2,
        ).status_code == 200
        with DB() as db:
            row = db.get("SELECT tracking_number, note FROM matches WHERE id = ?", (match_id,))
            assert row["tracking_number"] == "SF999999" and row["note"] == "新悄悄话"
        assert shipment_sent_count() == 2  # 单号变化 → 正常再通知一次

    def test_notifications_batch_read_clear_scoped(self, client):
        """批量标记已读只影响指定 id；清空只删已读，未读保留。"""
        h1, _ = register_and_login(client, "co_tx_notif_owner")
        h2, _ = register_and_login(client, "co_tx_notif_u2")
        h3, _ = register_and_login(client, "co_tx_notif_u3")
        code = create_event(client, h1, "CO tx notif")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)

        r = client.get("/api/notifications", headers=h1)
        items = r.get_json()["data"]["items"]
        assert len(items) == 2  # h2/h3 加入各一条
        assert r.get_json()["data"]["unread"] == 2
        ids = [n["id"] for n in items]

        # 只标记第一条已读
        r = client.post("/api/notifications/read", json={"ids": [ids[0]]}, headers=h1)
        assert r.status_code == 200, r.get_json()
        r = client.get("/api/notifications", headers=h1)
        assert r.get_json()["data"]["unread"] == 1
        by_id = {n["id"]: n["read"] for n in r.get_json()["data"]["items"]}
        assert by_id[ids[0]] is True and by_id[ids[1]] is False

        # 清空：只删已读那条，未读保留
        r = client.post("/api/notifications/clear", headers=h1)
        assert r.status_code == 200, r.get_json()
        r = client.get("/api/notifications", headers=h1)
        remaining = r.get_json()["data"]["items"]
        assert [n["id"] for n in remaining] == [ids[1]]
        assert r.get_json()["data"]["unread"] == 1

        # 全量标记已读（无 ids）→ 再清空 → 空
        r = client.post("/api/notifications/read", json={}, headers=h1)
        assert r.status_code == 200, r.get_json()
        r = client.post("/api/notifications/clear", headers=h1)
        assert r.status_code == 200, r.get_json()
        r = client.get("/api/notifications", headers=h1)
        assert r.get_json()["data"]["items"] == []


class TestDashboardCounts:
    def test_dashboard_counts_follow_state(self, client):
        """dashboard（组织者视图）统计：pendingShipments/unpostedGifts 随发货/晒图推进。"""
        h1, uid1 = register_and_login(client, "co_dash_owner")
        h2, uid2 = register_and_login(client, "co_dash_u2")
        h3, uid3 = register_and_login(client, "co_dash_u3")
        code = create_event(client, h1, "CO dashboard")
        join_event(client, h1, code)
        join_event(client, h2, code)
        join_event(client, h3, code)
        draw(client, h1, code)

        def dash():
            r = client.get(f"/api/events/{code}/dashboard", headers=h1)
            assert r.status_code == 200, r.get_json()
            return r.get_json()["data"]

        d = dash()
        assert d["count"] == 3
        assert d["pendingShipments"] == 3 and d["unpostedGifts"] == 0
        assert all(p["hasMatch"] for p in d["participants"])

        # h2 发货 → pending -1、unposted +1
        mm = my_match(client, h2, code)
        r = client.put(
            f"/api/events/{code}/shipment",
            json={"matchId": mm["matchId"], "carrier": "中通", "trackingNumber": "ZT0001", "status": "shipped"},
            headers=h2,
        )
        assert r.status_code == 200, r.get_json()
        d = dash()
        assert d["pendingShipments"] == 2 and d["unpostedGifts"] == 1

        # h3 晒图（收到礼物）：unposted 计数随「已发货未晒图」的 match 是否被
        # 签收而变化——抽签随机，无法固定预期值；与 DB 真值（原 counts 查询定义）比对
        m3 = matches_for_user(client, h1, code, uid3)
        r = client.put(
            f"/api/events/{code}/received-gift",
            json={"matchId": m3["id"], "rating": 5, "review": "收到", "photoUrl": "/uploads/dash.png"},
            headers=h3,
        )
        assert r.status_code == 200, r.get_json()
        d = dash()
        with DB() as db:
            e = db.get("SELECT id FROM events WHERE code = ?", (code,))
            truth = db.get(
                "SELECT "
                "SUM(CASE WHEN shipment_status = 'pending' THEN 1 ELSE 0 END) AS p, "
                "SUM(CASE WHEN shipment_status != 'pending' AND received_at IS NULL THEN 1 ELSE 0 END) AS u "
                "FROM matches WHERE event_id = ?",
                (e["id"],),
            )
        assert d["pendingShipments"] == truth["p"], (d["pendingShipments"], truth["p"])
        assert d["unpostedGifts"] == truth["u"], (d["unpostedGifts"], truth["u"])
        # 成员完成度字段与 match 字段联动：h2 发货反映在其收礼人那一行
        # （dashboard 每行 = 该参与者的「收礼 match」状态）
        by_user = {p["userId"]: p for p in d["participants"]}
        h2_receiver = my_match(client, h2, code)["receiverId"]
        assert by_user[h2_receiver]["shipmentStatus"] == "shipped"
        assert by_user[uid3]["postedGift"] is True
        assert by_user[uid1]["postedGift"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
