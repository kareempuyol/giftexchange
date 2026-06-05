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
              matched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_matches_event (event_id),
              CONSTRAINT fk_matches_event FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
              CONSTRAINT fk_matches_giver FOREIGN KEY (giver_id) REFERENCES participants(id) ON DELETE CASCADE,
              CONSTRAINT fk_matches_receiver FOREIGN KEY (receiver_id) REFERENCES participants(id) ON DELETE CASCADE
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
              matched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]

    with DB() as db:
        for statement in statements:
            db.execute(statement)
        run_migrations(db)


def run_migrations(db):
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
    ]
    for name, column_type in event_columns:
        try:
            db.execute(f"ALTER TABLE events ADD COLUMN {name} {column_type}")
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
    try:
        total = db.get("SELECT COUNT(*) AS count FROM users")["count"]
        admins = db.get("SELECT COUNT(*) AS count FROM users WHERE is_admin = 1")["count"]
        if int(total) > 0 and int(admins) == 0:
            first = db.get("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            if first:
                db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (first["id"],))
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
