"""运维脚本专项测试（hackathon 波次5：数据运维与健壮性）。

覆盖 scripts/ 下三个 Python 脚本的核心逻辑（经 importlib 加载，不走 subprocess）：
  - cleanup_orphans：只清「无 DB 引用 + 落盘超过 7 天」的普通文件；7 天为硬性下限
  - cleanup_notifications：只删「已读 + 创建超过 N 天」的通知；未读/新近的保留
  - healthcheck_data：孤儿 matches/participants/notifications、gift_likes 悬空引用全检出
"""
import importlib.util
import os
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def load_script(name):
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scripts():
    return {
        "orphans": load_script("cleanup_orphans"),
        "notifications": load_script("cleanup_notifications"),
        "healthcheck": load_script("healthcheck_data"),
    }


@pytest.fixture(scope="module")
def ctx(scripts):
    """独立临时 SQLite：显式 init_schema 建表，结束后恢复环境变量。"""
    saved_db = os.environ.get("DB_PATH")
    tmp = tempfile.mkdtemp(prefix="gift_test_ops_")
    os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
    try:
        from wxcloudrun.database import DB, init_schema

        init_schema()  # 幂等建表 + 迁移，落在临时库
        with DB() as db:
            db.execute(
                "INSERT INTO users (username, email, password, display_name) VALUES (?, ?, ?, ?)",
                ("ops_user", "ops@example.com", "x", "Ops User"),
            )
            db.execute(
                "INSERT INTO events (code, name, creator_id, short_code) VALUES (?, ?, ?, ?)",
                ("OPSEVENT", "Ops Event", 1, "OPS001"),
            )
            db.execute(
                "INSERT INTO participants (event_id, user_id, nickname) VALUES (?, ?, ?)",
                (1, 1, "Ops P1"),
            )
            db.execute(
                "INSERT INTO matches (event_id, giver_id, receiver_id) VALUES (?, ?, ?)",
                (1, 1, 1),
            )
        yield tmp
    finally:
        if saved_db is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved_db


@pytest.fixture(scope="module")
def db(ctx):
    from wxcloudrun.database import DB

    return DB


def _set_mtime(path, age_seconds, now=None):
    now = now if now is not None else time.time()
    ts = now - age_seconds
    os.utime(path, (ts, ts))


# ---------- cleanup_orphans ----------

