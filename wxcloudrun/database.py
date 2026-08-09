import os
import sqlite3
from pathlib import Path

from wxcloudrun.migrations import _column_exists, run_migrations_v2


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


def integrity_errors():
    """双引擎唯一约束冲突异常类型元组（并发去重/幂等兜底 catch 用）。

    业务层不要直接 catch sqlite3/pymysql 具体类型：SQLite 是 sqlite3.IntegrityError，
    MySQL 是 pymysql.err.IntegrityError，统一走本函数取当前引擎对应的类型。
    """
    types = [sqlite3.IntegrityError]
    if using_mysql():
        import pymysql

        types.append(pymysql.err.IntegrityError)
    return tuple(types)


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


def run_migrations(db):
    """迁移入口（对外接口不变，init_schema 调用处不动）。

    1. 未入册的历史列先补齐（_column_exists 守卫幂等，老库兜底，双引擎类型分离）。
       —— 必须先于版本化链：v11 的复合索引（如 idx_events_status_public_archived
       引用 events.is_public）依赖这些历史列存在；若老库缺列，索引创建会先失败。
    2. 版本化链（v1-v11）交给 migrations.run_migrations_v2：每个 ALTER 带 _column_exists
       幂等守卫 + schema_migrations 记录，旧库重跑不报 duplicate column。
    3. 数据兜底：首个用户提权为管理员 + 存量活动补齐短码。
    """
    user_columns = [
        ("is_admin", "TINYINT DEFAULT 0" if db.engine == "mysql" else "INTEGER DEFAULT 0"),
        ("phone", "VARCHAR(50)" if db.engine == "mysql" else "TEXT"),
        ("address", "TEXT"),
        ("receiver_name", "VARCHAR(120)" if db.engine == "mysql" else "TEXT"),
        ("gift_preference", "TEXT"),
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
    ]
    participant_columns = [
        ("receiver_name", "VARCHAR(120)" if db.engine == "mysql" else "TEXT"),
        ("phone", "VARCHAR(50)" if db.engine == "mysql" else "TEXT"),
        ("address", "TEXT"),
        ("preference_size", "VARCHAR(50)" if db.engine == "mysql" else "TEXT"),
        ("preference_color", "VARCHAR(80)" if db.engine == "mysql" else "TEXT"),
        ("wish_links", "TEXT"),
    ]
    # 未入册的历史列：_column_exists 守卫幂等（不再 try/except 吞异常——
    # 真实 SQL 错误会暴露而不是被静默跳过）
    for table, columns in (
        ("events", event_columns),
        ("participants", participant_columns),
        ("users", user_columns),
        ("matches", match_columns),
    ):
        for name, column_type in columns:
            if not _column_exists(db, table, name):
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

    # 版本化链（v1-v11）在历史列补齐之后应用：v11 复合索引引用 is_public 等历史列
    run_migrations_v2(db)

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
