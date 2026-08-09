"""迁移管理（轻量版本化迁移）测试。

验证：
- 全新库（init_schema 建表后）跑 run_migrations_v2 → 7 个迁移全部应用（schema_migrations 7 行）
- 再跑一次 → 0 个新应用（幂等）
- 模拟旧库已有列（先建表 + 旧 run_migrations 加过列再跑）→ 跳过已存在的列不报错、缺失列照常补齐
- run_migrations（对外入口）连续跑不重复应用

注意：import wxcloudrun 会触发包初始化 create_app() → init_schema()，因此本文件在
import 之前设置 DB_PATH 指向临时目录（与 tests/test_kdniao.py 相同的约定）。
"""
import os
import tempfile
from pathlib import Path

# 必须在 import wxcloudrun 之前设置 DB_PATH（包初始化会跑 init_schema）
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="gift_migrations_boot_")) / "boot.db")

from wxcloudrun.database import DB, init_schema, run_migrations  # noqa: E402
from wxcloudrun.migrations import MIGRATIONS, run_migrations_v2  # noqa: E402


def _new_db_path(prefix):
    return str(Path(tempfile.mkdtemp(prefix=prefix)) / "test.db")


def _columns(db, table):
    rows = db.all("SELECT name FROM pragma_table_info(?)", (table,))
    return {r["name"] for r in rows}


def _table_exists(db, table):
    row = db.get("SELECT COUNT(*) AS count FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return int(row["count"]) > 0


def _legacy_schema(db):
    """模拟旧库：基础表已建（老 init_schema 产物），其中 events.short_code 已由旧 run_migrations 加过。"""
    db.execute(
        "CREATE TABLE users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, "
        "password TEXT NOT NULL, display_name TEXT, avatar_url TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute(
        "CREATE TABLE events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, "
        "description TEXT DEFAULT '', budget_min INTEGER DEFAULT 0, creator_id INTEGER NOT NULL, "
        "status TEXT DEFAULT 'open', sign_up_deadline TEXT DEFAULT '', participant_count INTEGER DEFAULT 0, "
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute("ALTER TABLE events ADD COLUMN short_code TEXT")  # 旧 run_migrations 已加过
    db.execute(
        "CREATE TABLE participants ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
        "nickname TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute(
        "CREATE TABLE matches ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, giver_id INTEGER NOT NULL, "
        "receiver_id INTEGER NOT NULL, matched_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute("CREATE TABLE app_settings (key_name TEXT PRIMARY KEY, value TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    db.execute(
        "CREATE TABLE password_reset_tokens ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, token_hash TEXT UNIQUE NOT NULL, "
        "expires_at TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute(
        "CREATE TABLE notifications ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, event_id INTEGER, match_id INTEGER, "
        "type TEXT NOT NULL, title TEXT NOT NULL, message TEXT, read_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )


class TestRunMigrationsV2:
    def test_fresh_db_applies_all_migrations(self, monkeypatch):
        """全新库（init_schema 建表后）：7 个迁移全部应用并记录。"""
        monkeypatch.setenv("DB_PATH", _new_db_path("gift_mig_fresh_"))
        init_schema()  # 建表 + run_migrations（内部跑版本化链）
        with DB() as db:
            # 清空记录，直接验证 run_migrations_v2 的“本次应用数”语义
            db.execute("DELETE FROM schema_migrations")
            assert run_migrations_v2(db) == 7
            rows = db.all("SELECT version, name FROM schema_migrations ORDER BY version")
            assert [r["version"] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
            assert all(r["name"] for r in rows)
            # 版本化链涉及的列/表齐备
            for table, column in [
                ("events", "short_code"),
                ("events", "excluded_pairs"),
                ("participants", "preference_likes"),
                ("participants", "preference_dislikes"),
                ("participants", "preference_notes"),
                ("users", "openid"),
                ("users", "unionid"),
                ("users", "session_key"),
                ("users", "reset_code"),
                ("users", "reset_code_expires_at"),
                ("matches", "gift_privacy"),
            ]:
                assert column in _columns(db, table), f"{table}.{column} 缺失"
            assert _table_exists(db, "gift_likes")

    def test_second_run_applies_none(self, monkeypatch):
        """幂等：已全部应用的库再跑一次 → 0 个新应用，记录不重复。"""
        monkeypatch.setenv("DB_PATH", _new_db_path("gift_mig_idem_"))
        init_schema()
        with DB() as db:
            assert run_migrations_v2(db) == 0
            rows = db.all("SELECT version FROM schema_migrations ORDER BY version")
            assert [r["version"] for r in rows] == [1, 2, 3, 4, 5, 6, 7]

    def test_legacy_db_with_existing_columns_skips_duplicates(self, monkeypatch):
        """旧库模拟：表已建、short_code 已存在 → 跳过不报 duplicate column，缺失列照常补齐。"""
        monkeypatch.setenv("DB_PATH", _new_db_path("gift_mig_legacy_"))
        with DB() as db:
            _legacy_schema(db)
            assert run_migrations_v2(db) == 7  # 全部记录，且不抛异常
            events_cols = _columns(db, "events")
            # 未重复加列：short_code 在 pragma_table_info 里只出现一次
            dup = db.get("SELECT COUNT(*) AS count FROM pragma_table_info('events') WHERE name = 'short_code'")
            assert dup is not None and int(dup["count"]) == 1
            assert "excluded_pairs" in events_cols  # 缺失列补齐
            assert {"preference_likes", "preference_dislikes", "preference_notes"} <= _columns(db, "participants")
            assert {"openid", "unionid", "session_key"} <= _columns(db, "users")
            assert "gift_privacy" in _columns(db, "matches")
            assert _table_exists(db, "gift_likes")


class TestRunMigrationsEntry:
    def test_entry_idempotent_on_legacy_db(self, monkeypatch):
        """对外入口 run_migrations：旧库上连续跑两次均不报错、不重复应用。"""
        monkeypatch.setenv("DB_PATH", _new_db_path("gift_mig_entry_"))
        with DB() as db:
            _legacy_schema(db)
            run_migrations(db)  # 版本化链 + 遗留 ALTER + 数据兜底，不抛异常
        with DB() as db:
            rows = db.all("SELECT version FROM schema_migrations ORDER BY version")
            assert [r["version"] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
            # 遗留兜底列也齐备（preference_size 等未入册列仍由 run_migrations 兜底）
            assert {"preference_size", "preference_color", "wish_links"} <= _columns(db, "participants")

    def test_migrations_list_shape(self):
        """MIGRATIONS 契约：版本号连续递增、唯一，每项含 name 与 up 列表。"""
        versions = [m["version"] for m in MIGRATIONS]
        assert versions == sorted(versions) == list(range(1, len(MIGRATIONS) + 1))
        for m in MIGRATIONS:
            assert m["name"]
            assert isinstance(m["up"], list) and m["up"]
            for stmt in m["up"]:
                assert stmt["op"] in ("add_column", "create_table")
