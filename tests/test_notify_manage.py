"""通知批量管理测试（P1 MOA 3/3）：read-all / clear / 通知偏好过滤。

覆盖：
- 路由层（Flask test client 走真实 HTTP）：
    POST /api/notifications/read {}（无 ids = 全部已读）→ unread=0
    POST /api/notifications/clear → 已读消失、未读保留
    GET/PUT /api/notifications/preferences → 默认全开 / 部分更新合并 / 未知键忽略
- 逻辑层：
    notify() 收口偏好过滤：draw/giftReceived/remind 关闭后对应 type 不写库、返回 False
    scan_deadlines 受 deadline 偏好控制：关闭不发，重新打开恢复
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import uuid

import pytest

PASSWORD = "Pass123!"


@pytest.fixture(scope="module")
def ctx():
    """独立临时 DB：init_schema（含 run_migrations → v9 notification_prefs 列），结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    saved_jwt = os.environ.get("JWT_SECRET")
    tmp = tempfile.mkdtemp(prefix="gift_notif_manage_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    os.environ["JWT_SECRET"] = "test-secret-notif-manage"
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


@pytest.fixture(scope="module")
def client(ctx):
    return ctx.test_client()


def register_and_login(client, name):
    """注册+登录，返回 (auth headers, user_id)。"""
    r = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@test.com", "password": PASSWORD},
    )
    assert r.status_code == 201, r.get_json()
    r = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def seed_notification(db, user_id, type_name, read=False):
    """直接插一条通知（测试用，绕开偏好过滤以构造数据）。"""
    if read:
        db.execute(
            "INSERT INTO notifications (user_id, type, title, message, read_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, type_name, f"标题{type_name}", f"正文{type_name}"),
        )
    else:
        db.execute(
            "INSERT INTO notifications (user_id, type, title, message) VALUES (?, ?, ?, ?)",
            (user_id, type_name, f"标题{type_name}", f"正文{type_name}"),
        )


def get_notifs(client, headers):
    r = client.get("/api/notifications", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["data"]


# ---------- 路由层：read-all / clear ----------

class TestReadAll:
    def test_read_all_marks_everything_read(self, client):
        headers, uid = register_and_login(client, "ra")
        from wxcloudrun.database import DB

        with DB() as db:
            seed_notification(db, uid, "draw_result")
            seed_notification(db, uid, "gift_posted")
            seed_notification(db, uid, "deadline_24h", read=True)

        data = get_notifs(client, headers)
        assert data["unread"] == 2

        r = client.post("/api/notifications/read", json={}, headers=headers)
        assert r.status_code == 200, r.get_json()

        data = get_notifs(client, headers)
        assert data["unread"] == 0
        assert len(data["items"]) == 3
        assert all(item["read"] for item in data["items"])


class TestClear:
    def test_clear_removes_read_keeps_unread(self, client):
        headers, uid = register_and_login(client, "cl")
        from wxcloudrun.database import DB

        with DB() as db:
            seed_notification(db, uid, "shipment_sent", read=True)
            seed_notification(db, uid, "deadline_24h", read=True)
            seed_notification(db, uid, "draw_result")  # 未读，必须保留

        r = client.post("/api/notifications/clear", headers=headers)
        assert r.status_code == 200, r.get_json()

        data = get_notifs(client, headers)
        assert len(data["items"]) == 1
        assert data["items"][0]["type"] == "draw_result"
        assert data["unread"] == 1

    def test_clear_with_only_unread_is_noop(self, client):
        headers, uid = register_and_login(client, "cl2")
        from wxcloudrun.database import DB

        with DB() as db:
            seed_notification(db, uid, "draw_result")

        r = client.post("/api/notifications/clear", headers=headers)
        assert r.status_code == 200, r.get_json()
        data = get_notifs(client, headers)
        assert len(data["items"]) == 1
        assert data["unread"] == 1


# ---------- 路由层：偏好读写 ----------

class TestPreferences:
    def test_defaults_all_on(self, client):
        headers, _uid = register_and_login(client, "pf1")
        r = client.get("/api/notifications/preferences", headers=headers)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"] == {
            "deadline": True,
            "draw": True,
            "giftReceived": True,
            "remind": True,
        }

    def test_partial_update_merges_and_unknown_ignored(self, client):
        headers, _uid = register_and_login(client, "pf2")
        r = client.put(
            "/api/notifications/preferences",
            json={"draw": False, "bogusKey": False},
            headers=headers,
        )
        assert r.status_code == 200, r.get_json()
        data = r.get_json()["data"]
        assert data == {
            "deadline": True,
            "draw": False,
            "giftReceived": True,
            "remind": True,
        }
        # 持久化：重读一致
        r = client.get("/api/notifications/preferences", headers=headers)
        assert r.get_json()["data"]["draw"] is False

    def test_toggle_back_on(self, client):
        headers, _uid = register_and_login(client, "pf3")
        client.put("/api/notifications/preferences", json={"draw": False}, headers=headers)
        r = client.put("/api/notifications/preferences", json={"draw": True}, headers=headers)
        assert r.get_json()["data"]["draw"] is True


# ---------- 逻辑层：notify() 偏好收口 ----------

