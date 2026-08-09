"""notify 抽象 + 截止提醒任务测试（wxcloudrun/notify.py, wxcloudrun/jobs.py）。

注意：wxcloudrun/__init__.py 在 import 时执行 create_app()→init_schema()，
因此必须在 import wxcloudrun 之前设置 DB_PATH，让包初始化落在临时库上，
绝不触碰开发库 ~/giftexchange/data/gift_exchange.db。
"""
import inspect
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

# ---- 包导入前的环境准备（必须在 from wxcloudrun... 之前）----
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="gift_notify_test_"), "test.db")
for _k in ("MYSQL_ADDRESS", "MYSQL_HOST", "MYSQL_PORT"):
    os.environ.pop(_k, None)

from wxcloudrun.database import DB  # noqa: E402
from wxcloudrun.jobs import parse_deadline, scan_deadlines  # noqa: E402
from wxcloudrun.notify import notify, notify_deadline_approaching  # noqa: E402
from wxcloudrun.views import create_notification  # noqa: E402

NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


def deadline_in(hours):
    """NOW 之后 hours 小时的 ISO 字符串（带 +00:00 偏移，模拟前端 toISOString）"""
    return (NOW + timedelta(hours=hours)).isoformat()


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清空所有表（FK 安全顺序），测试间互不污染。"""
    with DB() as db:
        for table in (
            "gift_likes",
            "matches",
            "participants",
            "notifications",
            "events",
            "users",
            "app_settings",
        ):
            db.execute(f"DELETE FROM {table}")
    yield


# ---------- 测试辅助 ----------

def add_user(db, tag):
    db.execute(
        "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
        (f"{tag}_user", f"{tag}@test.local", "pw"),
    )
    return db.get("SELECT id FROM users WHERE username = ?", (f"{tag}_user",))["id"]


def add_event(db, creator_id, deadline, status="open", tag="evt"):
    db.execute(
        "INSERT INTO events (code, name, creator_id, status, sign_up_deadline) "
        "VALUES (?, ?, ?, ?, ?)",
        (f"{tag}_{id(object())}", f"活动{tag}", creator_id, status, deadline),
    )
    row = db.get("SELECT * FROM events WHERE creator_id = ? ORDER BY id DESC LIMIT 1", (creator_id,))
    return dict(row)


def notifs_for(db, event_id):
    return db.all("SELECT * FROM notifications WHERE event_id = ?", (event_id,))


# ---------- notify() 基础行为 ----------

class TestNotify:
    def test_writes_full_row(self):
        with DB() as db:
            uid = add_user(db, "a")
            event = add_event(db, uid, deadline_in(10))
            notify(db, uid, event["id"], None, "test_type", "标题", "正文")
            rows = db.all(
                "SELECT user_id, event_id, match_id, type, title, message FROM notifications"
            )
            assert rows == [
                {
                    "user_id": uid,
                    "event_id": event["id"],
                    "match_id": None,
                    "type": "test_type",
                    "title": "标题",
                    "message": "正文",
                }
            ]

    def test_requires_type_and_title(self):
        with DB() as db:
            with pytest.raises(ValueError):
                notify(db, 1, 2, None, "", "标题", "正文")
            with pytest.raises(ValueError):
                notify(db, 1, 2, None, "type", "", "正文")

    def test_signature_aligned_with_create_notification(self):
        """参数名与顺序必须与 views.create_notification 一致（未来可直接替换调用）"""
        notify_params = list(inspect.signature(notify).parameters)
        create_params = list(inspect.signature(create_notification).parameters)
        assert notify_params == create_params


# ---------- notify_deadline_approaching 去重 ----------

class TestNotifyDeadlineApproaching:
    def test_sends_once_then_dedup(self):
        with DB() as db:
            uid = add_user(db, "b")
            event = add_event(db, uid, deadline_in(10))
            assert notify_deadline_approaching(db, event, 24) is True
            assert notify_deadline_approaching(db, event, 24) is False
            rows = notifs_for(db, event["id"])
            assert len(rows) == 1
            assert rows[0]["type"] == "deadline_24h"
            assert rows[0]["user_id"] == uid
            assert "24 小时" in rows[0]["message"]

    def test_different_hours_are_distinct_types(self):
        """48h 与 24h 是不同 type：同一活动可以各发一次，互不压制"""
        with DB() as db:
            uid = add_user(db, "c")
            event = add_event(db, uid, deadline_in(10))
            assert notify_deadline_approaching(db, event, 48) is True
            assert notify_deadline_approaching(db, event, 24) is True
            rows = notifs_for(db, event["id"])
            assert len(rows) == 2
            assert {r["type"] for r in rows} == {"deadline_48h", "deadline_24h"}

    def test_dedup_scoped_per_event(self):
        """去重键是 event_id+type：不同活动互不影响"""
        with DB() as db:
            uid = add_user(db, "d")
            ev1 = add_event(db, uid, deadline_in(10), tag="e1")
            ev2 = add_event(db, uid, deadline_in(10), tag="e2")
            assert notify_deadline_approaching(db, ev1, 24) is True
            assert notify_deadline_approaching(db, ev2, 24) is True
            assert len(notifs_for(db, ev1["id"])) == 1
            assert len(notifs_for(db, ev2["id"])) == 1


# ---------- parse_deadline ----------

class TestParseDeadline:
    def test_iso_zulu(self):
        dt = parse_deadline("2026-08-10T12:00:00.000Z")
        assert dt == datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_naive_datetime_treated_as_utc(self):
        dt = parse_deadline("2026-12-25T20:00")
        assert dt == datetime(2026, 12, 25, 20, 0, 0, tzinfo=timezone.utc)

    def test_date_only_is_end_of_day(self):
        dt = parse_deadline("2026-12-25")
        assert dt == datetime(2026, 12, 25, 23, 59, 59, tzinfo=timezone.utc)

    def test_garbage_and_empty(self):
        assert parse_deadline("") is None
        assert parse_deadline(None) is None
        assert parse_deadline("not-a-date") is None


# ---------- jobs.scan_deadlines ----------

class TestScanDeadlines:
    def test_30h_remaining_fires_48h_only(self):
        with DB() as db:
            uid = add_user(db, "e")
            event = add_event(db, uid, deadline_in(30))
            assert scan_deadlines(db, now=NOW) == 1
            rows = notifs_for(db, event["id"])
            assert len(rows) == 1
            assert rows[0]["type"] == "deadline_48h"

    def test_10h_remaining_fires_24h_only(self):
        with DB() as db:
            uid = add_user(db, "f")
            event = add_event(db, uid, deadline_in(10))
            assert scan_deadlines(db, now=NOW) == 1
            rows = notifs_for(db, event["id"])
            assert len(rows) == 1
            assert rows[0]["type"] == "deadline_24h"

    def test_boundary_exact_hours(self):
        """恰好 48h 触发 48h 档；恰好 24h 只触发 24h 档（不双发）"""
        with DB() as db:
            uid = add_user(db, "g")
            ev48 = add_event(db, uid, deadline_in(48), tag="b48")
            ev24 = add_event(db, uid, deadline_in(24), tag="b24")
            assert scan_deadlines(db, now=NOW) == 2
            assert [r["type"] for r in notifs_for(db, ev48["id"])] == ["deadline_48h"]
            assert [r["type"] for r in notifs_for(db, ev24["id"])] == ["deadline_24h"]

    def test_far_future_and_past_skipped(self):
        with DB() as db:
            uid = add_user(db, "h")
            add_event(db, uid, deadline_in(50), tag="far")
            add_event(db, uid, deadline_in(-2), tag="past")
            assert scan_deadlines(db, now=NOW) == 0

    def test_non_open_and_empty_deadline_skipped(self):
        with DB() as db:
            uid = add_user(db, "i")
            add_event(db, uid, deadline_in(10), status="drawn", tag="drawn")
            add_event(db, uid, "", tag="no_dl")
            assert scan_deadlines(db, now=NOW) == 0

    def test_second_run_does_not_duplicate(self):
        with DB() as db:
            uid = add_user(db, "j")
            add_event(db, uid, deadline_in(10), tag="dup")
            assert scan_deadlines(db, now=NOW) == 1
            assert scan_deadlines(db, now=NOW) == 0  # 二次运行去重生效
            assert len(db.all("SELECT * FROM notifications")) == 1

    def test_without_db_arg_opens_own_connection(self):
        """不传 db 时自行开关连接，写入已 commit，可用新连接读回"""
        with DB() as db:
            uid = add_user(db, "k")
            event = add_event(db, uid, deadline_in(10), tag="own")
        assert scan_deadlines(now=NOW) == 1
        with DB() as db2:
            rows = notifs_for(db2, event["id"])
            assert len(rows) == 1
            assert rows[0]["type"] == "deadline_24h"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