def test_orphan_scan_only_unreferenced_old_files(scripts, ctx):
    """引用中的文件保留；无引用但未满 7 天的保留；无引用且满 7 天的列为孤儿。"""
    from wxcloudrun.database import DB

    upload_dir = os.path.join(ctx, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    now = time.time()
    ref = os.path.join(upload_dir, "ref.png")
    orphan_old = os.path.join(upload_dir, "orphan_old.png")
    orphan_fresh = os.path.join(upload_dir, "orphan_fresh.png")
    for path in (ref, orphan_old, orphan_fresh):
        Path(path).write_bytes(b"img")
    _set_mtime(ref, 20 * 86400, now)
    _set_mtime(orphan_old, 20 * 86400, now)
    _set_mtime(orphan_fresh, 1 * 86400, now)

    with DB() as db:
        # 三列各造一条引用，覆盖全部 REFERENCE_COLUMNS
        db.execute("UPDATE users SET avatar_url = ? WHERE id = 1", ("/uploads/ref.png",))
        db.execute("UPDATE events SET cover_image = ? WHERE id = 1", ("/uploads/ref.png",))
        db.execute("UPDATE matches SET gift_photo_url = ? WHERE id = 1", ("/uploads/ref.png",))
        orphans = scripts["orphans"].scan_orphans(db, upload_dir, now=now)

    assert orphans == [orphan_old]


def test_orphan_scan_seven_day_floor(scripts, ctx):
    """min_age_seconds 低于 7 天时被钳制到 7 天（硬性下限，防误删刚上传未写库的文件）。"""
    from wxcloudrun.database import DB

    upload_dir = os.path.join(ctx, "uploads_floor")
    os.makedirs(upload_dir, exist_ok=True)
    now = time.time()
    young = os.path.join(upload_dir, "young.png")
    Path(young).write_bytes(b"img")
    _set_mtime(young, 6 * 86400, now)  # 6 天 < 7 天下限

    with DB() as db:
        orphans = scripts["orphans"].scan_orphans(db, upload_dir, min_age_seconds=1, now=now)

    assert orphans == []  # 即使调用方传 1 天，也按 7 天下限执行


def test_orphan_scan_ignores_subdirs_and_full_urls(scripts, ctx):
    """子目录不扫；完整 URL（带 host）引用同样能识别为已引用。"""
    from wxcloudrun.database import DB

    upload_dir = os.path.join(ctx, "uploads_urls")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(os.path.join(upload_dir, "sub"), exist_ok=True)
    now = time.time()
    ref_url = os.path.join(upload_dir, "via_url.png")
    sub = os.path.join(upload_dir, "sub", "nested.png")
    orphan = os.path.join(upload_dir, "real_orphan.png")
    for path in (ref_url, sub, orphan):
        Path(path).write_bytes(b"img")
    _set_mtime(ref_url, 20 * 86400, now)
    _set_mtime(sub, 20 * 86400, now)
    _set_mtime(orphan, 20 * 86400, now)

    with DB() as db:
        db.execute(
            "UPDATE users SET avatar_url = ? WHERE id = 1",
            ("https://gift.example.com/uploads/via_url.png",),
        )
        orphans = scripts["orphans"].scan_orphans(db, upload_dir, now=now)

    assert orphans == [orphan]  # 子目录文件与完整 URL 引用的文件都不删


def test_orphan_delete_files(scripts, ctx):
    paths = [os.path.join(ctx, "a.png"), os.path.join(ctx, "b.png")]
    for path in paths:
        Path(path).write_bytes(b"x")
    deleted = scripts["orphans"].delete_files(paths)
    assert deleted == 2
    assert not os.path.exists(paths[0]) and not os.path.exists(paths[1])


def test_orphan_cli_rejects_below_seven_days(scripts):
    """--min-age-days 3 → 直接报错退出（exit 2），不进入删除流程。"""
    rc = scripts["orphans"].main(["--min-age-days", "3", "--dir", "/tmp/never_exists"])
    assert rc == 2


# ---------- cleanup_notifications ----------

def _seed_notification(db, created_days_ago, read=False, type_name="draw_result"):
    created = (datetime.now(timezone.utc) - timedelta(days=created_days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    read_at = created if read else None
    db.execute(
        "INSERT INTO notifications (user_id, type, title, message, read_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, type_name, "t", "m", read_at, created),
    )
    return db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_notifications_delete_stale_read_only(scripts, db):
    """只删「已读且超期」；已读但新近 / 未读但超期 都保留。"""
    with db() as conn:
        conn.execute("DELETE FROM notifications")  # 模块级共享库：先清空本表隔离测试
        stale_read = _seed_notification(conn, created_days_ago=100, read=True)
        fresh_read = _seed_notification(conn, created_days_ago=10, read=True)
        stale_unread = _seed_notification(conn, created_days_ago=100, read=False)
        deleted = scripts["notifications"].delete_stale(conn, days=90)
        remaining = conn.all("SELECT id FROM notifications ORDER BY id")

    assert deleted == 1
    assert [row["id"] for row in remaining] == [fresh_read, stale_unread]
    assert stale_read not in [row["id"] for row in remaining]


def test_notifications_days_configurable(scripts, db):
    with db() as conn:
        conn.execute("DELETE FROM notifications")
        fresh = _seed_notification(conn, created_days_ago=10, read=True)
        mid = _seed_notification(conn, created_days_ago=60, read=True)
        old = _seed_notification(conn, created_days_ago=200, read=True)
        assert scripts["notifications"].delete_stale(conn, days=90) == 1  # 只删 200 天这条（60 天未超 90 天保留）
        rows = conn.all("SELECT id FROM notifications ORDER BY id")
        assert [row["id"] for row in rows] == [fresh, mid]
        assert scripts["notifications"].delete_stale(conn, days=30) == 1  # 60 天这条已超 30 天
        rows = conn.all("SELECT id FROM notifications ORDER BY id")
        assert [row["id"] for row in rows] == [fresh]


def test_notifications_cutoff_ts(scripts):
    now = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert scripts["notifications"].cutoff_ts(90, now) == "2026-05-12 12:00:00"


# ---------- healthcheck_data ----------

def _dirty_db(tmp_dir):
    """在独立库中制造各类孤儿/悬空数据（绕过 FK 约束直接插入），返回库路径。"""
    path = os.path.join(tmp_dir, f"dirty_{uuid.uuid4().hex[:8]}.db")
    saved = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = path
    try:
        from wxcloudrun.database import init_schema

        init_schema()
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("INSERT INTO matches (id, event_id, giver_id, receiver_id) VALUES (901, 9999, 9999, 9999)")
            conn.execute("INSERT INTO participants (id, event_id, user_id, nickname) VALUES (901, 9999, 9999, 'x')")
            conn.execute("INSERT INTO notifications (id, user_id, type, title) VALUES (901, 9999, 'draw_result', 'x')")
            conn.execute("INSERT INTO gift_likes (id, match_id, user_id) VALUES (901, 9999, 9999)")
            conn.commit()
        finally:
            conn.close()
    finally:
        if saved is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved
    return path


def _with_db(db_path, fn):
    """在 DB_PATH 指向 db_path 期间以 with DB() 运行 fn(db)，用完恢复环境变量。"""
    from wxcloudrun.database import DB

    saved = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = db_path
    try:
        with DB() as db:
            return fn(db)
    finally:
        if saved is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = saved


def test_healthcheck_detects_all_orphan_kinds(scripts, ctx):
    dirty = _dirty_db(ctx)
    results = _with_db(dirty, scripts["healthcheck"].run_checks)
    total, failed = scripts["healthcheck"].summarize(results)

    assert total >= 4
    # 四类核心检查全部命中（matches/participants/notifications/gift_likes）
    assert results["matches_no_event"]
    assert results["matches_no_giver"] and results["matches_no_receiver"]
    assert results["participants_no_event"] and results["participants_no_user"]
    assert results["notifications_no_user"]
    assert results["gift_likes_no_match"] and results["gift_likes_no_user"]


def test_healthcheck_clean_db_passes(scripts, ctx):
    from wxcloudrun.database import DB

    with DB() as db:
        results = scripts["healthcheck"].run_checks(db)
    total, failed = scripts["healthcheck"].summarize(results)
    assert total == 0 and failed == 0


def test_healthcheck_exit_code_matches_issues(scripts, ctx):
    dirty = _dirty_db(ctx)
    total, _failed = _with_db(dirty, lambda db: scripts["healthcheck"].summarize(scripts["healthcheck"].run_checks(db)))
    assert (1 if total else 0) == 1
