import os
import sqlite3
from pathlib import Path


def _mysql_config():
    address = os.getenv("MYSQL_ADDRESS") or os.getenv("MYSQL_HOST")
    if not address:
        return None
    host, _, port = address.partition(":")
    return {
        "host": host,
        "port": int(os.getenv("MYSQL_PORT") or port or 3306),
        "user": os.getenv("MYSQL_USERNAME") or os.getenv("MYSQL_USER") or "root",
        "password": os.getenv("MYSQL_PASSWORD") or "",
        "database": os.getenv("MYSQL_DATABASE") or os.getenv("MYSQL_DB") or "gift_exchange",
        "charset": "utf8mb4",
    }


def using_mysql():
    return _mysql_config() is not None


class DB:
    def __init__(self):
        self.engine = "mysql" if using_mysql() else "sqlite"
        if self.engine == "mysql":
            import pymysql

            ensure_mysql_database()
            self.conn = pymysql.connect(**_mysql_config(), cursorclass=pymysql.cursors.DictCursor)
        else:
            db_path = Path(os.getenv("DB_PATH", Path(__file__).resolve().parent.parent / "data" / "gift_exchange.db"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            # R6: WAL 模式 + 忙等待 5s，提升并发读写（读不阻塞写）；仅 SQLite，MySQL 不适用
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA busy_timeout = 5000")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def _sql(self, sql):
        if self.engine == "mysql":
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql, params=()):
        cursor = self.conn.cursor()
        cursor.execute(self._sql(sql), params)
        return cursor

    def get(self, sql, params=()):
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    def all(self, sql, params=()):
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def init_schema():
    if using_mysql():
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
              id INT AUTO_INCREMENT PRIMARY KEY,
              username VARCHAR(80) UNIQUE NOT NULL,
              email VARCHAR(254) UNIQUE NOT NULL,
              password TEXT NOT NULL,
              display_name VARCHAR(120),
              avatar_url TEXT,
              is_admin TINYINT DEFAULT 0,
              phone VARCHAR(50),
              address TEXT,
              receiver_name VARCHAR(120),
              gift_preference TEXT,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key_name VARCHAR(80) PRIMARY KEY,
              value TEXT,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
              id INT AUTO_INCREMENT PRIMARY KEY,
              user_id INT NOT NULL,
              token_hash VARCHAR(128) UNIQUE NOT NULL,
              expires_at DATETIME NOT NULL,
              used_at DATETIME NULL,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_reset_user (user_id),
              INDEX idx_reset_token (token_hash),
              CONSTRAINT fk_reset_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
              id INT AUTO_INCREMENT PRIMARY KEY,
              code VARCHAR(64) UNIQUE NOT NULL,
              name VARCHAR(160) NOT NULL,
              description TEXT,
              budget_min INT DEFAULT 0,
              creator_id INT NOT NULL,
              status VARCHAR(24) DEFAULT 'open',
              match_visibility VARCHAR(24) DEFAULT 'private',
              sign_up_deadline VARCHAR(64) DEFAULT '',
              participant_count INT DEFAULT 0,
              cover_image TEXT,
              is_public TINYINT DEFAULT 1,
              max_participants INT DEFAULT NULL,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              INDEX idx_events_creator (creator_id),
              INDEX idx_events_code (code),
              CONSTRAINT fk_events_creator FOREIGN KEY (creator_id) REFERENCES users(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS participants (
              id INT AUTO_INCREMENT PRIMARY KEY,
              event_id INT NOT NULL,
              user_id INT NOT NULL,
              nickname VARCHAR(120) NOT NULL,
              receiver_name VARCHAR(120),
              phone VARCHAR(50),
              address TEXT,
              preference_likes TEXT,
              preference_dislikes TEXT,
              preference_notes TEXT,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              UNIQUE KEY uniq_event_user (event_id, user_id),
              INDEX idx_participants_event (event_id),
              INDEX idx_participants_user (user_id),
              CONSTRAINT fk_participants_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
              CONSTRAINT fk_participants_user FOREIGN KEY (user_id) REFERENCES users(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS matches (
              id INT AUTO_INCREMENT PRIMARY KEY,
              event_id INT NOT NULL,
              giver_id INT NOT NULL,
              receiver_id INT NOT NULL,
              note TEXT,
              shipment_status VARCHAR(24) DEFAULT 'pending',
              carrier VARCHAR(80),
              tracking_number VARCHAR(120),
              shipped_at DATETIME NULL,
              tracking_updated_at DATETIME NULL,
              tracking_summary TEXT,
              received_at DATETIME NULL,
              gift_rating INT,
              gift_review TEXT,
              gift_photo_url MEDIUMTEXT,
              gift_privacy VARCHAR(24) DEFAULT 'photo',
              matched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_matches_event (event_id),
              CONSTRAINT fk_matches_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
              CONSTRAINT fk_matches_giver FOREIGN KEY (giver_id) REFERENCES participants(id) ON DELETE CASCADE,
              CONSTRAINT fk_matches_receiver FOREIGN KEY (receiver_id) REFERENCES participants(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications (
              id INT AUTO_INCREMENT PRIMARY KEY,
              user_id INT NOT NULL,
              event_id INT NULL,
              match_id INT NULL,
              type VARCHAR(40) NOT NULL,
              title VARCHAR(160) NOT NULL,
              message TEXT,
              read_at DATETIME NULL,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_notifications_user (user_id),
              CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS gift_likes (
              id INT AUTO_INCREMENT PRIMARY KEY,
              match_id INT NOT NULL,
              user_id INT NOT NULL,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              UNIQUE KEY uniq_like_match_user (match_id, user_id),
              INDEX idx_likes_match (match_id),
              INDEX idx_likes_user (user_id),
              CONSTRAINT fk_likes_match FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
              CONSTRAINT fk_likes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ]
    else:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT UNIQUE NOT NULL,
              email TEXT UNIQUE NOT NULL,
              password TEXT NOT NULL,
              display_name TEXT,
              avatar_url TEXT,
              is_admin INTEGER DEFAULT 0,
              phone TEXT,
              address TEXT,
              receiver_name TEXT,
              gift_preference TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key_name TEXT PRIMARY KEY,
              value TEXT,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              token_hash TEXT UNIQUE NOT NULL,
              expires_at TEXT NOT NULL,
              used_at TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              code TEXT UNIQUE NOT NULL,
              name TEXT NOT NULL,
              description TEXT DEFAULT '',
              budget_min INTEGER DEFAULT 0,
              creator_id INTEGER NOT NULL REFERENCES users(id),
              status TEXT DEFAULT 'open',
              match_visibility TEXT DEFAULT 'private',
              sign_up_deadline TEXT DEFAULT '',
              participant_count INTEGER DEFAULT 0,
              cover_image TEXT DEFAULT '',
              is_public INTEGER DEFAULT 1,
              max_participants INTEGER DEFAULT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS participants (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL REFERENCES users(id),
              nickname TEXT NOT NULL,
              receiver_name TEXT,
              phone TEXT,
              address TEXT,
              preference_likes TEXT,
              preference_dislikes TEXT,
              preference_notes TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(event_id, user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS matches (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
              giver_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
              receiver_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
              note TEXT DEFAULT '',
              shipment_status TEXT DEFAULT 'pending',
              carrier TEXT,
              tracking_number TEXT,
              shipped_at TEXT,
              tracking_updated_at TEXT,
              tracking_summary TEXT,
              received_at TEXT,
              gift_rating INTEGER,
              gift_review TEXT,
              gift_photo_url TEXT,
              gift_privacy TEXT DEFAULT 'photo',
              matched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              event_id INTEGER,
              match_id INTEGER,
              type TEXT NOT NULL,
              title TEXT NOT NULL,
              message TEXT,
              read_at TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gift_likes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(match_id, user_id)
            )
            """,
        ]

    with DB() as db:
        for statement in statements:
            db.execute(statement)
        run_migrations(db)


def _column_exists(db, table, column):
    """幂等迁移辅助：检查列是否已存在（MySQL 走 information_schema，SQLite 走 pragma_table_info）。"""
    if db.engine == "mysql":
        row = db.get(
            "SELECT COUNT(*) AS count FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?",
            (table, column),
        )
    else:
        row = db.get("SELECT COUNT(*) AS count FROM pragma_table_info(?) WHERE name = ?", (table, column))
    return int(row["count"] or 0) > 0


def run_migrations(db):
    user_columns = [
        ("is_admin", "TINYINT DEFAULT 0" if db.engine == "mysql" else "INTEGER DEFAULT 0"),
        ("phone", "VARCHAR(50)" if db.engine == "mysql" else "TEXT"),
        ("address", "TEXT"),
        ("receiver_name", "VARCHAR(120)" if db.engine == "mysql" else "TEXT"),
        ("gift_preference", "TEXT"),
        # 微信小程序架构预留：仅加列，不做登录逻辑（阶段二G）
        ("openid", "VARCHAR(64)" if db.engine == "mysql" else "TEXT"),
        ("unionid", "VARCHAR(64)" if db.engine == "mysql" else "TEXT"),
        ("session_key", "VARCHAR(64)" if db.engine == "mysql" else "TEXT"),
    ]
    match_columns = [
        ("shipment_status", "VARCHAR(24) DEFAULT 'pending'" if db.engine == "mysql" else "TEXT DEFAULT 'pending'"),
        ("carrier", "VARCHAR(80)" if db.engine == "mysql" else "TEXT"),
        ("tracking_number", "VARCHAR(120)" if db.engine == "mysql" else "TEXT"),
        ("shipped_at", "DATETIME NULL" if db.engine == "mysql" else "TEXT"),
        ("tracking_updated_at", "DATETIME NULL" if db.engine == "mysql" else "TEXT"),
        ("tracking_summary", "TEXT"),
        ("received_at", "DATETIME NULL" if db.engine == "mysql" else "TEXT"),
        ("gift_rating", "INT" if db.engine == "mysql" else "INTEGER"),
        ("gift_review", "TEXT"),
        ("gift_photo_url", "MEDIUMTEXT" if db.engine == "mysql" else "TEXT"),
    ]
    event_columns = [
        ("match_visibility", "VARCHAR(24) DEFAULT 'private'" if db.engine == "mysql" else "TEXT DEFAULT 'private'"),
        ("cover_image", "TEXT" if db.engine == "mysql" else "TEXT DEFAULT ''"),
        ("is_public", "BOOLEAN DEFAULT TRUE" if db.engine == "mysql" else "INTEGER DEFAULT 1"),
        ("max_participants", "INT DEFAULT NULL" if db.engine == "mysql" else "INTEGER DEFAULT NULL"),
        ("short_code", "VARCHAR(16)" if db.engine == "mysql" else "TEXT"),
        ("excluded_pairs", "TEXT"),
    ]
    participant_columns = [
        ("receiver_name", "VARCHAR(120)" if db.engine == "mysql" else "TEXT"),
        ("phone", "VARCHAR(50)" if db.engine == "mysql" else "TEXT"),
        ("address", "TEXT"),
        ("preference_likes", "TEXT"),
        ("preference_dislikes", "TEXT"),
        ("preference_notes", "TEXT"),
        ("preference_size", "VARCHAR(50)" if db.engine == "mysql" else "TEXT"),
        ("preference_color", "VARCHAR(80)" if db.engine == "mysql" else "TEXT"),
        ("wish_links", "TEXT"),
    ]
    for name, column_type in event_columns:
        try:
            db.execute(f"ALTER TABLE events ADD COLUMN {name} {column_type}")
        except Exception:
            pass
    for name, column_type in participant_columns:
        try:
            db.execute(f"ALTER TABLE participants ADD COLUMN {name} {column_type}")
        except Exception:
            pass
    for name, column_type in user_columns:
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {name} {column_type}")
        except Exception:
            pass
    for name, column_type in match_columns:
        try:
            db.execute(f"ALTER TABLE matches ADD COLUMN {name} {column_type}")
        except Exception:
            pass
    # 晒图隐私（Luna 独到项：晒图不阻塞）：photo=公开照片 / text=仅文字 / blur=模糊照片。
    # 显式幂等检查（不依赖 try/except），新旧库均收敛到 DEFAULT 'photo'。
    if not _column_exists(db, "matches", "gift_privacy"):
        db.execute(
            "ALTER TABLE matches ADD COLUMN gift_privacy "
            + ("VARCHAR(24) DEFAULT 'photo'" if db.engine == "mysql" else "TEXT DEFAULT 'photo'")
        )
    try:
        total = db.get("SELECT COUNT(*) AS count FROM users")["count"]
        admins = db.get("SELECT COUNT(*) AS count FROM users WHERE is_admin = 1")["count"]
        if int(total) > 0 and int(admins) == 0:
            first = db.get("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            if first:
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (first["id"],))
    except Exception:
        pass

    # 存量活动补齐短码（v2 新增 short_code 列后，旧数据无短码）
    try:
        import random
        import string

        missing = db.all("SELECT id FROM events WHERE short_code IS NULL OR short_code = ''")
        if missing:
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混淆 0/O/1/I
            used = {row["short_code"] for row in db.all("SELECT short_code FROM events WHERE short_code IS NOT NULL")}
            for row in missing:
                for _ in range(20):
                    candidate = "".join(random.SystemRandom().choice(alphabet) for _ in range(6))
                    if candidate not in used:
                        used.add(candidate)
                        db.execute("UPDATE events SET short_code = ? WHERE id = ?", (candidate, row["id"]))
                        break
    except Exception:
        pass


def ensure_mysql_database():
    config = _mysql_config()
    database = config.pop("database")

    import pymysql

    conn = pymysql.connect(**config, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()