class TestNotifyPrefFilter:
    def test_draw_off_filters_draw_result_and_redraw(self, client):
        headers, uid = register_and_login(client, "nf1")
        client.put("/api/notifications/preferences", json={"draw": False}, headers=headers)
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            assert notify(db, uid, None, None, "draw_result", "抽签结果已出 🎉", "正文") is False
            assert notify(db, uid, None, None, "draw_redraw", "抽签已重置 🔄", "正文") is False
            assert len(db.all("SELECT * FROM notifications WHERE user_id = ?", (uid,))) == 0

    def test_gift_received_off_filters_gift_types(self, client):
        headers, uid = register_and_login(client, "nf2")
        client.put("/api/notifications/preferences", json={"giftReceived": False}, headers=headers)
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            assert notify(db, uid, None, None, "gift_posted", "TA 已晒礼物", "正文") is False
            assert notify(db, uid, None, None, "gift_wall_unlocked", "礼物墙已解锁 🎉", "正文") is False
            assert len(db.all("SELECT * FROM notifications WHERE user_id = ?", (uid,))) == 0

    def test_remind_off_filters_activity_types(self, client):
        headers, uid = register_and_login(client, "nf3")
        client.put("/api/notifications/preferences", json={"remind": False}, headers=headers)
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            assert notify(db, uid, None, None, "participant_joined", "有人加入", "正文") is False
            assert notify(db, uid, None, None, "shipment_sent", "礼物已发货", "正文") is False
            assert len(db.all("SELECT * FROM notifications WHERE user_id = ?", (uid,))) == 0

    def test_other_types_unaffected(self, client):
        headers, uid = register_and_login(client, "nf4")
        client.put("/api/notifications/preferences", json={"draw": False}, headers=headers)
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            # draw 关闭不影响 deadline / 未归类 type
            assert notify(db, uid, None, None, "deadline_24h", "即将截止", "正文") is True
            assert notify(db, uid, None, None, "future_type", "标题", "正文") is True
            assert len(db.all("SELECT * FROM notifications WHERE user_id = ?", (uid,))) == 2

    def test_enabled_again_restores_delivery(self, client):
        headers, uid = register_and_login(client, "nf5")
        client.put("/api/notifications/preferences", json={"draw": False}, headers=headers)
        client.put("/api/notifications/preferences", json={"draw": True}, headers=headers)
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            assert notify(db, uid, None, None, "draw_result", "抽签结果已出 🎉", "正文") is True
            assert len(db.all("SELECT * FROM notifications WHERE user_id = ?", (uid,))) == 1

    def test_null_prefs_treated_as_all_on(self, client):
        headers, uid = register_and_login(client, "nf6")
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            # 注册用户 notification_prefs 为 NULL → 不拦截
            assert notify(db, uid, None, None, "draw_result", "抽签结果已出 🎉", "正文") is True

    def test_corrupt_prefs_treated_as_all_on(self, client):
        headers, uid = register_and_login(client, "nf7")
        from wxcloudrun.database import DB
        from wxcloudrun.notify import notify

        with DB() as db:
            db.execute(
                "UPDATE users SET notification_prefs = ? WHERE id = ?",
                ("{not-json", uid),
            )
            assert notify(db, uid, None, None, "draw_result", "抽签结果已出 🎉", "正文") is True


# ---------- 逻辑层：scan_deadlines 受 deadline 偏好控制 ----------

class TestScanDeadlinesPref:
    NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    def _add_open_event(self, db, creator_id, hours):
        deadline = (self.NOW + timedelta(hours=hours)).isoformat()
        db.execute(
            "INSERT INTO events (code, name, creator_id, status, sign_up_deadline) "
            "VALUES (?, ?, ?, 'open', ?)",
            (f"pref_evt_{uuid.uuid4().hex[:8]}", "偏好活动", creator_id, deadline),
        )
        return dict(db.get("SELECT * FROM events WHERE creator_id = ? ORDER BY id DESC LIMIT 1", (creator_id,)))

    def test_deadline_off_blocks_scan_and_reopen_restores(self, client):
        headers, uid = register_and_login(client, "sd")
        from wxcloudrun.database import DB
        from wxcloudrun.jobs import scan_deadlines

        with DB() as db:
            event = self._add_open_event(db, uid, 10)

        # 关闭 deadline 偏好 → 扫描不发
        client.put("/api/notifications/preferences", json={"deadline": False}, headers=headers)
        with DB() as db:
            assert scan_deadlines(db, now=self.NOW) == 0
            assert len(db.all("SELECT * FROM notifications WHERE user_id = ?", (uid,))) == 0

        # 重新打开 → 恢复发送（窗口仍在）
        client.put("/api/notifications/preferences", json={"deadline": True}, headers=headers)
        with DB() as db:
            assert scan_deadlines(db, now=self.NOW) == 1
            rows = db.all("SELECT * FROM notifications WHERE event_id = ?", (event["id"],))
            assert len(rows) == 1
            assert rows[0]["type"] == "deadline_24h"

    def test_deadline_off_still_counts_other_users(self, client):
        """偏好按用户隔离：A 关闭不影响 B 的截止提醒。"""
        headers_a, uid_a = register_and_login(client, "sdA")
        _, uid_b = register_and_login(client, "sdB")
        from wxcloudrun.database import DB
        from wxcloudrun.jobs import scan_deadlines

        with DB() as db:
            event_a = self._add_open_event(db, uid_a, 10)
            self._add_open_event(db, uid_b, 10)

        client.put("/api/notifications/preferences", json={"deadline": False}, headers=headers_a)
        with DB() as db:
            assert scan_deadlines(db, now=self.NOW) == 1  # 只给 B 发
            rows = db.all("SELECT * FROM notifications WHERE user_id = ?", (uid_b,))
            assert len(rows) == 1
            assert rows[0]["user_id"] == uid_b
            assert rows[0]["event_id"] != event_a["id"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
